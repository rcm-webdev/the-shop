import os
import re
import sys
from urllib.parse import quote
from pymongo import MongoClient
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from dotenv import load_dotenv

# === CONFIGURATION ===
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
CREDENTIALS_FILE = os.getenv("GOOGLE_SHEETS_KEY_PATH")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
SHEET_NAME = "Inventory-Adds"
PROTECTED_COLUMNS = {"Box #", "Toy #", "Quantity", "Model Name", "Variant", "Brand", "Origin", "Extra", "Photo"}

SYNC_FIELDS = [
    "Series", "Col #", "Body", "Base Color/Type",
    "Country", "Wheel Type", "Window Color", "Interior Color", "Tampo", "Notes", "✔ Synced"
    # Year is now excluded
]

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
sheets_service = build('sheets', 'v4', credentials=creds)
sheet = sheets_service.spreadsheets()

client = MongoClient(MONGO_URI)
db = client["diecast_inventory"]
collection = db["variants"]

# === HELPERS ===

def normalize_key(key):
    mapping = {
        "Col #:": "Col #",
        "Coll #": "Col #",
        "Col#": "Col #",
        "Color": "Body",
        "Base Color": "Base Color/Type",
        "Base Color / Type": "Base Color/Type",
        "Base Color/ Type": "Base Color/Type",
        "Base Color/Type": "Base Color/Type",
        "brand": "Brand",
        "Brand": "Brand",
        "Year": None,  # ← Do not sync this field
        "Notes/Variations": "Notes",
        "Notes / Variations": "Notes",
        "Notes": "Notes",
        "Photo": None,
        "wiki_url": None,
        "wiki_title": None,
        "packaging_name": None,
    }
    return mapping.get(key.strip(), key.strip())

def build_wiki_url(model_name, brand):
    base = "https://hotwheels.fandom.com/wiki/" if brand.lower() == "hot wheels" else "https://matchbox.fandom.com/wiki/"
    model = model_name.replace("’", "'").replace(" ", "_")
    return base + quote(model, safe="_()/")

def get_sheet_data():
    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=f"{SHEET_NAME}").execute()
    values = result.get("values", [])
    headers = values[0]
    rows = values[1:]
    return headers, rows

def update_headers(headers):
    new_headers = headers[:]
    for field in SYNC_FIELDS:
        if not any(h.strip() == field for h in new_headers):
            print(f"🧩 Adding missing header: {field}")
            new_headers.append(field)
    sheet.values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!1:1",
        valueInputOption="RAW",
        body={"values": [new_headers]}
    ).execute()
    return new_headers

def get_column_index(headers):
    return {header: idx for idx, header in enumerate(headers)}

def parse_col_number(value):
    if not value:
        return []
    return re.findall(r'\bMB\d+\b', value)

def clean_series(series_value):
    return re.sub(r"(\D)(\d+/\d+)", r"\1 \2", series_value or "")

def query_variants(toy_number, model_name, col_number, brand):
    conditions = []

    def clean_toy_number(toy):
        return re.split(r"[_\s]", toy.strip())[0] if toy else ""

    cleaned_toy = clean_toy_number(toy_number)

    if cleaned_toy:
        conditions.append({"Toy #": cleaned_toy})

    if col_number:
        parsed = parse_col_number(col_number)
        for val in parsed:
            conditions.append({"Col #": val})

    if model_name and brand:
        constructed_url = build_wiki_url(model_name, brand)
        conditions.append({"wiki_url": constructed_url})

    if not conditions:
        return []

    candidates = list(collection.find({"$or": conditions}))

    if cleaned_toy:
        filtered = [doc for doc in candidates if doc.get("Toy #") == cleaned_toy]
        return filtered if filtered else candidates

    return candidates

def build_update_row(row, headers, variant, col_index):
    new_row = row[:] + [""] * (len(headers) - len(row))
    combined_notes = []

    for key, value in variant.items():
        if key in {"Notes", "Notes/Variations"}:
            if value:
                combined_notes.append(value)
            continue

        normalized_key = normalize_key(key)
        if normalized_key is None or normalized_key == "year":  # Exclude "year"
            continue

        if normalized_key not in col_index:
            print(f"⚠️ Key not found in sheet headers: {normalized_key}")
            continue

        if headers[col_index[normalized_key]] in PROTECTED_COLUMNS:
            print(f"🔒 Protected column (skipped): {normalized_key}")
            continue

        value_to_insert = clean_series(value) if normalized_key == "Series" else value
        print(f"✅ Syncing field: {normalized_key} -> {value_to_insert}")
        new_row[col_index[normalized_key]] = value_to_insert

    if combined_notes and "Notes" in col_index:
        notes_combined = " | ".join(combined_notes)
        print(f"📝 Combined Notes -> {notes_combined}")
        new_row[col_index["Notes"]] = notes_combined

    if "✔ Synced" in col_index:
        new_row[col_index["✔ Synced"]] = "✔ Synced"

    return new_row

def update_sheet_row(row_num, updated_row):
    range_str = f"{SHEET_NAME}!A{row_num + 2}"
    sheet.values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=range_str,
        valueInputOption="RAW",
        body={"values": [updated_row]}
    ).execute()

# === MAIN ===

def main():
    try:
        headers, rows = get_sheet_data()
        headers = update_headers(headers)
        col_index = get_column_index(headers)

        for i, row in enumerate(rows):
            if len(row) > col_index.get("✔ Synced", -1) and row[col_index["✔ Synced"]] == "✔ Synced":
                continue

            raw_toy_number = row[col_index["Toy #"]] if "Toy #" in col_index and len(row) > col_index["Toy #"] else ""
            toy_number = re.split(r"[-\s]", raw_toy_number.strip())[0] if raw_toy_number else ""
            model_name = row[col_index["Model Name"]] if "Model Name" in col_index and len(row) > col_index["Model Name"] else ""
            col_number = row[col_index["Col #"]] if "Col #" in col_index and len(row) > col_index["Col #"] else ""
            brand = row[col_index["Brand"]] if "Brand" in col_index and len(row) > col_index["Brand"] else ""

            if not any([toy_number, model_name, col_number]):
                continue

            print(f"\n🔍 Row {i+2} — Toy #: {toy_number}, Model: {model_name}, Col #: {col_number}")
            matches = query_variants(toy_number, model_name, col_number, brand)

            if not matches:
                print("❌ No matches found.")
                continue

            print(f"✅ {len(matches)} match(es) found. Auto-selecting the first.")
            updated_row = build_update_row(row, headers, matches[0], col_index)
            update_sheet_row(i, updated_row)
            print("✅ Row updated.")

    except KeyboardInterrupt:
        print("\n👋 Script interrupted. Exiting cleanly.")
        sys.exit(0)

if __name__ == "__main__":
    main()