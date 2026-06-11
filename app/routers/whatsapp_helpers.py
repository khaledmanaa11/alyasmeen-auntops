"""
WhatsApp session, customer, and catalog helpers — extracted from whatsapp.py
to keep the route file focused on request handling.
"""
from __future__ import annotations

import json
import logging
import pathlib
from typing import Any

from app.db.database import execute, query

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Product catalog (catalog.json — legacy; Supabase products table is live source)
# ---------------------------------------------------------------------------

def _load_catalog() -> list[dict[str, Any]]:
    p = pathlib.Path(__file__).resolve().parents[2] / "app" / "data" / "catalog.json"
    try:
        with open(p, encoding="utf-8") as f:
            raw = json.load(f)
        return [
            {
                "id": i + 1,
                "name": item.get("name", ""),
                "list_price": float(item.get("price", 0)),
                "description_sale": item.get("description", ""),
            }
            for i, item in enumerate(raw)
        ]
    except Exception:
        return []


_CATALOG: list[dict[str, Any]] = _load_catalog()

STATUS_LABELS = {
    "to_do":     "قيد التحضير 🔄",
    "ready":     "جاهز للاستلام ✅",
    "delivered": "تم التوصيل 🚚",
    "done":      "مكتمل ✅",
}


# ---------------------------------------------------------------------------
# Session helpers (PostgreSQL-backed)
# ---------------------------------------------------------------------------

def load_context(phone: str, history_limit: int = 8) -> dict[str, Any]:
    """Load session + customer + chat history in ONE database round trip.

    Replaces the load_session / upsert_customer-SELECT / load_history /
    get_customer_name / get_saved_address sequence (4-5 sequential RPCs)
    on the webhook hot path.

    Returns:
        {
          "session":  same shape as load_session(),
          "customer": {"name": ..., "saved_address": ...} or None if new,
          "history":  [{"role": ..., "content": ...}, ...] oldest-first,
        }
    """
    rows = query(
        """
        SELECT
          (SELECT row_to_json(s) FROM (
              SELECT stage, cart, fulfillment, menu_products, address
              FROM sessions WHERE phone = %s) s)                        AS session,
          (SELECT row_to_json(c) FROM (
              SELECT name, saved_address
              FROM customers WHERE phone = %s) c)                       AS customer,
          (SELECT coalesce(
              json_agg(json_build_object('role', h.role, 'content', h.content)
                       ORDER BY h.created_at),
              '[]'::json)
           FROM (SELECT role, content, created_at FROM chat_history
                 WHERE phone = %s
                 ORDER BY created_at DESC LIMIT %s) h)                  AS history
        """,
        (phone, phone, phone, history_limit),
    )
    row = rows[0] if rows else {}
    sess = row.get("session") or {}
    return {
        "session": {
            "stage": sess.get("stage") or "root",
            "cart": sess["cart"] if isinstance(sess.get("cart"), list) else [],
            "fulfillment": sess.get("fulfillment"),
            "menu_products": sess["menu_products"] if isinstance(sess.get("menu_products"), list) else [],
            "address": sess.get("address") or "",
        },
        "customer": row.get("customer"),
        "history": row.get("history") or [],
    }


def load_session(phone: str) -> dict[str, Any]:
    rows = query(
        "SELECT stage, cart, fulfillment, menu_products, address FROM sessions WHERE phone = %s",
        (phone,),
    )
    if rows:
        row = rows[0]
        return {
            "stage": row["stage"] or "root",
            "cart": row["cart"] if isinstance(row["cart"], list) else [],
            "fulfillment": row["fulfillment"],
            "menu_products": row["menu_products"] if isinstance(row["menu_products"], list) else [],
            "address": row["address"] or "",
        }
    return {"stage": "root", "cart": [], "fulfillment": None, "menu_products": [], "address": ""}


def save_session(phone: str, st: dict[str, Any]) -> None:
    execute(
        """
        INSERT INTO sessions (phone, stage, cart, fulfillment, menu_products, address, updated_at)
        VALUES (%s, %s, %s::jsonb, %s, %s::jsonb, %s, now())
        ON CONFLICT (phone) DO UPDATE SET
            stage          = EXCLUDED.stage,
            cart           = EXCLUDED.cart,
            fulfillment    = EXCLUDED.fulfillment,
            menu_products  = EXCLUDED.menu_products,
            address        = EXCLUDED.address,
            updated_at     = now()
        """,
        (
            phone,
            st.get("stage", "root"),
            json.dumps(st.get("cart") or []),
            st.get("fulfillment"),
            json.dumps(st.get("menu_products") or []),
            st.get("address") or "",
        ),
    )


def clear_session(phone: str) -> None:
    execute("DELETE FROM sessions WHERE phone = %s", (phone,))


# ---------------------------------------------------------------------------
# Chat history helpers (PostgreSQL-backed)
# ---------------------------------------------------------------------------

def load_history(phone: str, limit: int = 8) -> list[dict[str, str]]:
    rows = query(
        "SELECT role, content FROM chat_history WHERE phone = %s "
        "ORDER BY created_at DESC LIMIT %s",
        (phone, limit),
    )
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def append_history(phone: str, role: str, content: str) -> None:
    execute(
        "INSERT INTO chat_history (phone, role, content) VALUES (%s, %s, %s)",
        (phone, role, content),
    )


# ---------------------------------------------------------------------------
# Customer helpers
# ---------------------------------------------------------------------------

def upsert_customer(phone: str, name: str = "") -> bool:
    """
    Returns True (new customer) or False (returning customer).
    Saves the name on first contact; updates it later if it was blank before.
    """
    rows = query("SELECT phone, name FROM customers WHERE phone = %s", (phone,))
    if rows:
        if name and not (rows[0].get("name") or "").strip():
            execute(
                "UPDATE customers SET name = %s, updated_at = now() WHERE phone = %s",
                (name, phone),
            )
        return False
    execute(
        "INSERT INTO customers (phone, name, created_at, updated_at) VALUES (%s, %s, now(), now())",
        (phone, name),
    )
    return True


def create_customer(phone: str, name: str = "") -> None:
    """Insert a new customer row (no-op if it already exists)."""
    execute(
        "INSERT INTO customers (phone, name, created_at, updated_at) "
        "VALUES (%s, %s, now(), now()) ON CONFLICT (phone) DO NOTHING",
        (phone, name),
    )


def update_customer_name(phone: str, name: str) -> None:
    execute(
        "UPDATE customers SET name = %s, updated_at = now() WHERE phone = %s",
        (name, phone),
    )


def get_customer_name(phone: str) -> str:
    rows = query("SELECT name FROM customers WHERE phone = %s", (phone,))
    return (rows[0].get("name") or "").strip() if rows else ""


def get_saved_address(phone: str) -> str:
    rows = query("SELECT saved_address FROM customers WHERE phone = %s", (phone,))
    return (rows[0].get("saved_address") or "").strip() if rows else ""


def save_customer_address(phone: str, address: str) -> None:
    execute(
        "UPDATE customers SET saved_address = %s, updated_at = now() WHERE phone = %s",
        (address, phone),
    )


# ---------------------------------------------------------------------------
# Order lookup
# ---------------------------------------------------------------------------

def get_latest_order(phone: str):
    """Return the most recent order row for this phone, or None."""
    rows = query(
        "SELECT id, status, created_at, fulfillment FROM orders "
        "WHERE phone = %s ORDER BY created_at DESC LIMIT 1",
        (phone,),
    )
    return rows[0] if rows else None
