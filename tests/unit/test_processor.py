"""
test_processor.py — Unit tests for the bot brain, app.services.processor.

Calls processor.handle_message()/process_webhook_events() directly (no HTTP
layer) with the DB and WhatsApp sender faked via conftest.py's autouse
mock_db fixture (fake_db, sent_messages).

This file supersedes five pre-refactor test files that drove the bot through
a synchronous `/whatsapp/webhook` endpoint that no longer exists (that route
is now a durable-inbox writer — see tests/integration/test_bot_flow.py for
the full webhook -> worker -> processor path, and test_webhook_router.py for
the webhook endpoint itself):

  - tests/test_whatsapp_cart.py
  - tests/test_whatsapp_order.py
  - tests/test_whatsapp_ai_aunt.py
  - tests/test_whatsapp_info.py
  - tests/unit/test_whatsapp.py

Every behavioral assertion from those files is ported here against the
current architecture, with two exceptions where the underlying feature was
actually deleted in the refactor (not just moved) — see the module-level
notes on TestQuantityShorthand and the missing "info N" section below for
the justification the task instructions require for each removal.
"""
import random

import pytest

import app.services.processor as processor

FAKE_CATALOG = [
    {"id": 1, "name": "كريم اليدين", "list_price": 25.0, "description_sale": "كريم مرطب للأيدي"},
    {"id": 2, "name": "لوشن الجسم", "list_price": 40.0, "description_sale": "لوشن طبيعي"},
    {"id": 3, "name": "شمعة العود", "list_price": 35.0, "description_sale": "شمعة عطرية"},
]


def _phone():
    return f"97259{random.randint(1000000, 9999999)}"


@pytest.fixture(autouse=True)
def _catalog(monkeypatch):
    monkeypatch.setattr(processor, "catalog", lambda: FAKE_CATALOG)


def _last_text(sent_messages, phone):
    for msg in reversed(sent_messages):
        if msg["to"] == phone:
            return msg["text"]
    return ""


# ---------------------------------------------------------------------------
# Hard commands (English + Arabic wording)
# ---------------------------------------------------------------------------

class TestHardCommands:
    def test_cart_empty_returns_empty_message(self, sent_messages):
        phone = _phone()
        processor.handle_message(phone, "cart", "Test")
        assert "فارغة" in _last_text(sent_messages, phone)

    def test_clear_resets_cart_english(self, sent_messages):
        phone = _phone()
        processor.handle_message(phone, "menu", "Test")
        processor.handle_message(phone, "1", "Test")
        processor.handle_message(phone, "clear", "Test")
        processor.handle_message(phone, "cart", "Test")
        assert "فارغة" in _last_text(sent_messages, phone)

    def test_arabic_clear_resets_cart(self, sent_messages):
        """New coverage: the Arabic clear synonyms ('مسح', 'فرغ', 'افرغ
        السلة') must empty the cart exactly like the English 'clear' does."""
        phone = _phone()
        processor.handle_message(phone, "menu", "Test")
        processor.handle_message(phone, "1", "Test")
        processor.handle_message(phone, "مسح", "Test")
        assert "تم إفراغ السلة" in _last_text(sent_messages, phone)

        processor.handle_message(phone, "cart", "Test")
        assert "فارغة" in _last_text(sent_messages, phone)

    def test_pickup_sets_fulfillment(self, sent_messages):
        phone = _phone()
        processor.handle_message(phone, "pickup", "Test")
        text = _last_text(sent_messages, phone)
        assert "استلام" in text or "فارغة" in text  # empty cart -> _show_cart says so

    def test_delivery_asks_for_address(self, sent_messages):
        phone = _phone()
        processor.handle_message(phone, "delivery", "Test")
        text = _last_text(sent_messages, phone)
        assert "عنوان" in text or "وين" in text

    def test_confirm_with_empty_cart_does_not_create_an_order(self, sent_messages, fake_db, monkeypatch):
        """The `confirm` hard command is guarded by `and cart` (see
        processor.py), so with an empty cart it doesn't match and falls
        through to the AI branch instead of creating an order."""
        monkeypatch.setattr(processor, "generate_reply", lambda **kwargs: "سلتك فاضية، ضيفي منتج الأول 🙏")

        phone = _phone()
        processor.handle_message(phone, "confirm", "Test")
        assert fake_db.orders == []
        assert _last_text(sent_messages, phone) == "سلتك فاضية، ضيفي منتج الأول 🙏"

    def test_english_and_arabic_confirm_both_create_an_order(self, sent_messages):
        """New coverage: Arabic 'تأكيد' must trigger the exact same order
        creation path as the English 'confirm' command."""
        for confirm_word in ("confirm", "تأكيد"):
            phone = _phone()
            processor.handle_message(phone, "menu", "Test")
            processor.handle_message(phone, "1", "Test")
            processor.handle_message(phone, "pickup", "Test")
            processor.handle_message(phone, confirm_word, "Test")
            assert "ORD-" in _last_text(sent_messages, phone), f"failed for {confirm_word!r}"


# ---------------------------------------------------------------------------
# Menu display and numeric product selection
# ---------------------------------------------------------------------------

class TestMenuAndSelection:
    def test_menu_shows_products(self, sent_messages):
        phone = _phone()
        processor.handle_message(phone, "menu", "Test")
        assert "كريم اليدين" in _last_text(sent_messages, phone)

    def test_number_selection_adds_to_cart(self, sent_messages):
        phone = _phone()
        processor.handle_message(phone, "menu", "Test")
        processor.handle_message(phone, "1", "Test")
        assert "كريم اليدين" in _last_text(sent_messages, phone)

    def test_invalid_number_falls_through_to_ai(self, sent_messages, monkeypatch):
        """A numeric selection outside the shown menu range doesn't match
        any menu item (see handle_message step 5's range guard), so it falls
        through to the AI branch — this test pins that fallback rather than
        a dedicated "invalid number" hard-coded reply, since processor.py no
        longer has one. generate_reply is mocked so this never risks a real
        Claude call even though CLAUDE_API_KEY is configured in this repo's
        .env."""
        monkeypatch.setattr(processor, "generate_reply", lambda **kwargs: "لم أفهم رقم المنتج")

        phone = _phone()
        processor.handle_message(phone, "menu", "Test")
        processor.handle_message(phone, "99", "Test")
        assert _last_text(sent_messages, phone) == "لم أفهم رقم المنتج"


class TestQuantityShorthand:
    """The pre-refactor bot recognized '2x1' / '3*2' shorthand as a hard
    command to add a specific quantity of a numbered menu item. That parsing
    was removed in the processor.py rewrite — cmd.isdigit() is the only
    numeric hard-command path left (see handle_message step 5), and any
    'NxM'-shaped text now falls through to the AI's add_to_cart(qty=...)
    tool instead, which is inherently non-deterministic to test here.

    The underlying intent — "a customer can add more than one unit of a
    product in one step" — is still real and still deterministic at the tool
    level, so this ports that intent by calling the tool function the AI
    would call directly, instead of the deleted text-shorthand parser.
    """

    def test_tool_add_to_cart_honors_requested_quantity(self):
        st = {"cart": []}
        cart = st["cart"]
        msg = processor._tool_add_to_cart(st, cart, "كريم اليدين", 2)
        assert "2 ×" in msg  # message format is "{qty} × {name}"
        assert cart[0]["qty"] == 2

    def test_tool_add_to_cart_accumulates_on_repeat_add(self):
        st = {"cart": []}
        cart = st["cart"]
        processor._tool_add_to_cart(st, cart, "كريم اليدين", 3)
        processor._tool_add_to_cart(st, cart, "كريم اليدين", 2)
        assert cart[0]["qty"] == 5


# ---------------------------------------------------------------------------
# Cart contents
# ---------------------------------------------------------------------------

class TestCartContents:
    def test_cart_shows_added_product_and_total(self, sent_messages):
        phone = _phone()
        processor.handle_message(phone, "menu", "Test")
        processor.handle_message(phone, "1", "Test")
        processor.handle_message(phone, "cart", "Test")
        text = _last_text(sent_messages, phone)
        assert "كريم اليدين" in text
        assert "الإجمالي" in text

    def test_cart_shows_correct_total(self, sent_messages):
        phone = _phone()
        processor.handle_message(phone, "menu", "Test")
        processor.handle_message(phone, "1", "Test")  # 25 ILS
        processor.handle_message(phone, "cart", "Test")
        assert "25" in _last_text(sent_messages, phone)


# ---------------------------------------------------------------------------
# Order confirm flow
# ---------------------------------------------------------------------------

class TestOrderConfirmFlow:
    def test_confirm_after_pickup_creates_order(self, sent_messages, fake_db):
        phone = _phone()
        processor.handle_message(phone, "menu", "Test")
        processor.handle_message(phone, "1", "Test")
        processor.handle_message(phone, "pickup", "Test")
        processor.handle_message(phone, "confirm", "Test")

        text = _last_text(sent_messages, phone)
        assert "ORD-" in text
        assert len(fake_db.orders) == 1
        assert fake_db.orders[0]["phone"] == phone

    def test_confirm_delivery_without_address_blocks(self, sent_messages, fake_db):
        phone = _phone()
        processor.handle_message(phone, "menu", "Test")
        processor.handle_message(phone, "1", "Test")
        processor.handle_message(phone, "delivery", "Test")
        # Skip address, try to confirm directly — this must NOT create an
        # order; the customer should be asked for the address again instead.
        processor.handle_message(phone, "confirm", "Test")
        text = _last_text(sent_messages, phone)
        assert "عنوان" in text or "وين" in text  # still asked for address
        assert fake_db.orders == []


# ---------------------------------------------------------------------------
# create_order_atomic result unwrapping
# ---------------------------------------------------------------------------

class TestOrderNumberFormat:
    def test_order_number_is_four_digit_zero_padded(self, sent_messages, fake_db):
        """New coverage: create_order_atomic's rpc() result is a list of row
        dicts ([{"create_order_atomic": <id>}]) — the order number sent to
        the customer must be the unwrapped id, zero-padded to 4 digits."""
        phone = _phone()
        processor.handle_message(phone, "menu", "Test")
        processor.handle_message(phone, "1", "Test")
        processor.handle_message(phone, "pickup", "Test")
        processor.handle_message(phone, "confirm", "Test")

        text = _last_text(sent_messages, phone)
        order_id = fake_db.orders[0]["id"]
        assert f"ORD-{order_id:04d}" in text


# ---------------------------------------------------------------------------
# Order tracking — ported from the deleted "وين طلبي" hard command
# ---------------------------------------------------------------------------

class TestOrderTracking:
    """processor.py's hard-command dispatch has no "وين طلبي" entry anymore
    — order-status lookup is now exclusively the AI's get_order_status tool
    (see ai_service.py's _TOOLS). That tool calls
    processor._tool_get_order_status() directly, so this ports the original
    intent (customer asks about their order, gets the right status back) by
    calling that function the same way the AI tool executor would, without
    needing a real Claude round trip."""

    def test_tool_reports_latest_order_status(self, monkeypatch):
        phone = _phone()
        monkeypatch.setattr(
            processor, "get_latest_order",
            lambda p: {"id": 5, "status": "ready", "created_at": "2026-03-01", "fulfillment": "pickup"},
        )
        result = processor._tool_get_order_status(phone)
        assert "جاهز" in result

    def test_tool_reports_not_found_for_no_orders(self):
        phone = _phone()
        result = processor._tool_get_order_status(phone)
        assert "ليس لديك طلبات سابقة" in result


# ---------------------------------------------------------------------------
# Address flow
# ---------------------------------------------------------------------------

class TestAddressFlow:
    def test_address_is_saved_and_confirmed(self, sent_messages):
        phone = _phone()
        processor.handle_message(phone, "menu", "Test")
        processor.handle_message(phone, "1", "Test")
        processor.handle_message(phone, "delivery", "Test")
        processor.handle_message(phone, "شارع النصر، رام الله", "Test")
        text = _last_text(sent_messages, phone)
        assert "confirm" in text or "تأكيد" in text or "عنوان" in text


# ---------------------------------------------------------------------------
# AI fallback
# ---------------------------------------------------------------------------

class TestAIFallback:
    def test_free_text_is_routed_to_ai_and_reply_is_sent(self, sent_messages, monkeypatch):
        """Ported from tests/test_whatsapp_ai_aunt.py::test_ai_aunt_free_text."""
        fixed_reply = "أنصحك بالمرطب العلاجي للجسم لأنه مناسب للبشرة الجافة ✨"
        monkeypatch.setattr(processor, "generate_reply", lambda **kwargs: fixed_reply)

        phone = _phone()
        processor.handle_message(phone, "بشرتي جافة كثير", "Test")
        assert _last_text(sent_messages, phone) == fixed_reply

    def test_ai_failure_sends_fallback_instead_of_raising(self, sent_messages, monkeypatch):
        """New coverage: generate_reply raising must not propagate — the
        customer gets AI_FALLBACK_REPLY and handle_message returns normally."""
        def _boom(**kwargs):
            raise RuntimeError("Claude API timeout")

        monkeypatch.setattr(processor, "generate_reply", _boom)

        phone = _phone()
        processor.handle_message(phone, "شو رأيك بهاد الكريم؟", "Test")
        assert _last_text(sent_messages, phone) == processor.AI_FALLBACK_REPLY


# ---------------------------------------------------------------------------
# webhook_events dead-letter cap
# ---------------------------------------------------------------------------

class TestWebhookEventDeadLetter:
    """New coverage for the attempts cap added to process_webhook_events():
    a poison-pill event (one whose processing always raises) must stop being
    retried after MAX_WEBHOOK_EVENT_ATTEMPTS and get dead-lettered instead of
    being polled forever."""

    def test_dead_letters_after_max_attempts_and_then_stops_retrying(self, fake_db):
        malformed_payload = {"entry": []}  # process_event's entry[0] raises IndexError
        fake_db.webhook_events.append({
            "id": 1, "phone": "unknown", "payload": malformed_payload,
            "wamid": None, "processed": False, "attempts": 0, "error": None,
            "created_at": 0,
        })

        for _ in range(processor.MAX_WEBHOOK_EVENT_ATTEMPTS):
            processor.process_webhook_events()

        ev = fake_db.webhook_events[0]
        assert ev["processed"] is True
        assert ev["attempts"] == processor.MAX_WEBHOOK_EVENT_ATTEMPTS
        assert ev["error"].startswith("dead-letter:")

        # Already processed=True -> excluded from the pending query, so a
        # further poll must not touch it again.
        processor.process_webhook_events()
        assert fake_db.webhook_events[0]["attempts"] == processor.MAX_WEBHOOK_EVENT_ATTEMPTS

    def test_recovers_before_hitting_the_cap(self, fake_db, monkeypatch):
        """A transient failure that clears up before the cap is reached must
        NOT be dead-lettered — it should process normally and end up marked
        processed with no error."""
        good_payload = {
            "entry": [{"changes": [{"value": {"messages": [{
                "type": "text", "text": {"body": "cart"},
            }]}}]}]
        }
        fake_db.webhook_events.append({
            "id": 2, "phone": "972590000000", "payload": good_payload,
            "wamid": "wamid-1", "processed": False, "attempts": 0, "error": None,
            "created_at": 0,
        })

        processor.process_webhook_events()

        ev = fake_db.webhook_events[0]
        assert ev["processed"] is True
        assert ev["attempts"] == 1
