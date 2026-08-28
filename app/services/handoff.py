"""handoff.py — Handoff resolution and read paths (REQ-prod-handoff).

Phase 5 owns handoff *resolution* and read paths only. Creating a handoff,
pausing the session, keyword/media detection, and the policy gate that
decides when a conversation needs a human belong to Phase 3
(`03-01-PLAN.md` / `03-02-PLAN.md`) and must be added there when that phase
runs, not duplicated here. This module deliberately does not define that
entry point — an empty stub that looks implemented would be worse than an
absent one.

Everything below reads/writes the `handoffs` and `sessions` tables that
already exist live (migrations `20260614000001` and `20260615000000`).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog

from app.db.database import execute, query

log = structlog.get_logger(__name__)

# How recently the bot must have replied to a customer for it to still be
# considered "active" on that conversation. This guards against a human and
# the bot overlapping on one customer, not two concurrent humans — row
# versioning / advisory locks / a distributed lock manager would be wildly
# disproportionate for a 10-30 orders/day shop.
CONFLICT_WINDOW_MINUTES = 5


def resolve(handoff_id: str, resolved_by: str) -> bool:
    """Return the conversation to the bot.

    Idempotent: returns False (and issues no writes) if the handoff does not
    exist or is already resolved, instead of corrupting state.
    """
    rows = query("SELECT id, phone, status FROM handoffs WHERE id = %s", (handoff_id,))
    if not rows or rows[0]["status"] != "active":
        return False

    phone = rows[0]["phone"]

    execute(
        "UPDATE handoffs SET status = 'resolved', resolved_at = now(), "
        "metadata = COALESCE(metadata, '{}'::jsonb) || jsonb_build_object('resolved_by', %s) "
        "WHERE id = %s AND status = 'active'",
        (resolved_by, handoff_id),
    )
    # The "return to bot" half — without this the bot stays muted forever.
    # A no-op UPDATE (no session row yet) is fine.
    execute("UPDATE sessions SET paused = FALSE WHERE phone = %s", (phone,))

    # Imported lazily to avoid an import cycle if a future module imports
    # this one and audit both.
    from app.services import audit

    audit.log_action(resolved_by, "handoff_resolved", {"handoff_id": handoff_id, "phone": phone})

    return True


def active_count() -> int:
    """Number of active handoffs — powers the dashboard nav badge."""
    rows = query("SELECT COUNT(*) AS count FROM handoffs WHERE status = 'active'")
    return int(rows[0]["count"]) if rows else 0


def bot_recently_active(phone: str, window_minutes: int = CONFLICT_WINDOW_MINUTES) -> dict | None:
    """Bot-vs-aunt conflict detection.

    Returns {'last_activity': iso, 'paused': bool} when the bot has written
    to chat_history for this phone within `window_minutes`, else None. A
    cheap heuristic on purpose — see CONFLICT_WINDOW_MINUTES above for why.
    """
    rows = query(
        "SELECT MAX(created_at) AS last_at FROM chat_history WHERE phone = %s AND role = 'assistant'",
        (phone,),
    )
    last_at = rows[0]["last_at"] if rows else None
    if not last_at:
        return None

    if isinstance(last_at, str):
        last_at = datetime.fromisoformat(last_at.replace("Z", "+00:00"))
    if last_at.tzinfo is None:
        last_at = last_at.replace(tzinfo=timezone.utc)

    if datetime.now(timezone.utc) - last_at > timedelta(minutes=window_minutes):
        return None

    paused_rows = query("SELECT paused FROM sessions WHERE phone = %s", (phone,))
    paused = bool(paused_rows[0]["paused"]) if paused_rows else False

    return {"last_activity": last_at.isoformat(), "paused": paused}
