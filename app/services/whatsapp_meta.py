"""WhatsApp Meta Cloud API sender — real production implementation. Sends text messages and PDF documents via Meta Graph API v19.0. Only used when USE_MOCK_WHATSAPP=0."""
import hashlib
import hmac

import requests

from app.services.config import Config


def send_text(to: str, text: str) -> dict:
    """Send a text message via the Meta Cloud API.

    Falls back to the mock sender if USE_MOCK_WHATSAPP is set.

    Args:
        to:   Recipient phone number (spaces are stripped automatically).
        text: Message body.

    Returns:
        Dict with status (HTTP code) and resp (API response) keys.
    """
    if Config.USE_MOCK_WHATSAPP:
        from app.services.whatsapp_dev import send_text as dev_send
        return dev_send(to, text)

    url = f"https://graph.facebook.com/v19.0/{Config.WA_META_PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {Config.WA_META_TOKEN}", "Content-Type":"application/json"}
    payload = {
        "messaging_product":"whatsapp",
        "to": to.replace(" ", ""),
        "type":"text",
        "text":{"body": text}
    }
    r = requests.post(url, headers=headers, json=payload, timeout=15)
    try:
        data = r.json()
    except Exception:
        data = {"status": r.status_code, "text": r.text}
    return {"status": r.status_code, "resp": data}

def send_document_bytes(to: str, pdf_bytes: bytes, filename: str, caption: str | None = None) -> dict:
    """Upload PDF bytes to the Meta media API, then send as a WhatsApp document."""
    if Config.USE_MOCK_WHATSAPP:
        from app.services.whatsapp_dev import send_document_bytes as dev_send
        return dev_send(to, pdf_bytes, filename, caption)

    upload_url = f"https://graph.facebook.com/v19.0/{Config.WA_META_PHONE_ID}/media"
    upload_r = requests.post(
        upload_url,
        headers={"Authorization": f"Bearer {Config.WA_META_TOKEN}"},
        data={"messaging_product": "whatsapp", "type": "application/pdf"},
        files={"file": (filename, pdf_bytes, "application/pdf")},
        timeout=30,
    )
    upload_r.raise_for_status()
    media_id = upload_r.json()["id"]

    msg_url = f"https://graph.facebook.com/v19.0/{Config.WA_META_PHONE_ID}/messages"
    payload: dict = {
        "messaging_product": "whatsapp",
        "to": to.replace(" ", ""),
        "type": "document",
        "document": {"id": media_id, "filename": filename},
    }
    if caption:
        payload["document"]["caption"] = caption
    r = requests.post(
        msg_url,
        headers={"Authorization": f"Bearer {Config.WA_META_TOKEN}", "Content-Type": "application/json"},
        json=payload,
        timeout=20,
    )
    try:
        data = r.json()
    except Exception:
        data = {"status": r.status_code, "text": r.text}
    return {"status": r.status_code, "resp": data}


def send_document(to: str, url: str, filename: str, caption: str | None = None) -> dict:
    """Send a document by URL via the Meta Cloud API.

    Falls back to the mock sender if USE_MOCK_WHATSAPP is set.

    Args:
        to:       Recipient phone number (spaces are stripped automatically).
        url:      Publicly accessible URL of the document to send.
        filename: Display name for the document in WhatsApp.
        caption:  Optional message caption shown below the document.

    Returns:
        Dict with status (HTTP code) and resp (API response) keys.
    """
    if Config.USE_MOCK_WHATSAPP:
        from app.services.whatsapp_dev import send_document as dev_send_document
        return dev_send_document(to, url, filename, caption)

    msg_url = f"https://graph.facebook.com/v19.0/{Config.WA_META_PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {Config.WA_META_TOKEN}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to.replace(" ", ""),
        "type": "document",
        "document": {
            "link": url,
            "filename": filename,
        },
    }
    if caption:
        payload["document"]["caption"] = caption
    r = requests.post(msg_url, headers=headers, json=payload, timeout=20)
    try:
        data = r.json()
    except Exception:
        data = {"status": r.status_code, "text": r.text}
    return {"status": r.status_code, "resp": data}

def verify_get(params: dict, headers: dict|None=None, body_bytes: bytes|None=None) -> tuple[bool,int,str]:
    """Verify a Meta webhook GET request and optionally verify a POST signature.

    For GET: checks hub.mode == "subscribe" and hub.verify_token matches config.
    For POST: if headers, body_bytes, and WA_META_APP_SECRET are all provided,
    validates the X-Hub-Signature-256 HMAC header.

    Args:
        params:     Query parameters from the webhook GET request.
        headers:    Request headers (used for POST signature verification).
        body_bytes: Raw request body bytes (used for POST signature verification).

    Returns:
        Tuple of (success, http_status_code, response_body_string).
    """
    # GET verification (Meta calls with hub.* params)
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge", "")
    if mode == "subscribe" and token == Config.WA_META_VERIFY_TOKEN:
        return True, 200, challenge

    # Optional: verify POST signature
    if headers and body_bytes and Config.WA_META_APP_SECRET:
        their = headers.get("X-Hub-Signature-256")
        mac = hmac.new(Config.WA_META_APP_SECRET.encode(), body_bytes, hashlib.sha256)
        ours = "sha256=" + mac.hexdigest()
        if not their or their != ours:
            return False, 403, "Invalid signature"
    return False, 403, "Forbidden"
