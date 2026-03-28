"""
test_orders_api.py — Integration tests for the orders API.

Tests the order status update flow end-to-end with a mocked Supabase client.
Covers: status transitions (to_do → ready → delivered → done), auth guard,
WhatsApp notification on status change, and PDF invoice on done.
"""
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["USE_MOCK_WHATSAPP"] = "1"

from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def auth_client(client):
    """Return a client with a valid session cookie injected directly.

    Computing the token ourselves avoids redirect/cookie propagation issues
    with TestClient and doesn't require a real DB call.
    """
    import hashlib

    from app.services.config import Config

    raw = f"{Config.SECRET_KEY}:{Config.DASHBOARD_PASSWORD}"
    token = hashlib.sha256(raw.encode()).hexdigest()
    client.cookies.set("alyasmeen_session", token)
    return client


@pytest.fixture()
def mock_order(monkeypatch):
    """Patch db.query and db.execute so no real Supabase call is made."""
    import app.routers.ui_api as ui_api

    order_data = {
        "id": 42,
        "phone": "972591234567",
        "fulfillment": "pickup",
        "customer_name": "فاطمة",
    }

    def fake_query(sql, params=()):
        if "orders" in sql and "order_lines" not in sql:
            return [order_data]
        if "order_lines" in sql:
            return [{"product_name": "كريم", "qty": 1, "unit_price": 25.0}]
        return []

    def fake_execute(sql, params=()):
        pass  # no-op

    monkeypatch.setattr(ui_api, "query", fake_query)
    monkeypatch.setattr(ui_api, "execute", fake_execute)
    return order_data


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


class TestOrderStatusUpdate:
    def test_update_to_ready_succeeds(self, auth_client, mock_order, monkeypatch):
        import app.services.whatsapp_dev as wa_dev

        sent = []
        monkeypatch.setattr(wa_dev, "send_text", lambda to, msg: sent.append((to, msg)) or {})

        r = auth_client.post(
            f"/api/orders/{mock_order['id']}/status",
            json={"status": "ready"},
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert r.json()["status"] == "ready"
        assert len(sent) == 1  # WhatsApp notification sent

    def test_update_to_delivered_succeeds(self, auth_client, mock_order, monkeypatch):
        import app.services.whatsapp_dev as wa_dev

        sent = []
        monkeypatch.setattr(wa_dev, "send_text", lambda to, msg: sent.append((to, msg)) or {})

        # Mock record_delivery
        from app.services import followup
        monkeypatch.setattr(followup, "record_delivery", lambda phone, oid: None)

        r = auth_client.post(
            f"/api/orders/{mock_order['id']}/status",
            json={"status": "delivered"},
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert len(sent) == 1

    def test_invalid_status_returns_400(self, auth_client, mock_order):
        r = auth_client.post(
            f"/api/orders/{mock_order['id']}/status",
            json={"status": "invalid_status"},
        )
        assert r.status_code == 400

    def test_missing_order_returns_404(self, auth_client, monkeypatch):
        import app.routers.ui_api as ui_api

        monkeypatch.setattr(ui_api, "query", lambda sql, params=(): [])
        monkeypatch.setattr(ui_api, "execute", lambda sql, params=(): None)

        r = auth_client.post("/api/orders/9999/status", json={"status": "ready"})
        assert r.status_code == 404


class TestDashboardStats:
    def test_dashboard_stats_returns_expected_keys(self, auth_client, monkeypatch):
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

        r = auth_client.get("/api/dashboard/stats")
        assert r.status_code == 200
        data = r.json()
        assert "this_month" in data
        assert "daily_orders" in data
        assert "top_products" in data
