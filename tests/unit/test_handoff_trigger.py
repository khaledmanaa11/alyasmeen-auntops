"""test_handoff_trigger.py — Unit tests for app.services.handoff.trigger().

Follows tests/unit/test_handoff_resolve.py's established pattern: a local
FakeHandoffDB + a fake_handoff_db fixture that monkeypatches
query/execute/execute_returning ON app.services.handoff directly — never on
app.db.database (see Pitfall 1 in 03-RESEARCH.md and tests/conftest.py's own
module docstring: patching the wrong reference silently reaches the LIVE
production Supabase project, which has already happened twice in this
repo's history, both during Phase 5).

app.services.handoff is deliberately NOT in tests/conftest.py's shared
autouse mock_db patch list (only wh/processor/audit are), so every test in
this file is fully self-contained and does not rely on that fixture at all.

processor.queue_text is patched directly (via the `queued` fixture below)
rather than letting it fall through to the outbox table — this asserts the
notification without needing a fake outbox_jobs table, and matches the
plan's instruction to keep this file's fake DB scoped to what trigger()
itself touches (handoffs, sessions, customers).
"""
from __future__ import annotations

import pytest

import app.services.audit as audit
import app.services.handoff as handoff
import app.services.processor as processor
from app.services.audit import OPERATOR_ACTIONS
from app.services.config import Config

PHONE = "+972500000009"


class FakeHandoffDB:
    """In-memory stand-in for the handoffs/sessions/customers tables that
    trigger() reads and writes."""

    def __init__(self) -> None:
        self.handoffs: dict[str, dict] = {}
        self.sessions: dict[str, dict] = {}
        self.customers: dict[str, dict] = {}
        self._next_id = 0

    # -- SELECT ----------------------------------------------------------

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        s = sql.upper()

        if "SELECT ID FROM HANDOFFS WHERE PHONE" in s:
            (phone,) = params
            actives = [
                h for h in self.handoffs.values()
                if h["phone"] == phone and h["status"] == "active"
            ]
            if not actives:
                return []
            newest = sorted(actives, key=lambda h: h["created_at"])[-1]
            return [{"id": newest["id"]}]

        if "SELECT NAME FROM CUSTOMERS" in s:
            (phone,) = params
            row = self.customers.get(phone)
            return [{"name": row["name"]}] if row else []

        return []

    # -- INSERT / UPDATE ---------------------------------------------------

    def execute(self, sql: str, params: tuple = ()) -> None:
        s = sql.upper()

        if "INSERT INTO SESSIONS (PHONE, PAUSED)" in s:
            (phone,) = params
            self.sessions.setdefault(phone, {})["paused"] = True
            return

        # Anything else (e.g. a stray audit INSERT) is irrelevant to these
        # tests — audit.log_action is patched separately below, so this
        # branch should never actually fire.
        return

    def execute_returning(self, sql: str, params: tuple = ()) -> dict | None:
        s = sql.upper()

        if "INSERT INTO HANDOFFS" in s:
            phone, reason, assigned_to, metadata = params
            self._next_id += 1
            handoff_id = f"h{self._next_id}"
            self.handoffs[handoff_id] = {
                "id": handoff_id,
                "phone": phone,
                "reason": reason,
                "status": "active",
                "assigned_to": assigned_to,
                "metadata": metadata,
                "created_at": self._next_id,
            }
            return {"id": handoff_id}

        return None


@pytest.fixture()
def fake_handoff_db(monkeypatch) -> FakeHandoffDB:
    fake = FakeHandoffDB()
    monkeypatch.setattr(handoff, "query", fake.query)
    monkeypatch.setattr(handoff, "execute", fake.execute)
    monkeypatch.setattr(handoff, "execute_returning", fake.execute_returning)

    # trigger() lazily imports app.services.audit and calls log_action — a
    # no-op here so these tests never touch the real audit_logs write path
    # (covered separately by test_audit.py and, for the action-string
    # assertion specifically, by test_writes_handoff_triggered_audit_action
    # below which overrides this with its own spy).
    monkeypatch.setattr(audit, "log_action", lambda *a, **k: None)

    return fake


@pytest.fixture()
def queued(monkeypatch) -> list[tuple[str, str]]:
    """Captures every processor.queue_text(phone, text) call trigger()
    makes, without a fake outbox table."""
    sent: list[tuple[str, str]] = []

    def fake_queue_text(phone: str, text: str) -> None:
        sent.append((phone, text))

    monkeypatch.setattr(processor, "queue_text", fake_queue_text)
    return sent


@pytest.fixture(autouse=True)
def _fixed_phones(monkeypatch):
    """Every test in this file sets its own AUNT_PHONE/ADMIN_PHONE rather
    than depending on whatever happens to be in the developer's .env — the
    loop guard's correctness depends on these being distinct from PHONE."""
    monkeypatch.setattr(Config, "AUNT_PHONE", "972590000001")
    monkeypatch.setattr(Config, "ADMIN_PHONE", "972590000002")


# ---------------------------------------------------------------------------
# trigger()
# ---------------------------------------------------------------------------

class TestTrigger:
    def test_creates_active_handoff_row(self, fake_handoff_db, queued):
        handoff_id = handoff.trigger(PHONE, "keyword_request", metadata={"note": "angry"})

        assert handoff_id is not None
        row = fake_handoff_db.handoffs[handoff_id]
        assert row["status"] == "active"
        assert row["reason"] == "keyword_request"
        assert row["metadata"] == {"note": "angry"}

    def test_pauses_session_even_when_no_session_row_exists(self, fake_handoff_db, queued):
        # Regression test for the bare-UPDATE bug the plan avoids: a
        # brand-new customer's first message may be a voice note, reaching
        # trigger() before save_session() has ever run for this phone.
        assert PHONE not in fake_handoff_db.sessions

        handoff.trigger(PHONE, "unsupported_media")

        assert fake_handoff_db.sessions[PHONE]["paused"] is True

    def test_second_trigger_for_same_phone_reuses_active_handoff(self, fake_handoff_db, queued):
        first_id = handoff.trigger(PHONE, "keyword_request")
        second_id = handoff.trigger(PHONE, "keyword_request")

        assert first_id == second_id
        assert len(fake_handoff_db.handoffs) == 1
        assert len(queued) == 1

    def test_notifies_aunt_through_queue_text(self, fake_handoff_db, queued):
        fake_handoff_db.customers[PHONE] = {"name": "فاطمة"}

        handoff.trigger(PHONE, "keyword_request")

        assert len(queued) == 1
        recipient, body = queued[0]
        assert recipient == Config.AUNT_PHONE
        assert "فاطمة" in body
        assert handoff.REASON_LABELS["keyword_request"] in body

    def test_does_not_notify_when_customer_is_the_aunt(self, fake_handoff_db, queued):
        aunt_phone = Config.AUNT_PHONE

        handoff_id = handoff.trigger(aunt_phone, "keyword_request")

        # Loop guard: the handoff itself still opens (the durable state
        # transition doesn't depend on who the phone belongs to)...
        assert handoff_id is not None
        assert fake_handoff_db.handoffs[handoff_id]["phone"] == aunt_phone
        # ...but no WhatsApp alert about the aunt is ever queued to herself.
        assert queued == []

    def test_notification_failure_does_not_break_the_handoff(self, fake_handoff_db, monkeypatch):
        def _boom(*args, **kwargs):
            raise RuntimeError("outbox down")

        monkeypatch.setattr(processor, "queue_text", _boom)

        handoff_id = handoff.trigger(PHONE, "keyword_request")

        assert handoff_id is not None
        assert fake_handoff_db.handoffs[handoff_id]["status"] == "active"

    def test_writes_handoff_triggered_audit_action(self, fake_handoff_db, queued, monkeypatch):
        calls: list[tuple] = []
        monkeypatch.setattr(audit, "log_action", lambda *a, **k: calls.append(a))

        handoff.trigger(PHONE, "keyword_request")

        assert len(calls) == 1
        actor, action, details = calls[0]
        assert actor == "bot"
        assert action == "handoff_triggered"
        assert action in OPERATOR_ACTIONS
        assert details["phone"] == PHONE
        assert details["reason"] == "keyword_request"
