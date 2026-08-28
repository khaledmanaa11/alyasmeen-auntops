"""
test_alerts_api.py — Integration tests for the alerts API.

Covers: GET /api/alerts (dead-lettered webhook_events + permanently-failed
outbox_jobs, reframed as plain-Arabic action cards naming the customer — see
app.routers.ui_api._frame_alert), the two one-click per-item retry
endpoints, and POST /api/alerts/retry_all (bulk post-outage recovery). Auth
is injected via the operator_client fixture (tests/conftest.py) — a FastAPI
dependency override, same pattern as test_orders_api.py / test_ui_api.py.

05-06 wired audit.log_action(op.email, ...) into every mutating endpoint
here (alert_retried / alert_retry_all). Unmocked, app.services.audit hits
the REAL live Supabase instance (confirmed and cleaned up during this plan's
own development — see 05-06-SUMMARY.md) — every test below that reaches a
mutation therefore monkeypatches audit.log_action to a no-op.
"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["USE_MOCK_WHATSAPP"] = "1"


FAKE_DEAD_EVENT = {
    "id": "11111111-1111-1111-1111-111111111111",
    "phone": "972591234567",
    "payload": {"foo": "bar"},
    "error": "dead-letter: boom",
    "attempts": 3,
    "created_at": "2026-03-01T12:00:00Z",
    "customer_name": "فاطمة",
}

FAKE_FAILED_JOB = {
    "id": "22222222-2222-2222-2222-222222222222",
    "kind": "whatsapp_message",
    "phone": "972591234567",
    "payload": {"text": "hi"},
    "last_error": "send failed",
    "attempts": 3,
    "max_attempts": 3,
    "created_at": "2026-03-01T12:05:00Z",
    "customer_name": "فاطمة",
}

FAKE_FAILED_JOB_UNKNOWN_PHONE = {
    "id": "33333333-3333-3333-3333-333333333333",
    "kind": "whatsapp_message",
    "phone": "972590000000",
    "payload": {"text": "hi"},
    "last_error": "send failed",
    "attempts": 3,
    "max_attempts": 3,
    "created_at": "2026-03-01T12:10:00Z",
    "customer_name": "",
}


@pytest.fixture(autouse=True)
def _no_real_audit(monkeypatch):
    """Autouse for this file: every mutating alerts endpoint calls
    audit.log_action — never let it reach the real Supabase instance."""
    from app.services import audit

    monkeypatch.setattr(audit, "log_action", lambda *a, **k: None)


class TestAlertsAuth:
    def test_api_alerts_requires_auth(self, client):
        r = client.get("/api/alerts")
        assert r.status_code == 401

    def test_retry_webhook_event_requires_auth(self, client):
        r = client.post("/api/alerts/webhook_events/some-id/retry")
        assert r.status_code == 401

    def test_retry_outbox_job_requires_auth(self, client):
        r = client.post("/api/alerts/outbox_jobs/some-id/retry")
        assert r.status_code == 401

    def test_retry_all_requires_auth(self, client):
        r = client.post("/api/alerts/retry_all")
        assert r.status_code == 401


class TestAlertsList:
    def test_api_alerts_returns_alerts_and_counts_shape(self, operator_client, monkeypatch):
        import app.routers.ui_api as ui_api

        def fake_query(sql, params=()):
            if "webhook_events" in sql:
                return [dict(FAKE_DEAD_EVENT)]
            if "outbox_jobs" in sql:
                return [dict(FAKE_FAILED_JOB)]
            return []

        monkeypatch.setattr(ui_api, "query", fake_query)

        r = operator_client.get("/api/alerts")
        assert r.status_code == 200
        data = r.json()
        assert "alerts" in data
        assert "counts" in data
        assert len(data["alerts"]) == 2
        assert data["counts"]["total"] == 2

    def test_whatsapp_message_alert_is_customer_facing_and_names_customer(
        self, operator_client, monkeypatch
    ):
        import app.routers.ui_api as ui_api

        monkeypatch.setattr(
            ui_api, "query",
            lambda sql, params=(): [dict(FAKE_FAILED_JOB)] if "outbox_jobs" in sql else [],
        )

        r = operator_client.get("/api/alerts")
        assert r.status_code == 200
        alert = r.json()["alerts"][0]
        assert alert["severity"] == "customer_facing"
        assert FAKE_FAILED_JOB["customer_name"] in alert["what_happened"]
        assert alert["source"] == "outbox_job"
        assert alert["kind"] == "whatsapp_message"

    def test_unknown_phone_falls_back_to_number_not_empty_name(
        self, operator_client, monkeypatch
    ):
        import app.routers.ui_api as ui_api

        monkeypatch.setattr(
            ui_api, "query",
            lambda sql, params=(): [dict(FAKE_FAILED_JOB_UNKNOWN_PHONE)] if "outbox_jobs" in sql else [],
        )

        r = operator_client.get("/api/alerts")
        alert = r.json()["alerts"][0]
        # Falls back to the phone number in the sentence — never an empty name.
        assert alert["what_happened"] == f"رسالة لم تصل إلى {FAKE_FAILED_JOB_UNKNOWN_PHONE['phone']}"
        assert alert["what_happened"] != "رسالة لم تصل إلى "

    def test_alert_has_wa_link(self, operator_client, monkeypatch):
        import app.routers.ui_api as ui_api

        monkeypatch.setattr(
            ui_api, "query",
            lambda sql, params=(): [dict(FAKE_FAILED_JOB)] if "outbox_jobs" in sql else [],
        )

        r = operator_client.get("/api/alerts")
        alert = r.json()["alerts"][0]
        assert alert["wa_link"] == f"https://wa.me/{FAKE_FAILED_JOB['phone']}"

    def test_technical_fields_survive_for_details_toggle(self, operator_client, monkeypatch):
        import app.routers.ui_api as ui_api

        monkeypatch.setattr(
            ui_api, "query",
            lambda sql, params=(): [dict(FAKE_FAILED_JOB)] if "outbox_jobs" in sql else [],
        )

        r = operator_client.get("/api/alerts")
        alert = r.json()["alerts"][0]
        assert alert["error"] == FAKE_FAILED_JOB["last_error"]
        assert alert["payload"] == FAKE_FAILED_JOB["payload"]
        assert alert["attempts"] == FAKE_FAILED_JOB["attempts"]
        assert alert["max_attempts"] == FAKE_FAILED_JOB["max_attempts"]

    def test_dead_letter_webhook_event_is_customer_facing(self, operator_client, monkeypatch):
        import app.routers.ui_api as ui_api

        monkeypatch.setattr(
            ui_api, "query",
            lambda sql, params=(): [dict(FAKE_DEAD_EVENT)] if "webhook_events" in sql else [],
        )

        r = operator_client.get("/api/alerts")
        alert = r.json()["alerts"][0]
        assert alert["source"] == "webhook_event"
        assert alert["severity"] == "customer_facing"
        assert FAKE_DEAD_EVENT["customer_name"] in alert["what_happened"]
        assert alert["error"] == FAKE_DEAD_EVENT["error"]

    def test_non_customer_facing_kind_is_internal(self, operator_client, monkeypatch):
        import app.routers.ui_api as ui_api

        internal_job = dict(FAKE_FAILED_JOB)
        internal_job["kind"] = "monthly_report"
        internal_job["customer_name"] = ""

        monkeypatch.setattr(
            ui_api, "query",
            lambda sql, params=(): [internal_job] if "outbox_jobs" in sql else [],
        )

        r = operator_client.get("/api/alerts")
        alert = r.json()["alerts"][0]
        assert alert["severity"] == "internal"
        assert "monthly_report" in alert["what_happened"]

    def test_api_alerts_empty_when_nothing_dead(self, operator_client, monkeypatch):
        import app.routers.ui_api as ui_api

        monkeypatch.setattr(ui_api, "query", lambda sql, params=(): [])

        r = operator_client.get("/api/alerts")
        assert r.status_code == 200
        data = r.json()
        assert data["alerts"] == []
        assert data["counts"] == {"total": 0, "customer_facing": 0, "internal": 0}


class TestRetryWebhookEvent:
    def test_retry_webhook_event_resets_row(self, operator_client, monkeypatch):
        import app.routers.ui_api as ui_api

        captured = []

        def fake_execute(sql, params=()):
            captured.append((sql, params))

        monkeypatch.setattr(ui_api, "execute", fake_execute)

        r = operator_client.post(
            f"/api/alerts/webhook_events/{FAKE_DEAD_EVENT['id']}/retry"
        )
        assert r.status_code == 200
        assert r.json() == {"ok": True}
        assert len(captured) == 1
        sql, params = captured[0]
        assert "processed = FALSE" in sql
        assert params == (FAKE_DEAD_EVENT["id"],)


class TestRetryOutboxJob:
    def test_retry_outbox_job_resets_row(self, operator_client, monkeypatch):
        import app.routers.ui_api as ui_api

        captured = []

        def fake_execute(sql, params=()):
            captured.append((sql, params))

        monkeypatch.setattr(ui_api, "execute", fake_execute)

        r = operator_client.post(
            f"/api/alerts/outbox_jobs/{FAKE_FAILED_JOB['id']}/retry"
        )
        assert r.status_code == 200
        assert r.json() == {"ok": True}
        assert len(captured) == 1
        sql, params = captured[0]
        assert "status = 'pending'" in sql
        assert params == (FAKE_FAILED_JOB["id"],)


class TestRetryAll:
    def test_retry_all_issues_two_updates_and_returns_counts(self, operator_client, monkeypatch):
        import app.routers.ui_api as ui_api

        captured_execute = []

        def fake_query(sql, params=()):
            if "webhook_events" in sql:
                return [{"count": 2}]
            if "outbox_jobs" in sql:
                return [{"count": 5}]
            return []

        def fake_execute(sql, params=()):
            captured_execute.append((sql, params))

        monkeypatch.setattr(ui_api, "query", fake_query)
        monkeypatch.setattr(ui_api, "execute", fake_execute)

        r = operator_client.post("/api/alerts/retry_all")

        assert r.status_code == 200
        assert r.json() == {"ok": True, "webhook_events": 2, "outbox_jobs": 5}

        update_calls = [c for c in captured_execute if c[0].strip().upper().startswith("UPDATE")]
        assert len(update_calls) == 2
        assert any("webhook_events" in sql for sql, _ in update_calls)
        assert any("outbox_jobs" in sql for sql, _ in update_calls)

    def test_retry_all_with_nothing_to_retry_returns_zero_counts(self, operator_client, monkeypatch):
        import app.routers.ui_api as ui_api

        monkeypatch.setattr(ui_api, "query", lambda sql, params=(): [{"count": 0}])
        monkeypatch.setattr(ui_api, "execute", lambda sql, params=(): None)

        r = operator_client.post("/api/alerts/retry_all")

        assert r.status_code == 200
        assert r.json() == {"ok": True, "webhook_events": 0, "outbox_jobs": 0}
