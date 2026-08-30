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
    def test_arabic_request_for_human_opens_handoff(
        self, sent_messages, fake_db, flush_outbox, monkeypatch
    ):
        # Pin the operator phones like test_processor.py/test_handoff_trigger.py
        # do — the suite must not depend on what the operator's real .env holds.
        monkeypatch.setattr(processor.Config, "AUNT_PHONE", "972590000001")
        monkeypatch.setattr(processor.Config, "ADMIN_PHONE", "972590000002")
        phone = _phone()
        processor.handle_message(phone, "بدي احكي مع حنان مش بوت", "Test")
        flush_outbox()

        row = last_handoff(fake_db, phone)
        assert row is not None
        assert row["reason"] == "keyword_request"
        assert fake_db.sessions[phone]["paused"] is True

        # Exactly two sends: the customer's single deterministic ack, and the
        # aunt's handoff alert (queued by handoff._notify_aunt via the outbox).
        assert sorted(m["to"] for m in sent_messages) == sorted([phone, "972590000001"])
        assert _last_text(sent_messages, phone) == processor.HANDOFF_ACK_REPLY
        aunt_msg = _last_text(sent_messages, "972590000001")
        assert "محادثات" in aunt_msg and phone in aunt_msg

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


# ---------------------------------------------------------------------------
# Unsupported media
# ---------------------------------------------------------------------------

def _media_payload(msg_type: str, name: str = "Test") -> dict:
    """A realistic Meta webhook payload for a non-text message —
    entry[0].changes[0].value.messages[0] with the given `type`."""
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{"type": msg_type}],
                    "contacts": [{"profile": {"name": name}}],
                }
            }]
        }]
    }


def _seed_webhook_event(fake_db, event_id, phone, payload):
    fake_db.webhook_events.append({
        "id": event_id, "phone": phone, "payload": payload,
        "wamid": None, "processed": False, "attempts": 0, "error": None,
        "created_at": len(fake_db.webhook_events),
    })


class TestUnsupportedMedia:
    def test_voice_note_gets_a_reply_and_a_handoff(self, sent_messages, fake_db, flush_outbox):
        phone = _phone()
        _seed_webhook_event(fake_db, 1, phone, _media_payload("audio"))

        processor.process_event(1, phone, _media_payload("audio"))
        flush_outbox()

        assert _last_text(sent_messages, phone) == processor.UNSUPPORTED_MEDIA_REPLY
        row = last_handoff(fake_db, phone)
        assert row is not None
        assert row["reason"] == "unsupported_media"
        assert fake_db.sessions[phone]["paused"] is True

    @pytest.mark.parametrize(
        "msg_type", ["audio", "image", "sticker", "document", "video", "location"]
    )
    def test_image_sticker_document_all_handled(self, sent_messages, fake_db, flush_outbox, msg_type):
        phone = _phone()
        _seed_webhook_event(fake_db, 1, phone, _media_payload(msg_type))

        processor.process_event(1, phone, _media_payload(msg_type))
        flush_outbox()

        assert _last_text(sent_messages, phone) == processor.UNSUPPORTED_MEDIA_REPLY
        row = last_handoff(fake_db, phone)
        assert row is not None
        assert row["reason"] == "unsupported_media"
        assert row["metadata"]["msg_type"] == msg_type

    def test_customer_row_is_created_for_a_first_contact_voice_note(self, fake_db, flush_outbox):
        phone = _phone()
        assert phone not in fake_db.customers

        processor.process_event(1, phone, _media_payload("audio", name="سارة"))
        flush_outbox()

        assert phone in fake_db.customers

    def test_event_is_still_marked_processed(self, fake_db, flush_outbox):
        phone = _phone()
        _seed_webhook_event(fake_db, 7, phone, _media_payload("sticker"))

        processor.process_event(7, phone, _media_payload("sticker"))
        flush_outbox()

        ev = fake_db.webhook_events[0]
        assert ev["processed"] is True
        assert ev["error"] is None

    def test_media_during_active_handoff_does_not_resend_the_apology(self, sent_messages, fake_db, flush_outbox):
        phone = _phone()
        _seed_paused_session(fake_db, phone)

        processor.process_event(1, phone, _media_payload("audio"))
        processor.process_event(2, phone, _media_payload("image"))
        flush_outbox()

        assert len(sent_messages) <= 1

    def test_text_message_path_is_unchanged(self, sent_messages, fake_db, flush_outbox):
        phone = _phone()
        text_payload = {
            "entry": [{"changes": [{"value": {"messages": [{
                "type": "text", "text": {"body": "cart"},
            }]}}]}]
        }
        _seed_webhook_event(fake_db, 1, phone, text_payload)

        processor.process_event(1, phone, text_payload)
        flush_outbox()

        assert "فارغة" in _last_text(sent_messages, phone)
        assert last_handoff(fake_db, phone) is None
