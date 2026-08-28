"""
test_csrf.py — Integration tests for CSRFMiddleware (REQ-prod-csrf),
registered in app/main.py scoped via sensitive_cookies={SESSION_COOKIE_NAME}.

The `operator_client`/`admin_client` fixtures in tests/conftest.py deliberately
do NOT set a real session cookie (they override the FastAPI dependency
instead), so CSRF enforcement never engages for them by default. This file
sets the session cookie explicitly via `client.cookies.set(SESSION_COOKIE_NAME,
"any-value")` to make a request "sensitive" from the middleware's point of
view — the middleware only checks for the cookie's presence by name, it never
validates the session itself (that is `require_operator`'s job, downstream).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["USE_MOCK_WHATSAPP"] = "1"

from app.shared.constants import SESSION_COOKIE_NAME  # noqa: E402


class TestCSRFEnforcement:
    def test_mutating_request_with_session_cookie_and_no_token_is_rejected(
        self, operator_client
    ):
        """A cookie-authenticated POST with no x-csrftoken header must 403 —
        this is the forgeable request CSRF protection exists to stop."""
        operator_client.cookies.set(SESSION_COOKIE_NAME, "any-value")

        r = operator_client.post("/api/products", json={})

        assert r.status_code == 403

    def test_mutating_request_with_valid_double_submit_token_is_not_rejected(
        self, operator_client
    ):
        """A preceding GET sets the csrftoken cookie (CSRFMiddleware issues
        one on any response that doesn't already carry it); echoing that
        value back in the x-csrftoken header must clear the CSRF check."""
        login_resp = operator_client.get("/login")
        assert login_resp.status_code == 200
        csrf_token = operator_client.cookies.get("csrftoken")
        assert csrf_token, "GET /login should have set a csrftoken cookie"

        operator_client.cookies.set(SESSION_COOKIE_NAME, "any-value")

        r = operator_client.post(
            "/api/products",
            json={},
            headers={"x-csrftoken": csrf_token},
        )

        # The request clears CSRF; whatever the route does with an empty
        # body (400 for "name required") is irrelevant here — just not 403.
        assert r.status_code != 403

    def test_whatsapp_webhook_is_exempt_by_construction(self, client):
        """No session cookie is ever presented to the webhook (Meta
        authenticates it via X-Hub-Signature-256 over the raw body, not a
        browser cookie) — sensitive_cookies scoping means CSRF never
        engages for it at all, with no exempt_urls regex required."""
        r = client.post("/whatsapp/webhook", json={})

        assert r.status_code != 403

    def test_safe_method_is_never_enforced(self, operator_client, monkeypatch):
        """GET is a safe method — CSRFMiddleware's default safe_methods set
        excludes it from enforcement even with the session cookie present
        and no token supplied."""
        import app.routers.ui_api as api

        monkeypatch.setattr(api, "query", lambda *a, **k: [])
        operator_client.cookies.set(SESSION_COOKIE_NAME, "any-value")

        r = operator_client.get("/api/products")

        assert r.status_code != 403
