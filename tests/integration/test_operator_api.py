"""test_operator_api.py — Integration tests for the handoffs + audit JSON
API (app/routers/operator_api.py). Auth is injected via the operator_client
fixture (tests/conftest.py) — a FastAPI dependency override, same pattern as
test_orders_api.py / test_ui_api.py / test_alerts_api.py.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["USE_MOCK_WHATSAPP"] = "1"

import app.routers.operator_api as operator_api  # noqa: E402
import app.services.audit as audit  # noqa: E402
import app.services.handoff as handoff  # noqa: E402

FAKE_HANDOFF = {
    "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    "phone": "+972591234567",
    "reason": "تحتاج مساعدة",
    "status": "active",
    "assigned_to": None,
    "created_at": "2026-08-28T10:00:00Z",
    "resolved_at": None,
    "metadata": {},
    "customer_name": "فاطمة",
}


# ---------------------------------------------------------------------------
# Auth — every route 401s unauthenticated
# ---------------------------------------------------------------------------

class TestOperatorApiAuth:
    def test_list_handoffs_requires_auth(self, client):
        assert client.get("/api/handoffs").status_code == 401

    def test_handoffs_count_requires_auth(self, client):
        assert client.get("/api/handoffs/count").status_code == 401

    def test_handoff_detail_requires_auth(self, client):
        assert client.get("/api/handoffs/some-id").status_code == 401

    def test_resolve_handoff_requires_auth(self, client):
        assert client.post("/api/handoffs/some-id/resolve").status_code == 401

    def test_audit_requires_auth(self, client):
        assert client.get("/api/audit").status_code == 401


# ---------------------------------------------------------------------------
# GET /api/handoffs
# ---------------------------------------------------------------------------

class TestHandoffsList:
    def test_returns_customer_name_and_wa_link(self, operator_client, monkeypatch):
        monkeypatch.setattr(operator_api, "query", lambda sql, params=(): [dict(FAKE_HANDOFF)])

        r = operator_client.get("/api/handoffs")

        assert r.status_code == 200
        rows = r.json()["handoffs"]
        assert len(rows) == 1
        assert rows[0]["customer_name"] == "فاطمة"
        assert rows[0]["wa_link"] == "https://wa.me/972591234567"

    def test_status_resolved_passes_status_param(self, operator_client, monkeypatch):
        captured = {}

        def fake_query(sql, params=()):
            captured["sql"] = sql
            captured["params"] = params
            return []

        monkeypatch.setattr(operator_api, "query", fake_query)

        r = operator_client.get("/api/handoffs?status=resolved")

        assert r.status_code == 200
        assert captured["params"] == ("resolved",)
        assert "h.status = %s" in captured["sql"]

    def test_invalid_status_is_400(self, operator_client):
        r = operator_client.get("/api/handoffs?status=bogus")
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/handoffs/count — must not be captured by {handoff_id}
# ---------------------------------------------------------------------------

class TestHandoffsCount:
    def test_returns_active_count_not_captured_by_handoff_id_route(self, operator_client, monkeypatch):
        """If GET /api/handoffs/{handoff_id} were registered before /count,
        FastAPI would treat 'count' as a handoff_id and this would 404 or
        return a handoff-shaped body instead of the count shape."""
        monkeypatch.setattr(handoff, "query", lambda sql, params=(): [{"count": 3}])

        r = operator_client.get("/api/handoffs/count")

        assert r.status_code == 200
        assert r.json() == {"active": 3}


# ---------------------------------------------------------------------------
# GET /api/handoffs/{handoff_id}
# ---------------------------------------------------------------------------

class TestHandoffDetail:
    def test_returns_transcript_in_chronological_order(self, operator_client, monkeypatch):
        def fake_query(sql, params=()):
            if "chat_history" in sql:
                # Mirrors the real "ORDER BY created_at DESC LIMIT %s" — rows
                # arrive newest-first; the handler reverses them back to
                # chronological order.
                return [
                    {"role": "user", "content": "msg3", "created_at": "2026-08-28T10:02:00Z"},
                    {"role": "assistant", "content": "msg2", "created_at": "2026-08-28T10:01:00Z"},
                    {"role": "user", "content": "msg1", "created_at": "2026-08-28T10:00:00Z"},
                ]
            return [dict(FAKE_HANDOFF)]

        monkeypatch.setattr(operator_api, "query", fake_query)

        r = operator_client.get(f"/api/handoffs/{FAKE_HANDOFF['id']}")

        assert r.status_code == 200
        data = r.json()
        assert data["reason"] == FAKE_HANDOFF["reason"]
        assert data["wa_link"] == "https://wa.me/972591234567"
        contents = [t["content"] for t in data["transcript"]]
        assert contents == ["msg1", "msg2", "msg3"]

    def test_404_on_unknown_id(self, operator_client, monkeypatch):
        monkeypatch.setattr(operator_api, "query", lambda sql, params=(): [])

        r = operator_client.get("/api/handoffs/unknown-id")

        assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/handoffs/{handoff_id}/resolve
# ---------------------------------------------------------------------------

class TestResolveHandoff:
    def test_resolve_once_then_409_on_second_call(self, operator_client, monkeypatch):
        state = {"status": "active"}

        def fake_query(sql, params=()):
            return [{"id": FAKE_HANDOFF["id"], "phone": FAKE_HANDOFF["phone"], "status": state["status"]}]

        def fake_execute(sql, params=()):
            if "UPDATE handoffs" in sql:
                state["status"] = "resolved"

        monkeypatch.setattr(handoff, "query", fake_query)
        monkeypatch.setattr(handoff, "execute", fake_execute)
        monkeypatch.setattr(audit, "execute", lambda sql, params=(): None)

        r1 = operator_client.post(f"/api/handoffs/{FAKE_HANDOFF['id']}/resolve")
        assert r1.status_code == 200
        assert r1.json() == {"ok": True}

        r2 = operator_client.post(f"/api/handoffs/{FAKE_HANDOFF['id']}/resolve")
        assert r2.status_code == 409
        assert r2.json() == {"ok": False, "detail": "already resolved"}


# ---------------------------------------------------------------------------
# GET /api/audit
# ---------------------------------------------------------------------------

class TestAuditTrail:
    def test_returns_entries_and_clamps_excessive_limit(self, operator_client, monkeypatch):
        captured = {}

        def fake_query(sql, params=()):
            captured["params"] = params
            return [{
                "id": "1", "actor": "aunt@alyasmeen.org", "action": "handoff_resolved",
                "details": {}, "created_at": "2026-08-28T10:00:00Z",
            }]

        monkeypatch.setattr(audit, "query", fake_query)

        r = operator_client.get("/api/audit?limit=9999")

        assert r.status_code == 200
        entries = r.json()["entries"]
        assert len(entries) == 1
        assert entries[0]["action"] == "handoff_resolved"
        assert captured["params"][-1] == 500
