"""debug.py — Development-only endpoints for ALYASMEEN AuntOps.

Provides a POST /dev/test_order endpoint that creates a synthetic order
in the database without going through the WhatsApp bot flow. Used for
local testing of the dashboard, order status updates, and notifications.
These routes are registered by main.py and should not be exposed in production.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.database import execute, execute_returning
from app.routers.whatsapp import _CATALOG

log = logging.getLogger(__name__)

router = APIRouter(prefix="/dev", tags=["dev"])


class TestItem(BaseModel):
    """A single line item for a test order, referencing a product by 1-based catalog index."""

    product_index: int  # 1-based index into catalog.json
    qty: int = 1


class CreateTestOrder(BaseModel):
    """Request body for POST /dev/test_order.

    If items is empty, the first three products from the catalog are used.
    """

    phone: str = "+972500000999"
    items: list[TestItem] = []  # if empty, auto-picks first 3 from catalog
    fulfillment: str = "pickup"  # or 'delivery'
    address: str = ""
    note: str | None = None


@router.post("/test_order")
def create_test_order(p: CreateTestOrder):
    """Create a synthetic test order directly in the database.

    Inserts a customer (if not already present), an order row, and order line
    items based on the provided cart. Useful for exercising the dashboard and
    status-update flows without sending a real WhatsApp message.

    Args:
        p: CreateTestOrder payload — phone, items, fulfillment, address, note.

    Returns:
        Dict with ok=True, order_id, order_name, and cart on success.

    Raises:
        HTTPException 400: if fulfillment is invalid or a product_index is out of range.
        HTTPException 500: if the catalog is empty or missing.
    """
    if p.fulfillment not in ("pickup", "delivery"):
        raise HTTPException(status_code=400, detail="fulfillment must be pickup or delivery")

    if not _CATALOG:
        raise HTTPException(status_code=500, detail="catalog.json is empty or missing")

    # Build cart from catalog
    if not p.items:
        cart = [
            {"product_id": prod["id"], "name": prod["name"],
             "price": float(prod.get("list_price", 0) or 0), "qty": 1}
            for prod in _CATALOG[:3]
        ]
    else:
        cart = []
        for it in p.items:
            idx = it.product_index - 1
            if idx < 0 or idx >= len(_CATALOG):
                raise HTTPException(status_code=400, detail=f"product_index {it.product_index} out of range")
            prod = _CATALOG[idx]
            cart.append({
                "product_id": prod["id"],
                "name": prod["name"],
                "price": float(prod.get("list_price", 0) or 0),
                "qty": it.qty,
            })

    total = sum(it["qty"] * it["price"] for it in cart)

    # Ensure customer exists (FK requirement)
    execute(
        "INSERT INTO customers (phone, name) VALUES (%s, %s) ON CONFLICT (phone) DO NOTHING",
        (p.phone, "Test Customer"),
    )

    # Insert into PostgreSQL
    order_row = execute_returning(
        """
        INSERT INTO orders (phone, fulfillment, address, total, status, channel, created_at, updated_at)
        VALUES (%s, %s, %s, %s, 'to_do', 'whatsapp', now(), now())
        RETURNING id
        """,
        (p.phone, p.fulfillment, p.address, total),
    )
    order_id = order_row["id"]
    order_name = f"ORD-{order_id:04d}"
    execute("UPDATE orders SET order_name = %s WHERE id = %s", (order_name, order_id))

    for it in cart:
        execute(
            "INSERT INTO order_lines (order_id, product_name, qty, unit_price, line_total) VALUES (%s, %s, %s, %s, %s)",
            (order_id, it["name"], it["qty"], it["price"], it["qty"] * it["price"]),
        )

    return {
        "ok": True,
        "order_id": order_id,
        "order_name": order_name,
        "cart": cart,
    }
