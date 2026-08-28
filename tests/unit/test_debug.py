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

    def fake_rpc(name, params=None, retryable=False):
        # Matches the shape of app.db.database.rpc(): a list of row dicts.
        # create_order_atomic is a scalar-returning function, so it comes
        # back as [{"create_order_atomic": <id>}] — see debug.py's unwrap.
        assert name == "create_order_atomic"
        _order_seq[0] += 1
        return [{"create_order_atomic": _order_seq[0]}]

    monkeypatch.setattr(debug_module, "execute", fake_execute)
    monkeypatch.setattr(debug_module, "rpc", fake_rpc)
    monkeypatch.setattr(debug_module, "catalog", lambda: FAKE_CATALOG)
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
        monkeypatch.setattr(debug_module, "catalog", lambda: [])
        r = client.post("/dev/test_order", json={})
        assert r.status_code == 500

    def test_auto_picks_first_three_products(self, client):
        r = client.post("/dev/test_order", json={})
        data = r.json()
        # With 2 products in fake catalog, auto-picks both
        assert len(data["cart"]) == 2


class TestChatMessage:
    """POST /dev/chat/message — runs one message through the bot brain
    (app.services.processor.handle_message) synchronously and returns the
    captured reply, since the real /whatsapp/webhook only queues the event
    for the async worker and has nothing to show a test page inline."""

    def test_requires_text(self, client):
        r = client.post("/dev/chat/message", json={"from_number": "+972500000001"})
        assert r.status_code == 400

    def test_empty_cart_reply_is_returned_synchronously(self, client):
        r = client.post(
            "/dev/chat/message",
            json={"from_number": "+972500000001", "text": "سلة", "wa_name": "Test"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("dev") is True
        assert data.get("to") == "+972500000001"
        assert "فارغة" in data.get("text", "")

    def test_restores_the_real_senders_after_the_request(self, client):
        """The endpoint temporarily swaps processor.send_text/send_buttons to
        capture the reply, then must restore them — a leaked patch would
        break every later request/test in the process."""
        import app.services.processor as processor

        before_text, before_buttons = processor.send_text, processor.send_buttons
        client.post(
            "/dev/chat/message",
            json={"from_number": "+972500000002", "text": "سلة"},
        )
        assert processor.send_text is before_text
        assert processor.send_buttons is before_buttons


class TestDebugRouterRegistered:
    """Sanity check that USE_MOCK_WHATSAPP=1 (the default under pytest, see
    .env / .env.example) keeps /dev/* routes registered — the actual
    off-switch is verified end-to-end in test_main_debug_gate.py."""

    def test_test_order_route_exists(self):
        paths = {r.path for r in app.routes}
        assert "/dev/test_order" in paths
        assert "/dev/chat" in paths
        assert "/dev/chat/message" in paths
