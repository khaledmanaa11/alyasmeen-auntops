"""
test_debug.py — Unit tests for app/routers/debug.py

Tests the POST /dev/test_order endpoint with a mocked catalog and mocked DB.
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

import app.routers.debug as debug_module  # noqa: E402
from app.main import app  # noqa: E402

FAKE_CATALOG = [
    {"id": 1, "name": "كريم اليدين", "list_price": 25.0, "description_sale": "كريم مرطب"},
    {"id": 2, "name": "لوشن الجسم", "list_price": 40.0, "description_sale": "لوشن طبيعي"},
]


@pytest.fixture()
def client(monkeypatch):
    _order_seq = [0]

    def fake_execute(sql, params=()):
        pass

    def fake_execute_returning(sql, params=()):
        _order_seq[0] += 1
        return {"id": _order_seq[0]}

    monkeypatch.setattr(debug_module, "execute", fake_execute)
    monkeypatch.setattr(debug_module, "execute_returning", fake_execute_returning)
    monkeypatch.setattr(debug_module, "_CATALOG", FAKE_CATALOG)
    return TestClient(app)


class TestCreateTestOrder:
    def test_default_order_succeeds(self, client):
        r = client.post("/dev/test_order", json={})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert isinstance(data["order_id"], int)
        assert data["order_name"].startswith("ORD-")

    def test_custom_items(self, client):
        r = client.post("/dev/test_order", json={
            "phone": "+972591111111",
            "items": [{"product_index": 1, "qty": 2}],
            "fulfillment": "pickup",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert len(data["cart"]) == 1
        assert data["cart"][0]["qty"] == 2

    def test_delivery_fulfillment(self, client):
        r = client.post("/dev/test_order", json={
            "fulfillment": "delivery",
            "address": "شارع النصر، رام الله",
        })
        assert r.status_code == 200

    def test_invalid_fulfillment_returns_400(self, client):
        r = client.post("/dev/test_order", json={"fulfillment": "teleport"})
        assert r.status_code == 400

    def test_invalid_product_index_returns_400(self, client):
        r = client.post("/dev/test_order", json={
            "items": [{"product_index": 99, "qty": 1}],
        })
        assert r.status_code == 400

    def test_empty_catalog_returns_500(self, client, monkeypatch):
        monkeypatch.setattr(debug_module, "_CATALOG", [])
        r = client.post("/dev/test_order", json={})
        assert r.status_code == 500

    def test_auto_picks_first_three_products(self, client):
        r = client.post("/dev/test_order", json={})
        data = r.json()
        # With 2 products in fake catalog, auto-picks both
        assert len(data["cart"]) == 2
