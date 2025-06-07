import requests
import base64
import gspread
import os
import csv
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
import time
from datetime import datetime

# === Load secrets from .env ===
load_dotenv()
CLIENT_ID = os.getenv("EBAY_CLIENT_ID")
CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET")

# === CONFIG ===
CREDENTIALS_FILE = "credentials.json"
SPREADSHEET_NAME = "Hot Wheels and Matchbox Inventory"
WORKSHEET_NAME = "Inventory"
TOY_COL = "Toy #"
MODEL_COL = "Model Name"
PRICE_COL = "eBay API Price"
LINK_COL = "eBay Listing URL"
CSV_LOG_FILE = f"ebay_price_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

# === STEP 1: Authenticate with eBay API ===

def get_ebay_access_token():
    credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {encoded_credentials}"
    }
    data = {
        "grant_type": "client_credentials",
        "scope": "https://api.ebay.com/oauth/api_scope"
    }

    response = requests.post("https://api.ebay.com/identity/v1/oauth2/token", headers=headers, data=data)
    if response.status_code == 200:
        token = response.json().get("access_token")
        print("\n✅ Access token retrieved.")
        return token
    else:
        print("\n❌ Failed to retrieve access token.")
        print("Status:", response.status_code)
        print("Response:", response.text)
        return None

# === STEP 2: Authenticate with Google Sheets ===

def authorize_google_sheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)

# === STEP 3: Fetch eBay Listings and Return Average Price + Best Link ===

def get_price_and_link_from_ebay(access_token, toy_number, model_name):
    query = f"{toy_number} {model_name} carded"
    url = f"https://api.ebay.com/buy/browse/v1/item_summary/search?q={query}&limit=3&filter=buyingOptions:FIXED_PRICE,conditionIds:1000"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    try:
        res = requests.get(url, headers=headers)
        data = res.json()
        prices = []
        links = []
        titles = []
        if "itemSummaries" in data:
            print(f"🔍 Results for: {query}")
            for item in data["itemSummaries"]:
                title = item.get("title", "No title")
                link = item.get("itemWebUrl", "No link")
                price = item["price"]["value"]
                currency = item["price"]["currency"]
                prices.append(float(price))
                links.append(link)
                titles.append(title)
                print(f" → ${price} {currency} | {title}")
                print(f"    {link}")
            if prices:
                avg_price = round(sum(prices) / len(prices), 2)
                return f"${avg_price} {currency}", links[0], titles[0]
        return None, None, None
    except Exception as e:
        print(f"Error fetching eBay listings for {toy_number}: {e}")
        return None, None, None

# === STEP 4: Run Everything ===

def run():
    print("🔐 Authenticating with eBay...")
    token = get_ebay_access_token()
    if not token:
        return

    print("📄 Accessing Google Sheet...")
    sheet = authorize_google_sheet()
    headers = sheet.row_values(1)

    toy_col_idx = headers.index(TOY_COL) + 1
    model_col_idx = headers.index(MODEL_COL) + 1
    price_col_idx = headers.index(PRICE_COL) + 1

    # Add link column if missing
    if LINK_COL not in headers:
        sheet.update_cell(1, len(headers) + 1, LINK_COL)
        link_col_idx = len(headers) + 1
    else:
        link_col_idx = headers.index(LINK_COL) + 1

    rows = sheet.get_all_values()

    with open(CSV_LOG_FILE, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["Row", "Toy #", "Model Name", "Avg Price", "Title", "Link"])

        for idx, row in enumerate(rows[1:], start=2):  # Skip header
            toy_number = row[toy_col_idx - 1].split("-")[0].strip()
            model_name = row[model_col_idx - 1].strip()

            if toy_number and model_name:
                price, link, title = get_price_and_link_from_ebay(token, toy_number, model_name)
                if price:
                    sheet.update_cell(idx, price_col_idx, price)
                    sheet.update_cell(idx, link_col_idx, link)
                    writer.writerow([idx, toy_number, model_name, price, title, link])
                else:
                    print(" → No price found.")
                time.sleep(1.5)

if __name__ == "__main__":
    run()