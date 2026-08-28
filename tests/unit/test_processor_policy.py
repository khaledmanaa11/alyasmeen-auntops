"""
test_processor_policy.py — Unit tests for 03-05: the deterministic policy
gate wired into the AI tool executor, the request_human_handoff tool, and
AI-failure escalation.

Follows tests/unit/test_processor.py's/test_processor_safety.py's
conventions exactly: calls processor.handle_message() directly (no HTTP
layer), with the DB and WhatsApp sender faked via conftest.py's autouse
mock_db fixture (fake_db, sent_messages). Customer-facing sends go through
outbox_jobs, so every test that asserts on sent_messages calls flush_outbox()
first.

Everything is driven through the real handle_message() with
processor.generate_reply monkeypatched to a stub (_ai_calling) that invokes
the supplied tool_executor — that exercises the genuine executor closure
(policy.validate() -> dispatch) without ever making a real Claude API call.
"""
import random

import pytest

import app.services.processor as processor
from tests.conftest import last_handoff

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


def _ai_calling(tool_name, args, final="تمام"):
    """A generate_reply() stub that invokes the real tool_executor closure
    (so policy.validate() genuinely runs) and then returns `final` as
    Claude's own conversational reply — exactly the two-call agentic loop's
    shape, without any real Anthropic API call."""
    def _fake(**kwargs):
        kwargs["tool_executor"](tool_name, args)
        return final
    return _fake


# ---------------------------------------------------------------------------
# The policy gate blocks bad tool calls before they touch state
# ---------------------------------------------------------------------------

class TestPolicyGateBlocksBadToolCalls:
    def test_hallucinated_product_is_not_added_to_cart(self, sent_messages, fake_db, flush_outbox, monkeypatch):
        monkeypatch.setattr(
            processor, "generate_reply",
            _ai_calling("add_to_cart", {"product_name": "منتج غير موجود", "qty": 1}, final="ما لقيت هالمنتج للأسف"),
        )
        phone = _phone()
        processor.handle_message(phone, "عندي سؤال عن منتج", "Test")
        flush_outbox()

        assert fake_db.sessions[phone]["cart"] == []
        # The denial is Claude's problem to phrase around, not a crash —
        # the customer still gets a normal reply.
        assert _last_text(sent_messages, phone) == "ما لقيت هالمنتج للأسف"

    def test_quantity_is_clamped_before_the_cart_is_touched(self, sent_messages, fake_db, flush_outbox, monkeypatch):
        monkeypatch.setattr(
            processor, "generate_reply",
            _ai_calling("add_to_cart", {"product_name": "كريم اليدين", "qty": 999}, final="تمام أضفتلك"),
        )
        phone = _phone()
        processor.handle_message(phone, "بدي كمية كبيرة كريم اليدين", "Test")
        flush_outbox()

        cart = fake_db.sessions[phone]["cart"]
        assert len(cart) == 1
        assert cart[0]["qty"] == processor.MAX_CART_QTY

    def test_short_address_is_not_saved(self, sent_messages, fake_db, flush_outbox, monkeypatch):
        monkeypatch.setattr(
            processor, "generate_reply",
            _ai_calling("save_address", {"address": "رام الله"}, final="وين بالضبط؟"),
        )
        phone = _phone()
        processor.handle_message(phone, "عنواني رام الله", "Test")
        flush_outbox()

        # upsert_customer() has already created the customers row by the
        # time the tool would run — its saved_address must stay untouched.
        assert fake_db.customers[phone]["saved_address"] == ""
        assert fake_db.sessions[phone]["stage"] != "confirm"

    def test_canonical_product_name_is_used(self, sent_messages, fake_db, flush_outbox, monkeypatch):
        monkeypatch.setattr(
            processor, "generate_reply",
            _ai_calling("add_to_cart", {"product_name": "كريم", "qty": 1}, final="تمام أضفتلك"),
        )
        phone = _phone()
        processor.handle_message(phone, "بدي كريم", "Test")
        flush_outbox()

        cart = fake_db.sessions[phone]["cart"]
        assert len(cart) == 1
        assert cart[0]["name"] == "كريم اليدين"
        assert cart[0]["price"] == 25.0

    def test_unknown_tool_is_denied_and_escalates(self, fake_db):
        phone = _phone()
        st = {"cart": []}
        executor = processor._make_tool_executor(phone, st, st["cart"])

        executor("delete_everything", {"anything": "goes"})

        row = last_handoff(fake_db, phone)
        assert row is not None
        assert row["reason"] == "policy_denied"

    def test_no_extra_database_read_for_non_order_tools(self, fake_db, monkeypatch):
        def _boom(phone):
            raise AssertionError("get_latest_order should not be called for a non-order tool")

        monkeypatch.setattr(processor, "get_latest_order", _boom)

        phone = _phone()
        st = {"cart": []}
        executor = processor._make_tool_executor(phone, st, st["cart"])

        # Neither call raises — the lazy order_status_provider lambda is
        # never invoked because show_menu/add_to_cart are not order-scoped.
        executor("show_menu", {"category": ""})
        executor("add_to_cart", {"product_name": "كريم اليدين", "qty": 1})


# ---------------------------------------------------------------------------
# request_human_handoff tool — real handoff, exactly one message
# ---------------------------------------------------------------------------

class TestRequestHumanHandoffTool:
    def test_tool_opens_handoff_and_pauses_session(self, sent_messages, fake_db, flush_outbox, monkeypatch):
        monkeypatch.setattr(
            processor, "generate_reply",
            _ai_calling("request_human_handoff", {"reason": "الزبونة محتاجة متابعة خاصة"}, final="رح احولك لحنان"),
        )
        phone = _phone()
        processor.handle_message(phone, "عندي طلب خاص", "Test")
        flush_outbox()

        row = last_handoff(fake_db, phone)
        assert row is not None
        assert row["reason"] == "ai_requested"
        assert fake_db.sessions[phone]["paused"] is True

    def test_customer_receives_exactly_one_message_and_it_is_the_ack(self, sent_messages, fake_db, flush_outbox, monkeypatch):
        """The double-message regression test: the model's own `final` reply
        must NOT reach the customer once the tool opened a handoff — only
        the deterministic HANDOFF_ACK_REPLY does."""
        monkeypatch.setattr(
            processor, "generate_reply",
            _ai_calling("request_human_handoff", {"reason": "test"}, final="رح احولك لحنان خلال ساعة أكيد"),
        )
        phone = _phone()
        processor.handle_message(phone, "عندي طلب خاص", "Test")
        flush_outbox()

        to_customer = [m for m in sent_messages if m["to"] == phone]
        assert len(to_customer) == 1
        assert to_customer[0]["text"] == processor.HANDOFF_ACK_REPLY

    def test_failed_handoff_write_does_not_promise_an_escalation(self, sent_messages, fake_db, flush_outbox, monkeypatch):
        def _boom(*args, **kwargs):
            raise RuntimeError("handoffs insert failed")

        monkeypatch.setattr(processor.handoff, "trigger", _boom)
        monkeypatch.setattr(
            processor, "generate_reply",
            _ai_calling("request_human_handoff", {"reason": "test"}, final="بعتذر، صار خلل تقني"),
        )
        phone = _phone()
        processor.handle_message(phone, "عندي طلب خاص", "Test")
        flush_outbox()

        # No durable write happened, so the customer gets the model's own
        # (honest, apologetic) reply — never the ack that would promise an
        # escalation that did not actually occur.
        assert _last_text(sent_messages, phone) == "بعتذر، صار خلل تقني"
        assert last_handoff(fake_db, phone) is None


# ---------------------------------------------------------------------------
# AI-failure escalation
# ---------------------------------------------------------------------------

class TestAIFailureEscalation:
    def test_ai_unavailable_sends_fallback_and_opens_handoff(self, sent_messages, fake_db, flush_outbox, monkeypatch):
        def _boom(**kwargs):
            raise processor.AIUnavailableError("CLAUDE_API_KEY missing")

        monkeypatch.setattr(processor, "generate_reply", _boom)

        phone = _phone()
        processor.handle_message(phone, "عندي سؤال عن المنتجات", "Test")
        flush_outbox()

        assert _last_text(sent_messages, phone) == processor.AI_FALLBACK_REPLY
        row = last_handoff(fake_db, phone)
        assert row is not None
        assert row["reason"] == "ai_failure"
        assert fake_db.sessions[phone]["paused"] is True

    def test_generic_exception_also_escalates(self, sent_messages, fake_db, flush_outbox, monkeypatch):
        def _boom(**kwargs):
            raise RuntimeError("Claude API timeout")

        monkeypatch.setattr(processor, "generate_reply", _boom)

        phone = _phone()
        processor.handle_message(phone, "عندي سؤال عن المنتجات", "Test")
        flush_outbox()

        assert _last_text(sent_messages, phone) == processor.AI_FALLBACK_REPLY
        row = last_handoff(fake_db, phone)
        assert row is not None
        assert row["reason"] == "ai_failure"
        assert fake_db.sessions[phone]["paused"] is True

    def test_second_message_during_ai_outage_does_not_open_a_second_handoff(self, sent_messages, fake_db, flush_outbox, monkeypatch):
        """The paused gate (03-04) short-circuits the second message before
        it ever reaches the AI call, and handoff.trigger() is idempotent —
        together these must produce exactly one handoff row and exactly one
        aunt notification per customer during an outage, not an alert
        storm."""
        monkeypatch.setattr(processor.Config, "AUNT_PHONE", "972590000001")

        def _boom(**kwargs):
            raise RuntimeError("Claude API down")

        monkeypatch.setattr(processor, "generate_reply", _boom)

        phone = _phone()
        processor.handle_message(phone, "عندي سؤال عن المنتجات", "Test")
        processor.handle_message(phone, "لسا بستنى رد", "Test")
        flush_outbox()

        handoff_rows = [h for h in fake_db.handoffs if h["phone"] == phone]
        assert len(handoff_rows) == 1

        aunt_jobs = [j for j in fake_db.outbox_jobs if j["phone"] == "972590000001"]
        assert len(aunt_jobs) == 1


# ---------------------------------------------------------------------------
# Paused session blocks every tool, not just the message pipeline's gate
# ---------------------------------------------------------------------------

class TestPausedSessionBlocksTools:
    def test_tools_are_denied_while_paused(self, fake_db):
        phone = _phone()
        st = {"cart": [], "paused": True}
        cart = st["cart"]
        executor = processor._make_tool_executor(phone, st, cart)

        executor("add_to_cart", {"product_name": "كريم اليدين", "qty": 1})

        assert cart == []
