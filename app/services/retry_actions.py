"""
retry_actions.py — Dispatch logic for individual retry actions.
Extracted from retry_queue.py to keep the queue management code focused.
"""
from __future__ import annotations

import logging

from app.db.database import query
from app.services.config import Config

if Config.USE_MOCK_WHATSAPP:
    from app.services.whatsapp_dev import send_text
else:
    from app.services.whatsapp_meta import send_text

log = logging.getLogger(__name__)


def execute_action(action: str, order_id: int, phone: str) -> None:
    """Execute one retry action.  Raises on any failure so the caller can record it."""

    if action == "send_text_ready":
        rows = query("SELECT fulfillment FROM orders WHERE id = %s", (order_id,))
        fulfillment = (rows[0]["fulfillment"] if rows else None) or "pickup"
        if fulfillment == "delivery":
            send_text(phone, f"🚚 طلبك رقم {order_id} في الطريق إليك!")
        else:
            send_text(phone, f"✅ طلبك رقم {order_id} جاهز للاستلام!")

    elif action == "send_text_done":
        send_text(phone, f"✅ شكراً! استلمت طلبك رقم {order_id}. نتمنى تكون راضي 💚")

    elif action == "send_text_delivered":
        send_text(phone, f"📦 تم توصيل طلبك رقم {order_id}. نتمنى تكون راضي! 💚")

    elif action == "pdf_invoice":
        from app.services.pdf_invoice import generate_invoice_pdf
        if Config.USE_MOCK_WHATSAPP:
            from app.services.whatsapp_dev import send_document_bytes
        else:
            from app.services.whatsapp_meta import send_document_bytes
        from datetime import date

        order_rows = query(
            """
            SELECT o.id, o.phone, c.name AS customer_name
            FROM orders o
            LEFT JOIN customers c ON c.phone = o.phone
            WHERE o.id = %s
            """,
            (order_id,),
        )
        customer_name = (order_rows[0]["customer_name"] or "") if order_rows else ""
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
            filename=f"חשבונית-{order_id}.pdf",
            caption=f"🧾 החשבונית שלך להזמנה מספר {order_id}",
        )
        log.info("retry_actions pdf_invoice sent phone=%s order_id=%s", phone, order_id)

    else:
        log.error("retry_actions unknown action=%s order_id=%s — dropping", action, order_id)
        # Mark as resolved so we don't loop forever on garbage rows
        raise ValueError(f"unknown action: {action}")
