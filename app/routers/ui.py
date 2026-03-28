from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.services.config import Config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ui"])

templates = Jinja2Templates(
    directory=str(Path(__file__).parent.parent / "templates")
)
# Jinja2 LRUCache uses dict as cache key which is unhashable in Python 3.13.
# Disabling the cache is the safe workaround until the runtime is on 3.11.
templates.env.cache = None

COOKIE_NAME = "alyasmeen_session"


def _session_token() -> str:
    raw = f"{Config.SECRET_KEY}:{Config.DASHBOARD_PASSWORD}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _is_authenticated(request: Request) -> bool:
    return request.cookies.get(COOKIE_NAME) == _session_token()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if _is_authenticated(request):
        return RedirectResponse(url="/orders", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
async def login_submit(request: Request, password: str = Form(...)):
    if password == Config.DASHBOARD_PASSWORD:
        resp = RedirectResponse(url="/orders", status_code=303)
        resp.set_cookie(COOKIE_NAME, _session_token(), httponly=True, samesite="lax")
        return resp
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "كلمة المرور غير صحيحة"},
        status_code=401,
    )


@router.get("/logout")
async def logout():
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie(COOKIE_NAME)
    return resp


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@router.get("/orders", response_class=HTMLResponse)
async def orders_page(request: Request):
    if not _is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("orders.html", {"request": request})


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    if not _is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("dashboard.html", {"request": request})


@router.get("/products", response_class=HTMLResponse)
async def products_page(request: Request):
    if not _is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("products.html", {"request": request})


@router.get("/broadcast", response_class=HTMLResponse)
async def broadcast_page(request: Request):
    if not _is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("broadcast.html", {"request": request})
