"""debug.py — Development-only endpoints for ALYASMEEN AuntOps.

Provides a POST /dev/test_order endpoint that creates a synthetic order
in the database without going through the WhatsApp bot flow. Used for
local testing of the dashboard, order status updates, and notifications.
These routes are registered by main.py and should not be exposed in production.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.db.database import execute, execute_returning
from app.routers.whatsapp import catalog

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

    Inserts a customer (if not already present), an order row, and order line
    items based on the provided cart. Useful for exercising the dashboard and
    status-update flows without sending a real WhatsApp message.

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

    # Insert into PostgreSQL
    order_row = execute_returning(
        """
        INSERT INTO orders (phone, fulfillment, address, total, status, channel, created_at, updated_at)
        VALUES (%s, %s, %s, %s, 'to_do', 'whatsapp', now(), now())
        RETURNING id
        """,
        (p.phone, p.fulfillment, p.address, total),
    )
    order_id = order_row["id"]
    order_name = f"ORD-{order_id:04d}"
    execute("UPDATE orders SET order_name = %s WHERE id = %s", (order_name, order_id))

    for it in cart:
        execute(
            "INSERT INTO order_lines (order_id, product_name, qty, unit_price, line_total) VALUES (%s, %s, %s, %s, %s)",
            (order_id, it["name"], it["qty"], it["price"], it["qty"] * it["price"]),
        )

    return {
        "ok": True,
        "order_id": order_id,
        "order_name": order_name,
        "cart": cart,
    }


@router.get("/chat", response_class=HTMLResponse)
def chat_ui():
    """Simple chat interface to test the WhatsApp bot without real WhatsApp."""
    return HTMLResponse(content=_CHAT_HTML)


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
      const res = await fetch('/whatsapp/webhook', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ from_number: phone, text: text, wa_name: 'عميل اختبار' })
      });
      const data = await res.json();

      typingEl.classList.remove('show');

      // send_text returns {dev:true, to:..., text:...}
      // confirm returns {ok:true, order_id:..., order_name:...}
      if (data.text) {
        addBubble(data.text, 'bot', data.buttons || null);
      } else if (data.ok && data.order_name) {
        addBubble('✅ تم إنشاء الطلب! رقم طلبك ' + data.order_name, 'bot');
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
