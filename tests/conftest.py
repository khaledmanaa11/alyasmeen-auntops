"""
Shared pytest fixtures.

Replaces the DB-backed session/history helpers in whatsapp.py with
in-memory equivalents so tests never touch the real Supabase instance,
and session state actually persists between requests within a test.
"""
import pytest


@pytest.fixture(autouse=True)
def mock_db(monkeypatch):
    import app.services.worker_tasks as wa

    _sessions: dict = {}
    _history: dict = {}
    _order_seq = [0]

    def fake_load_session(phone):
        return dict(_sessions.get(phone, {"stage": "root", "cart": [], "fulfillment": None, "menu_products": [], "address": ""}))

    def fake_save_session(phone, st):
        _sessions[phone] = dict(st)

    def fake_clear_session(phone):
        _sessions.pop(phone, None)

    def fake_load_history(phone, limit=6):
        return list(_history.get(phone, []))[-limit:]

    def fake_append_history(phone, role, content):
        _history.setdefault(phone, []).append({"role": role, "content": content})

    def fake_execute_returning(sql, params=()):
        _order_seq[0] += 1
        return {"id": _order_seq[0]}

    def fake_execute(sql, params=()):
        pass  # no-op: order_lines inserts, order_name update, session deletes, etc.

    def fake_search_products(query=None, category=None):
        return [
            {"sku": "1", "name": "كريم اليدين", "price": 25.0},
            {"sku": "2", "name": "لوشن الجسم", "price": 40.0},
        ]

    monkeypatch.setattr(wa, "load_session", fake_load_session)
    monkeypatch.setattr(wa, "save_session", fake_save_session)
    monkeypatch.setattr(wa, "clear_session", fake_clear_session)
    monkeypatch.setattr(wa, "load_history", fake_load_history)
    monkeypatch.setattr(wa, "append_history", fake_append_history)
    monkeypatch.setattr(wa, "upsert_customer", lambda phone, name="": False)
    monkeypatch.setattr(wa, "get_customer_name", lambda phone: "")
    monkeypatch.setattr(wa, "get_saved_address", lambda phone: "")
    monkeypatch.setattr(wa, "save_customer_address", lambda phone, address: None)
    monkeypatch.setattr(wa, "get_latest_order", lambda phone: None)
    monkeypatch.setattr(wa, "execute_returning", fake_execute_returning)
    monkeypatch.setattr(wa, "execute", fake_execute)
    monkeypatch.setattr(wa, "search_products", fake_search_products)
