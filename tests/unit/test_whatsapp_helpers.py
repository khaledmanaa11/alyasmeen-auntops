"""
test_whatsapp_helpers.py — Unit tests for app/routers/whatsapp_helpers.py

Tests session CRUD, chat history helpers, and customer management functions
with fully mocked database calls.
"""
import json

import pytest


@pytest.fixture(autouse=True)
def patch_db(monkeypatch):
    """Patch query/execute at the module level in whatsapp_helpers."""
    import app.routers.whatsapp_helpers as wh

    _db: dict = {"sessions": {}, "customers": {}, "history": {}}

    def fake_query(sql, params=()):
        if "sessions" in sql and "SELECT" in sql:
            phone = params[0] if params else ""
            row = _db["sessions"].get(phone)
            return [row] if row else []
        if "customers" in sql and "SELECT" in sql:
            phone = params[0] if params else ""
            row = _db["customers"].get(phone)
            return [row] if row else []
        if "chat_history" in sql and "SELECT" in sql:
            phone = params[0] if params else ""
            limit = params[1] if len(params) > 1 else 8
            hist = _db["history"].get(phone, [])
            return hist[-limit:]
        if "orders" in sql and "SELECT" in sql:
            phone = params[0] if params else ""
            row = _db.get("orders", {}).get(phone)
            return [row] if row else []
        return []

    def fake_execute(sql, params=()):
        if "sessions" in sql:
            if "DELETE" in sql:
                _db["sessions"].pop(params[0], None)
            elif "INSERT" in sql:
                phone = params[0]
                _db["sessions"][phone] = {
                    "stage": params[1],
                    "cart": json.loads(params[2]),
                    "fulfillment": params[3],
                    "menu_products": json.loads(params[4]),
                    "address": params[5],
                }
        elif "customers" in sql:
            if "INSERT" in sql:
                phone, name = params[0], params[1]
                _db["customers"][phone] = {"phone": phone, "name": name, "saved_address": ""}
            elif "UPDATE" in sql and "name" in sql:
                phone = params[1]
                if phone in _db["customers"]:
                    _db["customers"][phone]["name"] = params[0]
            elif "UPDATE" in sql and "saved_address" in sql:
                phone = params[1]
                if phone in _db["customers"]:
                    _db["customers"][phone]["saved_address"] = params[0]
        elif "chat_history" in sql:
            phone, role, content = params[0], params[1], params[2]
            _db["history"].setdefault(phone, []).append({"role": role, "content": content})

    monkeypatch.setattr(wh, "query", fake_query)
    monkeypatch.setattr(wh, "execute", fake_execute)
    return _db


class TestSessionHelpers:
    def test_load_session_returns_default_for_new_phone(self):
        from app.routers.whatsapp_helpers import load_session

        st = load_session("new-phone")
        assert st["stage"] == "root"
        assert st["cart"] == []
        assert st["fulfillment"] is None

    def test_save_and_load_session(self):
        from app.routers.whatsapp_helpers import load_session, save_session

        phone = "972591234567"
        st = {"stage": "confirm", "cart": [{"name": "كريم", "qty": 1, "price": 25.0}],
              "fulfillment": "pickup", "menu_products": [], "address": ""}
        save_session(phone, st)

        loaded = load_session(phone)
        assert loaded["stage"] == "confirm"
        assert loaded["fulfillment"] == "pickup"

    def test_clear_session(self):
        from app.routers.whatsapp_helpers import clear_session, load_session, save_session

        phone = "972591234567"
        save_session(phone, {"stage": "confirm", "cart": [], "fulfillment": None,
                              "menu_products": [], "address": ""})
        clear_session(phone)
        loaded = load_session(phone)
        assert loaded["stage"] == "root"  # default after clear


class TestChatHistory:
    def test_load_history_empty_for_new_phone(self):
        from app.routers.whatsapp_helpers import load_history

        hist = load_history("new-phone")
        assert hist == []

    def test_append_and_load_history(self):
        from app.routers.whatsapp_helpers import append_history, load_history

        phone = "972591234567"
        append_history(phone, "user", "مرحبا")
        append_history(phone, "assistant", "أهلا!")

        hist = load_history(phone)
        assert len(hist) == 2
        roles = {m["role"] for m in hist}
        assert "user" in roles
        assert "assistant" in roles

    def test_load_history_respects_limit(self):
        from app.routers.whatsapp_helpers import append_history, load_history

        phone = "972591234567"
        for i in range(10):
            append_history(phone, "user", f"message {i}")

        hist = load_history(phone, limit=3)
        assert len(hist) == 3


class TestCustomerHelpers:
    def test_upsert_new_customer_returns_true(self):
        from app.routers.whatsapp_helpers import upsert_customer

        result = upsert_customer("972591111111", "أحمد")
        assert result is True

    def test_upsert_existing_customer_returns_false(self, patch_db):
        from app.routers.whatsapp_helpers import upsert_customer

        phone = "972591111111"
        patch_db["customers"][phone] = {"phone": phone, "name": "أحمد", "saved_address": ""}
        result = upsert_customer(phone, "أحمد")
        assert result is False

    def test_get_customer_name_existing(self, patch_db):
        from app.routers.whatsapp_helpers import get_customer_name

        phone = "972591111111"
        patch_db["customers"][phone] = {"phone": phone, "name": "فاطمة", "saved_address": ""}
        name = get_customer_name(phone)
        assert name == "فاطمة"

    def test_get_customer_name_missing(self):
        from app.routers.whatsapp_helpers import get_customer_name

        assert get_customer_name("nonexistent") == ""

    def test_save_and_get_address(self, patch_db):
        from app.routers.whatsapp_helpers import get_saved_address, save_customer_address

        phone = "972591111111"
        patch_db["customers"][phone] = {"phone": phone, "name": "Test", "saved_address": ""}
        save_customer_address(phone, "شارع النصر، رام الله")
        addr = get_saved_address(phone)
        assert addr == "شارع النصر، رام الله"
