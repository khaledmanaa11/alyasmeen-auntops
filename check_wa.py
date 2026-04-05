"""Find the correct WABA ID and Phone Number ID."""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("WA_META_TOKEN")
USER_ID = "122094121352844780"  # from token debug

headers = {"Authorization": f"Bearer {TOKEN}"}

# Try to get businesses linked to this system user
print("=== Businesses ===")
r = requests.get(
    f"https://graph.facebook.com/v18.0/{USER_ID}/businesses",
    headers=headers
)
print(r.status_code, r.text)

# Try direct WABA endpoint with the ID we have (maybe it IS the WABA)
WABA_ID = os.getenv("WA_META_PHONE_ID")  # test if this is actually WABA
print(f"\n=== Is {WABA_ID} a WABA? ===")
r = requests.get(
    f"https://graph.facebook.com/v18.0/{WABA_ID}",
    headers=headers,
    params={"fields": "id,name,phone_numbers"}
)
print(r.status_code, r.text)

# Try the app ID to find linked WABAs
APP_ID = "1217622313492596"
print(f"\n=== WABAs linked to app {APP_ID} ===")
r = requests.get(
    f"https://graph.facebook.com/v18.0/{APP_ID}/subscriptions",
    headers=headers
)
print(r.status_code, r.text)
