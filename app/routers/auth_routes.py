"""
auth_routes.py — Email+password login, TOTP MFA challenge, and logout for
the ALYASMEEN operator dashboard (REQ-prod-auth-mfa, REQ-prod-session-opaque,
REQ-dash-login).

Deliberately NO router-level guard: these routes must stay reachable while
signed out (that is the whole point of a login flow). Each route pulls in
only the auth_deps dependency it actually needs — optional_operator for
GET /login (must special-case an already-signed-in visitor), require_operator
for the two routes that DO require an existing session.

A dashboard session cookie is minted in exactly two places in this module —
both only after identity is fully established:
  - login_submit(), when sign_in() reports mfa_required=False (no verified
    TOTP factor yet, or the browser presents a still-trusted device cookie)
  - login_mfa_submit(), immediately after verify_totp() succeeds

Every other path — bad credentials, MFA required with no trusted device,
wrong TOTP code — deliberately never sets or refreshes the session cookie.
`sign_in()` alone is NEVER sufficient to authenticate a request; see
app/services/auth.py's module docstring for why.

`auth_service` and `sessions` are imported as module references (not
`from ... import name`) specifically so tests can monkeypatch
`app.routers.auth_routes.auth_service` / `app.routers.auth_routes.sessions`
wholesale with fakes, without touching the real Supabase-backed modules —
see tests/conftest.py's module docstring for the same pattern applied to the
DB/WhatsApp seams. `AuthError` is imported directly and kept stable so a
fake `auth_service`'s functions can raise the real exception type without
also needing to carry their own `.AuthError` attribute.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

import app.services.auth as auth_service
import app.services.sessions as sessions
from app.routers.auth_deps import optional_operator, require_operator
from app.routers.ui import templates
from app.services.auth import AuthError
from app.services.config import Config
from app.services.sessions import Operator
from app.shared.constants import (
    DEVICE_COOKIE_NAME,
    DEVICE_COOKIE_TTL_DAYS,
    PENDING_LOGIN_COOKIE_NAME,
    PENDING_LOGIN_TTL_MINUTES,
    SESSION_COOKIE_NAME,
    SESSION_TTL_DAYS,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])


def _set_pending_cookie(resp, raw_token: str) -> None:
    resp.set_cookie(
        PENDING_LOGIN_COOKIE_NAME,
        raw_token,
        httponly=True,
        samesite="lax",
        secure=not Config.USE_MOCK_WHATSAPP,
        max_age=PENDING_LOGIN_TTL_MINUTES * 60,
    )


def _mint_session_response(
    user_id: str, email: str, is_admin: bool, device_id: str | None = None
) -> RedirectResponse:
    """Mint an opaque dashboard session and 303 to /orders. The pending-login
    cookie (if any) is always cleared here too — harmless no-op when it was
    never set (the no-MFA-enrolled path)."""
    raw = sessions.create_session(user_id, email, is_admin, device_id=device_id)
    resp = RedirectResponse(url="/orders", status_code=303)
    resp.set_cookie(
        SESSION_COOKIE_NAME,
        raw,
        httponly=True,
        samesite="lax",
        secure=not Config.USE_MOCK_WHATSAPP,
        max_age=SESSION_TTL_DAYS * 86400,
    )
    resp.delete_cookie(PENDING_LOGIN_COOKIE_NAME)
    return resp


@router.get("/login")
async def login_page(request: Request, op: Operator | None = Depends(optional_operator)):
    if op is not None:
        return RedirectResponse(url="/orders", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
async def login_submit(request: Request, email: str = Form(...), password: str = Form(...)):
    try:
        result = auth_service.sign_in(email, password)
    except AuthError:
        # Never reveal whether the email exists — one generic message for
        # both "no such account" and "wrong password".
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "البريد الإلكتروني أو كلمة المرور غير صحيحة"},
            status_code=401,
        )

    if result.mfa_required:
        device = sessions.find_trusted_device(
            result.user_id, request.cookies.get(DEVICE_COOKIE_NAME)
        )
        if device is not None:
            # Remember-device satisfies the TOTP requirement for this login.
            return _mint_session_response(
                result.user_id, result.email, result.is_admin, device_id=device["id"]
            )

        # Bridge the AAL1 tokens to the TOTP step. Do NOT mint a dashboard
        # session on this path — this is the check that stops MFA from being
        # decorative: a successful password grant alone only reaches AAL1.
        token = sessions.create_pending_login(
            result.user_id,
            result.email,
            result.is_admin,
            result.factor_id,
            result.access_token,
            result.refresh_token,
        )
        resp = templates.TemplateResponse(request, "mfa_challenge.html", {"error": None})
        _set_pending_cookie(resp, token)
        return resp

    # No verified factor enrolled yet. CONTEXT locks enrollment as assisted,
    # not a forced self-serve wall, so a not-yet-enrolled operator must still
    # be able to sign in (the dashboard nags for enrollment separately).
    logger.warning("login_without_mfa email=%s", result.email)
    return _mint_session_response(result.user_id, result.email, result.is_admin)


@router.post("/login/mfa")
async def login_mfa_submit(request: Request, code: str = Form(...)):
    pending_token = request.cookies.get(PENDING_LOGIN_COOKIE_NAME)
    pending = sessions.consume_pending_login(pending_token)
    if pending is None:
        # Expired or already-consumed (replayed) pending login.
        return RedirectResponse(url="/login", status_code=303)

    try:
        auth_service.verify_totp(
            pending["access_token"],
            pending["refresh_token"],
            pending["factor_id"],
            code,
        )
    except AuthError:
        # Give her another attempt without re-entering the password:
        # consume_pending_login() already deleted the single-use row above,
        # so re-issue a fresh one (and a fresh cookie) rather than dead-end.
        new_token = sessions.create_pending_login(
            pending["user_id"],
            pending["email"],
            pending["is_admin"],
            pending["factor_id"],
            pending["access_token"],
            pending["refresh_token"],
        )
        resp = templates.TemplateResponse(
            request,
            "mfa_challenge.html",
            {"error": "الرمز غير صحيح، جرّبي مرة أخرى"},
            status_code=401,
        )
        _set_pending_cookie(resp, new_token)
        return resp

    device_token = request.cookies.get(DEVICE_COOKIE_NAME) or sessions.mint_token()
    device_id, created = sessions.remember_device(
        pending["user_id"], device_token, label=request.headers.get("user-agent")
    )
    request.state.new_device = created
    # 05-09 fires the admin WhatsApp alert here

    resp = _mint_session_response(
        pending["user_id"], pending["email"], pending["is_admin"], device_id=device_id
    )
    resp.set_cookie(
        DEVICE_COOKIE_NAME,
        device_token,
        httponly=True,
        samesite="lax",
        secure=not Config.USE_MOCK_WHATSAPP,
        max_age=DEVICE_COOKIE_TTL_DAYS * 86400,
    )
    return resp


@router.get("/logout")
async def logout(op: Operator | None = Depends(optional_operator)):
    """Revoke only THIS session — the device cookie is kept (multi-device is
    intentional: logging out on the laptop must not sign out the phone)."""
    if op is not None:
        sessions.revoke_session(op.session_id)
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE_NAME)
    return resp


@router.post("/logout-all")
async def logout_all(op: Operator = Depends(require_operator)):
    """Log out everywhere — revokes every active session for this operator."""
    sessions.revoke_all_for_user(op.user_id)
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE_NAME)
    return resp
