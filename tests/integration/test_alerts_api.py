"""
test_alerts_api.py — Integration tests for the alerts API.

Covers: GET /api/alerts (dead-lettered webhook_events + permanently-failed
outbox_jobs), and the two one-click retry endpoints that reset either row
type back to a pollable state. Auth is injected via cookie, same pattern as
test_orders_api.py / test_ui_api.py.
"""
import hashlib
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["USE_MOCK_WHATSAPP"] = "1"

from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def auth_client(client):
    from app.services.config import Config

    raw = f"{Config.SECRET_KEY}:{Config.DASHBOARD_PASSWORD}"
    token = hashlib.sha256(raw.encode()).hexdigest()
    client.cookies.set("alyasmeen_session", token)
    return client


FAKE_DEAD_EVENT = {
    "id": "11111111-1111-1111-1111-111111111111",
    "phone": "972591234567",
    "payload": {"foo": "bar"},
    "error": "dead-letter: boom",
    "attempts": 3,
    "created_at": "2026-03-01T12:00:00Z",
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
}


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


class TestAlertsList:
    def test_api_alerts_returns_both_lists(self, auth_client, monkeypatch):
        import app.routers.ui_api as ui_api

        def fake_query(sql, params=()):
            if "webhook_events" in sql:
                return [dict(FAKE_DEAD_EVENT)]
            if "outbox_jobs" in sql:
                return [dict(FAKE_FAILED_JOB)]
            return []

        monkeypatch.setattr(ui_api, "query", fake_query)

        r = auth_client.get("/api/alerts")
        assert r.status_code == 200
        data = r.json()
        assert "webhook_events" in data
        assert "outbox_jobs" in data
        assert len(data["webhook_events"]) == 1
        assert data["webhook_events"][0]["id"] == FAKE_DEAD_EVENT["id"]
        assert data["webhook_events"][0]["error"] == FAKE_DEAD_EVENT["error"]
        assert len(data["outbox_jobs"]) == 1
        assert data["outbox_jobs"][0]["id"] == FAKE_FAILED_JOB["id"]
        assert data["outbox_jobs"][0]["last_error"] == FAKE_FAILED_JOB["last_error"]

    def test_api_alerts_empty_when_nothing_dead(self, auth_client, monkeypatch):
        import app.routers.ui_api as ui_api

        monkeypatch.setattr(ui_api, "query", lambda sql, params=(): [])

        r = auth_client.get("/api/alerts")
        assert r.status_code == 200
        data = r.json()
        assert data["webhook_events"] == []
        assert data["outbox_jobs"] == []


class TestRetryWebhookEvent:
    def test_retry_webhook_event_resets_row(self, auth_client, monkeypatch):
        import app.routers.ui_api as ui_api

        captured = []

        def fake_execute(sql, params=()):
            captured.append((sql, params))

        monkeypatch.setattr(ui_api, "execute", fake_execute)

        r = auth_client.post(
            f"/api/alerts/webhook_events/{FAKE_DEAD_EVENT['id']}/retry"
        )
        assert r.status_code == 200
        assert r.json() == {"ok": True}
        assert len(captured) == 1
        sql, params = captured[0]
        assert "processed = FALSE" in sql
        assert params == (FAKE_DEAD_EVENT["id"],)


class TestRetryOutboxJob:
    def test_retry_outbox_job_resets_row(self, auth_client, monkeypatch):
        import app.routers.ui_api as ui_api

        captured = []

        def fake_execute(sql, params=()):
            captured.append((sql, params))

        monkeypatch.setattr(ui_api, "execute", fake_execute)

        r = auth_client.post(
            f"/api/alerts/outbox_jobs/{FAKE_FAILED_JOB['id']}/retry"
        )
        assert r.status_code == 200
        assert r.json() == {"ok": True}
        assert len(captured) == 1
        sql, params = captured[0]
        assert "status = 'pending'" in sql
        assert params == (FAKE_FAILED_JOB["id"],)
