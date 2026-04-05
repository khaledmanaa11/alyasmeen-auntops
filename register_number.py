"""One-time script to register the WhatsApp phone number with Meta Cloud API."""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("WA_META_TOKEN")
PHONE_NUMBER_ID = os.getenv("WA_META_PHONE_ID")

if not TOKEN or not PHONE_NUMBER_ID:
    print("ERROR: WA_META_TOKEN and WA_META_PHONE_ID must be set in .env")
    exit(1)

url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/register"

response = requests.post(
    url,
    headers={"Authorization": f"Bearer {TOKEN}"},
    json={"messaging_product": "whatsapp", "pin": "000000"},
)

print(f"Status: {response.status_code}")
print(f"Response: {response.text}")
