import structlog
from fastapi import APIRouter, Request, Header, HTTPException
from fastapi.responses import PlainTextResponse

from app.db.database import execute
from app.services.config import Config

if Config.USE_MOCK_WHATSAPP:
    from app.services.whatsapp_dev import send_text, send_buttons, verify_get, verify_signature
else:
    from app.services.whatsapp_meta import send_text, send_buttons, verify_get, verify_signature

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

log = structlog.get_logger("whatsapp")

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/webhook")
async def webhook_get(request: Request):
    """Verify Meta webhook challenge (GET request)."""
    params = dict(request.query_params)
    ok, code, body = verify_get(params)
    if ok:
        return PlainTextResponse(content=body)
    raise HTTPException(status_code=code, detail=body)


@router.post("/webhook")
async def webhook_post(
    request: Request,
    x_hub_signature_256: str | None = Header(None)
):
    """Inbound webhook entry point. Validates signature and persists raw event."""
    body_bytes = await request.body()
    
    # 1. HMAC Verification
    if not verify_signature(body_bytes, x_hub_signature_256):
        log.warning("webhook_signature_invalid", signature=x_hub_signature_256)
        raise HTTPException(status_code=403, detail="Invalid signature")

    # 2. Extract payload
    try:
        payload = await request.json()
    except Exception as e:
        log.error("webhook_json_decode_failed", error=str(e))
        return {"ok": False, "error": "invalid_json"}

    # 3. Extract metadata (phone and wamid) for the durable inbox
    # Meta payload structure: entry[0].changes[0].value.messages[0]
    # Everything here is defensive: Meta can send empty entry/changes arrays,
    # status-only events with no "messages" key, or other malformed shapes.
    # Variables are initialized up front and the whole parse is one broad
    # try/except so no payload shape can crash the handler — it always falls
    # through to persisting the (possibly default) phone/wamid below and
    # returning 200.
    phone = "unknown"
    wamid = None
    value: dict = {}

    try:
        entries = payload.get("entry") or []
        entry = entries[0] if entries else {}
        changes = entry.get("changes") or []
        change = changes[0] if changes else {}
        value = change.get("value") or {}

        messages = value.get("messages") or []
        if messages:
            message = messages[0]
            phone = message.get("from") or phone
            wamid = message.get("id")
        else:
            # Could be a status update or other non-message event
            statuses = value.get("statuses") or []
            if statuses:
                status = statuses[0]
                phone = status.get("recipient_id") or phone
                wamid = status.get("id")  # status wamid
    except Exception as e:
        # Unexpected payload shape — log it and keep going with the defaults
        # above so the event is still persisted instead of crashing the request.
        log.warning("webhook_payload_shape_unexpected", error=str(e), payload=payload)

    # 4. Save to webhook_events (Durable Inbox)
    # Note: message processing is paused until Plan 02-02 implements the worker.
    try:
        # Using db.execute with %s placeholders (escaped by our database.py)
        execute(
            "INSERT INTO webhook_events (phone, payload, wamid, processed) VALUES (%s, %s, %s, FALSE) ON CONFLICT (wamid) DO NOTHING",
            (phone, payload, wamid)
        )
        log.info("webhook_received", phone=phone, wamid=wamid)
    except Exception as e:
        log.error("webhook_persistence_failed", error=str(e), phone=phone, wamid=wamid)
        # We still return 200 to Meta to avoid retries if it's a transient DB error 
        # but technically we failed the inbox pattern here.
        # But per plan, return 200 OK immediately after "successful" insertion.
        # If it fails, we might want to return 500 to Meta so they retry.
        raise HTTPException(status_code=500, detail="Database error")

    return {"status": "received"}
