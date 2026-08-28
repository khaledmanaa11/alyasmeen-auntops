import structlog
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette_csrf import CSRFMiddleware

from app.shared.logging import setup_logging

# Initialize structured logging
setup_logging()
logger = structlog.get_logger(__name__)

# Load .env from current CWD and also the project folder (auntops_fixed/.env)
load_dotenv()
try:
    proj_env = Path(__file__).resolve().parents[1] / ".env"
    if proj_env.is_file():
        load_dotenv(dotenv_path=str(proj_env))
except Exception:
    pass

from app.db.database import ping
from app.routers.auth_routes import router as auth_router  # noqa: E402
from app.routers.broadcast import router as broadcast_router  # noqa: E402
from app.routers.ui import router as ui_router  # noqa: E402
from app.routers.ui_api import router as ui_api_router  # noqa: E402
from app.routers.whatsapp import router as whatsapp_router  # noqa: E402
from app.services.config import Config  # noqa: E402
from app.shared.constants import SESSION_COOKIE_NAME  # noqa: E402

# /dev/* routes (test_order, chat UI) are dev-only conveniences that must
# never be reachable in production — gate them on the same flag that already
# picks the mock WhatsApp sender, instead of a new env var.
debug_router = None
if Config.USE_MOCK_WHATSAPP:
    try:
        from app.routers.debug import router as debug_router  # noqa: E402
    except Exception as _e:
        import traceback; traceback.print_exc()
        print(f"[WARN] debug router not loaded: {_e}")
        debug_router = None

app = FastAPI(title="Aunt Orders Backend (MOCK Odoo Ready)")

_static_dir = Path(__file__).resolve().parent / "static"
if _static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

app.include_router(whatsapp_router)
app.include_router(auth_router)
app.include_router(ui_router)
app.include_router(ui_api_router)
app.include_router(broadcast_router)
if debug_router:
    app.include_router(debug_router)

# CSRF protection (REQ-prod-csrf) — double-submit cookie via starlette-csrf.
# `sensitive_cookies={SESSION_COOKIE_NAME}` scopes enforcement to requests
# that actually carry the dashboard session cookie: POST /whatsapp/webhook
# (authenticated by Meta's X-Hub-Signature-256 over the raw body, never by a
# browser cookie) and the dev-only /dev/* routes are exempt BY CONSTRUCTION,
# with no exempt_urls regex to maintain every time a route is added. The same
# applies to POST /login and POST /login/mfa — no session cookie exists yet
# at that point, so CSRF simply doesn't engage for them either.
#
# Middleware ordering: Starlette's add_middleware() prepends to the internal
# list, so the LAST-registered middleware ends up OUTERMOST. CSRFMiddleware
# is registered here, and SecurityHeadersMiddleware is registered after it
# (further down) — that makes the headers middleware outermost, so a CSRF
# 403 response still carries the security headers on its way back out.
app.add_middleware(
    CSRFMiddleware,
    secret=Config.SECRET_KEY,
    cookie_name="csrftoken",
    header_name="x-csrftoken",
    cookie_secure=not Config.USE_MOCK_WHATSAPP,
    cookie_samesite="lax",
    sensitive_cookies={SESSION_COOKIE_NAME},
)


# Global exception handler — logs via structlog and always returns 500.
# WhatsApp webhook errors used to be masked as HTTP 200 here so Meta would
# never retry a genuinely failed delivery. That's no longer needed: the
# webhook handler itself (app/routers/whatsapp.py) now parses defensively
# and never raises for a malformed payload, so any exception that reaches
# this handler is a real failure Meta should retry.
@app.exception_handler(Exception)
async def _all_exception_handler(request: Request, exc: Exception):
    logger.error(
        "unhandled_exception",
        path=str(request.url.path),
        method=request.method,
        error=str(exc),
        exc_info=exc,
    )
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


@app.get("/")
def root():
    return {"ok": True, "service": "aunt-orders-backend", "routers": ["/whatsapp", "/ui"]}


@app.get("/health")
def health():
    """Health check endpoint that verifies database connectivity."""
    db_status = ping()
    if not db_status.get("ok"):
        return JSONResponse(status_code=503, content={"ok": False, "db": db_status})
    return {"ok": True, "db": db_status}
