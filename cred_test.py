from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

try:
    creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    service = build("sheets", "v4", credentials=creds)
    print("✅ Credentials are valid.")
except Exception as e:
    print("❌ Credential error:", e)