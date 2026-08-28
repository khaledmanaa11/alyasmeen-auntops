"""
followup.py — Post-purchase follow-up service.

Runs on a schedule (every 6 hours via APScheduler in main.py).
Finds orders delivered 3+ days ago that haven't received a follow-up yet,
sends a WhatsApp message, and marks them as sent.
"""
from __future__ import annotations

import logging

from app.db.database import execute, query
from app.services.processor import queue_text

log = logging.getLogger(__name__)

FOLLOWUP_MESSAGE = (
    "أهلاً! 🌿 نتمنى إنك راضي/ة عن طلبك من ALYASMEEN ✨\n\n"
    "كيف كانت تجربتك مع المنتج؟ رأيك يهمنا كثير 💚\n"
    "وإذا عندك أي سؤال أو بدك توصي مرة ثانية — احكيلنا!"
)


def record_delivery(phone: str, order_id: str) -> None:
    """
    Called from appsheet.py when a delivery is confirmed.
    Inserts a row into follow_ups so the scheduler can send a follow-up in 3 days.
    """
    execute(
        "INSERT INTO follow_ups (phone, order_id, delivered_at, sent) VALUES (%s, %s, now(), false)",
        (phone, order_id),
    )
    log.info("follow_up recorded phone=%s order_id=%s", phone, order_id)


def send_followups() -> int:
    """
    Finds all deliveries that happened 3+ days ago and haven't been followed up.
    Sends a WhatsApp message to each customer and marks them as sent.
    Returns the number of messages sent.
    """
    rows = query(
        """
        SELECT id, phone, order_id
        FROM follow_ups
        WHERE sent = FALSE
          AND delivered_at <= now() - INTERVAL '3 days'
        """,
    )

    if not rows:
        log.info("follow_up: no pending follow-ups")
        return 0

    sent_count = 0
    for row in rows:
        phone = row["phone"]
        order_id = row["order_id"]
        followup_id = row["id"]
        try:
            queue_text(phone, FOLLOWUP_MESSAGE)
            execute(
                "UPDATE follow_ups SET sent = TRUE, sent_at = now() WHERE id = %s",
                (followup_id,),
            )
            sent_count += 1
            log.info("follow_up sent phone=%s order_id=%s", phone, order_id)
        except Exception:
            log.exception("follow_up failed phone=%s order_id=%s", phone, order_id)

    log.info("follow_up: sent %d messages", sent_count)
    return sent_count
