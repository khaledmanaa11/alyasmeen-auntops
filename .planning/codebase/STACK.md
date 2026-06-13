# Technology Stack

**Analysis Date:** 2026-06-13

## Languages

**Primary:**
- Python 3.11.9 — entire backend, bot logic, dashboard, AI layer, PDF generation

**Secondary:**
- HTML/CSS/JS — Jinja2 templates in `app/templates/` for the web dashboard (no separate JS framework)
- SQL — schema in `app/db/schema.sql`, all queries written by hand in `app/db/database.py`

## Runtime

**Environment:**
- Python 3.11.9 (pinned in `runtime.txt`)

**Package Manager:**
- pip (via `requirements.txt` for Railway/Render compatibility)
- `pyproject.toml` is the authoritative dependency declaration
- `uv.lock` present — uv lockfile
- Lockfile: present (`uv.lock`)

**Build System:**
- nixpacks (Railway): `nixpacks.toml` — installs `python311` and `gcc`

## Frameworks

**Core:**
- FastAPI `>=0.115.0` — HTTP server, routing, request validation (`app/main.py`)
- Starlette `>=0.27.0` — ASGI base, static files, responses
- Pydantic `>=2.0` — request/response models, validation in routers
- Uvicorn `>=0.22` — ASGI server, started via `Procfile`: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

**Templating:**
- Jinja2 `==3.1.5` — server-side HTML rendering for all 5 dashboard pages in `app/templates/`

**Scheduling:**
- APScheduler `>=3.10.0` — `AsyncIOScheduler` wired in `app/main.py` startup event
  - Follow-up job: every 6 hours (`app/services/followup.py`)
  - Monthly report: 1st of month at 08:00 (`app/services/monthly_report.py`)
  - Retry queue: every 15 minutes (`app/services/retry_queue.py`)

**PDF Generation:**
- fpdf2 `>=2.7.0` — generates Hebrew/Arabic invoice PDFs in `app/services/pdf_invoice.py`
- python-bidi `>=0.6.0` — BiDi algorithm for RTL text rendering in PDFs
- Font file: `app/data/fonts/Heebo-Regular.ttf`

**Testing:**
- pytest (configured in `pytest.ini` + `pyproject.toml` `[tool.pytest.ini_options]`)
- Coverage target: 85% (`fail_under = 85` in `pyproject.toml`)
- Test path: `tests/`

## Key Dependencies

**Critical:**
- `anthropic>=0.25.0` — Anthropic SDK for Claude Haiku AI replies (`app/services/ai_service.py`)
- `supabase>=2.0.0` — Supabase HTTPS client, all DB access (`app/db/database.py`)
- `requests>=2.32` — HTTP client for Meta Graph API calls in `app/services/whatsapp_meta.py`
- `apscheduler>=3.10.0` — background job scheduler wired into FastAPI lifecycle

**Infrastructure:**
- `python-dotenv>=1.0` — loads `.env` in `app/main.py` and `app/services/config.py`
- `python-multipart>=0.0.9` — form data parsing (login form, product form in dashboard)
- `aiofiles>=23.0.0` — async file I/O (static file serving)
- `jinja2==3.1.5` — pinned version for template rendering

## Configuration

**Environment:**
- All env vars centralized in `app/services/config.py` via the `Config` class
- Loaded by `python-dotenv` at startup
- Never read `os.getenv()` directly outside `config.py`
- Template for required vars: `.env.example`

**JSON Config Files:**
- `config/setup.json` — app settings (max cart items, session timeout, scheduler intervals)
- `config/rate_limits.json` — per-service rate limits for WhatsApp and Claude AI
- Both loaded lazily by `Config._load_json_config()` on startup

**Build:**
- `pyproject.toml` — dependency declarations, ruff linter config (line-length 100, target py310), coverage config
- `nixpacks.toml` — Railway build: `nixpkgs = ["python311", "gcc"]`
- `Procfile` — `web: uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- `runtime.txt` — `python-3.11.9`

**Linting:**
- ruff — configured in `pyproject.toml` `[tool.ruff]`
  - Rules: E, F, W, I, N, UP, B, C4, SIM
  - E501 (line length) ignored; enforced at 100 chars

## Platform Requirements

**Development:**
- Python 3.10+ (pyproject.toml `requires-python = ">=3.10"`, runtime pinned to 3.11.9)
- `.env` file populated from `.env.example`
- Start: `uvicorn app.main:app --reload --port 8000`
- Dashboard: `http://localhost:8000/login`

**Production:**
- Railway (primary target) with nixpacks build
- Custom domain `alyasmeen.org` configured
- Render also supported (same `Procfile`/`requirements.txt` approach)
- Environment variables set in Railway dashboard

---

*Stack analysis: 2026-06-13*
