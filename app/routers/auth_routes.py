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
from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

import app.services.auth as auth_service
import app.services.sessions as sessions
from app.routers.auth_deps import (
    optional_operator,
    require_admin,
    require_operator,
    require_operator_page,
)
from app.routers.ui import templates
from app.services import audit
from app.services.auth import AuthError
from app.services.config import Config
from app.services.processor import queue_text
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
        audit.log_action(email, "login_failed", {"reason": "invalid_credentials"})
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
            audit.log_action(result.email, "login_success", {"new_device": False})
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
    audit.log_action(result.email, "login_success", {"new_device": False})
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
        audit.log_action(pending["email"], "login_failed", {"reason": "invalid_totp"})
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
    audit.log_action(pending["email"], "login_success", {"new_device": created})

    if created and Config.ADMIN_PHONE:
        # Admin only — CONTEXT: "the aunt is not bothered" by her own
        # new-device logins. queue_text is the durable outbox (never a
        # direct sender), and a notification failure must never block the
        # login it's reporting on.
        try:
            ua = (request.headers.get("user-agent") or "غير معروف")[:80]
            when = datetime.now().strftime("%Y-%m-%d %H:%M")
            queue_text(
                Config.ADMIN_PHONE,
                f"🔐 تسجيل دخول من جهاز جديد\nالحساب: {pending['email']}\n"
                f"الجهاز: {ua}\nالوقت: {when}",
            )
        except Exception:
            logger.warning("new_device_admin_alert_failed", exc_info=True)

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


# ---------------------------------------------------------------------------
# Account — TOTP MFA enrollment (REQ-prod-auth-mfa)
#
# Assisted, never forced (CONTEXT): the QR/secret are shown only during this
# explicit flow, and nothing anywhere redirects an un-enrolled operator into
# it — see docs/OPERATOR_ACCOUNTS.md's "Assisted TOTP enrollment" section.
# ---------------------------------------------------------------------------

@router.post("/account/mfa/enroll")
async def account_mfa_enroll_start(
    password: str = Form(...), op: Operator = Depends(require_operator)
):
    """Re-authenticates with the operator's CURRENT password to obtain a fresh
    AAL1 Supabase access/refresh token pair. The opaque dashboard session
    deliberately discards Supabase's own tokens after login (the opaque
    session is the sole source of truth — see app/services/sessions.py's
    module docstring), so enroll_totp() has nothing live to use unless a
    fresh pair is minted here. Re-asking for the password immediately before
    a credential change (adding an MFA factor) is correct security practice
    on its own merits, and it avoids the alternative of holding a live
    Supabase token pair in the session store for the full 30-day life of a
    dashboard session just in case she enrolls."""
    try:
        result = auth_service.sign_in(op.email, password)
    except AuthError:
        return JSONResponse({"detail": "كلمة المرور غير صحيحة"}, status_code=401)

    try:
        enrollment = auth_service.enroll_totp(result.access_token, result.refresh_token)
    except AuthError:
        return JSONResponse({"detail": "تعذّر بدء التفعيل، حاولي مرة أخرى"}, status_code=400)

    # Reuse the same single-use, 5-minute pending-login bridge the login flow
    # uses (app/services/sessions.py's pending_logins table) rather than
    # inventing a second one.
    pending_token = sessions.create_pending_login(
        op.user_id,
        op.email,
        op.is_admin,
        enrollment["factor_id"],
        result.access_token,
        result.refresh_token,
    )
    resp = JSONResponse(
        {
            "factor_id": enrollment["factor_id"],
            "qr_code": enrollment["qr_code"],
            "secret": enrollment["secret"],
        }
    )
    _set_pending_cookie(resp, pending_token)
    return resp


@router.post("/account/mfa/enroll/verify")
async def account_mfa_enroll_verify(request: Request, op: Operator = Depends(require_operator)):
    body = await request.json()
    code = str((body or {}).get("code") or "")

    pending_token = request.cookies.get(PENDING_LOGIN_COOKIE_NAME)
    pending = sessions.consume_pending_login(pending_token)
    if pending is None or pending["user_id"] != op.user_id:
        # Expired/replayed, or (defensively) a pending row that isn't hers —
        # same "verify ownership before acting" discipline applied to
        # session revocation below.
        return JSONResponse(
            {"detail": "انتهت صلاحية الجلسة، ابدئي التفعيل من جديد"}, status_code=400
        )

    try:
        auth_service.verify_enrollment(
            pending["access_token"], pending["refresh_token"], pending["factor_id"], code
        )
    except AuthError:
        # Bad code: do NOT revoke anything.
        return JSONResponse({"detail": "الرمز غير صحيح، حاولي مرة أخرى"}, status_code=400)

    # CONTEXT: any credential change revokes ALL sessions — except this one,
    # so she isn't thrown out mid-enrollment.
    sessions.revoke_all_for_user(op.user_id, except_session_id=op.session_id)
    device_token = request.cookies.get(DEVICE_COOKIE_NAME) or sessions.mint_token()
    sessions.remember_device(op.user_id, device_token, label=request.headers.get("user-agent"))
    audit.log_action(op.email, "mfa_enrolled", {})

    resp = JSONResponse({"ok": True})
    resp.delete_cookie(PENDING_LOGIN_COOKIE_NAME)
    resp.set_cookie(
        DEVICE_COOKIE_NAME,
        device_token,
        httponly=True,
        samesite="lax",
        secure=not Config.USE_MOCK_WHATSAPP,
        max_age=DEVICE_COOKIE_TTL_DAYS * 86400,
    )
    return resp


@router.get("/account/mfa/status")
async def account_mfa_status(op: Operator = Depends(require_operator)):
    try:
        factors = auth_service.admin_list_factors(op.user_id)
    except AuthError:
        factors = []
    verified = [f for f in factors if f.get("status") == "verified"]
    return {"enrolled": bool(verified), "factors": len(verified)}


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
