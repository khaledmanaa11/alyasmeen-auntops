"""
app/services/auth.py — Supabase Auth wrapper.

This is the ONLY module in this codebase allowed to import `supabase` for identity
purposes (app/db/database.py owns the separate, unrelated data-access client). It wraps
password sign-in, TOTP MFA enrollment/verification, admin factor management, admin user
creation/listing, and password-reset email dispatch.

CRITICAL — read before calling sign_in() anywhere:
`sign_in_with_password` succeeds and returns a full session EVEN WHEN the user has a
verified TOTP factor; Supabase only *elevates* the AAL on successful MFA verification, it
never *blocks* the initial password grant. sign_in() therefore always follows the password
grant with an authenticator-assurance-level check and reports the result via
AuthResult.mfa_required. sign_in() must NEVER be treated by callers as "the operator is
logged in" — it returns a *result*, not a session. Only after mfa_required is confirmed
False (either no MFA enrolled, or verify_totp() has separately succeeded) may the caller
(05-03's route layer) mint an app-owned opaque session. Skipping this check makes MFA
silently decorative.

Never implement TOTP generation or verification here (no pyotp, ever) — Supabase Auth is
the system of record for which factors exist and are verified. A parallel implementation
would immediately desync from what auth.mfa.list_factors() reports as enrolled.

Every Supabase call below is wrapped in try/except and re-raised as AuthError so callers
never need to import supabase_auth's exception types directly. Failures are logged with
the module logger, but the password, the TOTP code, the access token and the TOTP secret
are NEVER logged — only the provider's own error message/code.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from supabase import create_client

from app.services.config import Config

logger = logging.getLogger(__name__)


class AuthError(Exception):
    """Raised for any Supabase Auth failure. Wraps the underlying provider exception's
    message and, when available, its error `code` (e.g. "over_email_send_rate_limit",
    "mfa_verification_failed") so callers can special-case specific failures without
    importing supabase_auth's exception types directly."""

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class AuthResult:
    """Result of a password sign-in attempt. NOT a login — see module docstring.

    mfa_required is True only when the account has a verified TOTP factor AND the
    session has not yet reached AAL2 in this request. Callers must gate app-session
    creation on this being False (either directly, or after a subsequent verify_totp()
    call succeeds).
    """

    user_id: str
    email: str
    is_admin: bool
    mfa_required: bool
    factor_id: str | None
    access_token: str
    refresh_token: str


def _anon_client():
    """Fresh client for the non-admin identity surface (sign-in, MFA, password reset).
    Uses SUPABASE_ANON_KEY — never SUPABASE_KEY — so this surface behaves exactly as it
    would if a browser called it directly, even though nothing in this app ever does.
    A fresh client is built per call rather than shared/cached: these are short-lived,
    request-scoped operations, and a shared client would carry one operator's session
    state into another operator's request."""
    return create_client(Config.SUPABASE_URL, Config.SUPABASE_ANON_KEY)


def _admin_client():
    """Fresh client for admin-only identity operations (user creation, factor listing/
    deletion, listing users). Uses SUPABASE_KEY (service_role) — this client's calls must
    never be reachable from anything a browser could trigger directly."""
    return create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)


def _to_auth_error(exc: Exception) -> AuthError:
    code = getattr(exc, "code", None)
    message = str(exc) or exc.__class__.__name__
    logger.warning("Supabase Auth call failed: %s (code=%s)", message, code)
    return AuthError(message, code=code)


def _is_admin(user) -> bool:
    app_metadata = getattr(user, "app_metadata", None) or {}
    return app_metadata.get("role") == "admin"


def sign_in(email: str, password: str) -> AuthResult:
    """Password sign-in. Always performs the AAL check — see module docstring. Returns a
    result the caller must inspect (mfa_required) before treating the operator as
    authenticated; never mints or implies an app session on its own."""
    client = _anon_client()
    try:
        resp = client.auth.sign_in_with_password({"email": email, "password": password})
    except Exception as exc:  # noqa: BLE001 — re-raised as AuthError below
        raise _to_auth_error(exc) from exc

    session = resp.session
    user = resp.user
    if session is None or user is None:
        raise AuthError("Sign-in did not return a session")

    try:
        aal = client.auth.mfa.get_authenticator_assurance_level()
        factors = client.auth.mfa.list_factors()
    except Exception as exc:  # noqa: BLE001
        raise _to_auth_error(exc) from exc

    verified_totp = factors.totp  # already filtered to factor_type == "totp", status == "verified"
    mfa_required = bool(verified_totp) and aal.current_level != aal.next_level
    factor_id = verified_totp[0].id if mfa_required else None

    return AuthResult(
        user_id=user.id,
        email=user.email or email,
        is_admin=_is_admin(user),
        mfa_required=mfa_required,
        factor_id=factor_id,
        access_token=session.access_token,
        refresh_token=session.refresh_token,
    )


def verify_totp(access_token: str, refresh_token: str, factor_id: str, code: str) -> str:
    """Completes MFA verification for the AAL1 session captured by sign_in(). Rehydrates
    that session on a fresh client, then challenges and verifies the given TOTP code.
    Returns the verified user's id. The AAL2 tokens Supabase returns from this call are
    discarded — the app mints its own opaque session instead (see 05-01's session store),
    never Supabase's own JWT/refresh-token pair."""
    client = _anon_client()
    try:
        client.auth.set_session(access_token, refresh_token)
        result = client.auth.mfa.challenge_and_verify({"factor_id": factor_id, "code": code})
    except Exception as exc:  # noqa: BLE001
        raise _to_auth_error(exc) from exc
    return result.user.id


def enroll_totp(access_token: str, refresh_token: str) -> dict:
    """Starts TOTP enrollment for the currently-authenticated operator (AAL1 is enough —
    there is nothing to challenge yet). Returns {"factor_id", "qr_code", "secret"}.
    `qr_code` is already a data:image/svg+xml;utf-8,... URI usable straight in
    `<img src>` — do not re-encode it."""
    client = _anon_client()
    try:
        session_resp = client.auth.set_session(access_token, refresh_token)
        email = getattr(session_resp.user, "email", None) or "operator"
        enrolled = client.auth.mfa.enroll(
            {"factor_type": "totp", "issuer": "ALYASMEEN", "friendly_name": email}
        )
    except Exception as exc:  # noqa: BLE001
        raise _to_auth_error(exc) from exc

    totp = enrolled.totp
    return {
        "factor_id": enrolled.id,
        "qr_code": totp.qr_code if totp else None,
        "secret": totp.secret if totp else None,
    }


def verify_enrollment(access_token: str, refresh_token: str, factor_id: str, code: str) -> None:
    """Completes TOTP enrollment: the first successful verification of an unverified
    factor activates it. Per Supabase's own docs, this also logs out all of that user's
    OTHER Supabase-side sessions and elevates this one to AAL2 — that is Supabase's own
    session bookkeeping and is separate from this app's opaque operator_sessions table.
    The caller (05-09's enrollment-success handler) must still explicitly revoke this
    user's other app sessions to honor "credential change revokes all sessions"."""
    client = _anon_client()
    try:
        client.auth.set_session(access_token, refresh_token)
        client.auth.mfa.challenge_and_verify({"factor_id": factor_id, "code": code})
    except Exception as exc:  # noqa: BLE001
        raise _to_auth_error(exc) from exc


def admin_list_factors(user_id: str) -> list[dict]:
    """Lists every MFA factor (verified and unverified) attached to a user, via the
    service_role-keyed admin surface."""
    client = _admin_client()
    try:
        factors = client.auth.admin.mfa.list_factors({"user_id": user_id})
    except Exception as exc:  # noqa: BLE001
        raise _to_auth_error(exc) from exc
    return [
        {
            "id": f.id,
            "factor_type": f.factor_type,
            "status": f.status,
            "friendly_name": f.friendly_name,
        }
        for f in factors
    ]


def admin_delete_all_factors(user_id: str) -> int:
    """Deletes every MFA factor for a user (lost-phone recovery escape hatch). Returns the
    count deleted. The caller is still responsible for revoking that user's app sessions
    and reminding them to re-enroll."""
    client = _admin_client()
    try:
        factors = client.auth.admin.mfa.list_factors({"user_id": user_id})
        deleted = 0
        for f in factors:
            client.auth.admin.mfa.delete_factor({"user_id": user_id, "id": f.id})
            deleted += 1
    except Exception as exc:  # noqa: BLE001
        raise _to_auth_error(exc) from exc
    return deleted


def admin_create_user(email: str, password: str, role: str) -> str:
    """Creates an operator account with email already confirmed (she must not have to
    click a confirmation link) and `app_metadata.role` set for is_admin checks. Returns
    the new user's id."""
    client = _admin_client()
    try:
        resp = client.auth.admin.create_user(
            {
                "email": email,
                "password": password,
                "email_confirm": True,
                "app_metadata": {"role": role},
            }
        )
    except Exception as exc:  # noqa: BLE001
        raise _to_auth_error(exc) from exc
    return resp.user.id


def admin_list_users() -> list[dict]:
    """Lists every Supabase Auth user with their role and MFA-factor count, for the
    manage_operators.py `list` subcommand and any future admin UI."""
    client = _admin_client()
    try:
        users = client.auth.admin.list_users()
    except Exception as exc:  # noqa: BLE001
        raise _to_auth_error(exc) from exc
    return [
        {
            "id": u.id,
            "email": u.email,
            "role": (u.app_metadata or {}).get("role"),
            "factor_count": len(u.factors or []),
        }
        for u in users
    ]


def send_password_reset(email: str) -> None:
    """Sends a password-reset email. The installed client defaults to the PKCE flow, so
    the landing route receives a `?code=` query param that a server-rendered page can
    actually read (the implicit flow's URL fragment never reaches the server) — 05-09
    builds that landing route. Subject to Supabase's built-in 2 emails/hour project-wide
    limit; a rate-limited call surfaces here as AuthError(code="over_email_send_rate_limit")."""
    client = _anon_client()
    try:
        client.auth.reset_password_for_email(
            email, {"redirect_to": f"{Config.DASHBOARD_BASE_URL}/login/reset"}
        )
    except Exception as exc:  # noqa: BLE001
        raise _to_auth_error(exc) from exc
