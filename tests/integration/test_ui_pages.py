"""test_ui_pages.py — Page-level auth coverage for the dashboard HTML routes
(app/routers/ui.py), added alongside the new /handoffs and /audit pages
(plan 05-07).

Uses the shared `client`/`operator_client` fixtures from tests/conftest.py
(no locally-declared TestClient) — every page route in ui.py is guarded by
the router-level `require_operator_page` dependency, so these tests only
exercise routing/auth/template-rendering, never the database (the page
handlers themselves issue no DB calls; the data is fetched client-side by
each page's own JS after render).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["USE_MOCK_WHATSAPP"] = "1"

PAGES = ["/handoffs", "/audit", "/orders", "/alerts"]


class TestSignedInPagesRender:
    def test_pages_return_200_and_carry_shared_nav(self, operator_client):
        for path in PAGES:
            r = operator_client.get(path)
            assert r.status_code == 200, f"{path} did not render 200"
            html = r.text
            assert "/handoffs" in html, f"{path} is missing the shared nav's /handoffs link"
            assert "/audit" in html, f"{path} is missing the shared nav's /audit link"
            assert "handoffCount" in html, f"{path} is missing the nav badge element"


class TestSignedOutPagesRedirect:
    def test_handoffs_and_audit_redirect_to_login_when_signed_out(self, client):
        for path in ("/handoffs", "/audit"):
            r = client.get(path, follow_redirects=False)
            assert r.status_code == 303, f"{path} should redirect an unauthenticated request"
            assert r.headers["location"] == "/login"
