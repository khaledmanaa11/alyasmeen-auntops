"""
test_bot_flow.py — Integration tests for the full WhatsApp bot conversation
flow, end-to-end through the durable-inbox webhook pipeline: POST
/whatsapp/webhook (persists to webhook_events) -> process_webhook_events()
(the worker's poll loop, run synchronously here) -> process_event() ->
processor.handle_message() -> outbox_jobs -> process_outbox_jobs() (the
worker's other poll loop, also run synchronously here).

Tests the complete order lifecycle: new customer -> menu -> add to cart ->
choose fulfillment -> confirm -> notification to aunt. All DB access and
WhatsApp sends are mocked via the conftest.py fixtures (fake_db,
sent_messages). handle_message() no longer calls send_text/send_buttons
directly — it enqueues into outbox_jobs via queue_text/queue_buttons, and
only process_outbox_jobs() (driven by process_job()) actually sends — so
_process_all() below drains both poll loops before a test reads
sent_messages back.
"""
import random

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import drain_outbox_jobs

FAKE_CATALOG = [
    {"id": 1, "name": "كريم اليدين", "list_price": 25.0, "description_sale": "كريم مرطب"},
    {"id": 2, "name": "لوشن الجسم", "list_price": 40.0, "description_sale": "لوشن طبيعي"},
]


def _phone():
    return f"97259{random.randint(1000000, 9999999)}"


@pytest.fixture()
def client(monkeypatch):
    # mock_db (conftest, autouse) already fakes the DB/session/sender seams;
    # only the product catalog (backed by Supabase via app.ai.retriever)
    # needs its own override here.
    monkeypatch.setattr("app.services.processor.catalog", lambda: FAKE_CATALOG)
    return TestClient(app)


def _process_all():
    """Drain the durable inbox synchronously — stands in for the worker's
    process_webhook_events poll loop (app/worker.py runs it every 3s) — then
    drains the outbox poller too (a separate 2s job in worker.py, see
    drain_outbox_jobs) so the resulting customer-facing reply actually lands
    in sent_messages instead of sitting in outbox_jobs as 'pending'."""
    from app.services.processor import process_webhook_events
    process_webhook_events()
    drain_outbox_jobs()


def _last_message_to(sent_messages, phone):
    """The most recent {"to", "text", "buttons"} entry sent to `phone`, or an
    empty stand-in if nothing was sent. send_buttons' body is captured as
    `text` too, so callers don't need to special-case button messages."""
    for msg in reversed(sent_messages):
        if msg["to"] == phone:
            return msg
    return {"to": phone, "text": "", "buttons": None}


def _post_webhook(client, phone, text, name="Test User"):
    # Simulated Meta webhook payload — matches what process_event() parses.
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "16505559999", "phone_number_id": "106132048924043"},
                    "contacts": [{"profile": {"name": name}, "wa_id": phone}],
                    "messages": [{
                        "from": phone,
                        "id": f"wamid.{random.randint(100000, 999999)}",
                        "timestamp": "1665401156",
                        "text": {"body": text},
                        "type": "text"
                    }]
                },
                "field": "messages"
            }]
        }]
    }
    r = client.post("/whatsapp/webhook", json=payload)
    assert r.status_code == 200
    _process_all()
    return r


class TestNewCustomerWelcome:
    def test_first_message_triggers_welcome(self, client, sent_messages, monkeypatch):
        # No dedicated welcome message exists yet — free text falls through
        # to the AI path. Pin that path so this test doesn't depend on (or
        # need) a real Claude call, and confirm a brand-new customer's first
        # message is answered rather than silently dropped.
        monkeypatch.setattr("app.services.processor.generate_reply", lambda **kwargs: "أهلاً!")

        phone = _phone()
        _post_webhook(client, phone, "مرحبا")
        assert _last_message_to(sent_messages, phone)["text"] == "أهلاً!"

    def test_returning_customer_no_welcome(self, client, sent_messages):
        phone = _phone()
        _post_webhook(client, phone, "cart")
        assert "فارغة" in _last_message_to(sent_messages, phone)["text"]


class TestFullPickupOrderFlow:
    def test_complete_pickup_order(self, client, sent_messages):
        """Full flow: menu -> add product -> pickup -> confirm -> get order ID."""
        phone = _phone()

        # Step 1: Show menu
        _post_webhook(client, phone, "menu")
        assert "كريم اليدين" in _last_message_to(sent_messages, phone)["text"]

        # Step 2: Add product 1
        _post_webhook(client, phone, "1")
        assert "كريم اليدين" in _last_message_to(sent_messages, phone)["text"]

        # Step 3: Check cart — fulfillment isn't chosen yet, so _show_cart
        # asks via send_buttons (body captured into "text" too).
        _post_webhook(client, phone, "cart")
        last = _last_message_to(sent_messages, phone)
        assert "كريم اليدين" in last["text"]
        assert "25" in last["text"]

        # Step 4: Choose pickup — _show_cart runs again, now as plain text.
        _post_webhook(client, phone, "pickup")
        assert "25" in _last_message_to(sent_messages, phone)["text"]

        # Step 5: Confirm
        _post_webhook(client, phone, "confirm")
        assert "ORD-" in _last_message_to(sent_messages, phone)["text"]

        # Step 6: Cart should be cleared after confirm
        _post_webhook(client, phone, "cart")
        assert "فارغة" in _last_message_to(sent_messages, phone)["text"]


class TestFullDeliveryOrderFlow:
    def test_complete_delivery_order(self, client, sent_messages):
        """Full flow: menu -> add -> delivery -> address -> confirm -> order ID."""
        phone = _phone()

        _post_webhook(client, phone, "menu")
        _post_webhook(client, phone, "1")

        # Choose delivery
        _post_webhook(client, phone, "delivery")
        text = _last_message_to(sent_messages, phone)["text"]
        assert "عنوان" in text or "وين" in text

        # Provide address
        _post_webhook(client, phone, "شارع النصر، رام الله")
        assert "confirm" in _last_message_to(sent_messages, phone)["text"]

        # Confirm
        _post_webhook(client, phone, "confirm")
        assert "ORD-" in _last_message_to(sent_messages, phone)["text"]


class TestAuntNotification:
    def test_aunt_notified_on_confirm(self, client, sent_messages, monkeypatch):
        """When AUNT_PHONE is set, aunt should receive notification on confirm."""
        import app.services.config as config_mod

        aunt_phone = "972591111111"
        monkeypatch.setattr(config_mod.Config, "AUNT_PHONE", aunt_phone)

        phone = _phone()
        _post_webhook(client, phone, "menu")
        _post_webhook(client, phone, "1")
        _post_webhook(client, phone, "pickup")
        _post_webhook(client, phone, "confirm")

        aunt_msg = _last_message_to(sent_messages, aunt_phone)
        assert "طلب جديد" in aunt_msg["text"]

    def test_no_notification_when_aunt_phone_not_set(self, client, sent_messages, monkeypatch):
        """When AUNT_PHONE is not set, no notification is sent to aunt."""
        import app.services.config as config_mod

        monkeypatch.setattr(config_mod.Config, "AUNT_PHONE", None)

        phone = _phone()
        _post_webhook(client, phone, "menu")
        _post_webhook(client, phone, "1")
        _post_webhook(client, phone, "pickup")
        _post_webhook(client, phone, "confirm")

        assert not any(m["to"] == "972591111111" for m in sent_messages)


class TestAIFallback:
    def test_unknown_message_goes_to_ai(self, client, sent_messages, monkeypatch):
        """Messages that don't match any hard command fall through to AI."""
        monkeypatch.setattr("app.services.processor.generate_reply", lambda **kwargs: "Mocked AI Reply")

        phone = _phone()
        _post_webhook(client, phone, "ما هو أفضل كريم للبشرة الجافة؟")

        assert _last_message_to(sent_messages, phone)["text"] == "Mocked AI Reply"

    def test_ai_failure_sends_arabic_fallback_instead_of_raising(self, client, sent_messages, monkeypatch):
        """If the AI call itself raises, the customer must still get a reply
        (the Arabic fallback), not a dropped message or a 500."""
        import app.services.processor as processor

        def _boom(**kwargs):
            raise RuntimeError("Claude API timeout")

        monkeypatch.setattr(processor, "generate_reply", _boom)

        phone = _phone()
        r = _post_webhook(client, phone, "بشرتي جافة كثير وين الحل؟")

        assert r.status_code == 200
        assert _last_message_to(sent_messages, phone)["text"] == processor.AI_FALLBACK_REPLY
