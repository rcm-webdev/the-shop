import os
import json
import time
import requests
from bs4 import BeautifulSoup
from pymongo import MongoClient, ASCENDING, TEXT
from dotenv import load_dotenv
from tqdm import tqdm

# Load environment variables
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")

client = MongoClient(MONGO_URI)
db = client["diecast_inventory"]
collection = db["variants"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
}

BASE_WIKIS = {
    "Hot Wheels": "https://hotwheels.fandom.com",
    "Matchbox": "https://matchbox.fandom.com"
}

START_YEAR = 1989
END_YEAR = 2024

PROCESSED_LOG = "processed_pages.json"

COLUMN_MAP = {
    "Model": "Model Name",
    "Model Name": "Model Name",
    "Variant Name": "Variant",
    "Variation": "Variant",
    "Brand": "Brand",
    "Origin": "Origin",
    "Extra": "Extra",
    "Year": "Year",
    "Year Released": "Year",
    "Series": "Series",
    "Series Name": "Series",
    "Col #": "Col #",
    "Collector #": "Col #",
    "Coll #": "Col #",
    "Col#": "Col #",
    "Body": "Body",
    "Body Color": "Body",
    "Color": "Body",
    "Base": "Base Color/Type",
    "Base Color": "Base Color/Type",
    "Base Type": "Base Color/Type",
    "Base Color/Type": "Base Color/Type",
    "Country": "Country",
    "Made in": "Country",
    "Wheel": "Wheel Type",
    "Wheels": "Wheel Type",
    "Wheel Type": "Wheel Type",
    "Window": "Window Color",
    "Windows": "Window Color",
    "Window Color": "Window Color",
    "Interior": "Interior Color",
    "Interior Color": "Interior Color",
    "Tampo": "Tampo",
    "Deco": "Tampo",
    "Decoration": "Tampo",
    "Notes": "Notes",
    "Notes/Variations": "Notes",
    "Comments": "Notes",
    "Variations": "Notes",
    "Packaging Name": "packaging_name",
    "Packaged As": "packaging_name",
    "Toy #": "Toy #",
    "Toy Number": "Toy #",
    "Toy Number(s)": "Toy #",
    "Photo": None,
    "Image": None,
    "Ref": None,
    "Wiki": None,
    "Link": None
}

# Load or initialize log
if os.path.exists(PROCESSED_LOG):
    with open(PROCESSED_LOG, 'r') as f:
        processed_pages = set(json.load(f))
else:
    processed_pages = set()

def save_processed_log():
    with open(PROCESSED_LOG, 'w') as f:
        json.dump(list(processed_pages), f)

def get_yearly_list_pages():
    pages = []
    for brand, base_url in BASE_WIKIS.items():
        for year in range(START_YEAR, END_YEAR + 1):
            list_page = f"{base_url}/wiki/List_of_{year}_{brand.replace(' ', '_')}"
            pages.append((brand, year, list_page))
    return pages

def get_car_links_from_list_page(url, brand):
    try:
        res = session.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        return [BASE_WIKIS[brand] + a['href'] for a in soup.select('table a[href^="/wiki/"]') if not a['href'].startswith('/wiki/List')]
    except Exception as e:
        print(f"Error getting car links from {url}: {e}")
        return []

def extract_text_or_image(cell):
    text = cell.get_text(strip=True)
    if text:
        return text
    img = cell.find("img")
    if img:
        return img.get("alt") or os.path.basename(img.get("src", ""))
    return ""

def extract_variants_from_versions_table(soup):
    variants = []
    tables = soup.select("table.wikitable")
    for table_index, table in enumerate(tables):
        headers = [th.get_text(strip=True).replace('.', '') for th in table.select("tr th")]
        rowspan_cache = {}
        rows = table.select("tr")[1:]

        for row in rows:
            cells = row.find_all(["td", "th"])
            data = []
            col_idx = 0

            while col_idx in rowspan_cache:
                data.append(rowspan_cache[col_idx]["value"])
                rowspan_cache[col_idx]["rows_left"] -= 1
                if rowspan_cache[col_idx]["rows_left"] == 0:
                    del rowspan_cache[col_idx]
                col_idx += 1

            for cell in cells:
                value = extract_text_or_image(cell)
                rowspan = int(cell.get("rowspan", 1))
                data.append(value)

                if rowspan > 1:
                    rowspan_cache[col_idx] = {
                        "value": value,
                        "rows_left": rowspan - 1
                    }
                col_idx += 1

            if len(data) > len(headers):
                data = data[:len(headers)]

            variant = dict(zip(headers, data))
            filtered_variant = {}

            for k, v in variant.items():
                std_key = COLUMN_MAP.get(k.strip(), k.strip())
                if std_key is not None:
                    filtered_variant[std_key] = v

            filtered_variant["source_table"] = f"Versions Table {table_index + 1}"
            variants.append(filtered_variant)

    return variants

def process_car_page(url, brand, year):
    if url in processed_pages:
        return

    try:
        res = session.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')

        variants = extract_variants_from_versions_table(soup)
        for variant in variants:
            variant.update({"brand": brand, "year": year, "wiki_url": url})

        if variants:
            collection.insert_many(variants)

        processed_pages.add(url)
        save_processed_log()

        time.sleep(0.2)

    except Exception as e:
        print(f"❌ Failed processing {url}: {e}")

def create_indexes():
    print("🔧 Creating indexes...")
    collection.create_index([
        ("wiki_title", TEXT),
        ("packaging_name", TEXT),
        ("Model Name", TEXT)
    ])
    collection.create_index([("Toy #", ASCENDING), ("brand", ASCENDING)])
    collection.create_index([("brand", ASCENDING), ("year", ASCENDING)])
    collection.create_index([("Model Name", ASCENDING), ("year", ASCENDING)])
    print("✅ Indexing complete.")

def main():
    pages = get_yearly_list_pages()
    all_car_links = []

    print("🔍 Collecting car URLs...")
    for brand, year, list_page in tqdm(pages):
        links = get_car_links_from_list_page(list_page, brand)
        all_car_links.extend([(link, brand, year) for link in links])

    print(f"🚗 Found {len(all_car_links)} car pages. Scraping sequentially...")
    for url, brand, year in tqdm(all_car_links):
        process_car_page(url, brand, year)

    create_indexes()
    print("✅ Scraping and indexing complete.")

if __name__ == "__main__":
    with requests.Session() as session:
        main()