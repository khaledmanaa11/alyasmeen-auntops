"""
test_orders_api.py — Integration tests for the orders API.

Tests the order status update flow end-to-end with a mocked Supabase client.
Covers: status transitions (to_do → ready → delivered → done), auth guard,
WhatsApp notification on status change, and PDF invoice on done.

Auth is injected via the operator_client fixture (tests/conftest.py) — a
FastAPI dependency override, not a forged session cookie.
"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["USE_MOCK_WHATSAPP"] = "1"


@pytest.fixture()
def mock_order(monkeypatch):
    """Patch db.query and db.execute so no real Supabase call is made.

    queue_text/queue_pdf_invoice (called from ui_api's status-update
    endpoint) are bound to app.services.processor's own imported `execute`
    reference, not ui_api's — so this fixture patches execute on BOTH
    modules and routes them through the same shared execute_calls list, so
    tests can assert on outbox inserts regardless of which module's `execute`
    actually ran.

    05-06 wired handoff.bot_recently_active() and audit.log_action() into
    api_update_status. Both are bound to the REAL app.services.handoff /
    app.services.audit modules — unpatched, bot_recently_active would issue
    a real SELECT (and, worse, an unhandled exception would turn every
    status-update test into a 500 instead of 200) and log_action would issue
    a real best-effort write against the live Supabase instance. Default to
    "no conflict" and a capturing audit spy so every existing test keeps
    working, while still letting individual tests override either.
    """
    import app.routers.ui_api as ui_api
    import app.services.audit as audit
    import app.services.handoff as handoff
    import app.services.processor as processor

    order_data = {
        "id": 42,
        "phone": "972591234567",
        "fulfillment": "pickup",
        "status": "to_do",
        "customer_name": "فاطمة",
    }

    execute_calls = []
    audit_calls = []

    def fake_query(sql, params=()):
        if "orders" in sql and "order_lines" not in sql:
            return [order_data]
        if "order_lines" in sql:
            return [{"product_name": "كريم", "qty": 1, "unit_price": 25.0}]
        return []

    def fake_execute(sql, params=()):
        execute_calls.append((sql, params))

    def fake_log_action(actor, action, details=None):
        audit_calls.append((actor, action, details))

    monkeypatch.setattr(ui_api, "query", fake_query)
    monkeypatch.setattr(ui_api, "execute", fake_execute)
    monkeypatch.setattr(processor, "execute", fake_execute)
    monkeypatch.setattr(handoff, "bot_recently_active", lambda phone, window_minutes=5: None)
    monkeypatch.setattr(audit, "log_action", fake_log_action)
    result = dict(order_data)
    result["execute_calls"] = execute_calls
    result["audit_calls"] = audit_calls
    return result


class TestOrdersAPIAuth:
    def test_api_orders_requires_auth(self, client):
        r = client.get("/api/orders")
        assert r.status_code == 401

    def test_api_order_lines_requires_auth(self, client):
        r = client.get("/api/orders/1/lines")
        assert r.status_code == 401

    def test_api_update_status_requires_auth(self, client):
        r = client.post("/api/orders/1/status", json={"status": "ready"})
        assert r.status_code == 401

    def test_api_products_requires_auth(self, client):
        r = client.get("/api/products")
        assert r.status_code == 401


def _outbox_inserts(execute_calls, kind=None):
    """Filter execute_calls down to outbox_jobs INSERTs, optionally by kind
    (the first element of the params tuple)."""
    inserts = [
        params for sql, params in execute_calls
        if "INSERT INTO outbox_jobs" in sql
    ]
    if kind is not None:
        inserts = [p for p in inserts if p[0] == kind]
    return inserts


class TestOrderStatusUpdate:
    def test_update_to_ready_succeeds(self, operator_client, mock_order):
        r = operator_client.post(
            f"/api/orders/{mock_order['id']}/status",
            json={"status": "ready"},
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert r.json()["status"] == "ready"
        # Queued to the outbox instead of sent inline in the request.
        inserts = _outbox_inserts(mock_order["execute_calls"], kind="whatsapp_message")
        assert len(inserts) == 1

    def test_update_to_delivered_succeeds(self, operator_client, mock_order, monkeypatch):
        # Mock record_delivery
        from app.services import followup
        monkeypatch.setattr(followup, "record_delivery", lambda phone, oid: None)

        r = operator_client.post(
            f"/api/orders/{mock_order['id']}/status",
            json={"status": "delivered"},
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True
        inserts = _outbox_inserts(mock_order["execute_calls"], kind="whatsapp_message")
        assert len(inserts) == 1

    def test_update_to_done_succeeds(self, operator_client, mock_order):
        """New coverage: marking an order 'done' must queue TWO outbox jobs —
        the thank-you text and the pdf_invoice regeneration+send — instead of
        sending the WhatsApp message and generating/sending the PDF inline in
        the HTTP request."""
        r = operator_client.post(
            f"/api/orders/{mock_order['id']}/status",
            json={"status": "done"},
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert r.json()["status"] == "done"

        text_inserts = _outbox_inserts(mock_order["execute_calls"], kind="whatsapp_message")
        assert len(text_inserts) == 1

        pdf_inserts = _outbox_inserts(mock_order["execute_calls"], kind="pdf_invoice")
        assert len(pdf_inserts) == 1
        assert pdf_inserts[0][2] == {"order_id": mock_order["id"]}

    def test_invalid_status_returns_400(self, operator_client, mock_order):
        r = operator_client.post(
            f"/api/orders/{mock_order['id']}/status",
            json={"status": "invalid_status"},
        )
        assert r.status_code == 400

    def test_missing_order_returns_404(self, operator_client, monkeypatch):
        import app.routers.ui_api as ui_api

        monkeypatch.setattr(ui_api, "query", lambda sql, params=(): [])
        monkeypatch.setattr(ui_api, "execute", lambda sql, params=(): None)

        r = operator_client.post("/api/orders/9999/status", json={"status": "ready"})
        assert r.status_code == 404

    def test_successful_status_change_produces_audit_log(self, operator_client, mock_order):
        """05-06: every status change is attributed via audit.log_action,
        naming the operator (op.email) and the from/to status."""
        r = operator_client.post(
            f"/api/orders/{mock_order['id']}/status",
            json={"status": "ready"},
        )
        assert r.status_code == 200

        audit_calls = mock_order["audit_calls"]
        matches = [c for c in audit_calls if c[1] == "order_status_changed"]
        assert len(matches) == 1
        actor, action, details = matches[0]
        assert actor == "aunt@example.test"  # FAKE_OPERATOR.email
        assert details["order_id"] == mock_order["id"]
        assert details["to"] == "ready"


class TestBotConflictGuard:
    """05-06: a status change that collides with a live bot conversation
    returns 409 instead of silently applying, unless the operator forces it."""

    def test_no_recent_bot_activity_still_succeeds(self, operator_client, mock_order):
        """Regression: mock_order's default bot_recently_active() returns
        None (no conflict), so a normal status change is unaffected."""
        r = operator_client.post(
            f"/api/orders/{mock_order['id']}/status",
            json={"status": "ready"},
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_bot_active_without_force_returns_409_and_blocks_update(
        self, operator_client, mock_order, monkeypatch
    ):
        import app.services.handoff as handoff

        monkeypatch.setattr(
            handoff, "bot_recently_active",
            lambda phone, window_minutes=5: {
                "last_activity": "2026-08-28T10:00:00+00:00", "paused": False,
            },
        )

        r = operator_client.post(
            f"/api/orders/{mock_order['id']}/status",
            json={"status": "ready"},
        )

        assert r.status_code == 409
        body = r.json()
        assert body["conflict"] is True
        assert body["reason"] == "bot_active"
        assert body["phone"] == mock_order["phone"]
        assert body["requested_status"] == "ready"

        # No order UPDATE (or anything else) was issued — the conflict guard
        # runs BEFORE any change is applied.
        assert mock_order["execute_calls"] == []

    def test_bot_active_with_force_applies_pauses_bot_and_opens_handoff(
        self, operator_client, mock_order, monkeypatch
    ):
        import app.services.handoff as handoff

        monkeypatch.setattr(
            handoff, "bot_recently_active",
            lambda phone, window_minutes=5: {
                "last_activity": "2026-08-28T10:00:00+00:00", "paused": False,
            },
        )

        r = operator_client.post(
            f"/api/orders/{mock_order['id']}/status",
            json={"status": "ready", "force": True},
        )

        assert r.status_code == 200
        assert r.json()["ok"] is True

        calls = mock_order["execute_calls"]
        paused_updates = [c for c in calls if "UPDATE sessions" in c[0] and "paused = TRUE" in c[0]]
        assert len(paused_updates) == 1
        assert paused_updates[0][1] == (mock_order["phone"],)

        handoff_inserts = [c for c in calls if "INSERT INTO handoffs" in c[0]]
        assert len(handoff_inserts) == 1

        order_updates = [c for c in calls if "UPDATE orders" in c[0]]
        assert len(order_updates) == 1

        override_calls = [c for c in mock_order["audit_calls"] if c[1] == "order_status_conflict_override"]
        assert len(override_calls) == 1
        changed_calls = [c for c in mock_order["audit_calls"] if c[1] == "order_status_changed"]
        assert len(changed_calls) == 1


class TestDashboardStats:
    def test_dashboard_stats_returns_expected_keys(self, operator_client, monkeypatch):
        import app.routers.ui_api as ui_api

        def fake_query(sql, params=()):
            if "total_orders" in sql and "last_month" not in sql.lower():
                return [{"total_orders": 10, "revenue": 500.0}]
            if "total_orders" in sql:
                return [{"total_orders": 8, "revenue": 400.0}]
            if "COUNT" in sql and "customers" in sql:
                return [{"count": 25}]
            if "daily_orders" in sql or "TO_CHAR" in sql:
                return [{"day": "2026-03-01", "count": 3}]
            if "status_breakdown" in sql or "GROUP BY status" in sql:
                return [{"status": "done", "count": 5}]
            if "top_products" in sql or "product_name" in sql:
                return [{"product_name": "كريم", "total_qty": 10, "revenue": 250.0}]
            return [{"total_orders": 0, "revenue": 0}]

        monkeypatch.setattr(ui_api, "query", fake_query)

        r = operator_client.get("/api/dashboard/stats")
        assert r.status_code == 200
        data = r.json()
        assert "this_month" in data
        assert "daily_orders" in data
        assert "top_products" in data
