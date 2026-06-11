"""
Shared pytest fixtures.

Replaces the DB-backed context/session/history helpers in whatsapp.py with
in-memory equivalents so tests never touch the real Supabase instance,
and session state actually persists between requests within a test.
"""
import pytest


@pytest.fixture(autouse=True)
def mock_db(monkeypatch):
    import app.routers.whatsapp as wa

    _sessions: dict = {}
    _customers: dict = {}
    _history: dict = {}
    _order_seq = [0]

    def _default_session():
        return {"stage": "root", "cart": [], "fulfillment": None, "menu_products": [], "address": ""}

    def fake_load_context(phone, history_limit=8):
        return {
            "session": dict(_sessions.get(phone, _default_session())),
            # Default to an existing (returning) customer so tests don't get
            # the welcome message unless they patch load_context themselves.
            "customer": dict(_customers.get(phone, {"name": "", "saved_address": ""})),
            "history": list(_history.get(phone, []))[-history_limit:],
        }

    def fake_save_session(phone, st):
        _sessions[phone] = dict(st)

    def fake_clear_session(phone):
        _sessions.pop(phone, None)

    def fake_append_history(phone, role, content):
        _history.setdefault(phone, []).append({"role": role, "content": content})

    def fake_create_customer(phone, name=""):
        _customers.setdefault(phone, {"name": name, "saved_address": ""})

    def fake_update_customer_name(phone, name):
        _customers.setdefault(phone, {"name": "", "saved_address": ""})["name"] = name

    def fake_save_customer_address(phone, address):
        _customers.setdefault(phone, {"name": "", "saved_address": ""})["saved_address"] = address

    def fake_execute_returning(sql, params=()):
        _order_seq[0] += 1
        return {"id": _order_seq[0]}

    def fake_execute(sql, params=()):
        pass  # no-op: order_name + line inserts, session deletes, etc.

    def fake_search_products(q=None, category=None):
        # Serve the menu from wa._CATALOG (which tests patch) instead of the
        # live Supabase products table. Read at call time so per-test
        # monkeypatch.setattr(wa, "_CATALOG", ...) takes effect.
        return [
            {
                "sku": str(item.get("id", i + 1)),
                "name": item.get("name", ""),
                "price": float(item.get("list_price", 0) or 0),
                "description": item.get("description_sale", ""),
                "tags": [],
            }
            for i, item in enumerate(wa._CATALOG)
        ]

    monkeypatch.setattr(wa, "search_products", fake_search_products)
    monkeypatch.setattr(wa, "load_context", fake_load_context)
    monkeypatch.setattr(wa, "save_session", fake_save_session)
    monkeypatch.setattr(wa, "clear_session", fake_clear_session)
    monkeypatch.setattr(wa, "append_history", fake_append_history)
    monkeypatch.setattr(wa, "create_customer", fake_create_customer)
    monkeypatch.setattr(wa, "update_customer_name", fake_update_customer_name)
    monkeypatch.setattr(wa, "save_customer_address", fake_save_customer_address)
    monkeypatch.setattr(wa, "get_latest_order", lambda phone: None)
    monkeypatch.setattr(wa, "execute_returning", fake_execute_returning)
    monkeypatch.setattr(wa, "execute", fake_execute)
