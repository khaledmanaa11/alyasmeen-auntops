"""test_audit.py — Unit tests for app.services.audit.

query/execute are monkeypatched AS BOUND INTO app.services.audit (see
tests/conftest.py's module docstring for why this specific seam matters).
"""
from __future__ import annotations

import pytest

import app.services.audit as audit


class FakeAuditDB:
    """In-memory stand-in for the audit_logs table."""

    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.executed: list[tuple[str, tuple]] = []

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.executed.append((sql, params))
        actor, action, details = params
        self.rows.append({
            "id": f"row-{len(self.rows) + 1}",
            "actor": actor,
            "action": action,
            "details": details,
            "created_at": "2026-08-28T00:00:00Z",
        })

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        *allowlist, limit = params
        matched = [r for r in self.rows if r["action"] in allowlist]
        return matched[:limit]


@pytest.fixture()
def fake_audit_db(monkeypatch) -> FakeAuditDB:
    fake = FakeAuditDB()
    monkeypatch.setattr(audit, "execute", fake.execute)
    monkeypatch.setattr(audit, "query", fake.query)
    return fake


# ---------------------------------------------------------------------------
# log_action()
# ---------------------------------------------------------------------------

def test_log_action_issues_insert_with_three_params(fake_audit_db):
    audit.log_action("aunt@alyasmeen.org", "handoff_resolved", {"handoff_id": "h1"})

    assert len(fake_audit_db.executed) == 1
    sql, params = fake_audit_db.executed[0]
    assert "INSERT INTO audit_logs" in sql
    assert params == ("aunt@alyasmeen.org", "handoff_resolved", {"handoff_id": "h1"})


def test_log_action_swallows_raising_execute_and_does_not_propagate(monkeypatch):
    def _raise(sql, params=()):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(audit, "execute", _raise)

    # Must not raise — a lost audit row is strictly better than a 500 on the
    # operator action being recorded.
    audit.log_action("aunt@alyasmeen.org", "handoff_resolved", {})


def test_log_action_defaults_details_to_empty_dict(fake_audit_db):
    audit.log_action("aunt@alyasmeen.org", "logout", None)

    _, params = fake_audit_db.executed[0]
    assert params[2] == {}


# ---------------------------------------------------------------------------
# list_operator_actions()
# ---------------------------------------------------------------------------

def test_list_operator_actions_passes_full_allowlist_plus_limit(monkeypatch):
    captured = {}

    def fake_query(sql, params=()):
        captured["sql"] = sql
        captured["params"] = params
        return []

    monkeypatch.setattr(audit, "query", fake_query)

    audit.list_operator_actions(limit=50)

    assert "action IN (" in captured["sql"]
    assert captured["params"] == (*audit.OPERATOR_ACTIONS, 50)


def test_list_operator_actions_excludes_customer_generated_rows(fake_audit_db):
    fake_audit_db.rows.append({
        "id": "row-x", "actor": "+972500000000", "action": "order_created",
        "details": {}, "created_at": "2026-08-28T00:00:00Z",
    })
    fake_audit_db.rows.append({
        "id": "row-y", "actor": "aunt@alyasmeen.org", "action": "handoff_resolved",
        "details": {}, "created_at": "2026-08-28T00:01:00Z",
    })

    entries = audit.list_operator_actions(limit=200)

    actions = [e["action"] for e in entries]
    assert "order_created" not in actions
    assert "handoff_resolved" in actions


def test_operator_actions_has_eighteen_entries():
    assert len(audit.OPERATOR_ACTIONS) == 18
