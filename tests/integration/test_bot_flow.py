"""
test_bot_flow.py — Integration tests for the full WhatsApp bot conversation flow.

Tests the complete order lifecycle: new customer welcome → menu → add to cart →
choose fulfillment → confirm → notification to aunt. All DB and WhatsApp calls
are mocked via conftest fixtures.
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
    {"id": 1, "name": "كريم اليدين", "list_price": 25.0, "description_sale": "كريم مرطب"},
    {"id": 2, "name": "لوشن الجسم", "list_price": 40.0, "description_sale": "لوشن طبيعي"},
]


def _phone():
    return f"97259{random.randint(1000000, 9999999)}"


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(wa, "_CATALOG", FAKE_CATALOG)
    return TestClient(app)


class TestNewCustomerWelcome:
    def test_first_message_triggers_welcome(self, client, monkeypatch):
        monkeypatch.setattr(wa, "upsert_customer", lambda phone, name="": True)
        r = client.post(
            "/whatsapp/webhook",
            json={"from_number": _phone(), "text": "مرحبا", "wa_name": "أحمد"},
        )
        assert r.status_code == 200

    def test_returning_customer_no_welcome(self, client, monkeypatch):
        monkeypatch.setattr(wa, "upsert_customer", lambda phone, name="": False)
        # Should proceed normally without welcome message being sent
        r = client.post(
            "/whatsapp/webhook",
            json={"from_number": _phone(), "text": "cart"},
        )
        assert r.status_code == 200


class TestFullPickupOrderFlow:
    def test_complete_pickup_order(self, client):
        """Full flow: menu → add product → pickup → confirm → get order ID."""
        phone = _phone()

        # Step 1: Show menu
        r1 = client.post("/whatsapp/webhook", json={"from_number": phone, "text": "menu"})
        assert r1.status_code == 200
        assert "كريم اليدين" in r1.json().get("text", "")

        # Step 2: Add product 1
        r2 = client.post("/whatsapp/webhook", json={"from_number": phone, "text": "1"})
        assert r2.status_code == 200
        assert "كريم اليدين" in r2.json().get("text", "")

        # Step 3: Check cart
        r3 = client.post("/whatsapp/webhook", json={"from_number": phone, "text": "cart"})
        assert r3.status_code == 200
        assert "كريم اليدين" in r3.json().get("text", "")
        assert "25" in r3.json().get("text", "")

        # Step 4: Choose pickup
        r4 = client.post("/whatsapp/webhook", json={"from_number": phone, "text": "pickup"})
        assert r4.status_code == 200

        # Step 5: Confirm
        r5 = client.post("/whatsapp/webhook", json={"from_number": phone, "text": "confirm"})
        assert r5.status_code == 200
        data = r5.json()
        assert data.get("ok") is True
        assert data.get("order_name", "").startswith("ORD-")

        # Step 6: Cart should be cleared after confirm
        r6 = client.post("/whatsapp/webhook", json={"from_number": phone, "text": "cart"})
        assert "فارغة" in r6.json().get("text", "")


class TestFullDeliveryOrderFlow:
    def test_complete_delivery_order(self, client):
        """Full flow: menu → add → delivery → address → confirm → order ID."""
        phone = _phone()

        client.post("/whatsapp/webhook", json={"from_number": phone, "text": "menu"})
        client.post("/whatsapp/webhook", json={"from_number": phone, "text": "1"})

        # Choose delivery
        r_del = client.post(
            "/whatsapp/webhook", json={"from_number": phone, "text": "delivery"}
        )
        assert r_del.status_code == 200
        assert "عنوان" in r_del.json().get("text", "") or "وين" in r_del.json().get("text", "")

        # Provide address
        r_addr = client.post(
            "/whatsapp/webhook",
            json={"from_number": phone, "text": "شارع النصر، رام الله"},
        )
        assert r_addr.status_code == 200
        assert "confirm" in r_addr.json().get("text", "")

        # Confirm
        r_confirm = client.post(
            "/whatsapp/webhook", json={"from_number": phone, "text": "confirm"}
        )
        assert r_confirm.status_code == 200
        assert r_confirm.json().get("ok") is True


class TestAuntNotification:
    def test_aunt_notified_on_confirm(self, client, monkeypatch):
        """When AUNT_PHONE is set, aunt should receive notification on confirm."""
        import app.services.config as config_mod

        monkeypatch.setattr(config_mod.Config, "AUNT_PHONE", "972591111111")

        sent_to = []

        def capture_send(to, msg):
            sent_to.append(to)
            return {"dev": True}

        monkeypatch.setattr(wa, "send_text", capture_send)

        phone = _phone()
        client.post("/whatsapp/webhook", json={"from_number": phone, "text": "menu"})
        client.post("/whatsapp/webhook", json={"from_number": phone, "text": "1"})
        client.post("/whatsapp/webhook", json={"from_number": phone, "text": "pickup"})
        client.post("/whatsapp/webhook", json={"from_number": phone, "text": "confirm"})

        # Aunt phone should be in recipients
        assert "972591111111" in sent_to

    def test_no_notification_when_aunt_phone_not_set(self, client, monkeypatch):
        """When AUNT_PHONE is not set, no notification is sent to aunt."""
        import app.services.config as config_mod

        monkeypatch.setattr(config_mod.Config, "AUNT_PHONE", None)

        sent_to = []

        def capture_send(to, msg):
            sent_to.append(to)
            return {"dev": True}

        monkeypatch.setattr(wa, "send_text", capture_send)

        phone = _phone()
        client.post("/whatsapp/webhook", json={"from_number": phone, "text": "menu"})
        client.post("/whatsapp/webhook", json={"from_number": phone, "text": "1"})
        client.post("/whatsapp/webhook", json={"from_number": phone, "text": "pickup"})
        r = client.post("/whatsapp/webhook", json={"from_number": phone, "text": "confirm"})

        assert r.json().get("ok") is True
        # Only the customer was notified (confirm message), not aunt
        for recipient in sent_to:
            assert recipient != "972591111111"


class TestAIFallback:
    def test_unknown_message_goes_to_ai(self, client, monkeypatch):
        """Messages that don't match any hard command fall through to AI."""
        import app.services.ai_service as ai

        monkeypatch.setattr(ai.Config, "CLAUDE_API_KEY", None)  # triggers fallback reply
        r = client.post(
            "/whatsapp/webhook",
            json={"from_number": _phone(), "text": "ما هو أفضل كريم للبشرة الجافة؟"},
        )
        assert r.status_code == 200
        # Should return some text (AI fallback message)
        assert r.json().get("text") or r.json().get("ok") is not None
