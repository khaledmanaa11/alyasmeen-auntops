"""
retry_queue.py — Error retry queue for failed WhatsApp API calls.

When a WhatsApp send fails, it calls enqueue() to save the failed action
to the retry_queue table.

process_retries() runs every 15 minutes via APScheduler (wired in main.py).
It retries each pending action up to MAX_ATTEMPTS times with exponential
backoff (15 min → 30 min → 60 min).  Resolved rows are kept for auditing.
"""
from __future__ import annotations

import json
import logging

from app.db.database import execute, query
from app.services.retry_actions import execute_action

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
# Backoff in minutes per attempt number (0-indexed): 15 → 30 → 60
_BACKOFF = [15, 30, 60]


# ---------------------------------------------------------------------------
# Public: enqueue a failed action
# ---------------------------------------------------------------------------

def enqueue(action: str, order_id: int, phone: str, payload: dict | None = None) -> None:
    """
    Insert a failed action into retry_queue.

    action  — one of: 'send_text_ready', 'send_text_done', 'send_text_delivered'
    """
    execute(
        """
        INSERT INTO retry_queue (action, order_id, phone, payload, attempts, next_retry_at)
        VALUES (%s, %s, %s, %s::jsonb, 0, now() + INTERVAL '15 minutes')
        """,
        (action, order_id, phone, json.dumps(payload or {})),
    )
    log.info("retry_queue enqueued action=%s order_id=%s phone=%s", action, order_id, phone)


# ---------------------------------------------------------------------------
# Scheduler job: process_retries
# ---------------------------------------------------------------------------

def process_retries() -> int:
    """
    Retry pending failed actions.  Called by APScheduler every 15 minutes.
    Returns the number of actions successfully resolved this run.
    """
    rows = query(
        """
        SELECT id, action, order_id, phone, attempts
        FROM retry_queue
        WHERE resolved = FALSE
          AND attempts < max_attempts
          AND next_retry_at <= now()
        ORDER BY next_retry_at
        """,
    )

    if not rows:
        return 0

    resolved_count = 0
    for row in rows:
        rid = row["id"]
        action = row["action"]
        order_id = row["order_id"]
        phone = row["phone"]
        attempts = row["attempts"]

        try:
            execute_action(action, order_id, phone)
            execute(
                "UPDATE retry_queue SET resolved = TRUE, attempts = %s WHERE id = %s",
                (attempts + 1, rid),
            )
            resolved_count += 1
            log.info(
                "retry_queue resolved action=%s order_id=%s attempt=%s",
                action, order_id, attempts + 1,
            )

        except Exception as exc:
            new_attempts = attempts + 1
            backoff = _BACKOFF[min(new_attempts - 1, len(_BACKOFF) - 1)]
            execute(
                """
                UPDATE retry_queue
                SET attempts = %s,
                    last_error = %s,
                    next_retry_at = now() + (%s * INTERVAL '1 minute')
                WHERE id = %s
                """,
                (new_attempts, str(exc)[:500], backoff, rid),
            )
            log.warning(
                "retry_queue still failing action=%s order_id=%s attempt=%s error=%s",
                action, order_id, new_attempts, exc,
            )

    log.info("retry_queue run complete: %d resolved", resolved_count)
    return resolved_count
