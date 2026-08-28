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

    def test_rpc_calls_client_with_params(self, monkeypatch):
        import app.db.database as db

        captured_fn = None
        captured_args = None

        def fake_rpc(self, fn, args):
            nonlocal captured_fn, captured_args
            captured_fn = fn
            captured_args = args
            return type("Rpc", (), {"execute": lambda self: type("R", (), {"data": [{"val": 1}]})()})()

        fake_client = type("C", (), {"rpc": fake_rpc})()
        monkeypatch.setattr(db, "_client", fake_client)

        res = db.rpc("my_func", {"p1": "v1"})
        assert res == [{"val": 1}]
        assert captured_fn == "my_func"
        assert captured_args == {"p1": "v1"}


class TestResilience:
    """Tests for the retry + circuit-breaker layer around the Supabase RPC seam."""

    def _client_that_fails(self, fail_times, payload=None):
        """Build a fake Supabase client that raises ConnectionError the first
        ``fail_times`` calls, then returns ``payload`` rows. Tracks call count."""
        state = {"calls": 0}

        def rpc(self, fn, args):
            def execute(_self):
                state["calls"] += 1
                if state["calls"] <= fail_times:
                    raise ConnectionError("transient")
                return type("R", (), {"data": payload or []})()
            return type("Rpc", (), {"execute": execute})()

        client = type("C", (), {"rpc": rpc})()
        return client, state

    def setup_method(self):
        # Reset process-local circuit state before each test.
        import app.db.database as db

        db._consecutive_failures = 0
        db._circuit_open_until = 0.0

    def test_query_retries_then_succeeds(self, monkeypatch):
        import app.db.database as db

        client, state = self._client_that_fails(1, payload=[{"id": 1}])
        monkeypatch.setattr(db, "_client", client)
        monkeypatch.setattr(db.time, "sleep", lambda *_: None)  # no real backoff

        rows = db.query("SELECT 1", ())
        assert rows == [{"id": 1}]
        assert state["calls"] == 2  # failed once, retried once

    def test_query_raises_after_exhausting_retries(self, monkeypatch):
        import app.db.database as db

        client, state = self._client_that_fails(99)  # always fails
        monkeypatch.setattr(db, "_client", client)
        monkeypatch.setattr(db.time, "sleep", lambda *_: None)

        with pytest.raises(ConnectionError):
            db.query("SELECT 1", ())
        # max_retries=2 → 3 attempts total
        assert state["calls"] == 3

    def test_write_is_not_retried(self, monkeypatch):
        import app.db.database as db

        client, state = self._client_that_fails(99)
        monkeypatch.setattr(db, "_client", client)
        monkeypatch.setattr(db.time, "sleep", lambda *_: None)

        with pytest.raises(ConnectionError):
            db.execute("DELETE FROM sessions WHERE phone = %s", ("123",))
        assert state["calls"] == 1  # write attempted exactly once

    def test_circuit_opens_and_fails_fast(self, monkeypatch):
        import app.db.database as db

        client, _ = self._client_that_fails(99)
        monkeypatch.setattr(db, "_client", client)
        monkeypatch.setattr(db.time, "sleep", lambda *_: None)
        # Lower the threshold so the test trips quickly.
        monkeypatch.setattr(
            db, "_retry_cfg",
            lambda: {"max_retries": 0, "retry_after_seconds": 0,
                     "circuit_threshold": 2, "circuit_cooldown_seconds": 30},
        )

        # Two real failures reach the threshold...
        for _ in range(2):
            with pytest.raises(ConnectionError):
                db.execute("UPDATE x SET y = 1", ())

        # ...the next call fails fast without touching the client.
        with pytest.raises(RuntimeError, match="circuit open"):
            db.execute("UPDATE x SET y = 1", ())

    def test_success_resets_failure_count(self, monkeypatch):
        import app.db.database as db

        client, _ = self._client_that_fails(1, payload=[{"ok": 1}])
        monkeypatch.setattr(db, "_client", client)
        monkeypatch.setattr(db.time, "sleep", lambda *_: None)

        db.query("SELECT 1", ())  # fails once, retries, succeeds
        assert db._consecutive_failures == 0
