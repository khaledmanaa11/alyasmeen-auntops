import logging
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# Load .env from current CWD and also the project folder (auntops_fixed/.env)
load_dotenv()
try:
    proj_env = Path(__file__).resolve().parents[1] / ".env"
    if proj_env.is_file():
        load_dotenv(dotenv_path=str(proj_env))
except Exception:
    pass

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

app = FastAPI(title="Aunt Orders Backend (MOCK Odoo Ready)")

_static_dir = Path(__file__).resolve().parent / "static"
if _static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

app.include_router(whatsapp_router)
app.include_router(ui_router)
app.include_router(ui_api_router)
app.include_router(broadcast_router)
if debug_router:
    app.include_router(debug_router)

# ---------------------------------------------------------------------------
# Scheduler — runs follow-up job every 6 hours
# ---------------------------------------------------------------------------
_scheduler = AsyncIOScheduler()


@app.on_event("startup")
async def start_scheduler():
    from app.services.followup import send_followups
    from app.services.monthly_report import send_monthly_report
    from app.services.retry_queue import process_retries

    _scheduler.add_job(send_followups, "interval", hours=6, id="followup")
    _scheduler.add_job(send_monthly_report, "cron", day=1, hour=8, minute=0, id="monthly_report")
    _scheduler.add_job(process_retries, "interval", minutes=15, id="retry_queue")
    _scheduler.start()
    logging.getLogger(__name__).info(
        "Scheduler started — follow-up every 6h, monthly report on 1st, retry queue every 15min"
    )


@app.on_event("shutdown")
async def stop_scheduler():
    _scheduler.shutdown(wait=False)


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
