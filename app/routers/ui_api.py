"""
ui_api.py — All /api/* route handlers for the ALYASMEEN dashboard.
Extracted from ui.py to keep the page-route file under 150 lines.

Every route in this router requires a live operator session — the
router-level dependency below 401s an unauthenticated request, so no
per-handler guard is needed (see app/routers/auth_deps.py).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.db.database import execute, execute_returning, query
from app.routers.auth_deps import require_operator
from app.services import audit, handoff
from app.services.config import Config
from app.services.processor import queue_text, queue_pdf_invoice
from app.services.sessions import Operator

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ui"], dependencies=[Depends(require_operator)])


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
async def api_orders(status: str | None = None):
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
async def api_order_lines(order_id: int):
    rows = query(
        "SELECT product_name, qty, unit_price, line_total FROM order_lines WHERE order_id = %s",
        (order_id,),
    )
    return JSONResponse(content={"lines": rows})


@router.post("/api/orders/{order_id}/status")
async def api_update_status(order_id: int, request: Request, op: Operator = Depends(require_operator)):
    body = await request.json()
    new_status = (body.get("status") or "").strip().lower()
    force = bool(body.get("force"))

    if new_status not in {"ready", "delivered", "done"}:
        raise HTTPException(status_code=400, detail="Invalid status")

    # Load order
    rows = query(
        """SELECT o.id, o.phone, o.fulfillment, o.status,
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
    customer_name = order.get("customer_name") or ""
    from_status = order.get("status")

    # Bot-vs-aunt conflict guard — a heuristic, not a lock. The collision
    # being solved is one human (the aunt) versus one bot on the same
    # customer's conversation, on a 10-30 orders/day shop — not two
    # concurrent humans — so row versioning / advisory locks / a distributed
    # lock manager would be wildly disproportionate here (same reasoning as
    # handoff.bot_recently_active's own docstring). BEFORE any change is
    # applied, ask whether the bot is still talking to this customer.
    conflict = handoff.bot_recently_active(phone)
    if conflict and not force:
        return JSONResponse(status_code=409, content={
            "conflict": True,
            "reason": "bot_active",
            "customer_name": customer_name,
            "phone": phone,
            "last_activity": conflict["last_activity"],
            "requested_status": new_status,
            "message": f"البوت يتحدث مع {customer_name or phone} الآن",
        })

    if conflict and force:
        # The operator has explicitly chosen herself as the winner: stop the
        # bot on this conversation and open a takeover handoff so it shows up
        # in the handoffs tab with an explicit "return to bot" undo button.
        execute("UPDATE sessions SET paused = TRUE WHERE phone = %s", (phone,))
        execute(
            "INSERT INTO handoffs (phone, reason, status, assigned_to) VALUES (%s, %s, 'active', 'aunt')",
            (phone, "operator_takeover"),
        )
        audit.log_action(op.email, "order_status_conflict_override", {
            "order_id": order_id, "phone": phone, "from": from_status, "to": new_status,
        })

    # Every customer-facing send is enqueued into outbox_jobs instead of being
    # sent inline in this request handler. queue_text/queue_pdf_invoice are
    # just DB inserts (already covered by database.py's own retry/circuit-
    # breaker), so a failure here is a real DB problem that should surface as
    # a 500 to the operator, not vanish silently — the try/except swallow
    # that used to wrap each send is deliberately not carried over.
    if new_status == "ready":
        msg = (
            f"🚚 طلبك رقم {order_id} في الطريق إليك!"
            if fulfillment == "delivery"
            else f"✅ طلبك رقم {order_id} جاهز للاستلام!"
        )
        queue_text(phone, msg)
        execute(
            "UPDATE orders SET status = 'ready', updated_at = now() WHERE id = %s",
            (order_id,),
        )

    elif new_status == "delivered":
        queue_text(phone, f"📦 تم توصيل طلبك رقم {order_id}. نتمنى تكون راضي! 💚")
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
        queue_text(phone, f"✅ شكراً! استلمت طلبك رقم {order_id}. نتمنى تكون راضي 💚")
        queue_pdf_invoice(phone, order_id)
        execute(
            "UPDATE orders SET status = 'done', updated_at = now() WHERE id = %s",
            (order_id,),
        )

    audit.log_action(op.email, "order_status_changed", {
        "order_id": order_id, "from": from_status, "to": new_status,
    })

    return {"ok": True, "status": new_status, "order_id": order_id}


# ---------------------------------------------------------------------------
# Reports API
# ---------------------------------------------------------------------------

@router.get("/api/reports/months")
async def api_reports_months():
    """List all saved monthly snapshots (newest first)."""
    rows = query(
        "SELECT year, month FROM monthly_snapshots ORDER BY year DESC, month DESC"
    )
    return JSONResponse(content={"months": [{"year": r["year"], "month": r["month"]} for r in rows]})


# ---------------------------------------------------------------------------
# Dashboard stats API
# ---------------------------------------------------------------------------

@router.get("/api/dashboard/stats")
async def api_dashboard_stats(month: str | None = None):
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
async def api_list_products():
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
async def api_create_product(request: Request, op: Operator = Depends(require_operator)):
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
    audit.log_action(op.email, "product_created", {"product_id": row["id"], "name": name})
    return JSONResponse(content={"ok": True, "product": {
        "id": row["id"], "name": row["name"], "price": float(row["price"]),
        "description": row.get("description") or "", "tags": row.get("tags") or "",
        "active": row["active"],
    }})


@router.post("/api/products/{product_id}")
async def api_update_product(product_id: int, request: Request, op: Operator = Depends(require_operator)):
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
    audit.log_action(op.email, "product_updated", {"product_id": product_id, "name": name})
    return {"ok": True}


@router.post("/api/products/{product_id}/toggle")
async def api_toggle_product(product_id: int, op: Operator = Depends(require_operator)):
    rows = query("SELECT id, active, name FROM products WHERE id = %s", (product_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Product not found")
    new_active = not rows[0]["active"]
    execute("UPDATE products SET active = %s WHERE id = %s", (new_active, product_id))
    _invalidate()
    audit.log_action(op.email, "product_toggled", {
        "product_id": product_id, "name": rows[0].get("name"), "active": new_active,
    })
    return {"ok": True, "active": new_active}


@router.post("/api/products/{product_id}/delete")
async def api_delete_product(product_id: int, op: Operator = Depends(require_operator)):
    rows = query("SELECT id, name FROM products WHERE id = %s", (product_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Product not found")
    execute("DELETE FROM products WHERE id = %s", (product_id,))
    _invalidate()
    audit.log_action(op.email, "product_deleted", {
        "product_id": product_id, "name": rows[0].get("name"),
    })
    return {"ok": True}


# ---------------------------------------------------------------------------
# Alerts API — dead-lettered webhook_events + permanently-failed outbox_jobs
# ---------------------------------------------------------------------------

@router.get("/api/alerts")
async def api_alerts():
    dead_events = query(
        "SELECT id, phone, payload, error, attempts, created_at FROM webhook_events "
        "WHERE processed = TRUE AND error LIKE %s ORDER BY created_at DESC LIMIT 100",
        ("dead-letter:%",),
    )
    failed_jobs = query(
        "SELECT id, kind, phone, payload, last_error, attempts, max_attempts, created_at "
        "FROM outbox_jobs WHERE status = 'failed' AND attempts >= max_attempts "
        "ORDER BY created_at DESC LIMIT 100",
    )
    for row in dead_events + failed_jobs:
        if row.get("created_at") and not isinstance(row["created_at"], str):
            row["created_at"] = row["created_at"].isoformat()
    return JSONResponse(content={"webhook_events": dead_events, "outbox_jobs": failed_jobs})


@router.post("/api/alerts/webhook_events/{event_id}/retry")
async def api_retry_webhook_event(event_id: str, op: Operator = Depends(require_operator)):
    execute(
        "UPDATE webhook_events SET processed = FALSE, attempts = 0, error = NULL WHERE id = %s",
        (event_id,),
    )
    audit.log_action(op.email, "alert_retried", {"source": "webhook_event", "id": event_id})
    return {"ok": True}


@router.post("/api/alerts/outbox_jobs/{job_id}/retry")
async def api_retry_outbox_job(job_id: str, op: Operator = Depends(require_operator)):
    execute(
        "UPDATE outbox_jobs SET status = 'pending', attempts = 0, last_error = NULL, "
        "updated_at = now() WHERE id = %s",
        (job_id,),
    )
    audit.log_action(op.email, "alert_retried", {"source": "outbox_job", "id": job_id})
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
async def api_broadcast_audience(filter: str = "all"):
    if filter not in {"all", "month", "top"}:
        raise HTTPException(status_code=400, detail="filter must be all|month|top")
    phones = _broadcast_phones(filter)
    return JSONResponse(content={"count": len(phones)})


@router.post("/api/broadcast/send")
async def api_broadcast_send(request: Request, op: Operator = Depends(require_operator)):
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
    audit.log_action(op.email, "broadcast_sent", {"filter": filter, "sent": sent, "failed": failed})
    return JSONResponse(content={"sent": sent, "failed": failed, "total": len(phones)})
