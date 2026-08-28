from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.routers.auth_deps import require_operator_page

logger = logging.getLogger(__name__)

# Auth (GET/POST /login, POST /login/mfa, GET /logout, POST /logout-all) now
# lives in auth_routes.py, registered signed-out. Every route in THIS router
# requires a live operator session — the router-level dependency below 303s
# an unauthenticated request to /login, so no per-handler guard is needed.
router = APIRouter(tags=["ui"], dependencies=[Depends(require_operator_page)])

templates = Jinja2Templates(
    directory=str(Path(__file__).parent.parent / "templates")
)


class _NoCache:
    """Drop-in replacement for Jinja2's LRUCache.

    Jinja2 <= 3.1.3 builds a cache key that includes the globals dict,
    making the key unhashable (TypeError: unhashable type: 'dict').
    This stub accepts any key and always returns a cache miss so the
    template is re-parsed each request — safe at this request volume.
    """

    def get(self, key: object) -> None:  # noqa: ARG002
        return None

    def __setitem__(self, key: object, value: object) -> None:  # noqa: ARG002
        pass


templates.env.cache = _NoCache()


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@router.get("/orders", response_class=HTMLResponse)
async def orders_page(request: Request):
    return templates.TemplateResponse(request, "orders.html")


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    return templates.TemplateResponse(request, "dashboard.html")


@router.get("/products", response_class=HTMLResponse)
async def products_page(request: Request):
    return templates.TemplateResponse(request, "products.html")


@router.get("/broadcast", response_class=HTMLResponse)
async def broadcast_page(request: Request):
    return templates.TemplateResponse(request, "broadcast.html")


@router.get("/alerts", response_class=HTMLResponse)
async def alerts_page(request: Request):
    return templates.TemplateResponse(request, "alerts.html")
