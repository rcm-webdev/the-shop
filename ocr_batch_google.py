import os
import re
import shutil
import cv2
from google.cloud import vision
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Toggle to prevent deletion of source images during testing
TESTING_MODE = True

# Configuration paths from .env
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv("GOOGLE_VISION_KEY_PATH")
RAW_FOLDER = os.getenv("RAW_FOLDER")
ORG_FOLDER = os.getenv("ORG_FOLDER")
UNMATCHED_FOLDER = os.getenv("UNMATCHED_FOLDER")
LOG_FILE = os.getenv("LOG_FILE")

# Google Sheets configuration
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
CREDENTIALS_FILE = os.getenv("GOOGLE_SHEETS_KEY_PATH")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
WORKSHEET_NAME = os.getenv("WORKSHEET_NAME", "Inventory-Adds")
TOY_COLUMN = os.getenv("TOY_COLUMN", "B")
VARIANT_COLUMN = os.getenv("VARIANT_COLUMN", "G")
BOX_COLUMN = os.getenv("BOX_COLUMN", "A")

# Google Vision Client
client = vision.ImageAnnotatorClient()

# --- Image Conversion ---
def convert_heic_to_jpg(image_path):
    if not image_path.lower().endswith('.heic'):
        return image_path

    jpg_path = image_path.rsplit('.', 1)[0] + '.jpg'
    try:
        os.system(f'sips -s format jpeg "{image_path}" --out "{jpg_path}" >/dev/null 2>&1')
        if os.path.exists(jpg_path):
            img = cv2.imread(jpg_path)
            if img is not None and img.size > 0:
                print(f"🌀 Converted HEIC to JPG: {jpg_path}")
                if not TESTING_MODE:
                    try:
                        os.remove(image_path)
                        print(f"🧹 Deleted original HEIC: {image_path}")
                    except Exception as e:
                        print(f"⚠️ Failed to delete HEIC: {e}")
                return jpg_path
            else:
                print(f"❌ Conversion created unreadable JPG: {jpg_path}")
        else:
            print(f"❌ Failed to create JPG: {jpg_path}")
    except Exception as e:
        print(f"⚠️ Error during HEIC to JPG conversion: {e}")
    return None

# --- Preprocessing for OCR ---
def preprocess_image_for_ocr(image_path):
    try:
        image = cv2.imread(image_path)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        filtered = cv2.bilateralFilter(gray, 11, 17, 17)
        enhanced = cv2.adaptiveThreshold(filtered, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 11, 2)
        temp_path = image_path.replace(".jpg", "_pre.jpg")
        cv2.imwrite(temp_path, enhanced)
        return temp_path
    except Exception as e:
        print(f"⚠️ Failed to preprocess image: {e}")
        return image_path

# --- Logging ---
def ensure_log_headers():
    if not os.path.exists(LOG_FILE) or os.path.getsize(LOG_FILE) == 0:
        with open(LOG_FILE, "w") as log_file:
            log_file.write("Timestamp,File Path,Original Name,Identifier,Status,Box #\n")

def log_processed_image(file_path, original_name, identifier, status, box_number=""):
    ensure_log_headers()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as log_file:
        log_file.write(f"{timestamp},{file_path},{original_name},{identifier},{status},{box_number}\n")

def is_duplicate(identifier, box_number):
    try:
        with open(LOG_FILE, "r") as log_file:
            for line in log_file:
                parts = line.strip().split(',')
                if len(parts) >= 6 and parts[3] == identifier and parts[5] == box_number and parts[4].startswith("Processed"):
                    return True
    except FileNotFoundError:
        open(LOG_FILE, "a").close()
    return False

# --- OCR Extraction Logic ---
def extract_toy_number(text):
    cleaned_text = re.sub(r"Asst\.?\s*[:#]?\s*[A-Z0-9]{4,7}[^\n,]*", "", text, flags=re.IGNORECASE)
    match_with_dash = re.search(r"\b([A-Z]{1,2}[0-9]{4,5})-([A-Z0-9]{3,6})\b", cleaned_text, re.IGNORECASE)
    if match_with_dash:
        toy_num = match_with_dash.group(1).upper()
        print(f"✅ Matched Toy #: {toy_num}")
        return toy_num
    print("⚠️ No Toy # found in OCR text.")
    return None

# --- Google OCR Integration ---
def ocr_google(image_path):
    preprocessed_path = preprocess_image_for_ocr(image_path)
    try:
        with open(preprocessed_path, "rb") as img_file:
            content = img_file.read()
        image = vision.Image(content=content)
        response = client.text_detection(image=image)
        if response.text_annotations:
            extracted_text = response.full_text_annotation.text.strip()
            toy_number = extract_toy_number(extracted_text)
            if toy_number:
                print(f"✅ OCR Match: Toy # {toy_number}")
                return toy_number
            else:
                print("⚠️ OCR found text, but no Toy # matched.")
        else:
            print("❌ No text detected by OCR.")
    except Exception as e:
        print(f"❌ OCR Error: {e}")
    finally:
        if os.path.exists(preprocessed_path):
            try:
                os.remove(preprocessed_path)
            except Exception as e:
                print(f"⚠️ Failed to delete temp file: {e}")
    return None

# --- Google Sheets ---
def authenticate_google_sheets():
    try:
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
        print("✅ Google Sheets authenticated.")
        return build('sheets', 'v4', credentials=creds)
    except Exception as e:
        print(f"⚠️ Google Sheets auth error: {e}")
        return None

def get_box_number_from_sheet(sheets_service, toy_number):
    try:
        sheet = sheets_service.spreadsheets()
        range_str = f"'{WORKSHEET_NAME}'!{BOX_COLUMN}:{VARIANT_COLUMN}"
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=range_str).execute()
        values = result.get('values', [])
        for row in values:
            if row and len(row) >= 2 and row[1] == toy_number:
                return row[0] if len(row) > 0 else ""
    except Exception as e:
        print(f"⚠️ Box # lookup error: {e}")
    return ""

def get_variant_from_sheet(sheets_service, toy_number):
    try:
        sheet = sheets_service.spreadsheets()
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=f"'{WORKSHEET_NAME}'!{TOY_COLUMN}:{VARIANT_COLUMN}").execute()
        values = result.get('values', [])
        for row in values:
            if row and len(row) >= 10 and row[0] == toy_number:
                return row[9].strip() if row[9] else ""
    except Exception as e:
        print(f"⚠️ Sheets access error: {e}")
    return ""

# --- Main Logic ---
def process_batch(images, sheets_service):
    print(f"📸 Processing batch: {images}")
    if len(images) != 2:
        print(f"⚠️ Incomplete batch detected: {images}")
        return
    front_image, back_image = images
    front_image = convert_heic_to_jpg(front_image)
    back_image = convert_heic_to_jpg(back_image)
    front_original_name = os.path.basename(front_image)
    back_original_name = os.path.basename(back_image)
    print("🔍 Using Google Vision OCR...")
    toy_number = ocr_google(back_image)
    if toy_number:
        box_number = get_box_number_from_sheet(sheets_service, toy_number)
        if is_duplicate(toy_number, box_number):
            print(f"⚠️ Duplicate: {toy_number} in Box {box_number}")
            return
        variant = get_variant_from_sheet(sheets_service, toy_number)
        identifier = toy_number
        target_folder = os.path.join(ORG_FOLDER, identifier)
        os.makedirs(target_folder, exist_ok=True)
        for i, img_path in enumerate([front_image, back_image]):
            original_name = os.path.basename(img_path)
            new_name = f"{identifier}_{i + 1}.jpg"
            dest_path = os.path.join(target_folder, new_name)
            print(f"✅ Moving {img_path} to {dest_path}")
            try:
                if TESTING_MODE:
                    shutil.copy(img_path, dest_path)
                else:
                    shutil.move(img_path, dest_path)
                    if img_path.lower().endswith('.jpg') and os.path.exists(img_path):
                        try:
                            os.remove(img_path)
                            print(f"🧹 Deleted processed JPG from Drive: {img_path}")
                        except Exception as e:
                            print(f"⚠️ Failed to delete JPG from Drive: {e}")
                log_processed_image(dest_path, original_name, identifier, "Processed", box_number)
            except Exception as e:
                print(f"⚠️ Error moving {img_path}: {e}")
                log_processed_image(img_path, original_name, "Unknown", "Error", box_number)
    else:
        print("❌ Google OCR failed.")
        for img in [front_image, back_image]:
            original_name = os.path.basename(img)
            unmatched_dest = os.path.join(UNMATCHED_FOLDER, original_name)
            try:
                if TESTING_MODE:
                    shutil.copy(img, unmatched_dest)
                else:
                    shutil.move(img, unmatched_dest)
                log_processed_image(unmatched_dest, original_name, "Unknown", "Unmatched", "")
                print(f"📁 Moved unmatched: {original_name} → {unmatched_dest}")
            except Exception as e:
                print(f"⚠️ Error moving unmatched: {e}")

def process_images(sheets_service):
    files = sorted([
        os.path.join(RAW_FOLDER, f) for f in os.listdir(RAW_FOLDER)
        if f.lower().endswith('.heic') and not f.startswith('.') and f.lower() != "icon"
    ])
    for i in range(0, len(files), 2):
        batch = files[i:i + 2]
        if len(batch) == 2:
            process_batch(batch, sheets_service)

def main():
    print("🔍 Starting OCR Batch Processor (Google Vision only)...")
    os.makedirs(UNMATCHED_FOLDER, exist_ok=True)
    os.makedirs(ORG_FOLDER, exist_ok=True)
    sheets_service = authenticate_google_sheets()
    if sheets_service:
        process_images(sheets_service)

if __name__ == "__main__":
    main()