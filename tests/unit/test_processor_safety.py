"""
test_processor_safety.py — Unit tests for the two deterministic handoff
triggers wired directly into the message pipeline (03-04): the paused gate,
keyword-triggered handoff, and unsupported-media handoff.

Follows tests/unit/test_processor.py's conventions exactly: calls
processor.handle_message()/process_event() directly (no HTTP layer), with
the DB and WhatsApp sender faked via conftest.py's autouse mock_db fixture
(fake_db, sent_messages). Customer-facing sends go through outbox_jobs, so
every test that asserts on sent_messages calls flush_outbox() first.

app.services.handoff is now part of conftest.py's shared autouse mock_db
patch list (see that fixture's docstring), so handoff.trigger() calls made
through these tests land in the same fake_db passed in — no local/dedicated
fake DB needed here, unlike tests/unit/test_handoff_trigger.py.
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


def _seed_paused_session(fake_db, phone, **overrides):
    """Seed a sessions row that already has paused=True, matching the shape
    tests/conftest.py's FakeDB stores (see FakeDB._default_session)."""
    row = {
        "stage": "root", "cart": [], "fulfillment": None,
        "menu_products": [], "address": "", "paused": True,
    }
    row.update(overrides)
    fake_db.sessions[phone] = row
    return row


# ---------------------------------------------------------------------------
# Paused gate
# ---------------------------------------------------------------------------

class TestPausedGate:
    def test_paused_session_sends_nothing(self, sent_messages, fake_db, flush_outbox):
        phone = _phone()
        _seed_paused_session(fake_db, phone)

        processor.handle_message(phone, "شكراً", "Test")
        flush_outbox()

        assert sent_messages == []
        assert fake_db.outbox_jobs == []

    def test_paused_session_still_records_the_customer_message(self, fake_db):
        phone = _phone()
        _seed_paused_session(fake_db, phone)

        processor.handle_message(phone, "لسا مستنية رد", "Test")

        recorded = [h for h in fake_db.history.get(phone, []) if h["role"] == "user"]
        assert any(h["content"] == "لسا مستنية رد" for h in recorded)

    def test_paused_session_ignores_hard_commands(self, fake_db):
        phone = _phone()
        _seed_paused_session(
            phone=phone, fake_db=fake_db,
            cart=[{"name": "كريم اليدين", "qty": 1, "price": 25.0}],
            fulfillment="pickup",
        )

        processor.handle_message(phone, "confirm", "Test")

        assert fake_db.orders == []

    def test_unpaused_session_still_replies(self, sent_messages, fake_db, flush_outbox):
        """Regression guard: the paused gate must not break the normal path
        for a session that was never paused."""
        phone = _phone()
        processor.handle_message(phone, "cart", "Test")
        flush_outbox()
        assert "فارغة" in _last_text(sent_messages, phone)


# ---------------------------------------------------------------------------
# Keyword-triggered handoff
# ---------------------------------------------------------------------------

class TestKeywordHandoff:
    def test_arabic_request_for_human_opens_handoff(self, sent_messages, fake_db, flush_outbox):
        phone = _phone()
        processor.handle_message(phone, "بدي احكي مع حنان مش بوت", "Test")
        flush_outbox()

        row = last_handoff(fake_db, phone)
        assert row is not None
        assert row["reason"] == "keyword_request"
        assert fake_db.sessions[phone]["paused"] is True

        assert [m["to"] for m in sent_messages] == [phone]
        assert _last_text(sent_messages, phone) == processor.HANDOFF_ACK_REPLY

    def test_english_request_for_human_opens_handoff(self, sent_messages, fake_db, flush_outbox):
        phone = _phone()
        processor.handle_message(phone, "I want to talk to a human please", "Test")
        flush_outbox()

        row = last_handoff(fake_db, phone)
        assert row is not None
        assert row["reason"] == "keyword_request"
        assert _last_text(sent_messages, phone) == processor.HANDOFF_ACK_REPLY

    def test_ordinary_message_does_not_open_handoff(self, sent_messages, fake_db, flush_outbox, monkeypatch):
        monkeypatch.setattr(processor, "generate_reply", lambda **kwargs: "جربي المرطب اليومي 🌿")

        phone = _phone()
        processor.handle_message(phone, "بشرتي جافة", "Test")
        flush_outbox()

        assert last_handoff(fake_db, phone) is None

    def test_keyword_wins_over_hard_command_ordering(self, sent_messages, fake_db, flush_outbox):
        """Even a message containing a hard-command word (here 'cart') is
        routed to the handoff when it also contains an escalation phrase —
        the keyword gate in handle_message runs before the hard-command
        dispatch, not after."""
        phone = _phone()
        processor.handle_message(phone, "بدي احكي مع حنان cart", "Test")
        flush_outbox()

        row = last_handoff(fake_db, phone)
        assert row is not None
        assert row["reason"] == "keyword_request"
        assert _last_text(sent_messages, phone) == processor.HANDOFF_ACK_REPLY

    def test_handoff_write_failure_still_replies(self, sent_messages, fake_db, flush_outbox, monkeypatch):
        def _boom(*args, **kwargs):
            raise RuntimeError("handoffs insert failed")

        monkeypatch.setattr(processor.handoff, "trigger", _boom)

        phone = _phone()
        processor.handle_message(phone, "بدي احكي مع حنان", "Test")
        flush_outbox()

        assert _last_text(sent_messages, phone) == processor.AI_FALLBACK_REPLY
