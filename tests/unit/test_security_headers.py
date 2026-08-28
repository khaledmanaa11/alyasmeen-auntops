"""
test_security_headers.py — Unit tests for app.middleware.security_headers
(REQ-prod-sec-headers).

Uses the shared `client` fixture (tests/conftest.py) for the header-presence
assertions against a real route, and a direct `SecurityHeadersMiddleware.
dispatch()` call (no HTTP round trip, no permanent debug route) for the
request.state.csp_nonce assertion.
"""
from __future__ import annotations

import asyncio

from starlette.requests import Request
from starlette.responses import PlainTextResponse

from app.middleware import security_headers as security_headers_module
from app.middleware.security_headers import SecurityHeadersMiddleware

ALWAYS_ON_HEADERS = [
    "content-security-policy",
    "x-content-type-options",
    "x-frame-options",
    "referrer-policy",
    "permissions-policy",
]


class TestAlwaysOnHeaders:
    def test_login_response_carries_all_five_headers(self, client):
        r = client.get("/login")
        for header in ALWAYS_ON_HEADERS:
            assert header in r.headers, f"missing header: {header}"


class TestCSPContent:
    def test_csp_contains_expected_directives(self, client):
        r = client.get("/login")
        csp = r.headers["content-security-policy"]
        assert "frame-ancestors 'none'" in csp
        assert "object-src 'none'" in csp
        assert "cdn.tailwindcss.com" in csp


class TestHSTSModeGating:
    def test_no_hsts_header_when_mock_whatsapp_truthy(self, client, monkeypatch):
        monkeypatch.setattr(security_headers_module.Config, "USE_MOCK_WHATSAPP", True)
        r = client.get("/login")
        assert "strict-transport-security" not in r.headers

    def test_hsts_header_present_when_not_mock_whatsapp(self, client, monkeypatch):
        # Patch the bound Config referenced *inside this module*, not the
        # Config class globally — other modules read Config.USE_MOCK_WHATSAPP
        # too (e.g. CSRFMiddleware's cookie_secure), and a global monkeypatch
        # would bleed into their behavior for this request as well.
        monkeypatch.setattr(security_headers_module.Config, "USE_MOCK_WHATSAPP", False)
        r = client.get("/login")
        assert "strict-transport-security" in r.headers
        assert r.headers["strict-transport-security"] == "max-age=15552000; includeSubDomains"


class TestCSPNonce:
    def test_nonce_set_on_request_state(self):
        """Direct middleware unit call — no HTTP round trip, no permanent
        debug route added to the app just to observe request.state."""
        async def _call_next(request):
            return PlainTextResponse("ok")

        async def _run():
            mw = SecurityHeadersMiddleware(app=None)
            scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
            request = Request(scope)
            await mw.dispatch(request, _call_next)
            return request

        request = asyncio.run(_run())
        assert isinstance(request.state.csp_nonce, str)
        assert len(request.state.csp_nonce) > 0
