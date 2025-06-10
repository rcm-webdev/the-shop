import os
import shutil
import re
from datetime import datetime

RAW_FOLDER = "/Users/ikeyike/Library/CloudStorage/GoogleDrive-thetrueepg@gmail.com/My Drive/TheShopRawUploads"
ORG_FOLDER = "/Users/ikeyike/Desktop/the_shop_inventory/organized_images"
LOG_FILE = "/Users/ikeyike/Desktop/the_shop_inventory/processed_images.csv"
UNMATCHED_FOLDER = "/Users/ikeyike/Desktop/the_shop_inventory/unmatched"

# Toggle to prevent deletion of source images during testing
TESTING_MODE = True

# Ensure log file has headers
def ensure_log_headers():
    if not os.path.exists(LOG_FILE) or os.path.getsize(LOG_FILE) == 0:
        with open(LOG_FILE, "w") as log_file:
            log_file.write("Timestamp,File Path,Original Name,Identifier,Status\n")

# Log processed images with timestamp, original image name, and identifier
def log_processed_image(file_path, original_name, identifier, status):
    ensure_log_headers()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as log_file:
        log_file.write(f"{timestamp},{file_path},{original_name},{identifier},{status}\n")

# Extract Toy # and Variant from the folder name
def extract_toy_and_variant(folder_name):
    # Adjusted regex to handle 5, 6, or 7 characters for toy number
    match = re.match(r"^([A-Z0-9]{5,7})([-_])?(.*)$", folder_name, re.IGNORECASE)
    
    if match:
        toy_number = match.group(1).upper()
        variant = match.group(3).strip() if match.group(3) else ""
        identifier = f"{toy_number}-{variant}" if variant else toy_number
        print(f"✅ Extracted Identifier: {identifier}")
        return identifier

    print(f"⚠️ No valid identifier found in folder name: {folder_name}")
    return None

# Process a single folder
def process_folder(folder_path):
    folder_name = os.path.basename(folder_path)
    identifier = extract_toy_and_variant(folder_name)

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

    target_folder = os.path.join(ORG_FOLDER, identifier)
    os.makedirs(target_folder, exist_ok=True)

    file_index = 1

    for file_name in sorted(os.listdir(folder_path)):
        if file_name.startswith('.') or file_name.lower() in ["icon", "icon\r"]:
            continue

        src_path = os.path.join(folder_path, file_name)

        # Skip non-image files
        if not file_name.lower().endswith(('.jpg', '.jpeg', '.png', '.heic')):
            unmatched_dest = os.path.join(UNMATCHED_FOLDER, file_name)
            try:
                if TESTING_MODE:
                    shutil.copy(src_path, unmatched_dest)
                else:
                    shutil.move(src_path, unmatched_dest)

                log_processed_image(src_path, file_name, "Unknown", "Unmatched")

            except Exception as e:
                print(f"⚠️ Error moving to unmatched: {e}")
            continue

        # Construct new filename
        identifier_filename = identifier.replace("-", "_")
        new_name = f"{identifier_filename}_{file_index}.jpg"
        dest_path = os.path.join(target_folder, new_name)

        # Handle duplicates - print but do not log
        if os.path.exists(dest_path):
            print(f"⚠️ Duplicate detected (Not Logged): {src_path}")
            continue

        # Move and log
        try:
            if TESTING_MODE:
                shutil.copy(src_path, dest_path)
            else:
                shutil.move(src_path, dest_path)

            log_processed_image(dest_path, file_name, identifier, "Processed")
            file_index += 1

        except Exception as e:
            print(f"⚠️ Error moving {src_path}: {e}")
            log_processed_image(src_path, file_name, "Unknown", "Error")

    # Clean up empty folder
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

    for folder_name in os.listdir(RAW_FOLDER):
        folder_path = os.path.join(RAW_FOLDER, folder_name)
        if os.path.isdir(folder_path):
            process_folder(folder_path)

if __name__ == "__main__":
    main()
