"""audit.py — Operator action audit trail (REQ-prod-handoff).

Writes over the existing `audit_logs` table (`id, actor, action,
details JSONB, created_at`) — no migration needed. Writes are best-effort:
an audit write failing must never break the operator action it is
recording, so losing one trail row is strictly better than a 500 on a
status change.

Reads are filtered to OPERATOR_ACTIONS. `audit_logs` predates this phase and
already carries rows written by the `create_order_atomic` database function
where `actor` is a customer's phone number (e.g. action='order_created') —
showing those in the operator trail would mix customer activity into "who
did what". The read side filters on `action`, never on the shape of
`actor`.
"""
from __future__ import annotations

import structlog

from app.db.database import execute, query

log = structlog.get_logger(__name__)

OPERATOR_ACTIONS = (
    "login_success", "login_failed", "logout", "logout_all",
    "session_revoked", "mfa_enrolled", "mfa_reset", "password_reset_requested",
    "password_reset_completed",
    "order_status_changed", "order_status_conflict_override",
    "product_created", "product_updated", "product_toggled", "product_deleted",
    "broadcast_sent", "handoff_resolved",
    "alert_retried", "alert_retry_all",
)


def log_action(actor: str, action: str, details: dict | None = None) -> None:
    """Best-effort audit write. Never raises: the caller's real work (a
    status change, a resolve, a login) must succeed even if this fails."""
    if action not in OPERATOR_ACTIONS:
        # Still write it — the allowlist governs the read side
        # (list_operator_actions), not what may be recorded.
        log.warning("audit_action_not_in_allowlist", action=action)

    try:
        execute(
            "INSERT INTO audit_logs (actor, action, details) VALUES (%s, %s, %s)",
            (actor, action, details or {}),
        )
    except Exception as exc:  # noqa: BLE001 — best-effort by design
        log.warning("audit_log_write_failed", actor=actor, action=action, error=str(exc))


def list_operator_actions(limit: int = 200) -> list[dict]:
    """Chronological (newest-first) trail of operator actions only."""
    # The f-string below interpolates only a placeholder string built from
    # OPERATOR_ACTIONS, a fixed module constant — never from user input — so
    # this is not the SQL-injection pattern project rule 3 forbids.
    placeholders = ", ".join(["%s"] * len(OPERATOR_ACTIONS))
    sql = (
        f"SELECT id, actor, action, details, created_at FROM audit_logs "
        f"WHERE action IN ({placeholders}) ORDER BY created_at DESC LIMIT %s"
    )
    rows = query(sql, (*OPERATOR_ACTIONS, limit))
    for row in rows:
        if row.get("created_at") and not isinstance(row["created_at"], str):
            row["created_at"] = row["created_at"].isoformat()
    return rows
