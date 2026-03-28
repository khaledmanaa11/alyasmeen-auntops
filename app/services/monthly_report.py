"""
monthly_report.py — Monthly business summary sent to the aunt.

Runs on the 1st of each month via APScheduler (wired in main.py).
Queries the previous month's orders, sends an Arabic WhatsApp summary
to AUNT_PHONE, and saves a snapshot to monthly_snapshots for the dashboard.

Note: This file is ~162 lines — only slightly over 150 and contains tightly
coupled report-building and snapshot-saving logic. No split needed.
"""
from __future__ import annotations

import json
import logging
from calendar import monthrange
from datetime import date, timedelta

from app.db.database import execute, query
from app.services.config import Config

if Config.USE_MOCK_WHATSAPP:
    from app.services.whatsapp_dev import send_text
else:
    from app.services.whatsapp_meta import send_text

log = logging.getLogger(__name__)

_AR_MONTHS = [
    "", "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
    "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر",
]


def _previous_month() -> tuple[date, date]:
    today = date.today()
    first_of_this_month = today.replace(day=1)
    last_day_prev = first_of_this_month - timedelta(days=1)
    return last_day_prev.replace(day=1), last_day_prev


def build_report(year: int, month: int) -> str:
    _, last_day = monthrange(year, month)
    start = date(year, month, 1)
    end   = date(year, month, last_day)

    summary = query(
        """
        SELECT COUNT(*) AS total_orders,
               COALESCE(SUM(total), 0) AS total_revenue
        FROM orders
        WHERE created_at >= %s AND created_at < %s::date + INTERVAL '1 day'
        """,
        (start.isoformat(), end.isoformat()),
    )
    total_orders  = int(summary[0]["total_orders"])  if summary else 0
    total_revenue = float(summary[0]["total_revenue"]) if summary else 0.0

    top_products = query(
        """
        SELECT ol.product_name, SUM(ol.qty) AS total_qty
        FROM order_lines ol
        JOIN orders o ON o.id = ol.order_id
        WHERE o.created_at >= %s AND o.created_at < %s::date + INTERVAL '1 day'
        GROUP BY ol.product_name
        ORDER BY total_qty DESC
        LIMIT 5
        """,
        (start.isoformat(), end.isoformat()),
    )

    month_ar = _AR_MONTHS[month]
    lines = [
        f"📊 *تقرير شهر {month_ar} {year}*\n",
        f"📦 إجمالي الطلبات: *{total_orders}*",
        f"💰 إجمالي الإيرادات: *{total_revenue:.2f} ₪*\n",
    ]
    if top_products:
        lines.append("🏆 *أكثر المنتجات مبيعاً:*")
        for i, row in enumerate(top_products, 1):
            lines.append(f"  {i}. {row['product_name']} — {int(row['total_qty'])} قطعة")
    else:
        lines.append("لا توجد مبيعات مسجلة هذا الشهر.")

    lines.append("\nبالتوفيق يا عمتي! 🌿✨ — ALYASMEEN Bot")
    return "\n".join(lines)


def save_snapshot(year: int, month: int) -> None:
    """Save full monthly stats to monthly_snapshots so the dashboard can show history."""
    _, last_day = monthrange(year, month)
    start = date(year, month, 1)
    end   = date(year, month, last_day)
    s = start.isoformat()
    e = end.isoformat()

    summary = query(
        "SELECT COUNT(*) AS total_orders, COALESCE(SUM(total),0) AS revenue "
        "FROM orders WHERE created_at >= %s AND created_at < %s::date + INTERVAL '1 day'",
        (s, e),
    )
    total_customers = query("SELECT COUNT(*) AS count FROM customers")

    daily_orders = query(
        "SELECT TO_CHAR(DATE(created_at AT TIME ZONE 'UTC'),'YYYY-MM-DD') AS day, COUNT(*) AS count "
        "FROM orders WHERE created_at >= %s AND created_at < %s::date + INTERVAL '1 day' "
        "GROUP BY DATE(created_at AT TIME ZONE 'UTC') ORDER BY day",
        (s, e),
    )
    status_breakdown = query(
        "SELECT status, COUNT(*) AS count FROM orders "
        "WHERE created_at >= %s AND created_at < %s::date + INTERVAL '1 day' GROUP BY status",
        (s, e),
    )
    top_products = query(
        "SELECT ol.product_name, SUM(ol.qty) AS total_qty, COALESCE(SUM(ol.line_total),0) AS revenue "
        "FROM order_lines ol JOIN orders o ON o.id = ol.order_id "
        "WHERE o.created_at >= %s AND o.created_at < %s::date + INTERVAL '1 day' "
        "GROUP BY ol.product_name ORDER BY total_qty DESC LIMIT 5",
        (s, e),
    )

    m = summary[0] if summary else {"total_orders": 0, "revenue": 0}
    snapshot = {
        "year": year, "month": month,
        "this_month": {"orders": int(m["total_orders"]), "revenue": float(m["revenue"])},
        "last_month":  {"orders": 0, "revenue": 0},   # not meaningful for archives
        "total_customers": int(total_customers[0]["count"]) if total_customers else 0,
        "daily_orders":    [{"day": r["day"], "count": int(r["count"])} for r in daily_orders],
        "status_breakdown": [{"status": r["status"], "count": int(r["count"])} for r in status_breakdown],
        "top_products": [
            {"name": r["product_name"], "qty": int(r["total_qty"]), "revenue": float(r["revenue"])}
            for r in top_products
        ],
    }

    execute(
        """
        INSERT INTO monthly_snapshots (year, month, data)
        VALUES (%s, %s, %s)
        ON CONFLICT (year, month) DO UPDATE SET data = EXCLUDED.data, created_at = now()
        """,
        (year, month, json.dumps(snapshot, ensure_ascii=False)),
    )
    log.info("monthly_report: snapshot saved for %d-%02d", year, month)


def send_monthly_report() -> None:
    if not Config.AUNT_PHONE:
        log.warning("monthly_report: AUNT_PHONE not set — skipping")
        return

    first_day, _ = _previous_month()
    report = build_report(first_day.year, first_day.month)

    try:
        send_text(Config.AUNT_PHONE, report)
        log.info("monthly_report: sent for %d-%02d", first_day.year, first_day.month)
    except Exception:
        log.exception("monthly_report: failed to send WhatsApp report")

    try:
        save_snapshot(first_day.year, first_day.month)
    except Exception:
        log.exception("monthly_report: failed to save snapshot")
