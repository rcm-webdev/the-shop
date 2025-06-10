import re
import requests
import gspread
import csv
from bs4 import BeautifulSoup
from google.oauth2.service_account import Credentials
from urllib.parse import quote
from difflib import SequenceMatcher, get_close_matches
import time
from collections import defaultdict
from gspread.utils import rowcol_to_a1

# ---------------- CONFIG ------------------
GOOGLE_SHEET_NAME = "Hot Wheels and Matchbox Inventory"
SHEET_TAB_NAME = "Test"
LOG_FILE = "wiki_scraper_log.csv"
CONSTANT_COLUMNS = ["Box #", "Toy #", "Quantity", "Model Name", "Brand", "Origin", "Extra"]
DESIRED_KEYS = [
    "Year", "Toy #", "Col #", "Series", "Series #", "Color",
    "Body Color", "Base Color/Type", "Country",
    "Wheel Type", "Tampo", "Notes/Variations"
]
# -----------------------------------------

def clean(text):
    return re.sub(r"[^a-z0-9]+", "", str(text).lower().strip())

def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()

def map_header(header, desired_keys=DESIRED_KEYS, cutoff=0.8):
    matches = get_close_matches(header, desired_keys, n=1, cutoff=cutoff)
    return matches[0] if matches else header

def log_to_csv(row_num, model_name, toy_num, status, url):
    with open(LOG_FILE, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([row_num, model_name, toy_num, status, url])

def extract_all_version_rows(soup, target_toy):
    combined_rows = []
    tables = soup.find_all("table", class_="wikitable")

    for table in tables:
        raw_headers = [th.get_text(strip=True) for th in table.find_all("th")]
        headers = [h.strip() for h in raw_headers]
        if not headers or ("Toy" not in "".join(headers) and "Color" not in "".join(headers)):
            continue

        print("✅ Found version table with headers:", headers)
        prev_values = {}

        for tr in table.find_all("tr")[1:]:
            cells = tr.find_all(["td", "th"])
            full_data = {}

            for i, cell in enumerate(cells):
                key = headers[i] if i < len(headers) else f"Extra_{i}"
                val = cell.get_text(strip=True).replace("\xa0", " ")
                rowspan = int(cell.get("rowspan", 1))
                if rowspan > 1:
                    prev_values[key] = val
                full_data[key] = val

            for key, val in prev_values.items():
                if key not in full_data:
                    full_data[key] = val

            toy_cell = next((v for k, v in full_data.items() if "toy" in k.lower()), None)
            col_cell = next((v for k, v in full_data.items() if "col" in k.lower()), None)

            if (
                (toy_cell and clean(target_toy) in clean(toy_cell)) or
                (col_cell and clean(target_toy) in clean(col_cell))
            ):
                combined_rows.append(full_data)

    return combined_rows

def combine_variants(rows):
    combined = defaultdict(set)
    for row in rows:
        for key, val in row.items():
            mapped_key = map_header(key.strip())
            if mapped_key in DESIRED_KEYS:
                combined[mapped_key].add(val.strip())
    return {k: "; ".join(sorted(v)) for k, v in combined.items() if v}

def build_wiki_url(model_name, brand):
    base_url = "https://hotwheels.fandom.com/wiki/" if brand.lower() == "hot wheels" else "https://matchbox.fandom.com/wiki/"
    model_cleaned = model_name.replace("’", "'").split(" (")[0].replace(" ", "_")
    encoded_name = quote(model_cleaned, safe="_()")
    return base_url + encoded_name

def get_wiki_versions(toy_number, model, brand, year):
    url = build_wiki_url(model, brand)
    print(f"🔍 Fetching: {url}")
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            print("⚠️ Page not found.")
            return None, url
        soup = BeautifulSoup(response.text, "html.parser")
        matched_rows = extract_all_version_rows(soup, toy_number)

        if not matched_rows:
            print(f"⚠️ No match for Toy #: {toy_number}")
            return None, url

        combined = combine_variants(matched_rows)
        return combined, url

    except Exception as e:
        print(f"⚠️ Error: {e}")
    return None, url

def main():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open(GOOGLE_SHEET_NAME).worksheet(SHEET_TAB_NAME)

    header_row = sheet.row_values(1)
    header_index = {col: i for i, col in enumerate(header_row)}

    with open(LOG_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Row", "Model Name", "Toy #", "Status", "Wiki URL"])

    records = sheet.get_all_records()

    for idx, row in enumerate(records, start=2):
        if not row.get("Toy #") or not row.get("Model Name"):
            continue
        toy_num = row["Toy #"]
        model_name = row["Model Name"]
        brand = row.get("Brand", "Hot Wheels")
        year = row.get("Year", "")
        print(f"🔍 Row {idx}: {model_name} → {toy_num}")

        updates, page_url = get_wiki_versions(toy_num, model_name, brand, year)
        if not updates:
            log_to_csv(idx, model_name, toy_num, "No Data", page_url)
            continue

        updates["Toy #"] = toy_num
        updates["Model Name"] = model_name

        for key in updates:
            if key not in header_index and key not in CONSTANT_COLUMNS:
                col_num = len(header_row) + 1
                sheet.update_cell(1, col_num, key)
                header_row.append(key)
                header_index[key] = col_num - 1

        full_row = sheet.row_values(idx)
        full_row += ["" for _ in range(len(header_row) - len(full_row))]
        for col, val in updates.items():
            if col in CONSTANT_COLUMNS:
                continue
            if col in header_index:
                full_row[header_index[col]] = val

        range_label = f"A{idx}:{rowcol_to_a1(idx, len(header_row))}"
        print(f"✅ Updating Row {idx}: {updates}")
        sheet.update(range_label, [full_row])
        log_to_csv(idx, model_name, toy_num, "Updated", page_url)

        time.sleep(1.5)

if __name__ == "__main__":
    main()