import json
import logging
import time
from datetime import date, datetime
from typing import Any, Callable

import structlog
from app.db.database import execute, query, rpc
from app.services.ai_service import generate_reply
from app.services.config import Config
from app.services.pdf_invoice import generate_invoice_pdf
from app.services import handoff, policy
from app.services.policy import MAX_CART_QTY, MIN_CART_QTY
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
    from app.services.whatsapp_dev import send_text, send_buttons, send_document_bytes
else:
    from app.services.whatsapp_meta import send_text, send_buttons, send_document_bytes

# Poison-pill guard: after this many failed attempts a webhook event is
# dead-lettered (processed = TRUE, error prefixed) instead of retried forever.
MAX_WEBHOOK_EVENT_ATTEMPTS = 3

# AI-supplied cart quantities are clamped to this range before being applied.
# Canonical values now live in policy.py (imported above) so the gate and the
# execution agree on one source; the module-level names MIN_CART_QTY/
# MAX_CART_QTY stay valid here (processor.MIN_CART_QTY still works) because
# _tool_add_to_cart's own clamp is ALSO needed: the numeric menu-pick path
# (handle_message step 5) calls _tool_add_to_cart directly, bypassing the AI
# and therefore policy.validate() entirely, so both layers must clamp.

# Fallback reply sent to the customer when the AI call itself fails.
AI_FALLBACK_REPLY = "عذرًا، في مشكلة تقنية مؤقتة، جرب كمان شوي 🙏"

# Sent when the bot hands the conversation to Hanan. One deterministic
# sentence, never model-generated: the customer must not be promised an
# escalation that did not actually get written to the handoffs table.
HANDOFF_ACK_REPLY = "تمام 🌿 حوّلت المحادثة لحنان، رح ترد عليكِ بأقرب وقت."

UNSUPPORTED_MEDIA_REPLY = (
    "ما بقدر أفتح الرسائل الصوتية والصور والملفات 🙏 "
    "اكتبيلي رسالة نصية لو سمحتِ — وبنفس الوقت حوّلت المحادثة لحنان تتابع معك 🌿"
)


# ---------------------------------------------------------------------------
# Outbox enqueue — the durable-send seam
#
# All customer-facing sends from the message pipeline go through outbox_jobs
# instead of calling the WhatsApp API inline: a send failure then retries in
# the outbox poller (bounded by max_attempts) without failing — and therefore
# re-running — the webhook event that produced it. Only process_job() and the
# standalone scheduler services call send_text/send_buttons directly.
# ---------------------------------------------------------------------------

def queue_text(phone: str, text: str) -> None:
    """Queue an outbound text message for the outbox poller."""
    execute(
        "INSERT INTO outbox_jobs (kind, phone, payload) VALUES (%s, %s, %s)",
        ("whatsapp_message", phone, {"text": text}),
    )


def queue_buttons(phone: str, body: str, buttons: list) -> None:
    """Queue an outbound interactive-buttons message for the outbox poller."""
    execute(
        "INSERT INTO outbox_jobs (kind, phone, payload) VALUES (%s, %s, %s)",
        ("whatsapp_buttons", phone, {"body": body, "buttons": buttons}),
    )


def queue_pdf_invoice(phone: str, order_id: int) -> None:
    """Queue a PDF invoice regeneration+send for the outbox poller."""
    execute(
        "INSERT INTO outbox_jobs (kind, phone, payload) VALUES (%s, %s, %s)",
        ("pdf_invoice", phone, {"order_id": order_id}),
    )


# ---------------------------------------------------------------------------
# Proactive failure alerts (05-06) — a permanently-failed outbox job or a
# dead-lettered webhook event was previously only visible if someone opened
# /alerts. This pushes a plain-Arabic WhatsApp alert through the SAME outbox
# (queue_text — never a direct send) to the aunt (customer-facing failures)
# and to Khaled/admin (everything), exactly once per permanent failure.
# ---------------------------------------------------------------------------

# outbox_jobs kinds that reach a real customer — everything else is internal
# and only the admin needs to know about it.
CUSTOMER_FACING_KINDS = {"whatsapp_message", "whatsapp_buttons", "pdf_invoice"}


def notify_permanent_failure(source: str, phone: str, kind: str, error: str) -> None:
    """Queue a WhatsApp alert for a job/event that has permanently failed.

    `source` is "outbox_job" or "webhook_event". Wrapped end-to-end in
    try/except: a failing notification must never change the outcome of the
    job that already failed.
    """
    try:
        # Loop guard (mandatory): a failed alert addressed TO the aunt or the
        # admin must never itself queue another alert about that same
        # failure — that would be an infinite outbox loop (alert about a
        # failed alert about a failed alert...).
        if phone and phone in (Config.AUNT_PHONE, Config.ADMIN_PHONE):
            return

        rows = query("SELECT name FROM customers WHERE phone = %s", (phone,))
        customer_name = (rows[0].get("name") or "") if rows else ""
        label = customer_name or phone

        if (kind in CUSTOMER_FACING_KINDS or source == "webhook_event") and Config.AUNT_PHONE:
            if kind == "pdf_invoice":
                aunt_msg = f"⚠️ الفاتورة لم تصل إلى {label}. أعيدي المحاولة أو أرسليها يدوياً."
            elif source == "webhook_event":
                aunt_msg = f"⚠️ رسالة من {label} لم تُقرأ من النظام. افتحي المحادثة وشوفي شو بدها."
            else:
                aunt_msg = f"⚠️ رسالة لم تصل إلى {label}. تابعي المحادثة معها في واتساب."
            queue_text(Config.AUNT_PHONE, aunt_msg)

        if Config.ADMIN_PHONE:
            truncated_error = (error or "")[:200]
            admin_msg = f"⚠️ فشلت عملية ({kind}) للزبون {label} — {truncated_error}"
            queue_text(Config.ADMIN_PHONE, admin_msg)
    except Exception as exc:
        log.warning(
            "notify_permanent_failure_failed",
            source=source, phone=phone, kind=kind, error=str(exc),
        )


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
                notify_permanent_failure("webhook_event", ev["phone"], "inbound_message", str(e))
            else:
                execute(
                    "UPDATE webhook_events SET error = %s WHERE id = %s",
                    (str(e), ev["id"])
                )


def process_outbox_jobs():
    """Poll for pending outbox jobs and process them."""
    jobs = query(
        "SELECT id, kind, phone, payload, attempts, max_attempts FROM outbox_jobs "
        "WHERE status IN ('pending', 'failed') AND attempts < max_attempts ORDER BY created_at ASC LIMIT 10"
    )
    if not jobs:
        return

    log.info("processing_outbox_jobs", count=len(jobs))
    for job in jobs:
        try:
            process_job(
                job["id"], job["kind"], job["phone"], job["payload"], job["attempts"],
                job.get("max_attempts", 3),
            )
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
                else:
                    log.info("empty_text_message", phone=phone)
            elif msg_type == "interactive":
                # Handle button clicks
                interactive = msg.get("interactive", {})
                if interactive.get("type") == "button_reply":
                    text = interactive.get("button_reply", {}).get("id", "").strip()
                    handle_message(phone, text, name)
            else:
                # Voice note, image, sticker, document, video, location,
                # contacts, ... — anything this bot cannot read. Previously
                # silently dropped (processed=TRUE, no reply, no trace).
                handle_unsupported_media(phone, msg_type or "unknown", name)

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


def process_job(job_id: str, kind: str, phone: str, payload: dict, attempts: int, max_attempts: int = 3):
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
        elif kind == "pdf_invoice":
            order_id = payload.get("order_id")
            rows = query(
                "SELECT o.id, o.phone, c.name AS customer_name FROM orders o "
                "LEFT JOIN customers c ON c.phone = o.phone WHERE o.id = %s",
                (order_id,),
            )
            customer_name = (rows[0]["customer_name"] or "") if rows else ""
            lines = query(
                "SELECT product_name, qty, unit_price FROM order_lines WHERE order_id = %s",
                (order_id,),
            )
            total = sum(float(ln["unit_price"]) * int(ln["qty"]) for ln in lines)
            pdf_bytes = generate_invoice_pdf(
                order_id=order_id,
                customer_name=customer_name,
                order_date=date.today().strftime("%d/%m/%Y"),
                lines=lines,
                total=total,
            )
            send_document_bytes(
                phone,
                pdf_bytes,
                filename=f"فاتورة-{order_id}.pdf",
                caption=f"🧾 فاتورتك لطلب رقم {order_id}",
            )
        else:
            log.warning("unknown_job_kind", kind=kind, job_id=job_id)
            
        execute("UPDATE outbox_jobs SET status = 'sent', processed_at = now() WHERE id = %s", (job_id,))
    except Exception as e:
        log.error("job_execution_failed", job_id=job_id, error=str(e))
        execute("UPDATE outbox_jobs SET status = 'failed', last_error = %s, updated_at = now() WHERE id = %s", (str(e), job_id))
        if attempts + 1 >= max_attempts:
            notify_permanent_failure("outbox_job", phone, kind, str(e))


# ---------------------------------------------------------------------------
# Bot Logic (handle_message)
# ---------------------------------------------------------------------------

def _open_handoff(phone: str, reason: str, metadata: dict | None = None) -> bool:
    """Open a handoff without ever letting it break the reply path.

    Returns True on success. handoff.trigger() intentionally raises on a
    durable-state failure (see 03-01); the message pipeline must not, because
    the customer is waiting on a reply either way.
    """
    try:
        handoff.trigger(phone, reason, metadata)
        return True
    except Exception as e:
        log.error("handoff_trigger_failed", phone=phone, reason=reason, error=str(e))
        return False


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

    # 2a. Paused gate — a human owns this conversation. Record what the
    # customer said so the aunt sees it in the handoff transcript
    # (operator_api.py's transcript endpoint reads chat_history), but send
    # nothing: the whole point of a handoff is that the bot stops talking.
    # Must run before every hard command and before the AI fallback, so a
    # paused customer can never accidentally trigger an order/cart mutation.
    if st.get("paused"):
        append_history(phone, "user", text)
        log.info("bot_paused_skipping_reply", phone=phone)
        return

    # 2b. Keyword-triggered handoff — placed before the hard commands so an
    # escalation request can never be swallowed by a command match (the two
    # vocabularies are disjoint, see test_hard_commands_do_not_trigger in
    # tests/unit/test_policy.py). If the handoff write itself fails, the
    # customer gets the generic apology instead of a promise the system did
    # not actually keep.
    handoff_group = policy.detect_handoff_keyword(text)
    if handoff_group:
        append_history(phone, "user", text)
        opened = _open_handoff(
            phone, "keyword_request",
            {"group": handoff_group, "message": text[:200]},
        )
        reply = HANDOFF_ACK_REPLY if opened else AI_FALLBACK_REPLY
        append_history(phone, "assistant", reply)
        queue_text(phone, reply)
        return

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
        queue_text(phone, "تم إفراغ السلة 🗑️")
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
        queue_text(phone, "ممتاز! لمين وبأي عنوان التوصيل؟ (اكتبي المدينة والحي والشارع لو سمحتِ 🙏)")
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
            queue_text(phone, f"أبشري! أضفت {p['name']} للسلة 🛒 بدك تضيفي كمان شي ولا نتمم الطلب؟")
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
    queue_text(phone, reply)

    # Session might have been updated by tools
    save_session(phone, st)


# WhatsApp message types this bot cannot read, mapped to the plain-Arabic
# noun used in the customer-facing reply and in the chat_history placeholder
# (mirrors how the eval dataset itself represents these inputs, e.g.
# "[رسالة صوتية - 0:43]", "[ملصق]").
MEDIA_TYPE_LABELS = {
    "audio": "صوتية", "voice": "صوتية", "image": "صورة", "sticker": "ملصق",
    "document": "ملف", "video": "فيديو", "location": "موقع", "contacts": "جهة اتصال",
}


def handle_unsupported_media(phone: str, msg_type: str, name: str = "") -> None:
    """A voice note / image / sticker / document / video / location /
    contacts message arrived. The bot cannot read it, so: acknowledge it in
    chat_history (so the aunt sees what the customer actually sent), reply
    with a polite apology, and open a handoff so a human follows up — instead
    of process_event's previous silent drop (processed=TRUE, no reply, no
    trace).

    Unlike handle_message, this path is reached directly from process_event
    without any prior upsert_customer() call, so it does its own —
    handoffs.phone has a live FK to customers(phone); a brand-new customer
    whose very first message is a voice note would otherwise fail that FK.
    """
    upsert_customer(phone, name)

    # Same rule as the text path's paused gate: if a human already owns this
    # conversation, don't re-send the apology or open a second handoff for
    # every subsequent voice note/photo — just log the placeholder.
    if load_session(phone).get("paused"):
        label = MEDIA_TYPE_LABELS.get(msg_type, msg_type)
        append_history(phone, "user", f"[رسالة {label}]")
        return

    label = MEDIA_TYPE_LABELS.get(msg_type, msg_type)
    append_history(phone, "user", f"[رسالة {label}]")

    # Reply is queued before the handoff so a handoff failure can never cost
    # the customer her reply.
    queue_text(phone, UNSUPPORTED_MEDIA_REPLY)
    append_history(phone, "assistant", UNSUPPORTED_MEDIA_REPLY)

    _open_handoff(phone, "unsupported_media", {"msg_type": msg_type})

    log.info("unsupported_media", phone=phone, msg_type=msg_type)


# ---------------------------------------------------------------------------
# Tool Implementations
# ---------------------------------------------------------------------------

def _make_tool_executor(phone: str, st: dict, cart: list) -> Callable[[str, dict], str]:
    def executor(name: str, args: dict) -> str:
        log.info("tool_call", name=name, args=args, phone=phone)

        # The deterministic gate (REQ-prod-policy-gate): every AI-proposed
        # tool call passes through policy.validate() before its
        # implementation runs — no dispatch below this point sees an
        # un-validated argument. catalog() is already imported above and is
        # patched by every existing test (test_processor.py's autouse
        # _catalog fixture patches processor.catalog) — passing it in from
        # here is exactly why policy.py was kept I/O-free.
        decision = policy.validate(name, args, {
            "phone": phone,
            "paused": bool(st.get("paused")),
            "cart": cart,
            "catalog": catalog(),
            # Called by policy ONLY for order-scoped tools — none exist
            # today, so the gate costs zero extra database reads on the hot
            # path. Must stay a lambda, not an eagerly-evaluated value: this
            # closure runs inside the worker's BlockingScheduler loop, and
            # eagerly calling get_latest_order() here would add a DB round
            # trip to every single tool call regardless of tool.
            "order_status_provider": lambda: (get_latest_order(phone) or {}).get("status"),
        })

        if not decision.allowed:
            log.warning("tool_denied", name=name, code=decision.code, phone=phone)
            if decision.escalate and _open_handoff(
                phone, "policy_denied", {"tool": name, "code": decision.code}
            ):
                st["handoff_pending"] = True
            # The denial becomes the tool result. ai_service.py's agentic
            # loop feeds this string back to Claude as a tool_result, and
            # Claude writes the conversational reply around it — the
            # customer sees a natural sentence, not an error code.
            return decision.message

        args = decision.args

        if name == "add_to_cart":
            return _tool_add_to_cart(st, cart, args.get("product_name", ""), args.get("qty", 1))

        if name == "show_menu":
            return _tool_show_menu(phone, args.get("category", ""), st)

        if name == "get_order_status":
            return _tool_get_order_status(phone)

        if name == "save_address":
            return _tool_save_address(phone, st, args.get("address", ""))

        # Dead-code defence: policy's unknown_tool rule already denies any
        # name not in TOOL_SCOPES before this point is ever reached.
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

    queue_text(phone, text)
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
        queue_text(phone, "سلتك فارغة حالياً. شو حابة تشوفي من منتجاتنا؟")
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
        queue_buttons(
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
        queue_text(phone, "\n".join(lines))


def _handle_confirm(phone: str, st: dict, cart: list):
    if not cart:
        return

    # A delivery order must never be created without an address — re-prompt instead.
    if st.get("fulfillment") == "delivery" and not st.get("address"):
        st["stage"] = "address"
        save_session(phone, st)
        queue_text(phone, "قبل التأكيد، لمين وبأي عنوان التوصيل؟ (اكتبي المدينة والحي والشارع لو سمحتِ 🙏)")
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
        
        queue_text(phone, f"تم تأكيد طلبك بنجاح! 🎉\nرقم الطلب: {order_name}\nرح نتواصل معك قريباً لتأكيد الموعد. شكراً لثقتك بالياسمين 🌿")
        
        # Notify Aunt if configured
        if Config.AUNT_PHONE:
            queue_text(Config.AUNT_PHONE, f"طلب جديد! 🔔\nمن: {phone}\nرقم الطلب: {order_name}\nالقيمة: {total}₪")
            
        clear_session(phone)
        
    except Exception as e:
        log.error("order_confirmation_failed", error=str(e), phone=phone)
        queue_text(phone, "عذراً، صار خلل أثناء تأكيد الطلب. بنحاول مرة ثانية، أو تواصلي معنا مباشرة.")
