# database.py
# Connects to Supabase via HTTPS (supabase-py) instead of psycopg2.
# All SQL runs through two PostgreSQL helper functions created in Supabase:
#   run_query(sql)  → SELECT / INSERT...RETURNING  (returns JSON array)
#   run_exec(sql)   → INSERT / UPDATE / DELETE      (returns void)
# Every other file imports query / execute / execute_returning from here.

import json
import logging
import time
from typing import Any

from supabase import Client, create_client

from app.services.config import Config

log = logging.getLogger(__name__)

_client: Client | None = None


def _get_client() -> Client:
    """Return the Supabase HTTPS client singleton, creating it on first call.

    Reads SUPABASE_URL and SUPABASE_KEY from Config. The client is reused
    across all subsequent calls to avoid the overhead of repeated connections.
    """
    global _client
    if _client is None:
        log.info("Connecting to Supabase via HTTPS…")
        _client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
        log.info("✅ Supabase client ready")
    return _client


# ---------------------------------------------------------------------------
# SQL param escaping
# Converts a Python tuple of params into literal SQL values so they can be
# interpolated into the SQL string before sending to Supabase RPC.
# All SQL strings in the app are written by us — never from user input —
# so this is safe.  User-supplied strings (names, messages, addresses) are
# properly escaped by _escape() below.
# ---------------------------------------------------------------------------

def _escape(val: Any) -> str:
    """Escape one Python value into a safe SQL literal."""
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, (dict, list)):
        return "'" + json.dumps(val, ensure_ascii=False).replace("'", "''") + "'"
    # str, datetime, UUID, etc.
    return "'" + str(val).replace("'", "''") + "'"


def _build(sql: str, params: tuple) -> str:
    """Replace every %s placeholder with an escaped literal value."""
    if not params:
        return sql
    parts = sql.split("%s")
    if len(parts) - 1 != len(params):
        raise ValueError(
            f"SQL param mismatch: {len(parts)-1} placeholders vs {len(params)} params\nSQL: {sql}"
        )
    result = parts[0]
    for val, tail in zip(params, parts[1:], strict=False):
        result += _escape(val) + tail
    return result


# ---------------------------------------------------------------------------
# Resilience — retry + circuit breaker around the Supabase RPC seam.
# Every DB call in the app funnels through query/execute/execute_returning,
# so this is the single place to absorb transient Supabase failures (a brief
# network blip otherwise surfaces as a hard error on the customer's next message).
# Tunables live in config/rate_limits.json under "supabase" — never hardcoded.
# ---------------------------------------------------------------------------

# Circuit-breaker state (process-local).
_consecutive_failures = 0
_circuit_open_until = 0.0


def _retry_cfg() -> dict[str, Any]:
    """Read the 'supabase' resilience settings, with safe fallbacks."""
    cfg = (Config.RATE_LIMITS or {}).get("services", {}).get("supabase", {})
    return {
        "max_retries": cfg.get("max_retries", 2),
        "retry_after_seconds": cfg.get("retry_after_seconds", 0.5),
        "circuit_threshold": cfg.get("circuit_threshold", 5),
        "circuit_cooldown_seconds": cfg.get("circuit_cooldown_seconds", 10),
    }


def _call(rpc_name: str, final_sql: str, retryable: bool) -> list[dict[str, Any]]:
    """Run one Supabase RPC with a circuit breaker and optional retry.

    Reads (retryable=True) are retried with exponential backoff because they are
    idempotent. Writes are NOT retried here: an insert/update whose response was
    lost after it committed would double-apply on retry. The circuit breaker
    observes every call and, once enough consecutive failures pile up, fails fast
    for a cooldown window instead of hammering a down database.
    """
    global _consecutive_failures, _circuit_open_until
    cfg = _retry_cfg()

    now = time.monotonic()
    if now < _circuit_open_until:
        raise RuntimeError(
            f"Supabase circuit open — failing fast for "
            f"{_circuit_open_until - now:.1f}s after repeated errors"
        )

    attempts = cfg["max_retries"] + 1 if retryable else 1
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            result = _get_client().rpc(rpc_name, {"sql": final_sql}).execute()
            _consecutive_failures = 0
            return result.data or []
        except Exception as exc:
            last_exc = exc
            log.warning("db: %s failed attempt=%d/%d: %s", rpc_name, attempt + 1, attempts, exc)
            if attempt < attempts - 1:
                time.sleep(cfg["retry_after_seconds"] * (2 ** attempt))

    _consecutive_failures += 1
    if _consecutive_failures >= cfg["circuit_threshold"]:
        _circuit_open_until = time.monotonic() + cfg["circuit_cooldown_seconds"]
        log.error("db: circuit opened after %d consecutive failures", _consecutive_failures)
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Public API  (same interface as the old psycopg2 version)
# ---------------------------------------------------------------------------

REQUIRED_SCHEMA = {
    "products": {"id", "name", "price", "description", "tags", "aliases", "active", "created_at"},
    "customers": {"phone", "name", "saved_address", "created_at", "updated_at"},
    "orders": {
        "id", "order_name", "phone", "fulfillment", "address", "total",
        "status", "channel", "created_at", "updated_at"
    },
    "order_lines": {"id", "order_id", "product_name", "qty", "unit_price", "line_total"},
    "sessions": {
        "phone", "stage", "cart", "fulfillment", "menu_products",
        "address", "created_at", "updated_at"
    },
    "chat_history": {"id", "phone", "role", "content", "created_at"},
    "follow_ups": {"id", "phone", "order_id", "delivered_at", "sent", "sent_at"},
    "retry_queue": {
        "id", "action", "order_id", "phone", "payload", "attempts",
        "max_attempts", "last_error", "next_retry_at", "resolved", "created_at"
    },
    "monthly_snapshots": {"year", "month", "data", "created_at"}
}


def validate_schema() -> None:
    """Validate that the live Supabase schema matches REQUIRED_SCHEMA.

    Queries information_schema.columns to check for every required table and
    column. Raises RuntimeError if any part of the schema is missing.
    """
    log.info("db: validating schema integrity…")
    rows = query(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = 'public'"
    )

    actual: dict[str, set[str]] = {}
    for r in rows:
        actual.setdefault(r["table_name"], set()).add(r["column_name"])

    for table, req_cols in REQUIRED_SCHEMA.items():
        if table not in actual:
            raise RuntimeError(f"Database integrity error: Missing table '{table}'")

        missing = req_cols - actual[table]
        if missing:
            raise RuntimeError(
                f"Database integrity error: Table '{table}' missing columns: {sorted(list(missing))}"
            )

    log.info("✅ Database schema is valid (%d tables)", len(REQUIRED_SCHEMA))


def query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Run a SELECT.  Returns a list of row dicts.  Retried on transient failure."""
    final = _build(sql, params)
    return _call("run_query", final, retryable=True)


def execute(sql: str, params: tuple = ()) -> None:
    """Run INSERT / UPDATE / DELETE.  Not retried (writes are non-idempotent)."""
    final = _build(sql, params)
    _call("run_exec", final, retryable=False)


def execute_returning(sql: str, params: tuple = ()) -> dict[str, Any] | None:
    """Run INSERT/UPDATE … RETURNING *.  Returns the first affected row.

    Not retried — this is a write, so a lost response after commit must not
    double-apply.
    """
    final = _build(sql, params)
    rows = _call("run_query", final, retryable=False)
    return rows[0] if rows else None


def ping() -> dict[str, Any]:
    """Health check — confirms Supabase is reachable."""
    try:
        rows = query("SELECT current_database() AS db, now() AS time")
        return {"ok": True, "db": rows[0]["db"], "time": str(rows[0]["time"])}
    except Exception as e:
        return {"ok": False, "error": str(e)}
