"""
auth_deps.py — FastAPI auth dependencies for the operator dashboard
(REQ-prod-auth-mfa, REQ-prod-session-opaque).

Replaces the old scheme — every router hand-computing a deterministic hash of
the shared dashboard password and comparing it against the `alyasmeen_session`
cookie — with a single lookup against 05-01's opaque `operator_sessions`
store. There is exactly one place that resolves a cookie to an identity
(`_current`); everything else in this module composes it.

Usage:
  - JSON API routers (ui_api.py, broadcast.py): router-level
    `dependencies=[Depends(require_operator)]` — unauthenticated request gets
    a 401.
  - HTML page router (ui.py): router-level
    `dependencies=[Depends(require_operator_page)]` — unauthenticated request
    gets a 303 redirect to /login instead of a raw 401 (a browser navigating
    to a page should land somewhere useful, not see a bare error).
  - GET /login (auth_routes.py): `optional_operator` — never raises; used to
    redirect an ALREADY-signed-in operator to /orders instead of showing the
    login form again.
  - Admin-only endpoints (05-09): `Depends(require_admin)` — 403 when the
    signed-in operator's account is not flagged admin.

A handler that needs the identity itself (e.g. for audit logging) simply
adds `op: Operator = Depends(require_operator)` to its own signature —
FastAPI caches a dependency's result per request, so declaring it a second
time (once implicitly via the router-level `dependencies=[...]`, once
explicitly in a handler's own signature) does not re-query the session
store.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from app.services.sessions import Operator, lookup_session
from app.shared.constants import SESSION_COOKIE_NAME


def _current(request: Request) -> Operator | None:
    """Resolve the live Operator behind this request's session cookie, or
    None if the cookie is missing, unknown, revoked, or expired."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    return lookup_session(token) if token else None


def optional_operator(request: Request) -> Operator | None:
    """Never raises. For routes that behave differently when signed in vs.
    signed out (today: only GET /login) rather than requiring auth."""
    return _current(request)


def require_operator(request: Request) -> Operator:
    """JSON API guard — 401 when there is no live session."""
    op = _current(request)
    if op is None:
        raise HTTPException(status_code=401)
    return op


def require_operator_page(request: Request) -> Operator:
    """HTML page guard — 303 redirect to /login when there is no live
    session, so an unauthenticated browser visit lands somewhere useful."""
    op = _current(request)
    if op is None:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return op


def require_admin(op: Operator = Depends(require_operator)) -> Operator:
    """Admin-only guard — 403 when the signed-in operator's account is not
    flagged admin. Composes on top of require_operator, so an unauthenticated
    request still 401s rather than 403ing."""
    if not op.is_admin:
        raise HTTPException(status_code=403)
    return op
