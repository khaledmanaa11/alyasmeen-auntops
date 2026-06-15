import json
import logging
import re

from app.ai.retriever import search_products
from app.db.database import execute, execute_returning
from app.routers.whatsapp_helpers import (
    STATUS_LABELS,
    append_history,
    catalog,
    clear_session,
    get_customer_name,
    get_latest_order,
    get_saved_address,
    load_history,
    load_session,
    save_customer_address,
    save_session,
    upsert_customer,
)
from app.services.ai_service import generate_reply as ai_generate_reply
from app.services.config import Config

if Config.USE_MOCK_WHATSAPP:
    from app.services.whatsapp_dev import send_text, send_buttons
else:
    from app.services.whatsapp_meta import send_text, send_buttons

log = logging.getLogger("worker_tasks")

WHATSAPP_MENU_LIMIT = 5

# Arabic aliases → normalized English command keys
_AR_ALIASES: dict[str, str] = {
    "سلة": "cart", "سلتي": "cart", "السلة": "cart", "شوف السلة": "cart", "عرض السلة": "cart",
    "امسح": "clear", "مسح": "clear", "مسح السلة": "clear", "امسح السلة": "clear",
    "قائمة": "menu", "منيو": "menu", "المنتجات": "menu", "شوف المنتجات": "menu", "عرض المنتجات": "menu",
    "استلام": "pickup", "استلم": "pickup",
    "توصيل": "delivery",
    "تأكيد": "confirm", "تأكيد الطلب": "confirm", "أكد الطلب": "confirm",
}

# ---------------------------------------------------------------------------
# Agentic tool handlers — called by Claude via tool_executor closure
# ---------------------------------------------------------------------------

def _tool_add_to_cart(inp: dict, st: dict, cart: list) -> str:
    """Find a product by name and add it to the cart. Modifies cart in place."""
    product_name = (inp.get("product_name") or "").strip()
    qty = max(1, int(inp.get("qty") or 1))

    results = search_products(product_name, None)
    if not results:
        return f"لم أجد منتجاً باسم '{product_name}'. اكتب 'menu' لرؤية المنتجات المتاحة."

    prod = results[0]
    prod_id = int(prod.get("sku", 0))
    existing = next((c for c in cart if c.get("product_id") == prod_id), None)
    if existing:
        existing["qty"] = int(existing.get("qty", 1)) + qty
    else:
        cart.append({
            "product_id": prod_id,
            "name": prod["name"],
            "price": float(prod.get("price", 0)),
            "qty": qty,
        })
    st["cart"] = cart
    return f"تمت إضافة {prod['name']} × {qty} إلى السلة. السعر: {float(prod.get('price', 0)):.2f}₪"


def _tool_show_menu(inp: dict, st: dict) -> str:
    """Load products from Supabase and build a numbered menu string. Updates session."""
    category = (inp.get("category") or "").strip() or None
    products = search_products(None, category) if category else search_products(None, None)
    products = products[:WHATSAPP_MENU_LIMIT]

    if not products:
        return "لا توجد منتجات متاحة حالياً."

    # Store in session so subsequent number selections work
    st["menu_products"] = [
        {"id": int(p["sku"]), "name": p["name"], "list_price": float(p.get("price", 0))}
        for p in products
    ]

    lines = ["📋 المنتجات المتاحة:"]
    for i, p in enumerate(products, 1):
        price = float(p.get("price", 0))
        lines.append(f"{i}) {p['name']} — {price:.0f}₪")
    lines.append("\nاكتب رقم المنتج لإضافته للسلة.")
    return "\n".join(lines)


def _tool_get_order_status(phone: str) -> str:
    """Look up the most recent order for this customer and return a status string."""
    order = get_latest_order(phone)
    if not order:
        return "لم أجد طلبات مسجلة على رقمك."
    status_label = STATUS_LABELS.get(order.get("status", ""), "غير معروف")
    created = str(order.get("created_at", ""))[:10]
    fulfillment = "توصيل 🚚" if order.get("fulfillment") == "delivery" else "استلام 🏪"
    return (
        f"آخر طلب لك:\n"
        f"الحالة: {status_label}\n"
        f"نوع التسليم: {fulfillment}\n"
        f"تاريخ الطلب: {created}"
    )


def _tool_save_address(inp: dict, phone: str, st: dict) -> str:
    """Save a delivery address to session and DB."""
    address = (inp.get("address") or "").strip()
    if not address:
        return "لم يتم تحديد عنوان. أرسل عنوانك كاملاً من فضلك."
    st["address"] = address
    st["stage"] = "root"
    save_customer_address(phone, address)
    return f"تم حفظ عنوانك: {address}"


def _make_tool_executor(phone: str, st: dict, cart: list, ran_flag: list[bool]):
    """Return a closure that Claude can call to execute any of the 4 tools.

    ran_flag is a single-element list used as a mutable flag: ran_flag[0] is set
    to True whenever a tool runs, so the caller knows to persist the session.
    """
    def executor(name: str, inp: dict) -> str:
        ran_flag[0] = True
        if name == "add_to_cart":
            return _tool_add_to_cart(inp, st, cart)
        if name == "show_menu":
            return _tool_show_menu(inp, st)
        if name == "get_order_status":
            return _tool_get_order_status(phone)
        if name == "save_address":
            return _tool_save_address(inp, phone, st)
        return "أداة غير معروفة."
    return executor


def _handle_message(phone: str, text: str, wa_name: str | None = None):
    """Verbatim handler logic extracted from webhook_post."""
    text = (text or "").strip()
    low = text.lower()
    wa_name = (wa_name or "").strip()

    log.info("WHATSAPP RX from=%s name=%s text=%s", phone, wa_name, text)

    st = load_session(phone)
    cart = st.get("cart") or []

    # Normalize Arabic aliases to command keys (e.g. "سلة" → "cart")
    low = _AR_ALIASES.get(low, low)

    # -----------------------------------------------------------------------
    # NEW CUSTOMER WELCOME — fires once on their very first message
    # -----------------------------------------------------------------------
    if upsert_customer(phone, wa_name):
        name_part = f" يا {wa_name}" if wa_name else ""
        send_text(
            phone,
            f"أهلاً وسهلاً{name_part}! 🌿✨\n"
            "مرحبتين في ALYASMEEN — منتجات طبيعية ومصنوعة بحب من فلسطين 💚\n\n"
            "أنا هنا أساعدك تختاري المنتج المناسب لبشرتك.\n"
            "احكيلي شو بدك أو شو مشكلة بشرتك وأنصحك! 😊"
        )
        # Don't return — continue processing their first message normally

    # -----------------------------------------------------------------------
    # HARD COMMANDS — always work regardless of conversation state
    # -----------------------------------------------------------------------

    # CART: show cart contents
    if low == "cart":
        if not cart:
            return send_text(phone, "سلة طلباتك فارغة. احكيلي شو بدك وأساعدك تختار! ✨")
        digit_map = {"0":"٠","1":"١","2":"٢","3":"٣","4":"٤","5":"٥","6":"٦","7":"٧","8":"٨","9":"٩"}
        def arabic_n(n: int) -> str:
            return "".join(digit_map[d] for d in str(n))
        lines = ["🛒 سلة طلباتك:"]
        total = 0.0
        for i, it in enumerate(cart, start=1):
            qty = int(it.get("qty", 1))
            price = float(it.get("price", 0) or 0)
            subtotal = qty * price
            total += subtotal
            lines.append(f"{arabic_n(i)}) {it.get('name','منتج')} × {qty} = {subtotal:.2f}₪")
        lines.append(f"\nالإجمالي: {total:.2f}₪")
        cart_text = "\n".join(lines)
        if st.get("fulfillment"):
            return send_buttons(phone, cart_text,
                [{"id": "confirm", "title": "✅ تأكيد الطلب"},
                 {"id": "clear",   "title": "🗑️ مسح السلة"}])
        return send_buttons(phone, cart_text,
            [{"id": "pickup",   "title": "🏪 استلام"},
             {"id": "delivery", "title": "🚚 توصيل"},
             {"id": "clear",    "title": "🗑️ مسح السلة"}])

    # CLEAR: empty the cart
    if low == "clear":
        st["cart"] = []
        st["stage"] = "root"
        save_session(phone, st)
        return send_text(phone, "تم مسح السلة. شو بدك تطلب؟ 😊")

    # FULFILLMENT: pickup or delivery
    if low in ("pickup", "delivery"):
        st["fulfillment"] = low
        if low == "delivery":
            saved = get_saved_address(phone)
            if saved:
                # Offer their saved address as a shortcut
                st["stage"] = "awaiting_address"
                save_session(phone, st)
                return send_text(
                    phone,
                    f"📍 عندنا عنوانك المحفوظ:\n{saved}\n\n"
                    "اكتب 'نفس العنوان' لاستخدامه، أو أرسل عنوانًا جديداً."
                )
            else:
                st["stage"] = "awaiting_address"
                save_session(phone, st)
                return send_text(phone, "📍 وين بدك نوصلك؟ أرسل عنوانك كاملاً (المدينة، الحي، الشارع).")
        else:
            save_session(phone, st)
            return send_buttons(phone, "تمام، استلام من المتجر ✅",
                [{"id": "confirm", "title": "✅ تأكيد الطلب"}])

    # CONFIRM: place the order
    if low == "confirm":
        if not cart:
            return send_text(phone, "السلة فارغة. احكيلي شو بدك تطلب وأضيفه للسلة! 😊")

        fulfillment = st.get("fulfillment") or "pickup"

        # Block delivery orders that have no address yet
        if fulfillment == "delivery" and not st.get("address"):
            st["stage"] = "awaiting_address"
            save_session(phone, st)
            return send_text(phone, "📍 محتاج عنوانك للتوصيل. أرسل عنوانك كاملاً (المدينة، الحي، الشارع).")

        # Calculate total
        total = sum(int(it.get("qty", 1)) * float(it.get("price", 0) or 0) for it in cart)

        # Insert order into PostgreSQL
        order_row = execute_returning(
            """
            INSERT INTO orders (phone, fulfillment, address, total, status, channel, created_at, updated_at)
            VALUES (%s, %s, %s, %s, 'to_do', 'whatsapp', now(), now())
            RETURNING id
            """,
            (phone, fulfillment, st.get("address") or "", total),
        )
        order_id = order_row["id"]
        order_name = f"ORD-{order_id:04d}"
        execute("UPDATE orders SET order_name = %s WHERE id = %s", (order_name, order_id))

        # Insert order lines
        for it in cart:
            qty = int(it.get("qty", 1))
            price = float(it.get("price", 0) or 0)
            execute(
                "INSERT INTO order_lines (order_id, product_name, qty, unit_price, line_total) VALUES (%s, %s, %s, %s, %s)",
                (order_id, it.get("name", ""), qty, price, qty * price),
            )

        clear_session(phone)
        send_text(phone, f"✅ تم إنشاء الطلب! رقم طلبك {order_name}. سنخبرك لما يكون جاهز 🎉")

        # Notify aunt of the new order
        if Config.AUNT_PHONE:
            try:
                customer_name = get_customer_name(phone) or phone
                fulfillment_label = "توصيل 🚚" if fulfillment == "delivery" else "استلام 🏪"
                items_lines = "\n".join(
                    f"  • {it.get('name', '')} × {int(it.get('qty', 1))}"
                    for it in cart
                )
                address_line = f"\n📍 {st.get('address')}" if fulfillment == "delivery" and st.get("address") else ""
                send_text(
                    Config.AUNT_PHONE,
                    f"🛍️ طلب جديد! {order_name}\n"
                    f"👤 {customer_name} — {phone}\n"
                    f"{items_lines}\n"
                    f"💰 الإجمالي: {total:.2f}₪\n"
                    f"📦 {fulfillment_label}{address_line}"
                )
            except Exception:
                log.warning("Failed to notify aunt of new order %s", order_name)

        return {"ok": True, "order_id": order_id, "order_name": order_name}

    # AWAITING ADDRESS: customer chose delivery and we're waiting for their address
    if st.get("stage") == "awaiting_address":
        if low in ("نفس العنوان", "same", "نفس", "same address"):
            address = get_saved_address(phone)
            if not address:
                return send_text(phone, "ما عندنا عنوان محفوظ لك. أرسل عنوانك كاملاً من فضلك.")
        else:
            address = text
            save_customer_address(phone, address)  # remember for next time
        st["address"] = address
        st["stage"] = "root"
        save_session(phone, st)
        return send_buttons(phone, f"✅ تم حفظ العنوان:\n{address}",
            [{"id": "confirm",  "title": "✅ تأكيد الطلب"},
             {"id": "delivery", "title": "🔄 تغيير العنوان"}])

    # MENU: show numbered product list from Supabase
    if low == "menu":
        products = search_products(None, None)[:WHATSAPP_MENU_LIMIT]

        if not products:
            return send_text(phone, "حالياً لا توجد منتجات متاحة.")

        st["menu_products"] = [
            {"id": int(p["sku"]), "name": p["name"], "list_price": float(p.get("price", 0))}
            for p in products
        ]
        save_session(phone, st)

        lines: list[str] = []
        for i, p in enumerate(products, start=1):
            price = float(p.get("price") or 0)
            lines.append(f"{i}) {p['name']} — {price:.0f}₪")
        lines.append("\nاكتب رقم المنتج لإضافته للسلة، أو 'info 1' لتفاصيله.")
        return send_text(phone, "قائمة المنتجات:\n" + "\n".join(lines))

    # NUMBER SELECTION: "1", "2", "3" → add product from last shown menu
    if low.isdigit() and st.get("menu_products"):
        idx = int(low) - 1
        products = st["menu_products"]
        if idx < 0 or idx >= len(products):
            return send_text(phone, "الرقم غير صحيح، حاول مرة أخرى.")
        prod = products[idx]
        existing = next((c for c in cart if c.get("product_id") == prod["id"]), None)
        if existing:
            existing["qty"] = int(existing.get("qty", 1)) + 1
        else:
            cart.append({
                "product_id": prod["id"],
                "name": prod["name"],
                "price": float(prod.get("list_price", 0) or 0),
                "qty": 1,
            })
        st["cart"] = cart
        st["stage"] = "confirm"
        save_session(phone, st)
        return send_buttons(phone, f"✅ تمت إضافة {prod['name']} للسلة 🎉",
            [{"id": "pickup",   "title": "🏪 استلام"},
             {"id": "delivery", "title": "🚚 توصيل"},
             {"id": "cart",     "title": "🛒 عرض السلة"}])

    # QUANTITY PATTERN: "2x1", "2 x 1", "3*2"
    qty_match = re.match(r"^\s*(\d+)\s*[xX*]\s*(\d+)\s*$", low)
    if qty_match and st.get("menu_products"):
        qty = int(qty_match.group(1))
        idx = int(qty_match.group(2)) - 1
        products = st["menu_products"]
        if 0 <= idx < len(products):
            prod = products[idx]
            existing = next((c for c in cart if c.get("product_id") == prod["id"]), None)
            if existing:
                existing["qty"] = int(existing.get("qty", 1)) + qty
            else:
                cart.append({
                    "product_id": prod["id"],
                    "name": prod["name"],
                    "price": float(prod.get("list_price", 0) or 0),
                    "qty": qty,
                })
            st["cart"] = cart
            st["stage"] = "confirm"
            save_session(phone, st)
            return send_buttons(phone, f"✅ تمت إضافة {prod['name']} × {qty} للسلة 🎉",
                [{"id": "pickup",   "title": "🏪 استلام"},
                 {"id": "delivery", "title": "🚚 توصيل"},
                 {"id": "cart",     "title": "🛒 عرض السلة"}])

    # INFO COMMAND: "info 1" or "تفاصيل 1"
    if low.startswith("info") or low.startswith("تفاصيل"):
        parts = low.split()
        if len(parts) >= 2 and parts[1].isdigit():
            idx = int(parts[1]) - 1
            cat = catalog()
            if 0 <= idx < len(cat):
                p = cat[idx]
                price = float(p.get("list_price") or 0)
                price_str = f"{price:.0f}".rstrip("0").rstrip(".")
                desc = (p.get("description_sale") or "").strip()
                body = f"{p.get('name','')}\nالسعر: {price_str}₪"
                if desc:
                    body += f"\n\n{desc}"
                return send_text(phone, body)
        return send_text(phone, "اكتب 'menu' أولاً ثم 'info 1' لتفاصيل المنتج الأول.")


    # ORDER TRACKING: "وين طلبي؟" / "where is my order?"
    order_keywords = ("طلبي", "وين طلب", "where is my order", "order status", "متى يجهز")
    if any(kw in low for kw in order_keywords):
        order = get_latest_order(phone)
        if order:
            status_label = STATUS_LABELS.get(order.get("status", ""), order.get("status", "غير معروف"))
            created = str(order.get("created_at", ""))[:10]
            fulfillment = "توصيل" if order.get("fulfillment") == "delivery" else "استلام"
            return send_text(
                phone,
                f"آخر طلب لك:\n"
                f"الحالة: {status_label}\n"
                f"نوع التسليم: {fulfillment}\n"
                f"تاريخ الطلب: {created}"
            )
        else:
            return send_text(phone, "ما لقيت طلبات مسجلة على رقمك. إذا طلبت مؤخراً تواصل معنا مباشرة 📞")


    # -----------------------------------------------------------------------
    # CONVERSATIONAL AI — handles everything else
    # Claude has 4 tools it can call to actually take action (add to cart,
    # show menu, get order status, save address). The executor runs them
    # here in whatsapp.py where we have full session/DB access.
    # -----------------------------------------------------------------------
    append_history(phone, "user", text)
    prev = load_history(phone, limit=8)
    customer_name = wa_name or get_customer_name(phone)

    # Track whether any tool call mutated session state
    _tools_ran: list[bool] = [False]

    executor = _make_tool_executor(phone, st, cart, _tools_ran)
    reply = ai_generate_reply(
        user_message=text,
        previous_messages=prev,
        cart=cart if cart else None,
        customer_name=customer_name or None,
        tool_executor=executor,
    )
    if not reply:
        reply = "عذرًا، صار خلل مؤقت. جرّب مرة ثانية. 🙏"

    # Persist session only if a tool actually ran and changed state
    if _tools_ran[0]:
        save_session(phone, st)

    append_history(phone, "assistant", reply)

    # If cart was just updated and fulfillment not chosen yet, attach fulfillment buttons
    if _tools_ran[0] and st.get("cart") and not st.get("fulfillment"):
        return send_buttons(phone,
            reply + "\n\nاختار طريقة الاستلام 👇",
            [{"id": "pickup",   "title": "🏪 استلام"},
             {"id": "delivery", "title": "🚚 توصيل"}])

    return send_text(phone, reply)
