"""
sessions.py — Opaque operator-session store for the Phase 5 dashboard auth
rewrite (REQ-prod-session-opaque).

Three tables (see the operator-auth migration under the project's migrations/ directory):
  operator_sessions — one row per logged-in browser/device; only a SHA-256
                       hash of the session cookie is ever stored or compared.
  trusted_devices    — 30-day "remember this device" MFA trust window.
  pending_logins     — single-use, 5-minute bridge between the password step
                       (AAL1) and the TOTP step (AAL2).

Every read/write goes through app.db.database's query/execute/execute_returning
(project rule 6 — never import the DB client library directly) using %s
placeholders only (project rule 3 — no f-string interpolation of parameter
*values*; the fixed TTL constants below ARE interpolated directly into the
SQL text as literal INTERVAL durations, which is safe because they are
hardcoded ints, never user input). The raw token returned to callers is what
goes in the cookie; the database only ever sees hashlib.sha256(raw).hexdigest().
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass
from typing import Any

from app.db.database import execute, execute_returning, query
from app.shared.constants import (
    DEVICE_MFA_TTL_DAYS,
    OPAQUE_TOKEN_BYTES,
    PENDING_LOGIN_TTL_MINUTES,
    SESSION_TTL_DAYS,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Operator:
    """The authenticated operator behind a live session — what request-time
    auth dependencies get back from lookup_session()."""

    user_id: str
    email: str
    is_admin: bool
    session_id: str


def mint_token() -> str:
    """A fresh random opaque token for a cookie. Never stored raw — see _hash()."""
    return secrets.token_urlsafe(OPAQUE_TOKEN_BYTES)


def _hash(raw: str) -> str:
    """SHA-256 hex digest of a raw token. This is the only form of any token
    that ever touches the database."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _serialize(row: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    """Mirror ui_api.py's created_at handling: datetime objects (from a real
    Supabase client) become ISO strings; values already strings pass through
    untouched (as our in-memory test fakes and JSON-decoded RPC rows are)."""
    out = dict(row)
    for key in keys:
        val = out.get(key)
        if val is not None and not isinstance(val, str) and hasattr(val, "isoformat"):
            out[key] = val.isoformat()
    return out


# ---------------------------------------------------------------------------
# operator_sessions
# ---------------------------------------------------------------------------

def create_session(
    user_id: str,
    email: str,
    is_admin: bool,
    device_id: str | None = None,
    user_agent: str | None = None,
) -> str:
    """Insert a new session row and return the RAW token (goes in the cookie).

    Fixed SESSION_TTL_DAYS expiry — not sliding, no idle timeout (CONTEXT:
    "30-day session lifetime; sign in roughly monthly").
    """
    raw = mint_token()
    execute(
        "INSERT INTO operator_sessions "
        "(user_id, email, is_admin, token_hash, device_id, user_agent, expires_at) "
        f"VALUES (%s, %s, %s, %s, %s, %s, NOW() + INTERVAL '{SESSION_TTL_DAYS} days')",
        (user_id, email, is_admin, _hash(raw), device_id, user_agent),
    )
    return raw


def lookup_session(raw_token: str) -> Operator | None:
    """Resolve a cookie's raw token to the live Operator, or None if the
    token is missing/unknown/revoked/expired."""
    if not raw_token:
        return None

    rows = query(
        "SELECT id, user_id, email, is_admin FROM operator_sessions "
        "WHERE token_hash = %s AND revoked_at IS NULL AND expires_at > NOW()",
        (_hash(raw_token),),
    )
    if not rows:
        return None

    row = rows[0]
    try:
        execute(
            "UPDATE operator_sessions SET last_seen_at = NOW() WHERE id = %s",
            (row["id"],),
        )
    except Exception:
        # A failed last_seen_at write must never log the operator out.
        log.warning("sessions: failed to bump last_seen_at for session %s", row["id"])

    return Operator(
        user_id=row["user_id"],
        email=row["email"],
        is_admin=bool(row["is_admin"]),
        session_id=row["id"],
    )


def revoke_session(session_id: str) -> None:
    """Log out one specific session (e.g. this browser's 'log out' button)."""
    execute(
        "UPDATE operator_sessions SET revoked_at = NOW() "
        "WHERE id = %s AND revoked_at IS NULL",
        (session_id,),
    )


def revoke_all_for_user(user_id: str, except_session_id: str | None = None) -> None:
    """Revoke every active session for one user. Powers BOTH "log out
    everywhere" and "any credential change revokes all sessions" — the two
    CONTEXT-mandated behaviors share this one statement.

    except_session_id, when given, spares the session making the request
    (e.g. changing your own password shouldn't immediately log you out).
    """
    if except_session_id:
        execute(
            "UPDATE operator_sessions SET revoked_at = NOW() "
            "WHERE user_id = %s AND revoked_at IS NULL AND id <> %s",
            (user_id, except_session_id),
        )
    else:
        execute(
            "UPDATE operator_sessions SET revoked_at = NOW() "
            "WHERE user_id = %s AND revoked_at IS NULL",
            (user_id,),
        )


def list_sessions_for_user(user_id: str) -> list[dict[str, Any]]:
    """Active sessions for one user, newest first. Never returns token_hash."""
    rows = query(
        "SELECT id, email, user_agent, created_at, last_seen_at, expires_at "
        "FROM operator_sessions "
        "WHERE user_id = %s AND revoked_at IS NULL AND expires_at > NOW() "
        "ORDER BY created_at DESC",
        (user_id,),
    )
    return [_serialize(r, ("created_at", "last_seen_at", "expires_at")) for r in rows]


def list_active_sessions() -> list[dict[str, Any]]:
    """Every operator's active sessions — powers the admin session view."""
    rows = query(
        "SELECT id, user_id, email, is_admin, user_agent, created_at, last_seen_at, expires_at "
        "FROM operator_sessions "
        "WHERE revoked_at IS NULL AND expires_at > NOW() "
        "ORDER BY created_at DESC"
    )
    return [_serialize(r, ("created_at", "last_seen_at", "expires_at")) for r in rows]


# ---------------------------------------------------------------------------
# trusted_devices — 30-day MFA remember-device
# ---------------------------------------------------------------------------

def find_trusted_device(user_id: str, raw_device_token: str | None) -> dict[str, Any] | None:
    """Return the trusted_devices row only while still inside its MFA trust
    window; None otherwise (unknown device, expired trust, or no token)."""
    if not raw_device_token:
        return None

    rows = query(
        "SELECT id, user_id, mfa_verified_until, label FROM trusted_devices "
        "WHERE user_id = %s AND device_token_hash = %s AND mfa_verified_until > NOW()",
        (user_id, _hash(raw_device_token)),
    )
    return rows[0] if rows else None


def remember_device(
    user_id: str, raw_device_token: str, label: str | None = None
) -> tuple[str, bool]:
    """Upsert the (user_id, device) trust row, refreshing the 30-day window.

    Returns (device_id, created) where created=True ONLY the first time this
    device is seen for this user — 05-09 uses that flag to fire the
    new-device WhatsApp alert to the admin.
    """
    row = execute_returning(
        "INSERT INTO trusted_devices "
        "(user_id, device_token_hash, label, mfa_verified_until, last_seen_at) "
        f"VALUES (%s, %s, %s, NOW() + INTERVAL '{DEVICE_MFA_TTL_DAYS} days', NOW()) "
        "ON CONFLICT (user_id, device_token_hash) DO UPDATE SET "
        "mfa_verified_until = EXCLUDED.mfa_verified_until, last_seen_at = NOW() "
        "RETURNING id, (xmax = 0) AS created",
        (user_id, _hash(raw_device_token), label),
    )
    if row is None:
        raise RuntimeError("remember_device: upsert returned no row")
    return row["id"], bool(row["created"])


# ---------------------------------------------------------------------------
# pending_logins — password-step -> TOTP-step bridge
# ---------------------------------------------------------------------------

def create_pending_login(
    user_id: str,
    email: str,
    is_admin: bool,
    factor_id: str,
    access_token: str,
    refresh_token: str,
) -> str:
    """Stash the AAL1 Supabase tokens server-side and return a RAW bridge
    token (goes in a short-lived cookie) for the TOTP step to redeem."""
    raw = mint_token()
    execute(
        "INSERT INTO pending_logins "
        "(token_hash, user_id, email, is_admin, factor_id, access_token, refresh_token, expires_at) "
        f"VALUES (%s, %s, %s, %s, %s, %s, %s, NOW() + INTERVAL '{PENDING_LOGIN_TTL_MINUTES} minutes')",
        (_hash(raw), user_id, email, is_admin, factor_id, access_token, refresh_token),
    )
    return raw


def consume_pending_login(raw_token: str) -> dict[str, Any] | None:
    """Single-use read: return the unexpired row, then delete it. A second
    call with the same token returns None."""
    if not raw_token:
        return None

    token_hash = _hash(raw_token)
    rows = query(
        "SELECT id, user_id, email, is_admin, factor_id, access_token, refresh_token "
        "FROM pending_logins WHERE token_hash = %s AND expires_at > NOW()",
        (token_hash,),
    )
    if not rows:
        return None

    execute("DELETE FROM pending_logins WHERE token_hash = %s", (token_hash,))
    return rows[0]


def purge_expired() -> None:
    """Housekeeping: delete pending_logins rows past their 5-minute window
    (abandoned MFA attempts)."""
    execute("DELETE FROM pending_logins WHERE expires_at <= NOW()")
