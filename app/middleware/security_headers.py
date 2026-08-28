"""
security_headers.py — SecurityHeadersMiddleware (REQ-prod-sec-headers).

Sets a fixed set of security headers on every response: Content-Security-
Policy, X-Content-Type-Options, X-Frame-Options, Referrer-Policy and
Permissions-Policy always; Strict-Transport-Security only in production
mode (never sent from a local http dev server).

Two things below look like mistakes and are not — read the comments before
"fixing" either:

1. `'unsafe-inline'` + `'unsafe-eval'` in script-src are deliberate. The
   dashboard loads Tailwind via the Play CDN, which injects unnonced
   <style> tags at runtime, and Alpine.js core evaluates x-data/x-on
   expressions through `new Function()`. A nonce-only, no-unsafe policy
   silently breaks the entire dashboard (Tailwind classes stop applying,
   Alpine throws "Refused to evaluate a string as JavaScript"). Tightening
   this requires precompiling Tailwind and switching to Alpine's CSP
   build — a frontend-build migration that is explicitly out of this
   phase's scope (tracked as follow-up debt in 05-04-SUMMARY.md).
2. The nonce is generated and exposed on request.state.csp_nonce but is
   intentionally not yet required by the policy (no 'nonce-...' in
   script-src), so a future strict CSP is a config change here rather
   than a re-plumb of every template.

Do NOT add HTTPSRedirectMiddleware and do NOT branch on request.url.scheme:
the Procfile runs uvicorn without --proxy-headers, so behind Railway's
TLS-terminating edge the scheme reads http and a redirect middleware would
loop forever. Setting the HSTS header with no redirect sidesteps this.
"""
from __future__ import annotations

import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.services.config import Config

CSP_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com "
    "https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: https:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "object-src 'none'; "
    "upgrade-insecure-requests"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        nonce = secrets.token_urlsafe(16)
        request.state.csp_nonce = nonce

        response = await call_next(request)

        response.headers["Content-Security-Policy"] = CSP_POLICY
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        if not Config.USE_MOCK_WHATSAPP:
            response.headers["Strict-Transport-Security"] = (
                "max-age=15552000; includeSubDomains"
            )

        return response
