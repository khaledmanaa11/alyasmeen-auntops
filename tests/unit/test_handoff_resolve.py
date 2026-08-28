"""test_handoff_resolve.py — Unit tests for app.services.handoff.

Follows tests/unit/test_operator_sessions.py's style: query/execute are
monkeypatched AS BOUND INTO app.services.handoff with an in-memory fake that
routes on keyword-matching the raw SQL text (see tests/conftest.py's module
docstring for why patching app.db.database itself would not work).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import app.services.handoff as handoff


class FakeHandoffDB:
    """In-memory stand-in for the handoffs/sessions/chat_history tables that
    app.services.handoff reads and writes."""

    def __init__(self) -> None:
        self.handoffs: dict[str, dict] = {}
        self.sessions: dict[str, dict] = {}
        self.chat_history: dict[str, list[dict]] = {}
        self.handoff_updates: list[tuple[str, tuple]] = []
        self.session_updates: list[tuple[str, tuple]] = []

    # -- SELECT ----------------------------------------------------------

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        s = sql.upper()

        if "SELECT ID, PHONE, STATUS FROM HANDOFFS" in s:
            (handoff_id,) = params
            row = self.handoffs.get(handoff_id)
            if not row:
                return []
            return [{"id": row["id"], "phone": row["phone"], "status": row["status"]}]

        if "COUNT(*) AS COUNT" in s and "FROM HANDOFFS" in s:
            count = sum(1 for h in self.handoffs.values() if h["status"] == "active")
            return [{"count": count}]

        if "MAX(CREATED_AT)" in s and "FROM CHAT_HISTORY" in s:
            (phone,) = params
            turns = [t for t in self.chat_history.get(phone, []) if t["role"] == "assistant"]
            if not turns:
                return [{"last_at": None}]
            return [{"last_at": max(t["created_at"] for t in turns)}]

        if "PAUSED FROM SESSIONS" in s:
            (phone,) = params
            row = self.sessions.get(phone)
            return [{"paused": row["paused"]}] if row else []

        return []

    # -- INSERT / UPDATE ---------------------------------------------------

    def execute(self, sql: str, params: tuple = ()) -> None:
        s = sql.upper()

        if "UPDATE HANDOFFS SET STATUS = 'RESOLVED'" in s:
            self.handoff_updates.append((sql, params))
            resolved_by, handoff_id = params
            row = self.handoffs.get(handoff_id)
            if row and row["status"] == "active":
                row["status"] = "resolved"
                row["resolved_by"] = resolved_by
            return

        if "UPDATE SESSIONS SET PAUSED = FALSE" in s:
            self.session_updates.append((sql, params))
            (phone,) = params
            self.sessions.setdefault(phone, {"paused": False})["paused"] = False
            return

        # audit.log_action's INSERT — irrelevant to these tests, no-op.
        return


@pytest.fixture()
def fake_handoff_db(monkeypatch) -> FakeHandoffDB:
    fake = FakeHandoffDB()
    monkeypatch.setattr(handoff, "query", fake.query)
    monkeypatch.setattr(handoff, "execute", fake.execute)
    # handoff.resolve() lazily imports app.services.audit and calls
    # log_action — patch it to a no-op so these tests never touch the real
    # audit_logs write path (that behaviour is covered by test_audit.py).
    import app.services.audit as audit

    monkeypatch.setattr(audit, "log_action", lambda *a, **k: None)
    return fake


# ---------------------------------------------------------------------------
# resolve()
# ---------------------------------------------------------------------------

class TestResolve:
    def test_resolve_active_handoff_returns_true_and_updates_both_tables(self, fake_handoff_db):
        fake_handoff_db.handoffs["h1"] = {"id": "h1", "phone": "+972500000001", "status": "active"}

        result = handoff.resolve("h1", "aunt@alyasmeen.org")

        assert result is True
        assert fake_handoff_db.handoffs["h1"]["status"] == "resolved"
        assert len(fake_handoff_db.handoff_updates) == 1
        assert len(fake_handoff_db.session_updates) == 1
        assert fake_handoff_db.session_updates[0][1] == ("+972500000001",)

    def test_resolve_already_resolved_returns_false_and_issues_no_update(self, fake_handoff_db):
        fake_handoff_db.handoffs["h1"] = {"id": "h1", "phone": "+972500000001", "status": "resolved"}

        result = handoff.resolve("h1", "aunt@alyasmeen.org")

        assert result is False
        assert fake_handoff_db.handoff_updates == []
        assert fake_handoff_db.session_updates == []

    def test_resolve_missing_id_returns_false(self, fake_handoff_db):
        result = handoff.resolve("does-not-exist", "aunt@alyasmeen.org")

        assert result is False
        assert fake_handoff_db.handoff_updates == []
        assert fake_handoff_db.session_updates == []


# ---------------------------------------------------------------------------
# active_count()
# ---------------------------------------------------------------------------

def test_active_count_returns_the_count(fake_handoff_db):
    fake_handoff_db.handoffs["h1"] = {"id": "h1", "phone": "+972500000001", "status": "active"}
    fake_handoff_db.handoffs["h2"] = {"id": "h2", "phone": "+972500000002", "status": "active"}
    fake_handoff_db.handoffs["h3"] = {"id": "h3", "phone": "+972500000003", "status": "resolved"}

    assert handoff.active_count() == 2


# ---------------------------------------------------------------------------
# bot_recently_active()
# ---------------------------------------------------------------------------

class TestBotRecentlyActive:
    def test_returns_none_when_no_assistant_message_ever_sent(self, fake_handoff_db):
        assert handoff.bot_recently_active("+972500000001") is None

    def test_returns_none_when_last_assistant_message_is_older_than_window(self, fake_handoff_db):
        old = datetime.now(timezone.utc) - timedelta(minutes=30)
        fake_handoff_db.chat_history["+972500000001"] = [
            {"role": "assistant", "content": "hi", "created_at": old},
        ]

        assert handoff.bot_recently_active("+972500000001") is None

    def test_returns_dict_when_last_assistant_message_is_inside_window(self, fake_handoff_db):
        recent = datetime.now(timezone.utc) - timedelta(minutes=1)
        fake_handoff_db.chat_history["+972500000001"] = [
            {"role": "assistant", "content": "hi", "created_at": recent},
        ]
        fake_handoff_db.sessions["+972500000001"] = {"paused": True}

        result = handoff.bot_recently_active("+972500000001")

        assert result is not None
        assert result["paused"] is True
        assert result["last_activity"] == recent.isoformat()
