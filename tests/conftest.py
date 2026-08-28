"""
Shared pytest fixtures.

Patches the DB and WhatsApp-sender seams as they are actually *used* today
(the names bound into app.routers.whatsapp_helpers, app.services.processor,
and app.routers.whatsapp — Python copies a reference at `from x import y`
time, so patching app.db.database.query itself would NOT reach code that
already did `from app.db.database import query`). This keeps every test from
ever touching the real Supabase instance or the real WhatsApp API.

Deliberately NOT patched: app.db.database's own query/execute/execute_returning/
rpc definitions. tests/unit/test_database.py exercises those directly against
a fake Supabase `_client`, so leaving the real functions in place lets that
retry/circuit-breaker logic actually run under test.

Also defines the three dashboard-auth fixtures (`client`, `operator_client`,
`admin_client`) every integration test in this repo now uses instead of
hand-computing a session cookie — see the `operator_client` docstring below
for why. Declared once here (not per-file) so plans 05-05/05-07/05-09's new
test files can consume them without re-declaring anything.
"""
from __future__ import annotations

import itertools
import json
from typing import Any

import pytest

from app.services.sessions import Operator


class FakeDB:
    """A tiny in-memory stand-in for the Supabase-backed tables the bot
    touches (sessions, chat_history, customers, orders, webhook_events).

    Routes by keyword-matching the raw SQL text (before %s substitution) —
    good enough to exercise real behavior without a real database.
    """

    def __init__(self) -> None:
        self.sessions: dict[str, dict] = {}
        self.customers: dict[str, dict] = {}
        self.history: dict[str, list[dict]] = {}
        self.orders: list[dict] = []
        self.webhook_events: list[dict] = []
        self.outbox_jobs: list[dict] = []
        self._order_seq = itertools.count(1)
        self._event_seq = itertools.count(1)
        self._outbox_seq = itertools.count(1)

    # -- reads -----------------------------------------------------------

    def query(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        s = sql.upper()
        if "FROM SESSIONS" in s:
            row = self.sessions.get(params[0])
            return [row] if row else []
        if "FROM CHAT_HISTORY" in s:
            phone = params[0]
            limit = params[1] if len(params) > 1 else 8
            # Mirrors "ORDER BY created_at DESC LIMIT %s" — whatsapp_helpers.
            # load_history() re-reverses this back to chronological order.
            return list(reversed(self.history.get(phone, [])))[:limit]
        if "FROM CUSTOMERS" in s:
            row = self.customers.get(params[0])
            return [row] if row else []
        if "FROM ORDERS" in s:
            phone = params[0]
            matches = [o for o in self.orders if o["phone"] == phone]
            return [matches[-1]] if matches else []
        if "FROM WEBHOOK_EVENTS" in s:
            pending = [e for e in self.webhook_events if not e["processed"]]
            pending.sort(key=lambda e: e["created_at"])
            return pending[:10]
        if "FROM OUTBOX_JOBS" in s:
            eligible = [
                j for j in self.outbox_jobs
                if j["status"] in ("pending", "failed") and j["attempts"] < j["max_attempts"]
            ]
            eligible.sort(key=lambda j: j["created_at"])
            return eligible[:10]
        return []

    # -- writes ------------------------------------------------------------

    def execute(self, sql: str, params: tuple = ()) -> None:
        s = sql.upper()

        if "INSERT INTO SESSIONS" in s:
            phone, stage, cart, fulfillment, menu, address = params
            self.sessions[phone] = {
                "stage": stage,
                "cart": json.loads(cart) if isinstance(cart, str) else (cart or []),
                "fulfillment": fulfillment,
                "menu_products": json.loads(menu) if isinstance(menu, str) else (menu or []),
                "address": address,
            }
            return

        if "DELETE FROM SESSIONS" in s:
            self.sessions.pop(params[0], None)
            return

        if "INSERT INTO CHAT_HISTORY" in s:
            phone, role, content = params
            self.history.setdefault(phone, []).append({"role": role, "content": content})
            return

        if "UPDATE CUSTOMERS" in s and "SAVED_ADDRESS" in s:
            address, phone = params
            self.customers.setdefault(phone, {"phone": phone, "name": "", "saved_address": ""})
            self.customers[phone]["saved_address"] = address
            return

        if "UPDATE CUSTOMERS" in s and "NAME" in s:
            name, phone = params
            self.customers.setdefault(phone, {"phone": phone, "name": "", "saved_address": ""})
            self.customers[phone]["name"] = name
            return

        if "INSERT INTO CUSTOMERS" in s:
            phone = params[0]
            name = params[1] if len(params) > 1 else ""
            self.customers.setdefault(phone, {"phone": phone, "name": name, "saved_address": ""})
            return

        if "INSERT INTO WEBHOOK_EVENTS" in s:
            phone, payload, wamid = params
            if wamid and any(e["wamid"] == wamid for e in self.webhook_events):
                return  # ON CONFLICT (wamid) DO NOTHING
            self.webhook_events.append({
                "id": next(self._event_seq),
                "phone": phone,
                "payload": payload,
                "wamid": wamid,
                "processed": False,
                "attempts": 0,
                "error": None,
                "created_at": len(self.webhook_events),
            })
            return

        if "UPDATE WEBHOOK_EVENTS" in s:
            # Order matters: check the more specific patterns first.
            if "PROCESSED = TRUE" in s and "ERROR" in s:
                error, event_id = params
                ev = self._webhook_event(event_id)
                if ev:
                    ev["processed"] = True
                    ev["error"] = error
                return
            if "PROCESSED = TRUE" in s:
                event_id = params[0]
                ev = self._webhook_event(event_id)
                if ev:
                    ev["processed"] = True
                return
            if "ATTEMPTS" in s:
                attempts, event_id = params
                ev = self._webhook_event(event_id)
                if ev:
                    ev["attempts"] = attempts
                return
            if "ERROR" in s:
                error, event_id = params
                ev = self._webhook_event(event_id)
                if ev:
                    ev["error"] = error
                return
            return

        if "INSERT INTO OUTBOX_JOBS" in s:
            kind, phone, payload = params
            self.outbox_jobs.append({
                "id": next(self._outbox_seq),
                "kind": kind,
                "phone": phone,
                "payload": payload,
                "status": "pending",
                "attempts": 0,
                "max_attempts": 3,
                "last_error": None,
                "created_at": len(self.outbox_jobs),
                "updated_at": None,
                "processed_at": None,
            })
            return

        if "UPDATE OUTBOX_JOBS" in s:
            # Order matters: check the more specific patterns first.
            if "STATUS = 'PROCESSING'" in s:
                job_id, = params
                job = self._outbox_job(job_id)
                if job:
                    job["status"] = "processing"
                    job["attempts"] += 1
                    job["updated_at"] = "now"
                return
            if "STATUS = 'SENT'" in s:
                job_id, = params
                job = self._outbox_job(job_id)
                if job:
                    job["status"] = "sent"
                    job["processed_at"] = "now"
                return
            if "STATUS = 'FAILED'" in s:
                last_error, job_id = params
                job = self._outbox_job(job_id)
                if job:
                    job["status"] = "failed"
                    job["last_error"] = last_error
                    job["updated_at"] = "now"
                return
            return

        # anything else: no-op stub.
        return

    def execute_returning(self, sql: str, params: tuple = ()) -> dict | None:
        return None

    def rpc(self, name: str, params: dict | None = None, retryable: bool = False) -> list[dict]:
        params = params or {}
        if name == "create_order_atomic":
            order_id = next(self._order_seq)
            self.orders.append({
                "id": order_id,
                "phone": params.get("p_phone"),
                "status": "to_do",
                "fulfillment": params.get("p_fulfillment"),
                "address": params.get("p_address"),
                "total": params.get("p_total"),
                "items": params.get("p_items"),
                "created_at": len(self.orders),
            })
            return [{"create_order_atomic": order_id}]
        return []

    def _webhook_event(self, event_id) -> dict | None:
        return next((e for e in self.webhook_events if e["id"] == event_id), None)

    def _outbox_job(self, job_id) -> dict | None:
        return next((j for j in self.outbox_jobs if j["id"] == job_id), None)


@pytest.fixture()
def fake_db() -> FakeDB:
    """A fresh in-memory FakeDB, exposed so tests can seed or assert on state
    directly (e.g. pre-seed a malformed webhook_events row, or check an
    order's total after confirm)."""
    return FakeDB()


@pytest.fixture()
def sent_messages() -> list[dict]:
    """Every outbound WhatsApp send during a test, in call order. Each entry
    is {"to": ..., "text": ..., "buttons": <list or None>}."""
    return []


@pytest.fixture(autouse=True)
def mock_db(monkeypatch, fake_db: FakeDB, sent_messages: list[dict]):
    """Autouse: patch DB and WhatsApp-sender seams so no test ever hits the
    real network. See module docstring for why these specific names."""
    import app.routers.whatsapp as wa
    import app.routers.whatsapp_helpers as wh
    import app.services.processor as processor

    def _capture_send_text(to, text):
        sent_messages.append({"to": to, "text": text, "buttons": None})
        return {"dev": True, "to": to, "text": text}

    def _capture_send_buttons(to, body, buttons):
        sent_messages.append({"to": to, "text": body, "buttons": buttons})
        return {"dev": True, "to": to, "text": body, "buttons": buttons}

    for mod in (wh, processor):
        monkeypatch.setattr(mod, "query", fake_db.query)
        monkeypatch.setattr(mod, "execute", fake_db.execute)

    monkeypatch.setattr(wa, "execute", fake_db.execute)
    monkeypatch.setattr(processor, "rpc", fake_db.rpc)
    monkeypatch.setattr(processor, "send_text", _capture_send_text)
    monkeypatch.setattr(processor, "send_buttons", _capture_send_buttons)

    return fake_db


FAKE_OPERATOR = Operator(
    user_id="00000000-0000-0000-0000-000000000001",
    email="aunt@example.test",
    is_admin=False,
    session_id="11111111-1111-1111-1111-111111111111",
)
FAKE_ADMIN = Operator(
    user_id="00000000-0000-0000-0000-000000000002",
    email="admin@example.test",
    is_admin=True,
    session_id="22222222-2222-2222-2222-222222222222",
)


@pytest.fixture()
def client():
    """Plain TestClient(app) with no auth override — every request is
    unauthenticated unless the test sets cookies itself. Use this fixture
    (never a locally-declared one) for 401/303-unauthenticated assertions."""
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


@pytest.fixture()
def operator_client(client):
    """A TestClient standing in for a signed-in, non-admin operator.

    Uses FastAPI's own `app.dependency_overrides` — the idiomatic pattern for
    testing dependency-guarded routes — to make `require_operator` and
    `require_operator_page` resolve to a fixed fake Operator, instead of
    computing and setting a real session cookie. No test should ever
    hand-compute a token to forge a session again; that scheme (a hash of a
    shared dashboard password) doesn't exist anymore — see
    app/routers/auth_deps.py.

    Dependencies are imported here, inside the fixture body rather than at
    module import time, so this file's import order never depends on
    app.routers.auth_deps already being importable.

    Because this fixture never sets a real session cookie, the CSRF
    middleware added in plan 05-04 (scoped via `sensitive_cookies`) will not
    engage for these requests — that is intentional; 05-04 adds its own
    dedicated CSRF test against a real cookie.
    """
    from app.main import app
    from app.routers.auth_deps import require_operator, require_operator_page

    app.dependency_overrides[require_operator] = lambda: FAKE_OPERATOR
    app.dependency_overrides[require_operator_page] = lambda: FAKE_OPERATOR
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def admin_client(client):
    """Same pattern as operator_client, but overrides all three auth_deps
    dependencies (require_operator, require_operator_page, require_admin) to
    resolve to a fixed fake admin Operator."""
    from app.main import app
    from app.routers.auth_deps import require_admin, require_operator, require_operator_page

    app.dependency_overrides[require_operator] = lambda: FAKE_ADMIN
    app.dependency_overrides[require_operator_page] = lambda: FAKE_ADMIN
    app.dependency_overrides[require_admin] = lambda: FAKE_ADMIN
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


def drain_outbox_jobs() -> None:
    """Repeatedly call app.services.processor.process_outbox_jobs() until no
    eligible outbox_jobs row remains (a single call only pulls up to 10 rows
    at a time, mirroring the real poller's LIMIT 10 — see process_outbox_jobs).

    processor.handle_message()/process_webhook_events() no longer send
    WhatsApp messages directly — they enqueue rows into outbox_jobs via
    queue_text()/queue_buttons(), and only process_job() (driven by
    process_outbox_jobs()) actually calls send_text/send_buttons. In
    production these are two separate scheduled jobs (see app/worker.py:
    process_webhook_events every 3s, process_outbox_jobs every 2s) — this
    helper stands in for the second one so tests can flush it explicitly
    before asserting on sent_messages.
    """
    import app.services.processor as processor

    while processor.query(
        "SELECT id, kind, phone, payload, attempts FROM outbox_jobs "
        "WHERE status IN ('pending', 'failed') AND attempts < max_attempts "
        "ORDER BY created_at ASC LIMIT 10"
    ):
        processor.process_outbox_jobs()


@pytest.fixture()
def flush_outbox():
    """Drain the outbox poller synchronously. Usage:

        processor.handle_message(phone, "cart", "Test")
        flush_outbox()
        assert "..." in _last_text(sent_messages, phone)

    Returns the drain_outbox_jobs() callable (rather than draining once
    itself) so it reads the same way at every call site regardless of how
    many outbox rows the preceding step queued.
    """
    return drain_outbox_jobs
