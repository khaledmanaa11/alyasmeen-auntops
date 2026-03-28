"""
test_database.py — Unit tests for app/db/database.py

Tests the SQL escaping and parameter substitution logic (_escape, _build)
without making any real Supabase calls. The public query/execute functions
are tested with a mocked Supabase client.
"""
import pytest


class TestEscape:
    """Tests for _escape() — converts Python values to safe SQL literals."""

    def setup_method(self):
        from app.db.database import _escape

        self.escape = _escape

    def test_none_becomes_null(self):
        assert self.escape(None) == "NULL"

    def test_true_becomes_true(self):
        assert self.escape(True) == "TRUE"

    def test_false_becomes_false(self):
        assert self.escape(False) == "FALSE"

    def test_integer(self):
        assert self.escape(42) == "42"

    def test_float(self):
        assert self.escape(3.14) == "3.14"

    def test_string_is_quoted(self):
        result = self.escape("hello")
        assert result == "'hello'"

    def test_string_with_single_quote_is_escaped(self):
        result = self.escape("it's")
        assert result == "'it''s'"

    def test_dict_is_json_quoted(self):
        result = self.escape({"key": "val"})
        assert result.startswith("'")
        assert result.endswith("'")
        assert "key" in result

    def test_list_is_json_quoted(self):
        result = self.escape([1, 2, 3])
        assert result.startswith("'")
        assert "[1, 2, 3]" in result or "1" in result

    def test_arabic_string_preserved(self):
        result = self.escape("مرحبا")
        assert "مرحبا" in result


class TestBuild:
    """Tests for _build() — substitutes %s placeholders with escaped values."""

    def setup_method(self):
        from app.db.database import _build

        self.build = _build

    def test_no_params_returns_sql_unchanged(self):
        sql = "SELECT * FROM orders"
        assert self.build(sql, ()) == sql

    def test_single_string_param(self):
        result = self.build("SELECT * FROM orders WHERE phone = %s", ("123",))
        assert result == "SELECT * FROM orders WHERE phone = '123'"

    def test_multiple_params(self):
        result = self.build(
            "SELECT * FROM orders WHERE phone = %s AND status = %s",
            ("123", "to_do"),
        )
        assert "'123'" in result
        assert "'to_do'" in result

    def test_integer_param_not_quoted(self):
        result = self.build("SELECT * FROM orders WHERE id = %s", (5,))
        assert result == "SELECT * FROM orders WHERE id = 5"

    def test_none_param_becomes_null(self):
        result = self.build("UPDATE customers SET address = %s WHERE id = %s", (None, 1))
        assert "NULL" in result

    def test_mismatch_raises_value_error(self):
        with pytest.raises(ValueError, match="param mismatch"):
            self.build("SELECT %s AND %s", ("only_one",))

    def test_sql_injection_attempt_is_escaped(self):
        malicious = "'; DROP TABLE orders; --"
        result = self.build("SELECT * FROM customers WHERE name = %s", (malicious,))
        # The single quote must be doubled, not left as-is
        assert "DROP TABLE" in result  # text preserved but safely quoted
        assert result.count("''") >= 1  # single quote doubled


class TestQueryAndExecute:
    """Tests for the public query/execute/execute_returning functions with mock client."""

    def test_query_returns_list(self, monkeypatch):
        import app.db.database as db

        fake_result = type("R", (), {"data": [{"id": 1, "name": "test"}]})()
        fake_rpc = type("Rpc", (), {"execute": lambda self: fake_result})()
        fake_client = type("C", (), {"rpc": lambda self, fn, args: fake_rpc})()
        monkeypatch.setattr(db, "_client", fake_client)

        rows = db.query("SELECT id, name FROM products", ())
        assert isinstance(rows, list)
        assert rows[0]["id"] == 1

    def test_execute_returns_none(self, monkeypatch):
        import app.db.database as db

        fake_result = type("R", (), {"data": None})()
        fake_rpc = type("Rpc", (), {"execute": lambda self: fake_result})()
        fake_client = type("C", (), {"rpc": lambda self, fn, args: fake_rpc})()
        monkeypatch.setattr(db, "_client", fake_client)

        result = db.execute("DELETE FROM sessions WHERE phone = %s", ("123",))
        assert result is None

    def test_execute_returning_returns_first_row(self, monkeypatch):
        import app.db.database as db

        fake_result = type("R", (), {"data": [{"id": 7}]})()
        fake_rpc = type("Rpc", (), {"execute": lambda self: fake_result})()
        fake_client = type("C", (), {"rpc": lambda self, fn, args: fake_rpc})()
        monkeypatch.setattr(db, "_client", fake_client)

        row = db.execute_returning("INSERT INTO orders ... RETURNING id", ())
        assert row == {"id": 7}

    def test_query_empty_result_returns_empty_list(self, monkeypatch):
        import app.db.database as db

        fake_result = type("R", (), {"data": []})()
        fake_rpc = type("Rpc", (), {"execute": lambda self: fake_result})()
        fake_client = type("C", (), {"rpc": lambda self, fn, args: fake_rpc})()
        monkeypatch.setattr(db, "_client", fake_client)

        rows = db.query("SELECT * FROM products WHERE id = %s", (9999,))
        assert rows == []
