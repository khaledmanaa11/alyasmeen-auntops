"""
WhatsApp session, customer, and catalog helpers — extracted from whatsapp.py
to keep the route file focused on request handling.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.ai.retriever import _catalog as _active_products
from app.db.database import execute, query

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Product catalog — live from the Supabase `products` table (app/ai/retriever.py)
# ---------------------------------------------------------------------------

def catalog() -> list[dict[str, Any]]:
    """Active products in the legacy {id, name, list_price, description_sale} shape.

    The bot's numeric `info N` command and the /dev/test_order endpoint index into
    this list. It adapts the cached Supabase loader in app/ai/retriever.py, so it
    always reflects the live `products` table; after a product create/update/delete
    the dashboard calls invalidate_catalog() there and the next call here is fresh.
    """
    out: list[dict[str, Any]] = []
    for r in _active_products():
        try:
            pid = int(r["sku"])
        except (TypeError, ValueError, KeyError):
            continue
        out.append({
            "id": pid,
            "name": r.get("name", ""),
            "list_price": float(r.get("price", 0) or 0),
            "description_sale": r.get("description", ""),
        })
    return out

STATUS_LABELS = {
    "to_do":     "قيد التحضير 🔄",
    "ready":     "جاهز للاستلام ✅",
    "delivered": "تم التوصيل 🚚",
    "done":      "مكتمل ✅",
}


# ---------------------------------------------------------------------------
# Session helpers (PostgreSQL-backed)
# ---------------------------------------------------------------------------

def load_session(phone: str) -> dict[str, Any]:
    rows = query(
        "SELECT stage, cart, fulfillment, menu_products, address, paused FROM sessions WHERE phone = %s",
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
            "paused": bool(row.get("paused")),
        }
    return {"stage": "root", "cart": [], "fulfillment": None, "menu_products": [], "address": "", "paused": False}


# save_session() deliberately never writes `paused` — the ON CONFLICT DO
# UPDATE SET list below is correct precisely because it omits that column.
# Only handoff.trigger() (sets TRUE) and handoff.resolve() (sets FALSE) own
# `sessions.paused`. Do not "fix" this apparent omission: doing so would
# silently un-pause every handed-off conversation the moment the customer's
# next message runs through the ordinary session-save path.
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
