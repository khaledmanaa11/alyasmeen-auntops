"""
test_whatsapp.py — Unit tests for WhatsApp bot command handling.

Tests hard command detection, cart management, order tracking, address flow,
and edge cases (empty cart, invalid input). All DB calls are mocked via
the conftest.py autouse fixture.
"""
import os
import random
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["USE_MOCK_WHATSAPP"] = "1"

import app.routers.whatsapp as wa  # noqa: E402
from app.main import app  # noqa: E402

FAKE_CATALOG = [
    {"id": 1, "name": "كريم اليدين", "list_price": 25.0, "description_sale": "كريم مرطب للأيدي"},
    {"id": 2, "name": "لوشن الجسم", "list_price": 40.0, "description_sale": "لوشن طبيعي"},
    {"id": 3, "name": "شمعة العود", "list_price": 35.0, "description_sale": "شمعة عطرية"},
]


def _phone():
    return f"97259{random.randint(1000000, 9999999)}"


@pytest.fixture()
def client(monkeypatch):
    import app.services.worker_tasks as wt
    from app.services.worker_tasks import _handle_message

    outbox = []

    def mock_enqueue(to, payload, transport="whatsapp"):
        outbox.append({"to": to, "payload": payload})

    # Capture outbox so we can see what the bot "replied"
    monkeypatch.setattr("app.services.worker_tasks.enqueue_outbox", mock_enqueue)

    # Patch search_products to use our FAKE_CATALOG
    def mock_search(query=None, category=None):
        return [
            {"sku": str(p["id"]), "name": p["name"], "price": p["list_price"]}
            for p in FAKE_CATALOG
        ]
    monkeypatch.setattr(wt, "search_products", mock_search)
    monkeypatch.setattr("app.routers.whatsapp_helpers.catalog", lambda: FAKE_CATALOG)

    class MockResponse:
        def __init__(self, json_data):
            self.status_code = 200
            self._json = json_data

        def json(self):
            return self._json

    class MockClient:
        def post(self, url, json):
            phone = json.get("from_number")
            text = json.get("text")
            outbox.clear()
            # The handler now returns either None (if it sent text/buttons)
            # or a dict (for the 'confirm' command).
            res = _handle_message(phone, text)

            last_msg = ""
            if outbox:
                # Get the last message sent to this specific phone
                phone_msgs = [o["payload"] for o in outbox if o["to"] == phone]
                if phone_msgs:
                    p = phone_msgs[-1]
                    last_msg = p.get("body", "")

            response_json = {"text": last_msg}
            if isinstance(res, dict):
                response_json.update(res)

            return MockResponse(response_json)

    return MockClient()


class TestHardCommands:
    def test_cart_empty_returns_empty_message(self, client):
        r = client.post("/whatsapp/webhook", json={"from_number": _phone(), "text": "cart"})
        assert r.status_code == 200
        assert "فارغة" in r.json().get("text", "")

    def test_clear_resets_cart(self, client):
        phone = _phone()
        # Add to cart then clear
        client.post("/whatsapp/webhook", json={"from_number": phone, "text": "menu"})
        client.post("/whatsapp/webhook", json={"from_number": phone, "text": "1"})
        r = client.post("/whatsapp/webhook", json={"from_number": phone, "text": "clear"})
        assert r.status_code == 200
        # Cart should be empty now
        r2 = client.post("/whatsapp/webhook", json={"from_number": phone, "text": "cart"})
        assert "فارغة" in r2.json().get("text", "")

    def test_pickup_sets_fulfillment(self, client):
        phone = _phone()
        r = client.post("/whatsapp/webhook", json={"from_number": phone, "text": "pickup"})
        assert r.status_code == 200
        assert "استلام" in r.json().get("text", "") or "confirm" in r.json().get("text", "")

    def test_delivery_asks_for_address(self, client):
        phone = _phone()
        r = client.post("/whatsapp/webhook", json={"from_number": phone, "text": "delivery"})
        assert r.status_code == 200
        text = r.json().get("text", "")
        assert "عنوان" in text or "وين" in text

    def test_confirm_empty_cart_returns_error(self, client):
        r = client.post("/whatsapp/webhook", json={"from_number": _phone(), "text": "confirm"})
        assert r.status_code == 200
        assert "فارغة" in r.json().get("text", "") or "فارغ" in r.json().get("text", "")


class TestMenuAndSelection:
    def test_menu_shows_products(self, client):
        r = client.post("/whatsapp/webhook", json={"from_number": _phone(), "text": "menu"})
        assert r.status_code == 200
        text = r.json().get("text", "")
        assert "كريم اليدين" in text

    def test_number_selection_adds_to_cart(self, client):
        phone = _phone()
        client.post("/whatsapp/webhook", json={"from_number": phone, "text": "menu"})
        r = client.post("/whatsapp/webhook", json={"from_number": phone, "text": "1"})
        assert r.status_code == 200
        assert "كريم اليدين" in r.json().get("text", "")

    def test_invalid_number_returns_error(self, client):
        phone = _phone()
        client.post("/whatsapp/webhook", json={"from_number": phone, "text": "menu"})
        r = client.post("/whatsapp/webhook", json={"from_number": phone, "text": "99"})
        assert r.status_code == 200
        assert "غير صحيح" in r.json().get("text", "")

    def test_quantity_pattern_2x1_adds_qty(self, client):
        phone = _phone()
        client.post("/whatsapp/webhook", json={"from_number": phone, "text": "menu"})
        r = client.post("/whatsapp/webhook", json={"from_number": phone, "text": "2x1"})
        assert r.status_code == 200
        text = r.json().get("text", "")
        assert "كريم اليدين" in text
        assert "× 2" in text

    def test_quantity_pattern_3_star_2(self, client):
        phone = _phone()
        client.post("/whatsapp/webhook", json={"from_number": phone, "text": "menu"})
        r = client.post("/whatsapp/webhook", json={"from_number": phone, "text": "3*2"})
        assert r.status_code == 200
        assert "× 3" in r.json().get("text", "")


class TestCartContents:
    def test_cart_shows_added_product(self, client):
        phone = _phone()
        client.post("/whatsapp/webhook", json={"from_number": phone, "text": "menu"})
        client.post("/whatsapp/webhook", json={"from_number": phone, "text": "1"})
        r = client.post("/whatsapp/webhook", json={"from_number": phone, "text": "cart"})
        text = r.json().get("text", "")
        assert "كريم اليدين" in text
        assert "الإجمالي" in text

    def test_cart_shows_correct_total(self, client):
        phone = _phone()
        client.post("/whatsapp/webhook", json={"from_number": phone, "text": "menu"})
        client.post("/whatsapp/webhook", json={"from_number": phone, "text": "1"})  # 25 ILS
        r = client.post("/whatsapp/webhook", json={"from_number": phone, "text": "cart"})
        text = r.json().get("text", "")
        assert "25" in text


class TestOrderConfirmFlow:
    def test_confirm_after_pickup_creates_order(self, client):
        phone = _phone()
        client.post("/whatsapp/webhook", json={"from_number": phone, "text": "menu"})
        client.post("/whatsapp/webhook", json={"from_number": phone, "text": "1"})
        client.post("/whatsapp/webhook", json={"from_number": phone, "text": "pickup"})
        r = client.post("/whatsapp/webhook", json={"from_number": phone, "text": "confirm"})
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True
        assert isinstance(data.get("order_id"), int)
        assert data.get("order_name", "").startswith("ORD-")

    def test_confirm_delivery_without_address_blocks(self, client):
        phone = _phone()
        client.post("/whatsapp/webhook", json={"from_number": phone, "text": "menu"})
        client.post("/whatsapp/webhook", json={"from_number": phone, "text": "1"})
        client.post("/whatsapp/webhook", json={"from_number": phone, "text": "delivery"})
        # Skip address, try to confirm directly
        r = client.post("/whatsapp/webhook", json={"from_number": phone, "text": "confirm"})
        assert r.status_code == 200
        text = r.json().get("text", "")
        assert "عنوان" in text  # asked for address again


class TestOrderTracking:
    def test_order_tracking_keywords(self, client, monkeypatch):
        import app.services.worker_tasks as wt
        phone = _phone()
        monkeypatch.setattr(
            wt, "get_latest_order",
            lambda p: {"id": 5, "status": "ready", "created_at": "2026-03-01", "fulfillment": "pickup"},
        )
        r = client.post("/whatsapp/webhook", json={"from_number": phone, "text": "وين طلبي"})
        assert r.status_code == 200
        text = r.json().get("text", "")
        assert "جاهز" in text or "طلب" in text

    def test_no_orders_returns_not_found(self, client):
        phone = _phone()
        r = client.post("/whatsapp/webhook", json={"from_number": phone, "text": "وين طلبي"})
        assert r.status_code == 200
        text = r.json().get("text", "")
        assert "ما لقيت" in text or "تواصل" in text


class TestAddressFlow:
    def test_address_is_saved_and_confirmed(self, client):
        phone = _phone()
        client.post("/whatsapp/webhook", json={"from_number": phone, "text": "menu"})
        client.post("/whatsapp/webhook", json={"from_number": phone, "text": "1"})
        client.post("/whatsapp/webhook", json={"from_number": phone, "text": "delivery"})
        r = client.post(
            "/whatsapp/webhook",
            json={"from_number": phone, "text": "شارع النصر، رام الله"},
        )
        assert r.status_code == 200
        text = r.json().get("text", "")
        assert "confirm" in text or "تأكيد" in text or "عنوان" in text
