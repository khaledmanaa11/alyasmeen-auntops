"""debug.py — Development-only endpoints for ALYASMEEN AuntOps.

Provides:
  - POST /dev/test_order — creates a synthetic order in the database without
    going through the WhatsApp bot flow. Used for local testing of the
    dashboard, order status updates, and notifications.
  - GET  /dev/chat        — a browser chat UI that talks to the bot brain
    (app.services.processor.handle_message) directly, for local testing
    without a real WhatsApp number.
  - POST /dev/chat/message — the synchronous endpoint the chat UI above
    posts to.

These routes are registered by main.py only when Config.USE_MOCK_WHATSAPP is
truthy (dev mode) and should never be reachable in production.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.db.database import execute, execute_returning, rpc
from app.routers.whatsapp_helpers import catalog

log = logging.getLogger(__name__)

router = APIRouter(prefix="/dev", tags=["dev"])


class TestItem(BaseModel):
    """A single line item for a test order, referencing a product by 1-based catalog index."""

    product_index: int  # 1-based index into the active product list (Supabase)
    qty: int = 1


class CreateTestOrder(BaseModel):
    """Request body for POST /dev/test_order.

    If items is empty, the first three products from the catalog are used.
    """

    phone: str = "+972500000999"
    items: list[TestItem] = []  # if empty, auto-picks first 3 from catalog
    fulfillment: str = "pickup"  # or 'delivery'
    address: str = ""
    note: str | None = None


@router.post("/test_order")
def create_test_order(p: CreateTestOrder):
    """Create a synthetic test order directly in the database.

    Inserts a customer (if not already present) and an order (with its line
    items) via the same create_order_atomic RPC the real bot flow uses.
    Useful for exercising the dashboard and status-update flows without
    sending a real WhatsApp message.

    Args:
        p: CreateTestOrder payload — phone, items, fulfillment, address, note.

    Returns:
        Dict with ok=True, order_id, order_name, and cart on success.

    Raises:
        HTTPException 400: if fulfillment is invalid or a product_index is out of range.
        HTTPException 500: if there are no active products in Supabase.
    """
    if p.fulfillment not in ("pickup", "delivery"):
        raise HTTPException(status_code=400, detail="fulfillment must be pickup or delivery")

    cat = catalog()
    if not cat:
        raise HTTPException(status_code=500, detail="no active products found in Supabase")

    # Build cart from the active product list
    if not p.items:
        cart = [
            {"product_id": prod["id"], "name": prod["name"],
             "price": float(prod.get("list_price", 0) or 0), "qty": 1}
            for prod in cat[:3]
        ]
    else:
        cart = []
        for it in p.items:
            idx = it.product_index - 1
            if idx < 0 or idx >= len(cat):
                raise HTTPException(status_code=400, detail=f"product_index {it.product_index} out of range")
            prod = cat[idx]
            cart.append({
                "product_id": prod["id"],
                "name": prod["name"],
                "price": float(prod.get("list_price", 0) or 0),
                "qty": it.qty,
            })

    total = sum(it["qty"] * it["price"] for it in cart)

    # Ensure customer exists (FK requirement)
    execute(
        "INSERT INTO customers (phone, name) VALUES (%s, %s) ON CONFLICT (phone) DO NOTHING",
        (p.phone, "Test Customer"),
    )

    # Create the order atomically (order + order_lines + audit log), the same
    # RPC the real confirm flow uses (app.services.processor._handle_confirm).
    items_payload = [
        {
            "product_name": it["name"],
            "qty": it["qty"],
            "unit_price": it["price"],
            "line_total": it["qty"] * it["price"]
        }
        for it in cart
    ]

    rows = rpc("create_order_atomic", {
        "p_phone": p.phone,
        "p_fulfillment": p.fulfillment,
        "p_address": p.address,
        "p_total": total,
        "p_items": items_payload
    })
    # rpc() returns a list of row dicts; a scalar-returning function like
    # create_order_atomic comes back as [{"create_order_atomic": <id>}].
    order_id = rows[0]["create_order_atomic"]
    order_name = f"ORD-{order_id:04d}"

    return {
        "ok": True,
        "order_id": order_id,
        "order_name": order_name,
        "cart": cart,
    }


class CreateTestHandoff(BaseModel):
    """Request body for POST /dev/test_handoff."""

    phone: str = "+972500000998"
    reason: str = "العميلة طلبت التحدث مع شخص حقيقي"


@router.post("/test_handoff")
def create_test_handoff(p: CreateTestHandoff):
    """Seed a realistic active handoff directly in the database.

    Phase 3 (which will own the real trigger() path — keyword/media
    detection, the policy gate, pausing the session) has not been executed
    yet on this branch, so there is no producer of real handoffs. Without
    this endpoint the handoffs UI (plan 05-07) and its rollout walkthrough
    (plan 05-09) would be unexercisable until Phase 3 ships. Inserts a
    customer (if absent), a paused sessions row, three chat_history turns,
    and an active handoffs row, then returns the handoff id.
    """
    execute(
        "INSERT INTO customers (phone, name) VALUES (%s, %s) ON CONFLICT (phone) DO NOTHING",
        (p.phone, "عميلة اختبار"),
    )
    execute(
        """
        INSERT INTO sessions (phone, stage, cart, fulfillment, menu_products, address, paused)
        VALUES (%s, %s, %s::jsonb, %s, %s::jsonb, %s, %s)
        ON CONFLICT (phone) DO UPDATE SET paused = TRUE, updated_at = now()
        """,
        (p.phone, "root", "[]", None, "[]", "", True),
    )
    for role, content in (
        ("user", "مرحبا، عندي مشكلة بطلبي"),
        ("assistant", "أهلاً! ممكن توضحي أكثر؟"),
        ("user", "بدي أحكي مع حدا مش بوت"),
    ):
        execute(
            "INSERT INTO chat_history (phone, role, content) VALUES (%s, %s, %s)",
            (p.phone, role, content),
        )
    row = execute_returning(
        "INSERT INTO handoffs (phone, reason, status) VALUES (%s, %s, 'active') RETURNING id",
        (p.phone, p.reason),
    )
    return {"ok": True, "handoff_id": row["id"] if row else None, "phone": p.phone}


@router.get("/chat", response_class=HTMLResponse)
def chat_ui():
    """Simple chat interface to test the WhatsApp bot without real WhatsApp."""
    return HTMLResponse(content=_CHAT_HTML)


@router.post("/chat/message")
def chat_send_message(payload: dict):
    """Dev-only: run one message through the bot brain synchronously and
    return what it would have sent back.

    The real webhook (POST /whatsapp/webhook) only persists the event to the
    durable inbox and returns immediately — the actual reply is produced
    later, out-of-band, by the worker's process_webhook_events() loop. That
    async round trip has nothing for this simple test page to display, so
    this endpoint instead calls app.services.processor.handle_message()
    directly (the same bot logic), drains the outbox it enqueued into, and
    captures what process_job() sends via send_text/send_buttons, so the
    chat UI can show the reply inline.
    """
    phone = (payload.get("from_number") or payload.get("phone") or "+972500000001").strip()
    text = (payload.get("text") or "").strip()
    name = payload.get("wa_name", "")
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    import app.services.processor as processor

    captured: list[dict] = []

    def _capture_send_text(to, body):
        captured.append({"dev": True, "to": to, "text": body})
        return captured[-1]

    def _capture_send_buttons(to, body, buttons):
        captured.append({"dev": True, "to": to, "text": body, "buttons": buttons})
        return captured[-1]

    original_send_text = processor.send_text
    original_send_buttons = processor.send_buttons
    processor.send_text = _capture_send_text
    processor.send_buttons = _capture_send_buttons
    try:
        processor.handle_message(phone, text, name)
        # Replies are queued in outbox_jobs now — drain them here so
        # process_job() delivers into the patched senders above. Bounded:
        # one message yields at most a couple of jobs per poll of 10.
        for _ in range(3):
            before = len(captured)
            processor.process_outbox_jobs()
            if len(captured) == before:
                break
    finally:
        processor.send_text = original_send_text
        processor.send_buttons = original_send_buttons

    return captured[-1] if captured else {"text": ""}


_CHAT_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>ALYASMEEN — اختبار البوت</title>
  <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap" rel="stylesheet">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Cairo', sans-serif; }
    body { background: #e5ddd5; height: 100vh; display: flex; flex-direction: column; }

    /* Header */
    .header {
      background: #006948; color: white; padding: 12px 16px;
      display: flex; align-items: center; gap: 12px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.2);
    }
    .avatar {
      width: 42px; height: 42px; border-radius: 50%;
      background: #00a36c; display: flex; align-items: center; justify-content: center;
      font-size: 22px; flex-shrink: 0;
    }
    .header-info { flex: 1; }
    .header-name  { font-weight: 800; font-size: 15px; }
    .header-sub   { font-size: 12px; opacity: 0.8; }
    .clear-btn {
      background: rgba(255,255,255,0.2); border: none; color: white;
      padding: 6px 14px; border-radius: 20px; cursor: pointer; font-size: 12px;
      font-family: 'Cairo', sans-serif; font-weight: 700;
    }
    .clear-btn:hover { background: rgba(255,255,255,0.3); }

    /* Phone selector */
    .phone-bar {
      background: #f0f7f4; border-bottom: 1px solid #d0e8dc;
      padding: 8px 16px; display: flex; align-items: center; gap: 10px; font-size: 13px;
    }
    .phone-bar label { color: #555; font-weight: 600; white-space: nowrap; }
    .phone-bar input {
      border: 1px solid #b3d9cc; border-radius: 20px; padding: 5px 12px;
      font-size: 13px; font-family: 'Cairo', sans-serif; color: #333;
      background: white; width: 180px;
    }
    .phone-bar input:focus { outline: none; border-color: #006948; }
    .phone-bar span { color: #888; font-size: 12px; }

    /* Messages area */
    .messages {
      flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 6px;
    }
    .bubble-wrap { display: flex; }
    .bubble-wrap.user  { justify-content: flex-start; }
    .bubble-wrap.bot   { justify-content: flex-end; }
    .bubble {
      max-width: 72%; padding: 9px 13px; border-radius: 12px;
      font-size: 14px; line-height: 1.55; white-space: pre-wrap; word-break: break-word;
      box-shadow: 0 1px 2px rgba(0,0,0,0.12);
    }
    .bubble-wrap.user .bubble {
      background: white; color: #111;
      border-top-right-radius: 4px;
    }
    .bubble-wrap.bot .bubble {
      background: #dcf8c6; color: #111;
      border-top-left-radius: 4px;
    }
    .bubble .time {
      font-size: 11px; color: #999; margin-top: 4px; text-align: left; direction: ltr;
    }
    .bubble-wrap.bot .bubble .time { text-align: right; }

    /* Typing indicator */
    .typing { display: none; }
    .typing.show { display: flex; }
    .typing-dots {
      background: white; border-radius: 12px; border-top-right-radius: 4px;
      padding: 10px 16px; display: flex; gap: 4px; align-items: center;
      box-shadow: 0 1px 2px rgba(0,0,0,0.12);
    }
    .dot {
      width: 8px; height: 8px; border-radius: 50%; background: #90a4ae;
      animation: bounce 1.2s infinite;
    }
    .dot:nth-child(2) { animation-delay: 0.2s; }
    .dot:nth-child(3) { animation-delay: 0.4s; }
    @keyframes bounce {
      0%,60%,100% { transform: translateY(0); }
      30% { transform: translateY(-6px); }
    }

    /* Input area */
    .input-area {
      background: #f0f0f0; padding: 10px 12px;
      display: flex; align-items: center; gap: 8px;
      border-top: 1px solid #ddd;
    }
    .msg-input {
      flex: 1; border: none; border-radius: 24px; padding: 10px 16px;
      font-size: 14px; font-family: 'Cairo', sans-serif; color: #333;
      background: white; outline: none; resize: none;
      max-height: 100px; min-height: 44px; overflow-y: auto;
    }
    .send-btn {
      width: 44px; height: 44px; border-radius: 50%; border: none; cursor: pointer;
      background: #006948; display: flex; align-items: center; justify-content: center;
      flex-shrink: 0; transition: background 0.15s;
    }
    .send-btn:hover { background: #004d33; }
    .send-btn svg { width: 20px; height: 20px; fill: white; transform: scaleX(-1); }

    /* WhatsApp-style inline buttons */
    .wa-buttons {
      display: flex; flex-direction: column; gap: 4px; margin-top: 6px;
    }
    .wa-btn {
      background: white; border: 1px solid #d4e8df; border-radius: 8px;
      color: #006948; font-size: 13px; font-weight: 700; padding: 8px 12px;
      cursor: pointer; text-align: center; font-family: 'Cairo', sans-serif;
      transition: all 0.15s;
    }
    .wa-btn:hover { background: #e6f3ee; }

    /* Quick commands */
    .quick-bar {
      background: #f8fffe; border-top: 1px solid #e0f0e8;
      padding: 6px 12px; display: flex; gap: 6px; overflow-x: auto;
    }
    .quick-btn {
      border: 1px solid #b3d9cc; background: white; color: #006948;
      padding: 4px 12px; border-radius: 16px; font-size: 12px; font-weight: 700;
      cursor: pointer; white-space: nowrap; font-family: 'Cairo', sans-serif;
      transition: all 0.15s;
    }
    .quick-btn:hover { background: #006948; color: white; }

    /* System message */
    .sys-msg {
      text-align: center; font-size: 12px; color: #888;
      background: rgba(255,255,255,0.6); border-radius: 8px;
      padding: 4px 12px; margin: 4px auto;
    }
  </style>
</head>
<body>

  <!-- Header -->
  <div class="header">
    <div class="avatar">🌿</div>
    <div class="header-info">
      <div class="header-name">ALYASMEEN Bot</div>
      <div class="header-sub">اختبار البوت — محلي</div>
    </div>
    <button class="clear-btn" onclick="clearChat()">مسح المحادثة</button>
  </div>

  <!-- Phone selector -->
  <div class="phone-bar">
    <label>رقم اختبار:</label>
    <input type="text" id="phone-input" value="+972500000001" />
    <span>غيّر الرقم لمحاكاة عميل مختلف</span>
  </div>

  <!-- Messages -->
  <div class="messages" id="messages">
    <div class="sys-msg">بدأت المحادثة — أرسل أي رسالة للبوت</div>
  </div>

  <!-- Typing indicator -->
  <div class="bubble-wrap bot typing" id="typing">
    <div class="typing-dots">
      <div class="dot"></div>
      <div class="dot"></div>
      <div class="dot"></div>
    </div>
  </div>

  <!-- Quick commands -->
  <div class="quick-bar">
    <button class="quick-btn" onclick="send('قائمة')">قائمة</button>
    <button class="quick-btn" onclick="send('سلة')">سلة</button>
    <button class="quick-btn" onclick="send('امسح')">امسح السلة</button>
    <button class="quick-btn" onclick="send('تأكيد')">تأكيد</button>
    <button class="quick-btn" onclick="send('استلام')">استلام</button>
    <button class="quick-btn" onclick="send('توصيل')">توصيل</button>
    <button class="quick-btn" onclick="send('وين طلبي')">وين طلبي؟</button>
  </div>

  <!-- Input -->
  <div class="input-area">
    <textarea id="msg-input" class="msg-input" rows="1"
      placeholder="اكتب رسالة..."
      onkeydown="handleKey(event)"
      oninput="autoResize(this)"></textarea>
    <button class="send-btn" onclick="sendInput()">
      <svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
    </button>
  </div>

<script>
  const messagesEl = document.getElementById('messages');
  const typingEl   = document.getElementById('typing');
  const inputEl    = document.getElementById('msg-input');

  function now() {
    return new Date().toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit' });
  }

  function addBubble(text, role, buttons) {
    const wrap = document.createElement('div');
    wrap.className = 'bubble-wrap ' + role;
    let btnsHtml = '';
    if (buttons && buttons.length) {
      btnsHtml = '<div class="wa-buttons">' +
        buttons.map(b =>
          `<button class="wa-btn" onclick="send('${b.id}')">${escHtml(b.title)}</button>`
        ).join('') +
        '</div>';
    }
    wrap.innerHTML = `<div class="bubble">${escHtml(text)}${btnsHtml}<div class="time">${now()}</div></div>`;
    messagesEl.appendChild(wrap);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function addSys(text) {
    const el = document.createElement('div');
    el.className = 'sys-msg';
    el.textContent = text;
    messagesEl.appendChild(el);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function escHtml(t) {
    return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\\n/g,'<br>');
  }

  async function send(text) {
    if (!text.trim()) return;
    const phone = document.getElementById('phone-input').value.trim() || '+972500000001';

    addBubble(text, 'user');

    typingEl.classList.add('show');
    messagesEl.scrollTop = messagesEl.scrollHeight;

    try {
      // Talks directly to the bot brain (see /dev/chat/message docstring) —
      // the real /whatsapp/webhook only queues the event for the worker and
      // has no synchronous reply to show here.
      const res = await fetch('/dev/chat/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ from_number: phone, text: text, wa_name: 'عميل اختبار' })
      });
      const data = await res.json();

      typingEl.classList.remove('show');

      if (data.text) {
        addBubble(data.text, 'bot', data.buttons || null);
      } else {
        addSys('استجابة: ' + JSON.stringify(data));
      }
    } catch (e) {
      typingEl.classList.remove('show');
      addSys('❌ خطأ في الاتصال: ' + e.message);
    }
  }

  function sendInput() {
    const text = inputEl.value.trim();
    if (!text) return;
    inputEl.value = '';
    autoResize(inputEl);
    send(text);
  }

  function handleKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendInput(); }
  }

  function autoResize(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 100) + 'px';
  }

  function clearChat() {
    messagesEl.innerHTML = '<div class="sys-msg">تم مسح المحادثة</div>';
  }

  inputEl.focus();
</script>
</body>
</html>"""
