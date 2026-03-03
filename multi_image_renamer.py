import os
import shutil
import re
from datetime import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

RAW_FOLDER = os.getenv("RAW_FOLDER")
ORG_FOLDER = os.getenv("ORG_FOLDER")
LOG_FILE = os.getenv("LOG_FILE")
UNMATCHED_FOLDER = os.getenv("UNMATCHED_FOLDER")
CREDENTIALS_FILE = os.getenv("GOOGLE_SHEETS_KEY_PATH")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
WORKSHEET_NAME = os.getenv("WORKSHEET_NAME", "Inventory-Adds")
TOY_COLUMN = os.getenv("TOY_COLUMN", "B")
VARIANT_COLUMN = os.getenv("VARIANT_COLUMN", "G")
BOX_COLUMN = os.getenv("BOX_COLUMN", "A")  # Default to column A

# Toggle to prevent deletion of source images during testing
TESTING_MODE = True

# Ensure log file has headers
def ensure_log_headers():
    if not os.path.exists(LOG_FILE) or os.path.getsize(LOG_FILE) == 0:
        with open(LOG_FILE, "w") as log_file:
            log_file.write("Timestamp,File Path,Original Name,Identifier,Status,Box #\n")

# Log processed images with Box #
def log_processed_image(file_path, original_name, identifier, status, box_number=""):
    ensure_log_headers()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as log_file:
        log_file.write(f"{timestamp},{file_path},{original_name},{identifier},{status},{box_number}\n")

# Get all processed identifier+box combinations from log
def get_processed_combinations():
    processed = set()
    try:
        with open(LOG_FILE, "r") as log_file:
            for line in log_file:
                parts = line.strip().split(',')
                if len(parts) >= 6:
                    identifier = parts[3].strip().upper()
                    box = parts[5].strip()
                    status = parts[4].strip()
                    if status == "Processed":
                        processed.add((identifier, box))
    except FileNotFoundError:
        pass
    return processed

# Convert column letter to index
def column_letter_to_index(letter):
    return ord(letter.upper()) - ord('A')

# Get all matching Box #s from sheet
def get_matching_boxes_from_sheet(toy_number, variant):
    box_numbers = set()
    try:
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE)
        service = build("sheets", "v4", credentials=creds)
        sheet = service.spreadsheets()
        result = sheet.values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{WORKSHEET_NAME}!A:Z"
        ).execute()
        rows = result.get("values", [])
        toy_index = column_letter_to_index(TOY_COLUMN)
        box_index = column_letter_to_index(BOX_COLUMN)

        combined = f"{toy_number}_{variant}".strip("_").replace(" ", "").upper()

        for row in rows:
            toy = row[toy_index].strip().replace(" ", "").upper() if len(row) > toy_index else ""
            if toy == combined:
                if len(row) > box_index:
                    box = row[box_index].strip()
                    if box:
                        box_numbers.add(box)

    except Exception as e:
        print(f"⚠️ Error fetching Box # from sheet: {e}")
    return list(box_numbers)

# Extract Toy # and Variant
def extract_toy_and_variant(folder_name):
    match = re.match(r"^([A-Z0-9]{5,7})([-_])?(.*)$", folder_name, re.IGNORECASE)
    if match:
        toy_number = match.group(1).upper()
        variant = match.group(3).strip() if match.group(3) else ""
        identifier = f"{toy_number}_{variant}" if variant else toy_number
        print(f"✅ Extracted Identifier: {identifier}")
        return identifier, toy_number, variant
    print(f"⚠️ No valid identifier found in folder name: {folder_name}")
    return None, None, None

# Process a folder of images
def process_folder(folder_path, processed_combos):
    folder_name = os.path.basename(folder_path)
    identifier, toy_number, variant = extract_toy_and_variant(folder_name)
    box_numbers = get_matching_boxes_from_sheet(toy_number, variant) if toy_number else []

    if not identifier:
        print(f"⚠️ No identifier in folder {folder_name}. Moving files to unmatched.")
        for file_name in os.listdir(folder_path):
            if file_name.startswith('.') or file_name.lower() in ["icon", "icon\r"]:
                continue
            src_path = os.path.join(folder_path, file_name)
            unmatched_dest = os.path.join(UNMATCHED_FOLDER, file_name)
            try:
                if TESTING_MODE:
                    shutil.copy(src_path, unmatched_dest)
                else:
                    shutil.move(src_path, unmatched_dest)
                log_processed_image(src_path, file_name, "Unknown", "Unmatched")
            except Exception as e:
                print(f"⚠️ Error moving to unmatched: {e}")
        if not os.listdir(folder_path):
            os.rmdir(folder_path)
        return

    for box_number in box_numbers:
        print(f"🔍 Checking for duplicates: Identifier={identifier}, Box={box_number}")
        if (identifier.strip().upper(), box_number.strip()) in processed_combos:
            print(f"⚠️ Duplicate found — already processed: {identifier} in Box {box_number}")
            return
        else:
            print(f"✅ Not a duplicate — continuing: {identifier} in Box {box_number}")

        target_folder = os.path.join(ORG_FOLDER, identifier)
        os.makedirs(target_folder, exist_ok=True)
        file_index = 1

        for file_name in sorted(os.listdir(folder_path)):
            if file_name.startswith('.') or file_name.lower() in ["icon", "icon\r"]:
                continue

            src_path = os.path.join(folder_path, file_name)

            if not file_name.lower().endswith(('.jpg', '.jpeg', '.png', '.heic')):
                unmatched_dest = os.path.join(UNMATCHED_FOLDER, file_name)
                try:
                    if TESTING_MODE:
                        shutil.copy(src_path, unmatched_dest)
                    else:
                        shutil.move(src_path, unmatched_dest)
                    log_processed_image(src_path, file_name, "Unknown", "Unmatched", box_number)
                except Exception as e:
                    print(f"⚠️ Error moving to unmatched: {e}")
                continue

            new_name = f"{identifier}_{file_index}.jpg"
            dest_path = os.path.join(target_folder, new_name)

            if os.path.exists(dest_path):
                print(f"⚠️ Duplicate filename detected (skipping): {dest_path}")
                continue

            try:
                if TESTING_MODE:
                    shutil.copy(src_path, dest_path)
                else:
                    shutil.move(src_path, dest_path)
                log_processed_image(dest_path, file_name, identifier, "Processed", box_number)
                print(f"✅ Processed: {new_name}")
                file_index += 1
            except Exception as e:
                print(f"⚠️ Error moving {src_path}: {e}")
                log_processed_image(src_path, file_name, "Unknown", "Error", box_number)

    try:
        if not os.listdir(folder_path):
            os.rmdir(folder_path)
            print(f"🗑️ Deleted empty folder: {folder_path}")
    except Exception as e:
        print(f"⚠️ Error deleting folder {folder_path}: {e}")

def main():
    print("Starting multi_image_renamer.py...")
    os.makedirs(UNMATCHED_FOLDER, exist_ok=True)
    os.makedirs(ORG_FOLDER, exist_ok=True)

    processed_combos = get_processed_combinations()

    for folder_name in os.listdir(RAW_FOLDER):
        folder_path = os.path.join(RAW_FOLDER, folder_name)
        if os.path.isdir(folder_path):
            process_folder(folder_path, processed_combos)

if __name__ == "__main__":
    main()