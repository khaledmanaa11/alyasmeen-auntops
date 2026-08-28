"""handoff.py — Handoff resolution AND creation (REQ-prod-handoff).

Phase 5 built handoff *resolution* and read paths: resolve(), active_count(),
bot_recently_active(), and the operator UI that consumes them
(`app/routers/operator_api.py`, `app/templates/handoffs.html`). This
module's docstring used to say the *creation* half — trigger(), pausing the
session on open, and the aunt notification — belonged to Phase 3
(`03-01-PLAN.md`) and would be added here when that phase ran. That phase is
this one: `trigger()` below is that entry point, added by 03-01. Keyword/
media detection and the deterministic policy gate that decide *when* to call
`trigger()` are separate concerns living in the message pipeline
(`app/services/processor.py`, plans 03-04/03-05) — this module only owns the
durable state transition and the notification, not the decision to fire it.

Everything below reads/writes the `handoffs` and `sessions` tables that
already exist live (migrations `20260614000001` and `20260615000000`).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog

from app.db.database import execute, execute_returning, query
from app.services.config import Config

log = structlog.get_logger(__name__)

# How recently the bot must have replied to a customer for it to still be
# considered "active" on that conversation. This guards against a human and
# the bot overlapping on one customer, not two concurrent humans — row
# versioning / advisory locks / a distributed lock manager would be wildly
# disproportionate for a 10-30 orders/day shop.
CONFLICT_WINDOW_MINUTES = 5

# Reason codes trigger() accepts, mapped to the plain-Arabic sentence the aunt
# reads in her WhatsApp alert. Callers must pass one of these keys — a
# free-text reason would end up rendered raw in her inbox.
REASON_LABELS = {
    "keyword_request":   "طلبت التحدث مع شخص",
    "unsupported_media": "أرسلت رسالة صوتية أو صورة أو ملصق",
    "ai_failure":        "خلل تقني في المساعد الذكي",
    "ai_requested":      "المساعد حوّل المحادثة",
    "policy_denied":     "طلب لا يستطيع البوت تنفيذه",
    "operator_takeover": "تدخّل يدوي من لوحة التحكم",
}


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


def trigger(phone: str, reason: str, metadata: dict | None = None,
            assigned_to: str = "aunt", notify: bool = True) -> str:
    """Open (or reuse) an active handoff for `phone` and pause the bot.

    Durable and idempotent per phone: a second call for a phone that already
    has an active handoff does not open a second row, write a second audit
    entry, or re-notify the aunt — it just re-asserts the session pause and
    returns the existing handoff id. There is no unique constraint stopping
    duplicate active `handoffs` rows (`idx_handoffs_status` is a plain
    partial index), so this function is the only thing preventing an alert
    storm when a customer sends several handoff-worthy messages in a row.

    Callers must have already upserted the customer row for `phone` —
    `handoffs.phone` has a live FK to `customers(phone)`. Every call site in
    the message pipeline already does this via `upsert_customer()` before
    any handoff-worthy code runs.

    `reason` should be one of REASON_LABELS' keys; it is rendered verbatim
    (in Arabic, via REASON_LABELS.get(reason, reason)) in the aunt's
    WhatsApp alert and stored as-is on the handoff row and in the audit
    entry.

    Error contract: the durable state transition — the idempotency check,
    the INSERT, and the sessions.paused upsert — is allowed to RAISE.
    `app/db/database.py` already retries reads and circuit-breaks failures
    for these calls, and a handoff nobody can see is worse than a loud
    failure. The audit write and the aunt notification are best-effort and
    never raise past this function. Callers in the message pipeline (plans
    03-04, 03-05) are responsible for wrapping the call to `trigger()` itself
    so a customer still gets a reply if the durable write fails.

    Returns the handoff id (existing or newly created).
    """
    existing = query(
        "SELECT id FROM handoffs WHERE phone = %s AND status = 'active' "
        "ORDER BY created_at DESC LIMIT 1",
        (phone,),
    )
    if existing:
        handoff_id = existing[0]["id"]
        # Self-heal: re-assert the pause in case it was lost, but do not
        # insert a second row, write a second audit entry, or re-notify.
        _pause_session(phone)
        log.info("handoff_already_active", phone=phone, handoff_id=handoff_id, reason=reason)
        return handoff_id

    row = execute_returning(
        "INSERT INTO handoffs (phone, reason, status, assigned_to, metadata) "
        "VALUES (%s, %s, 'active', %s, %s) RETURNING id",
        (phone, reason, assigned_to, metadata or {}),
    )
    handoff_id = row["id"]

    _pause_session(phone)

    try:
        # Lazy import: same cycle-avoidance pattern resolve() already uses.
        from app.services import audit

        audit.log_action("bot", "handoff_triggered", {
            "handoff_id": handoff_id, "phone": phone, "reason": reason,
        })
    except Exception as exc:  # noqa: BLE001 — best-effort, must not undo the handoff
        log.warning("handoff_audit_failed", phone=phone, handoff_id=handoff_id, error=str(exc))

    if notify:
        _notify_aunt(phone, reason, handoff_id)

    return handoff_id


def _pause_session(phone: str) -> None:
    """Upsert sessions.paused = TRUE for `phone`.

    An UPSERT, not an UPDATE: resolve() can use a bare UPDATE because a
    session row provably exists by the time a handoff is resolved. trigger()
    cannot — the very first message from a brand-new customer may be a voice
    note (an unsupported-media handoff), which reaches here before
    save_session() has ever run for that phone. A bare UPDATE would silently
    no-op and the bot would keep replying to a customer it had just "handed
    off".
    """
    execute(
        "INSERT INTO sessions (phone, paused) VALUES (%s, TRUE) "
        "ON CONFLICT (phone) DO UPDATE SET paused = TRUE, updated_at = now()",
        (phone,),
    )


def _notify_aunt(phone: str, reason: str, handoff_id: str) -> None:
    """Best-effort WhatsApp alert to AUNT_PHONE via the durable outbox.

    Modeled directly on processor.notify_permanent_failure() — the
    established, battle-tested shape for "the bot proactively WhatsApps the
    aunt". Wrapped end-to-end in try/except: a failing notification must
    never undo the handoff that already succeeded.
    """
    try:
        # Loop guard (mandatory, same as notify_permanent_failure): handing
        # off a conversation with the aunt's/admin's own number and then
        # WhatsApping them about it would be an outbox loop.
        if phone and phone in (Config.AUNT_PHONE, Config.ADMIN_PHONE):
            return
        if not Config.AUNT_PHONE:
            return

        rows = query("SELECT name FROM customers WHERE phone = %s", (phone,))
        customer_name = (rows[0].get("name") or "") if rows else ""
        name_label = customer_name or phone

        reason_label = REASON_LABELS.get(reason, reason)
        msg = (
            f"🙋 {reason_label} — {name_label}\n"
            "افتحي تبويب «محادثات» بلوحة التحكم للرد، ولما تخلصي اضغطي «أعد للبوت».\n"
            f"https://wa.me/{phone.lstrip('+')}"
        )

        # Lazy import: from plan 03-04 onward processor imports handoff, so a
        # module-level import here would be a circular import. Never call
        # send_text directly — queue_text is the durable outbox and the only
        # sanctioned send path from the message pipeline.
        from app.services import processor

        processor.queue_text(Config.AUNT_PHONE, msg)
    except Exception as exc:  # noqa: BLE001 — best-effort, must not undo the handoff
        log.warning("handoff_notify_failed", phone=phone, handoff_id=handoff_id, error=str(exc))
