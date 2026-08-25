import json
import logging
import time
from datetime import datetime
from typing import Any, Callable

import structlog
from app.db.database import execute, query, rpc
from app.services.ai_service import generate_reply
from app.services.config import Config
from app.routers.whatsapp_helpers import (
    load_session,
    save_session,
    clear_session,
    load_history,
    append_history,
    upsert_customer,
    get_customer_name,
    get_latest_order,
    catalog,
    STATUS_LABELS
)

# Use structlog for all logging
log = structlog.get_logger(__name__)

# Mockable senders (updated via config in worker)
if Config.USE_MOCK_WHATSAPP:
    from app.services.whatsapp_dev import send_text, send_buttons
else:
    from app.services.whatsapp_meta import send_text, send_buttons

# Poison-pill guard: after this many failed attempts a webhook event is
# dead-lettered (processed = TRUE, error prefixed) instead of retried forever.
MAX_WEBHOOK_EVENT_ATTEMPTS = 3

# AI-supplied cart quantities are clamped to this range before being applied.
MIN_CART_QTY = 1
MAX_CART_QTY = 50

# Fallback reply sent to the customer when the AI call itself fails.
AI_FALLBACK_REPLY = "عذرًا، في مشكلة تقنية مؤقتة، جرب كمان شوي 🙏"


# ---------------------------------------------------------------------------
# Polling Loops
# ---------------------------------------------------------------------------

def process_webhook_events():
    """Poll for pending webhook events and process them."""
    events = query(
        "SELECT id, phone, payload, wamid, attempts FROM webhook_events WHERE processed = FALSE ORDER BY created_at ASC LIMIT 10"
    )
    if not events:
        return

    log.info("processing_webhook_events", count=len(events))
    for ev in events:
        attempts = (ev.get("attempts") or 0) + 1
        try:
            execute(
                "UPDATE webhook_events SET attempts = %s WHERE id = %s",
                (attempts, ev["id"])
            )
            # Re-check idempotency just in case
            # (Though wamid unique constraint in DB handles most of it)
            process_event(ev["id"], ev["phone"], ev["payload"])
        except Exception as e:
            log.error("event_processing_failed", event_id=ev["id"], attempts=attempts, error=str(e))
            if attempts >= MAX_WEBHOOK_EVENT_ATTEMPTS:
                log.error(
                    "webhook_event_dead_lettered",
                    event_id=ev["id"], phone=ev["phone"], attempts=attempts, error=str(e),
                )
                execute(
                    "UPDATE webhook_events SET processed = TRUE, error = %s, processed_at = now() WHERE id = %s",
                    (f"dead-letter: {e}", ev["id"])
                )
            else:
                execute(
                    "UPDATE webhook_events SET error = %s WHERE id = %s",
                    (str(e), ev["id"])
                )


def process_outbox_jobs():
    """Poll for pending outbox jobs and process them."""
    jobs = query(
        "SELECT id, kind, phone, payload, attempts FROM outbox_jobs WHERE status IN ('pending', 'failed') AND attempts < max_attempts ORDER BY created_at ASC LIMIT 10"
    )
    if not jobs:
        return

    log.info("processing_outbox_jobs", count=len(jobs))
    for job in jobs:
        try:
            process_job(job["id"], job["kind"], job["phone"], job["payload"], job["attempts"])
        except Exception as e:
            log.error("job_processing_failed", job_id=job["id"], error=str(e))


# ---------------------------------------------------------------------------
# Single Event Processing
# ---------------------------------------------------------------------------

def process_event(event_id: str, phone: str, payload: dict):
    """Process a single webhook event."""
    # 1. Extract message
    # Meta payload structure: entry[0].changes[0].value.messages[0]
    try:
        entry = payload.get("entry", [])[0]
        change = entry.get("changes", [])[0]
        value = change.get("value", {})
        
        # Handle messages
        messages = value.get("messages", [])
        if messages:
            msg = messages[0]
            msg_type = msg.get("type")
            name = value.get("contacts", [{}])[0].get("profile", {}).get("name", "")
            
            if msg_type == "text":
                text = msg.get("text", {}).get("body", "").strip()
                if text:
                    handle_message(phone, text, name)
            elif msg_type == "interactive":
                # Handle button clicks
                interactive = msg.get("interactive", {})
                if interactive.get("type") == "button_reply":
                    text = interactive.get("button_reply", {}).get("id", "").strip()
                    handle_message(phone, text, name)
            
        # Handle statuses (read receipts, etc.) - currently just logged
        statuses = value.get("statuses", [])
        if statuses:
            log.info("webhook_status_update", phone=phone, status=statuses[0].get("status"))

    except Exception as e:
        log.error("payload_extraction_failed", error=str(e), phone=phone)
        raise

    # 2. Mark as processed
    execute(
        "UPDATE webhook_events SET processed = TRUE, processed_at = now() WHERE id = %s",
        (event_id,)
    )


def process_job(job_id: str, kind: str, phone: str, payload: dict, attempts: int):
    """Process a single outbox job."""
    execute("UPDATE outbox_jobs SET status = 'processing', attempts = attempts + 1, updated_at = now() WHERE id = %s", (job_id,))
    
    try:
        if kind == "whatsapp_message":
            text = payload.get("text")
            if text:
                send_text(phone, text)
        elif kind == "whatsapp_buttons":
            body = payload.get("body")
            buttons = payload.get("buttons")
            if body and buttons:
                send_buttons(phone, body, buttons)
        else:
            log.warning("unknown_job_kind", kind=kind, job_id=job_id)
            
        execute("UPDATE outbox_jobs SET status = 'sent', processed_at = now() WHERE id = %s", (job_id,))
    except Exception as e:
        log.error("job_execution_failed", job_id=job_id, error=str(e))
        execute("UPDATE outbox_jobs SET status = 'failed', last_error = %s, updated_at = now() WHERE id = %s", (str(e), job_id))


# ---------------------------------------------------------------------------
# Bot Logic (handle_message)
# ---------------------------------------------------------------------------

def handle_message(phone: str, text: str, name: str = ""):
    """Core bot brain: history -> state -> tools -> reply."""
    # 1. Update customer record
    is_new = upsert_customer(phone, name)
    customer_name = get_customer_name(phone) or name

    # 2. Load state
    st = load_session(phone)
    history = load_history(phone)
    cart = st.get("cart", [])
    
    log.info("handle_message", phone=phone, text=text, stage=st["stage"])

    # 3. Handle "hard" commands (overrides)
    cmd = text.lower().strip()
    
    if cmd in ("menu", "منتجات", "شو عندكم"):
        _tool_show_menu(phone, "", st)
        save_session(phone, st)
        return

    if cmd in ("cart", "سلة", "طلبي"):
        _show_cart(phone, cart)
        return

    if cmd in ("clear", "فرغ", "افرغ السلة", "مسح"):
        st["cart"] = []
        save_session(phone, st)
        send_text(phone, "تم إفراغ السلة 🗑️")
        return

    if cmd in ("confirm", "تأكيد", "اكد", "أكد", "تم") and cart:
        _handle_confirm(phone, st, cart)
        return

    if cmd in ("pickup", "استلام"):
        st["fulfillment"] = "pickup"
        st["stage"] = "confirm"
        save_session(phone, st)
        _show_cart(phone, cart)
        return

    if cmd in ("delivery", "توصيل"):
        st["fulfillment"] = "delivery"
        st["stage"] = "address"
        save_session(phone, st)
        send_text(phone, "ممتاز! لمين وبأي عنوان التوصيل؟ (اكتبي المدينة والحي والشارع لو سمحتِ 🙏)")
        return

    # 4. Handle stage-based inputs
    if st["stage"] == "address" and len(text) > 5:
        _tool_save_address(phone, st, text)
        # This path returns before the AI-fallback section's final save, so the
        # address/stage mutations must be persisted here or they are lost.
        save_session(phone, st)
        return

    # 5. Handle numeric product selection (from menu)
    if cmd.isdigit():
        idx = int(cmd) - 1
        menu_items = st.get("menu_products", [])
        if 0 <= idx < len(menu_items):
            p = menu_items[idx]
            _tool_add_to_cart(st, cart, p["name"], 1)
            save_session(phone, st)
            send_text(phone, f"أبشري! أضفت {p['name']} للسلة 🛒 بدك تضيفي كمان شي ولا نتمم الطلب؟")
            return

    # 6. Fallback to AI
    append_history(phone, "user", text)
    
    # Create tool executor closure
    tool_executor = _make_tool_executor(phone, st, cart)

    try:
        reply = generate_reply(
            user_message=text,
            previous_messages=history,
            cart=cart,
            customer_name=customer_name,
            tool_executor=tool_executor
        )
    except Exception as e:
        log.error("ai_reply_failed", error=str(e), phone=phone)
        reply = AI_FALLBACK_REPLY

    append_history(phone, "assistant", reply)
    send_text(phone, reply)
    
    # Session might have been updated by tools
    save_session(phone, st)


# ---------------------------------------------------------------------------
# Tool Implementations
# ---------------------------------------------------------------------------

def _make_tool_executor(phone: str, st: dict, cart: list) -> Callable[[str, dict], str]:
    def executor(name: str, args: dict) -> str:
        log.info("tool_call", name=name, args=args, phone=phone)
        
        if name == "add_to_cart":
            return _tool_add_to_cart(st, cart, args.get("product_name", ""), args.get("qty", 1))
        
        if name == "show_menu":
            return _tool_show_menu(phone, args.get("category", ""), st)
            
        if name == "get_order_status":
            return _tool_get_order_status(phone)
            
        if name == "save_address":
            return _tool_save_address(phone, st, args.get("address", ""))
            
        return f"Tool {name} not found"
    
    return executor


def _tool_add_to_cart(st: dict, cart: list, product_name: str, qty: int) -> str:
    # Find product in catalog
    all_products = catalog()
    p_match = None
    
    # 1. Exact match
    for p in all_products:
        if p["name"].lower() == product_name.lower():
            p_match = p
            break
            
    # 2. Partial match
    if not p_match:
        for p in all_products:
            if product_name.lower() in p["name"].lower():
                p_match = p
                break
                
    if not p_match:
        return f"لم أجد منتجاً باسم '{product_name}' في القائمة."

    # Clamp AI-supplied quantity to a sane range
    try:
        requested_qty = int(qty)
    except (TypeError, ValueError):
        requested_qty = 1
    qty = max(MIN_CART_QTY, min(requested_qty, MAX_CART_QTY))
    was_clamped = qty != requested_qty

    # Add to cart
    existing = next((item for item in cart if item["name"] == p_match["name"]), None)
    if existing:
        existing["qty"] += qty
    else:
        cart.append({
            "name": p_match["name"],
            "qty": qty,
            "price": p_match["list_price"]
        })

    st["cart"] = cart
    msg = f"تمت إضافة {qty} × {p_match['name']} إلى السلة."
    if was_clamped:
        msg += f" (تم تعديل الكمية لتكون ضمن الحد المسموح: {MIN_CART_QTY}-{MAX_CART_QTY})"
    return msg


def _tool_show_menu(phone: str, category: str, st: dict) -> str:
    all_products = catalog()
    filtered = all_products
    
    if category:
        filtered = [p for p in all_products if category.lower() in p.get("description_sale", "").lower() or category.lower() in p["name"].lower()]
        
    if not filtered:
        filtered = all_products # fallback to all
        
    # Format menu
    lines = ["🌿 *قائمة منتجات الياسمين* 🌿", "اكتبي رقم المنتج للإضافة للسلة:"]
    menu_data = []
    for i, p in enumerate(filtered[:10], 1):
        lines.append(f"{i}. {p['name']} - {p['list_price']}₪")
        menu_data.append({"name": p["name"], "price": p["list_price"]})
        
    text = "\n".join(lines)

    # Mutate the session dict the caller already holds so the caller's own
    # save_session() call persists menu_products — this tool used to load and
    # save its own fresh copy, which handle_message's stale snapshot would
    # then overwrite, reverting menu_products right after it was set.
    st["menu_products"] = menu_data

    send_text(phone, text)
    return "تم عرض القائمة للزبون."


def _tool_get_order_status(phone: str) -> str:
    order = get_latest_order(phone)
    if not order:
        return "ليس لديك طلبات سابقة."
    
    status_label = STATUS_LABELS.get(order["status"], order["status"])
    return f"طلبك الأخير رقم {order['id']} حالته حالياً: {status_label}"


def _tool_save_address(phone: str, st: dict, address: str) -> str:
    st["address"] = address
    st["stage"] = "confirm"
    # save_session is called at end of handle_message
    
    from app.routers.whatsapp_helpers import save_customer_address
    save_customer_address(phone, address)
    
    _show_cart(phone, st["cart"])
    return "تم حفظ العنوان."


def _show_cart(phone: str, cart: list):
    if not cart:
        send_text(phone, "سلتك فارغة حالياً. شو حابة تشوفي من منتجاتنا؟")
        return

    lines = ["🛒 *سلة المشتريات:*"]
    total = 0
    for item in cart:
        line_total = item["qty"] * item["price"]
        total += line_total
        lines.append(f"- {item['name']} ({item['qty']}) = {line_total}₪")
    
    lines.append(f"\n*الإجمالي:* {total}₪")
    
    st = load_session(phone)
    if not st.get("fulfillment"):
        # Ask for fulfillment
        send_buttons(
            phone,
            "\n".join(lines) + "\n\nكيف بتحبي تستلمي الطلب؟",
            [
                {"id": "pickup", "title": "استلام شخصي"},
                {"id": "delivery", "title": "توصيل"}
            ]
        )
    else:
        lines.append(f"\n*التوصيل:* {'استلام شخصي' if st['fulfillment'] == 'pickup' else 'توصيل'}")
        if st.get("address"):
            lines.append(f"*العنوان:* {st['address']}")
        
        lines.append("\nلتأكيد الطلب اكتبي 'confirm' ✅")
        send_text(phone, "\n".join(lines))


def _handle_confirm(phone: str, st: dict, cart: list):
    if not cart:
        return

    # A delivery order must never be created without an address — re-prompt instead.
    if st.get("fulfillment") == "delivery" and not st.get("address"):
        st["stage"] = "address"
        save_session(phone, st)
        send_text(phone, "قبل التأكيد، لمين وبأي عنوان التوصيل؟ (اكتبي المدينة والحي والشارع لو سمحتِ 🙏)")
        return

    total = sum(item["qty"] * item["price"] for item in cart)
    
    # Build items for RPC
    # p_items JSONB -- Array of {product_name, qty, unit_price, line_total}
    items = []
    for item in cart:
        items.append({
            "product_name": item["name"],
            "qty": item["qty"],
            "unit_price": item["price"],
            "line_total": item["qty"] * item["price"]
        })
        
    try:
        rows = rpc(
            "create_order_atomic",
            {
                "p_phone": phone,
                "p_fulfillment": st.get("fulfillment", "pickup"),
                "p_address": st.get("address", ""),
                "p_total": total,
                "p_items": items
            }
        )
        # rpc() returns a list of row dicts; a scalar-returning function like
        # create_order_atomic comes back as [{"create_order_atomic": <id>}].
        order_id = rows[0]["create_order_atomic"]

        order_name = f"ORD-{order_id:04d}"
        
        send_text(phone, f"تم تأكيد طلبك بنجاح! 🎉\nرقم الطلب: {order_name}\nرح نتواصل معك قريباً لتأكيد الموعد. شكراً لثقتك بالياسمين 🌿")
        
        # Notify Aunt if configured
        if Config.AUNT_PHONE:
            send_text(Config.AUNT_PHONE, f"طلب جديد! 🔔\nمن: {phone}\nرقم الطلب: {order_name}\nالقيمة: {total}₪")
            
        clear_session(phone)
        
    except Exception as e:
        log.error("order_confirmation_failed", error=str(e), phone=phone)
        send_text(phone, "عذراً، صار خلل أثناء تأكيد الطلب. بنحاول مرة ثانية، أو تواصلي معنا مباشرة.")
