"""
test_ui_api.py — Integration tests for the products and broadcast API.

Tests products CRUD (list, create, update, toggle, delete) and broadcast
endpoints with mocked DB. Auth is injected via cookie.
"""
import hashlib
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
    from app.services.config import Config

    raw = f"{Config.SECRET_KEY}:{Config.DASHBOARD_PASSWORD}"
    token = hashlib.sha256(raw.encode()).hexdigest()
    client.cookies.set("alyasmeen_session", token)
    return client


# ---------------------------------------------------------------------------
# Products API
# ---------------------------------------------------------------------------

FAKE_PRODUCTS = [
    {"id": 1, "name": "كريم اليدين", "price": 25.0,
     "description": "كريم مرطب", "tags": "ترطيب", "active": True},
    {"id": 2, "name": "لوشن الجسم", "price": 40.0,
     "description": "لوشن طبيعي", "tags": "ترطيب", "active": False},
]


@pytest.fixture()
def mock_products_db(monkeypatch):
    import app.routers.ui_api as api

    _products = {p["id"]: dict(p) for p in FAKE_PRODUCTS}
    _next_id = [3]

    def fake_query(sql, params=()):
        if "products" in sql and "SELECT" in sql:
            if params and "WHERE id" in sql:
                pid = params[0]
                row = _products.get(pid)
                return [row] if row else []
            return list(_products.values())
        return []

    def fake_execute(sql, params=()):
        if "UPDATE products SET active" in sql:
            pid = params[1]
            if pid in _products:
                _products[pid]["active"] = params[0]
        elif "DELETE FROM products" in sql:
            pid = params[0]
            _products.pop(pid, None)
        elif "UPDATE products SET name" in sql:
            pid = params[4]
            if pid in _products:
                _products[pid].update({"name": params[0], "price": params[1],
                                        "description": params[2], "tags": params[3]})

    def fake_execute_returning(sql, params=()):
        new_id = _next_id[0]
        _next_id[0] += 1
        row = {"id": new_id, "name": params[0], "price": float(params[1]),
               "description": params[2], "tags": params[3], "active": True}
        _products[new_id] = row
        return row

    monkeypatch.setattr(api, "query", fake_query)
    monkeypatch.setattr(api, "execute", fake_execute)
    monkeypatch.setattr(api, "execute_returning", fake_execute_returning)
    monkeypatch.setattr(api, "_invalidate", lambda: None)
    return _products


class TestProductsListAPI:
    def test_list_products_authenticated(self, auth_client, mock_products_db):
        r = auth_client.get("/api/products")
        assert r.status_code == 200
        data = r.json()
        assert "products" in data
        assert len(data["products"]) == 2

    def test_list_products_unauthenticated(self, client):
        r = client.get("/api/products")
        assert r.status_code == 401


class TestCreateProduct:
    def test_create_product_succeeds(self, auth_client, mock_products_db):
        r = auth_client.post("/api/products", json={
            "name": "شمعة العود",
            "price": 35.0,
            "description": "شمعة عطرية",
            "tags": "شموع",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["product"]["name"] == "شمعة العود"

    def test_create_without_name_returns_400(self, auth_client, mock_products_db):
        r = auth_client.post("/api/products", json={"price": 25.0})
        assert r.status_code == 400

    def test_create_with_zero_price_returns_400(self, auth_client, mock_products_db):
        r = auth_client.post("/api/products", json={"name": "test", "price": 0})
        assert r.status_code == 400

    def test_create_with_negative_price_returns_400(self, auth_client, mock_products_db):
        r = auth_client.post("/api/products", json={"name": "test", "price": -5.0})
        assert r.status_code == 400

    def test_create_with_invalid_price_returns_400(self, auth_client, mock_products_db):
        r = auth_client.post("/api/products", json={"name": "test", "price": "not-a-number"})
        assert r.status_code == 400


class TestUpdateProduct:
    def test_update_existing_product(self, auth_client, mock_products_db):
        r = auth_client.post("/api/products/1", json={
            "name": "كريم اليدين المحدث",
            "price": 30.0,
            "description": "كريم جديد",
            "tags": "ترطيب",
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_update_nonexistent_product_returns_404(self, auth_client, mock_products_db):
        r = auth_client.post("/api/products/9999", json={
            "name": "لا يوجد",
            "price": 10.0,
        })
        assert r.status_code == 404


class TestToggleProduct:
    def test_toggle_product_changes_active(self, auth_client, mock_products_db):
        r = auth_client.post("/api/products/1/toggle")
        assert r.status_code == 200
        data = r.json()
        assert "active" in data

    def test_toggle_nonexistent_returns_404(self, auth_client, mock_products_db):
        r = auth_client.post("/api/products/9999/toggle")
        assert r.status_code == 404


class TestDeleteProduct:
    def test_delete_existing_product(self, auth_client, mock_products_db):
        r = auth_client.post("/api/products/1/delete")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_delete_nonexistent_returns_404(self, auth_client, mock_products_db):
        r = auth_client.post("/api/products/9999/delete")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Broadcast API
# ---------------------------------------------------------------------------

class TestBroadcastAPI:
    def test_audience_count_all(self, auth_client, monkeypatch):
        import app.routers.ui_api as api
        monkeypatch.setattr(api, "query", lambda sql, params=(): [
            {"phone": "972591111111"}, {"phone": "972592222222"}
        ])
        r = auth_client.get("/api/broadcast/audience?filter=all")
        assert r.status_code == 200
        assert r.json()["count"] == 2

    def test_audience_invalid_filter_returns_400(self, auth_client):
        r = auth_client.get("/api/broadcast/audience?filter=invalid")
        assert r.status_code == 400

    def test_send_broadcast_to_all(self, auth_client, monkeypatch):
        import app.routers.ui_api as api
        import app.services.whatsapp_dev as dev

        monkeypatch.setattr(api, "query", lambda sql, params=(): [
            {"phone": "972591111111"}, {"phone": "972592222222"}
        ])
        sent = []
        monkeypatch.setattr(dev, "send_text", lambda to, msg: sent.append(to) or {})

        r = auth_client.post("/api/broadcast/send", json={
            "message": "عرض خاص هذا الأسبوع!",
            "filter": "all",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["sent"] == 2
        assert data["failed"] == 0

    def test_send_broadcast_empty_message_returns_400(self, auth_client):
        r = auth_client.post("/api/broadcast/send", json={"message": "", "filter": "all"})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

class TestPageRoutes:
    def test_login_page_renders(self, client):
        r = client.get("/login")
        assert r.status_code == 200

    def test_orders_page_redirects_to_login_unauthenticated(self, client):
        r = client.get("/orders", follow_redirects=False)
        assert r.status_code == 303
        assert "/login" in r.headers.get("location", "")

    def test_orders_page_renders_when_authenticated(self, auth_client):
        r = auth_client.get("/orders")
        assert r.status_code == 200

    def test_dashboard_page_renders_when_authenticated(self, auth_client):
        r = auth_client.get("/dashboard")
        assert r.status_code == 200

    def test_products_page_renders_when_authenticated(self, auth_client):
        r = auth_client.get("/products")
        assert r.status_code == 200

    def test_logout_clears_session(self, auth_client):
        r = auth_client.get("/logout", follow_redirects=False)
        assert r.status_code == 303
