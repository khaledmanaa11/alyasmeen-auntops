"""
operator_api.py — Handoffs + audit JSON API for the ALYASMEEN dashboard
(REQ-prod-handoff).

Every route here requires a live operator session — the router-level
dependency below 401s an unauthenticated request, matching the pattern
established by app/routers/ui_api.py (see app/routers/auth_deps.py).

GET /api/handoffs/count is declared BEFORE GET /api/handoffs/{handoff_id}.
FastAPI matches routes in declaration order, so if the parameterised route
came first it would swallow /api/handoffs/count as handoff_id="count" and
the nav badge would silently 404 (or worse, return a handoff-shaped error).
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from app.db.database import query
from app.routers.auth_deps import require_operator
from app.services import audit, handoff
from app.services.sessions import Operator

router = APIRouter(tags=["operator"], dependencies=[Depends(require_operator)])

# How many recent chat_history turns the handoff detail view shows, so the
# aunt has context before opening WhatsApp herself.
TRANSCRIPT_TURNS = 20

_HANDOFF_SELECT = (
    "SELECT h.id, h.phone, h.reason, h.status, h.assigned_to, h.created_at, "
    "h.resolved_at, h.metadata, COALESCE(c.name, '') AS customer_name "
    "FROM handoffs h LEFT JOIN customers c ON c.phone = h.phone"
)


def _wa_link(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    return f"https://wa.me/{digits}"


def _iso(row: dict, *fields: str) -> None:
    for f in fields:
        if row.get(f) and not isinstance(row[f], str):
            row[f] = row[f].isoformat()


# ---------------------------------------------------------------------------
# Handoffs
# ---------------------------------------------------------------------------

@router.get("/api/handoffs")
async def api_list_handoffs(status: str = "active"):
    if status not in ("active", "resolved", "all"):
        raise HTTPException(status_code=400, detail="status must be active|resolved|all")

    sql = _HANDOFF_SELECT
    params: tuple = ()
    if status != "all":
        sql += " WHERE h.status = %s"
        params = (status,)
    # Active first, then resolved newest-first — resolved handoffs stay
    # visible as recent history rather than disappearing.
    sql += " ORDER BY (h.status = 'active') DESC, h.created_at DESC LIMIT 100"

    rows = query(sql, params)
    for row in rows:
        _iso(row, "created_at", "resolved_at")
        row["wa_link"] = _wa_link(row["phone"])
    return JSONResponse(content={"handoffs": rows})


@router.get("/api/handoffs/count")
async def api_handoffs_count():
    """Live count of active handoffs — powers the nav tab badge."""
    return {"active": handoff.active_count()}


@router.get("/api/handoffs/{handoff_id}")
async def api_handoff_detail(handoff_id: str):
    rows = query(f"{_HANDOFF_SELECT} WHERE h.id = %s", (handoff_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Handoff not found")

    row = rows[0]
    _iso(row, "created_at", "resolved_at")
    row["wa_link"] = _wa_link(row["phone"])

    # Last N turns, newest-first from the DB, reversed back into
    # chronological order — same reversal whatsapp_helpers.load_history does.
    transcript_rows = query(
        "SELECT role, content, created_at FROM chat_history WHERE phone = %s "
        "ORDER BY created_at DESC LIMIT %s",
        (row["phone"], TRANSCRIPT_TURNS),
    )
    transcript = list(reversed(transcript_rows))
    for turn in transcript:
        _iso(turn, "created_at")
    row["transcript"] = transcript

    return JSONResponse(content=row)


@router.post("/api/handoffs/{handoff_id}/resolve")
async def api_resolve_handoff(handoff_id: str, op: Operator = Depends(require_operator)):
    """The single resolution action — "أعد للبوت". No dashboard reply box:
    the aunt converses with the customer in WhatsApp itself."""
    ok = handoff.resolve(handoff_id, op.email)
    if not ok:
        return JSONResponse(status_code=409, content={"ok": False, "detail": "already resolved"})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Audit trail — visible to both accounts, no require_admin
# ---------------------------------------------------------------------------

@router.get("/api/audit")
async def api_audit(limit: int = 200):
    limit = max(1, min(limit, 500))
    entries = audit.list_operator_actions(limit)
    return JSONResponse(content={"entries": entries})
