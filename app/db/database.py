# database.py
# Connects to Supabase via HTTPS (supabase-py) instead of psycopg2.
# All SQL runs through two PostgreSQL helper functions created in Supabase:
#   run_query(sql)  → SELECT / INSERT...RETURNING  (returns JSON array)
#   run_exec(sql)   → INSERT / UPDATE / DELETE      (returns void)
# Every other file imports query / execute / execute_returning from here.

import json
import logging
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
# Public API  (same interface as the old psycopg2 version)
# ---------------------------------------------------------------------------

def query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Run a SELECT.  Returns a list of row dicts."""
    final = _build(sql, params)
    result = _get_client().rpc("run_query", {"sql": final}).execute()
    return result.data or []


def execute(sql: str, params: tuple = ()) -> None:
    """Run INSERT / UPDATE / DELETE.  Returns nothing."""
    final = _build(sql, params)
    _get_client().rpc("run_exec", {"sql": final}).execute()


def execute_returning(sql: str, params: tuple = ()) -> dict[str, Any] | None:
    """Run INSERT/UPDATE … RETURNING *.  Returns the first affected row."""
    final = _build(sql, params)
    result = _get_client().rpc("run_query", {"sql": final}).execute()
    rows = result.data or []
    return rows[0] if rows else None


def ping() -> dict[str, Any]:
    """Health check — confirms Supabase is reachable."""
    try:
        rows = query("SELECT current_database() AS db, now() AS time")
        return {"ok": True, "db": rows[0]["db"], "time": str(rows[0]["time"])}
    except Exception as e:
        return {"ok": False, "error": str(e)}
