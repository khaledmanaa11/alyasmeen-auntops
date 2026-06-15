import contextlib
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# Make stdout/stderr render non-ASCII (Arabic, emoji) regardless of the console's
# native encoding. On a Windows dev console (cp1255) the default codec would raise
# UnicodeEncodeError when logging an inbound Arabic WhatsApp message; errors="replace"
# keeps logging — and the request handler — from ever crashing on encoding.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        with contextlib.suppress(Exception):
            _stream.reconfigure(encoding="utf-8", errors="replace")

# Load .env from current CWD and also the project folder (auntops_fixed/.env)
load_dotenv()
try:
    proj_env = Path(__file__).resolve().parents[1] / ".env"
    if proj_env.is_file():
        load_dotenv(dotenv_path=str(proj_env))
except Exception:
    pass

from app.db.database import validate_schema
from app.routers.broadcast import router as broadcast_router  # noqa: E402
from app.routers.ui import router as ui_router  # noqa: E402
from app.routers.ui_api import router as ui_api_router  # noqa: E402
from app.routers.whatsapp import router as whatsapp_router  # noqa: E402

try:
    from app.routers.debug import router as debug_router  # noqa: E402
except Exception as _e:
    import traceback; traceback.print_exc()
    print(f"[WARN] debug router not loaded: {_e}")
    debug_router = None

# Basic logging setup; consumers can configure more advanced logging/handlers
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: handles startup (validation) and shutdown."""
    # 1. Database Schema Validation (fail-fast)
    validate_schema()

    yield


app = FastAPI(title="Aunt Orders Backend (MOCK Odoo Ready)", lifespan=lifespan)

_static_dir = Path(__file__).resolve().parent / "static"
if _static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

app.include_router(whatsapp_router)
app.include_router(ui_router)
app.include_router(ui_api_router)
app.include_router(broadcast_router)
if debug_router:
    app.include_router(debug_router)


# Minimal global exception handler to avoid silent 500s during local dev
@app.exception_handler(Exception)
async def _all_exception_handler(request: Request, exc: Exception):
    try:
        import traceback

        traceback.print_exc()
    except Exception:
        pass
    # For WhatsApp endpoints, return a friendly JSON so Invoke-RestMethod shows content
    if str(request.url.path).startswith("/whatsapp/"):
        return JSONResponse(
            status_code=200,
            content={"ok": False, "error": "internal", "detail": str(exc)},
        )
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


@app.get("/")
def root():
    return {"ok": True, "service": "aunt-orders-backend", "routers": ["/whatsapp", "/ui"]}
