"""
ui_api.py — All /api/* route handlers for the ALYASMEEN dashboard.
Extracted from ui.py to keep the page-route file under 150 lines.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.db.database import execute, execute_returning, query
from app.services.config import Config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ui"])

COOKIE_NAME = "alyasmeen_session"


def _session_token() -> str:
    raw = f"{Config.SECRET_KEY}:{Config.DASHBOARD_PASSWORD}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _is_authenticated(request: Request) -> bool:
    return request.cookies.get(COOKIE_NAME) == _session_token()


# ---------------------------------------------------------------------------
# Helper: invalidate the in-memory product cache
# ---------------------------------------------------------------------------

def _invalidate():
    from app.ai.retriever import invalidate_catalog
    invalidate_catalog()


# ---------------------------------------------------------------------------
# Orders APIs
# ---------------------------------------------------------------------------

@router.get("/api/orders")
async def api_orders(request: Request, status: str | None = None):
    if not _is_authenticated(request):
        raise HTTPException(status_code=401)

    sql = """
        SELECT o.id, o.phone, o.fulfillment, o.address,
               o.total, o.status, o.created_at, o.order_name,
               COALESCE(c.name, '') AS customer_name,
               COUNT(ol.id) AS item_count
        FROM orders o
        LEFT JOIN customers c ON c.phone = o.phone
        LEFT JOIN order_lines ol ON ol.order_id = o.id
    """
    params: tuple = ()
    if status and status != "all":
        sql += " WHERE o.status = %s"
        params = (status,)
    sql += " GROUP BY o.id, c.name ORDER BY o.created_at DESC LIMIT 200"

    rows = query(sql, params)
    for row in rows:
        if row.get("created_at") and not isinstance(row["created_at"], str):
            row["created_at"] = row["created_at"].isoformat()
    return JSONResponse(content={"orders": rows})


@router.get("/api/orders/{order_id}/lines")
async def api_order_lines(order_id: int, request: Request):
    if not _is_authenticated(request):
        raise HTTPException(status_code=401)
    rows = query(
        "SELECT product_name, qty, unit_price, line_total FROM order_lines WHERE order_id = %s",
        (order_id,),
    )
    return JSONResponse(content={"lines": rows})


@router.post("/api/orders/{order_id}/status")
async def api_update_status(order_id: int, request: Request):
    if not _is_authenticated(request):
        raise HTTPException(status_code=401)

    body = await request.json()
    new_status = (body.get("status") or "").strip().lower()

    if new_status not in {"ready", "delivered", "done"}:
        raise HTTPException(status_code=400, detail="Invalid status")

    # Load order
    rows = query(
        """SELECT o.id, o.phone, o.fulfillment,
                  COALESCE(c.name, '') AS customer_name
           FROM orders o
           LEFT JOIN customers c ON c.phone = o.phone
           WHERE o.id = %s""",
        (order_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Order not found")

    order = rows[0]
    phone = order["phone"]
    fulfillment = order.get("fulfillment") or "pickup"

    # Choose WhatsApp sender
    if Config.USE_MOCK_WHATSAPP:
        from app.services.whatsapp_dev import send_text
    else:
        from app.services.whatsapp_meta import send_text

    if new_status == "ready":
        try:
            msg = (
                f"🚚 طلبك رقم {order_id} في الطريق إليك!"
                if fulfillment == "delivery"
                else f"✅ طلبك رقم {order_id} جاهز للاستلام!"
            )
            send_text(phone, msg)
        except Exception:
            logger.warning("send_text ready failed order_id=%s", order_id)
        execute(
            "UPDATE orders SET status = 'ready', updated_at = now() WHERE id = %s",
            (order_id,),
        )

    elif new_status == "delivered":
        try:
            send_text(phone, f"📦 تم توصيل طلبك رقم {order_id}. نتمنى تكون راضي! 💚")
        except Exception:
            logger.warning("send_text delivered failed order_id=%s", order_id)
        try:
            from app.services.followup import record_delivery
            record_delivery(phone, str(order_id))
        except Exception:
            logger.warning("record_delivery failed order_id=%s", order_id)
        execute(
            "UPDATE orders SET status = 'delivered', updated_at = now() WHERE id = %s",
            (order_id,),
        )

    elif new_status == "done":
        try:
            send_text(phone, f"✅ شكراً! استلمت طلبك رقم {order_id}. نتمنى تكون راضي 💚")
        except Exception:
            logger.warning("send_text done failed order_id=%s", order_id)
        try:
            lines = query(
                "SELECT product_name, qty, unit_price FROM order_lines WHERE order_id = %s",
                (order_id,),
            )
            from app.services.pdf_invoice import generate_invoice_pdf
            if Config.USE_MOCK_WHATSAPP:
                from app.services.whatsapp_dev import send_document_bytes
            else:
                from app.services.whatsapp_meta import send_document_bytes
            total = sum(float(ln["unit_price"]) * int(ln["qty"]) for ln in lines)
            pdf_bytes = generate_invoice_pdf(
                order_id=order_id,
                customer_name=order["customer_name"],
                order_date=date.today().strftime("%d/%m/%Y"),
                lines=lines,
                total=total,
            )
            send_document_bytes(
                phone,
                pdf_bytes,
                filename=f"فاتورة-{order_id}.pdf",
                caption=f"🧾 فاتورتك لطلب رقم {order_id}",
            )
        except Exception:
            logger.warning("pdf_invoice failed order_id=%s", order_id)
        execute(
            "UPDATE orders SET status = 'done', updated_at = now() WHERE id = %s",
            (order_id,),
        )

    return {"ok": True, "status": new_status, "order_id": order_id}


# ---------------------------------------------------------------------------
# Reports API
# ---------------------------------------------------------------------------

@router.get("/api/reports/months")
async def api_reports_months(request: Request):
    """List all saved monthly snapshots (newest first)."""
    if not _is_authenticated(request):
        raise HTTPException(status_code=401)
    rows = query(
        "SELECT year, month FROM monthly_snapshots ORDER BY year DESC, month DESC"
    )
    return JSONResponse(content={"months": [{"year": r["year"], "month": r["month"]} for r in rows]})


# ---------------------------------------------------------------------------
# Dashboard stats API
# ---------------------------------------------------------------------------

@router.get("/api/dashboard/stats")
async def api_dashboard_stats(request: Request, month: str | None = None):
    if not _is_authenticated(request):
        raise HTTPException(status_code=401)

    # Historical snapshot requested (format: "YYYY-MM")
    if month:
        try:
            year, m = map(int, month.split("-"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="month must be YYYY-MM") from exc
        rows = query(
            "SELECT data FROM monthly_snapshots WHERE year = %s AND month = %s",
            (year, m),
        )
        if not rows:
            raise HTTPException(status_code=404, detail="No snapshot for this month")
        return JSONResponse(content=rows[0]["data"])

    this_month = query("""
        SELECT COUNT(*) AS total_orders, COALESCE(SUM(total), 0) AS revenue
        FROM orders
        WHERE created_at >= date_trunc('month', now())
    """)

    last_month = query("""
        SELECT COUNT(*) AS total_orders, COALESCE(SUM(total), 0) AS revenue
        FROM orders
        WHERE created_at >= date_trunc('month', now() - INTERVAL '1 month')
          AND created_at  < date_trunc('month', now())
    """)

    total_customers = query("SELECT COUNT(*) AS count FROM customers")

    daily_orders = query("""
        SELECT TO_CHAR(DATE(created_at AT TIME ZONE 'UTC'), 'YYYY-MM-DD') AS day,
               COUNT(*) AS count
        FROM orders
        WHERE created_at >= now() - INTERVAL '30 days'
        GROUP BY DATE(created_at AT TIME ZONE 'UTC')
        ORDER BY day
    """)

    status_breakdown = query("""
        SELECT status, COUNT(*) AS count
        FROM orders
        GROUP BY status
    """)

    top_products = query("""
        SELECT ol.product_name,
               SUM(ol.qty)        AS total_qty,
               COALESCE(SUM(ol.line_total), 0) AS revenue
        FROM order_lines ol
        JOIN orders o ON o.id = ol.order_id
        WHERE o.created_at >= date_trunc('month', now())
        GROUP BY ol.product_name
        ORDER BY total_qty DESC
        LIMIT 5
    """)

    m = this_month[0] if this_month else {"total_orders": 0, "revenue": 0}
    p = last_month[0] if last_month else {"total_orders": 0, "revenue": 0}

    return {
        "this_month": {
            "orders": int(m["total_orders"]),
            "revenue": float(m["revenue"]),
        },
        "last_month": {
            "orders": int(p["total_orders"]),
            "revenue": float(p["revenue"]),
        },
        "total_customers": int(total_customers[0]["count"]) if total_customers else 0,
        "daily_orders": [
            {"day": r["day"], "count": int(r["count"])} for r in daily_orders
        ],
        "status_breakdown": [
            {"status": r["status"], "count": int(r["count"])} for r in status_breakdown
        ],
        "top_products": [
            {
                "name": r["product_name"],
                "qty": int(r["total_qty"]),
                "revenue": float(r["revenue"]),
            }
            for r in top_products
        ],
    }


# ---------------------------------------------------------------------------
# Products API
# ---------------------------------------------------------------------------

@router.get("/api/products")
async def api_list_products(request: Request):
    if not _is_authenticated(request):
        raise HTTPException(status_code=401)
    rows = query("SELECT id, name, price, description, tags, active FROM products ORDER BY id")
    return JSONResponse(content={"products": [
        {
            "id": r["id"],
            "name": r["name"],
            "price": float(r["price"]),
            "description": r.get("description") or "",
            "tags": r.get("tags") or "",
            "active": r["active"],
        }
        for r in rows
    ]})


@router.post("/api/products")
async def api_create_product(request: Request):
    if not _is_authenticated(request):
        raise HTTPException(status_code=401)
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    try:
        price = float(body.get("price") or 0)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="invalid price") from exc
    if price <= 0:
        raise HTTPException(status_code=400, detail="price must be > 0")
    description = (body.get("description") or "").strip()
    tags = (body.get("tags") or "").strip()
    row = execute_returning(
        "INSERT INTO products (name, price, description, tags) VALUES (%s, %s, %s, %s) RETURNING id, name, price, description, tags, active",
        (name, price, description, tags),
    )
    _invalidate()
    return JSONResponse(content={"ok": True, "product": {
        "id": row["id"], "name": row["name"], "price": float(row["price"]),
        "description": row.get("description") or "", "tags": row.get("tags") or "",
        "active": row["active"],
    }})


@router.post("/api/products/{product_id}")
async def api_update_product(product_id: int, request: Request):
    if not _is_authenticated(request):
        raise HTTPException(status_code=401)
    rows = query("SELECT id FROM products WHERE id = %s", (product_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Product not found")
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    try:
        price = float(body.get("price") or 0)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="invalid price") from exc
    if price <= 0:
        raise HTTPException(status_code=400, detail="price must be > 0")
    description = (body.get("description") or "").strip()
    tags = (body.get("tags") or "").strip()
    execute(
        "UPDATE products SET name = %s, price = %s, description = %s, tags = %s WHERE id = %s",
        (name, price, description, tags, product_id),
    )
    _invalidate()
    return {"ok": True}


@router.post("/api/products/{product_id}/toggle")
async def api_toggle_product(product_id: int, request: Request):
    if not _is_authenticated(request):
        raise HTTPException(status_code=401)
    rows = query("SELECT id, active FROM products WHERE id = %s", (product_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Product not found")
    new_active = not rows[0]["active"]
    execute("UPDATE products SET active = %s WHERE id = %s", (new_active, product_id))
    _invalidate()
    return {"ok": True, "active": new_active}


@router.post("/api/products/{product_id}/delete")
async def api_delete_product(product_id: int, request: Request):
    if not _is_authenticated(request):
        raise HTTPException(status_code=401)
    rows = query("SELECT id FROM products WHERE id = %s", (product_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Product not found")
    execute("DELETE FROM products WHERE id = %s", (product_id,))
    _invalidate()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Broadcast APIs
# ---------------------------------------------------------------------------

def _broadcast_phones(filter: str) -> list:
    """Return a deduplicated list of phone numbers for the given audience filter."""
    if filter == "month":
        rows = query("""
            SELECT DISTINCT o.phone
            FROM orders o
            WHERE o.created_at >= now() - INTERVAL '30 days'
              AND o.phone IS NOT NULL AND o.phone != %s
        """, ("",))
    elif filter == "top":
        rows = query("""
            SELECT phone
            FROM orders
            WHERE phone IS NOT NULL AND phone != %s
            GROUP BY phone
            ORDER BY COUNT(*) DESC
            LIMIT 10
        """, ("",))
    else:
        rows = query("""
            SELECT phone FROM customers
            WHERE phone IS NOT NULL AND phone != %s
        """, ("",))
    return [r["phone"] for r in rows if r.get("phone")]


@router.get("/api/broadcast/audience")
async def api_broadcast_audience(request: Request, filter: str = "all"):
    if not _is_authenticated(request):
        raise HTTPException(status_code=401)
    if filter not in {"all", "month", "top"}:
        raise HTTPException(status_code=400, detail="filter must be all|month|top")
    phones = _broadcast_phones(filter)
    return JSONResponse(content={"count": len(phones)})


@router.post("/api/broadcast/send")
async def api_broadcast_send(request: Request):
    if not _is_authenticated(request):
        raise HTTPException(status_code=401)

    body = await request.json()
    message = (body.get("message") or "").strip()
    filter = (body.get("filter") or "all").strip()

    if not message:
        raise HTTPException(status_code=400, detail="message required")
    if filter not in {"all", "month", "top"}:
        raise HTTPException(status_code=400, detail="filter must be all|month|top")

    phones = _broadcast_phones(filter)

    if Config.USE_MOCK_WHATSAPP:
        from app.services.whatsapp_dev import send_text
    else:
        from app.services.whatsapp_meta import send_text

    sent = 0
    failed = 0
    for phone in phones:
        try:
            send_text(phone, message)
            sent += 1
        except Exception as e:
            logger.warning("broadcast send_text failed phone=%s err=%s", phone, e)
            failed += 1

    logger.info("broadcast complete sent=%d failed=%d filter=%s", sent, failed, filter)
    return JSONResponse(content={"sent": sent, "failed": failed, "total": len(phones)})
