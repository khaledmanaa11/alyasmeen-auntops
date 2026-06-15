from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import PlainTextResponse

from app.db.database import execute
from app.services.config import Config
from app.services.transport import verify_meta_signature, parse_meta_envelope

if Config.USE_MOCK_WHATSAPP:
    from app.services.whatsapp_dev import verify_get
else:
    from app.services.whatsapp_meta import verify_get

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

log = logging.getLogger("whatsapp")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/webhook")
async def webhook_get(request: Request):
    params = dict(request.query_params)
    try:
        ok, code, body = verify_get(params)
        return PlainTextResponse(content=body) if code == 200 else (body, code)
    except TypeError:
        # Compatibility with older verify_get signatures
        ok, code, body = verify_get(params, dict(request.headers), b"")
        return PlainTextResponse(content=body) if code == 200 else (body, code)


@router.post("/webhook")
async def webhook_post(request: Request):
    """
    Ingest-and-Ack Webhook.
    
    1. Verifies HMAC signature from Meta.
    2. Parses the Meta envelope into individual events.
    3. Persists events to webhook_events table (Inbox).
    4. Returns 200 OK immediately.
    
    Processing is handled asynchronously by the Worker (Phase 08).
    """
    body_bytes = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    
    if not verify_meta_signature(body_bytes, signature):
        log.warning("REFUSED: Invalid Meta signature")
        raise HTTPException(status_code=403, detail="Invalid signature")

    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except Exception:
        return {"ok": False, "error": "Invalid JSON"}

    events = parse_meta_envelope(payload)
    
    if events:
        for event in events:
            wamid = event.get("wamid")
            if not wamid:
                continue
            try:
                execute(
                    "INSERT INTO webhook_events (wamid, payload) VALUES (%s, %s) ON CONFLICT (wamid) DO NOTHING",
                    (wamid, event["payload"])
                )
            except Exception as e:
                log.error("Failed to ingest wamid=%s: %s", wamid, e)
        return {"ok": True}

    # Fallback for flat dev/mock shape (internal use only)
    if "from_number" in payload:
        mock_wamid = f"mock-{hash(body_bytes)}"
        execute(
            "INSERT INTO webhook_events (wamid, payload) VALUES (%s, %s) ON CONFLICT (wamid) DO NOTHING",
            (mock_wamid, payload)
        )
        return {"ok": True}

    return {"ok": True}
