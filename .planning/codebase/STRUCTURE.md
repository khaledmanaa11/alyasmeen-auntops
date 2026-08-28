# Directory Structure

**Analysis Date:** 2026-06-13

## Top-Level Layout

```
auntops_fixed/
├── app/                    # All application code
│   ├── main.py             # FastAPI app, router registration, APScheduler startup
│   ├── routers/            # HTTP entry points (one router per surface)
│   ├── services/           # Business logic + external integrations
│   ├── ai/                 # Product retriever (catalog load/search/cache)
│   ├── db/                 # Supabase adapter + schema reference
│   ├── shared/             # Constants, gatekeeper, version
│   ├── templates/          # Jinja2 HTML (5 dashboard pages)
│   ├── static/             # CSS/JS assets (broadcast page)
│   └── data/               # catalog.json (legacy), fonts, knowledge/*.md
├── tests/                  # pytest — unit/ + integration/ + data/
├── config/                 # rate_limits.json, setup.json
├── CLAUDE.md               # Project brief (authoritative project doc)
├── README.md
├── catalog_template.md
├── requirements.txt        # pip deps (Railway/Render)
├── pyproject.toml          # authoritative deps + ruff + coverage config
├── pytest.ini              # pytest markers + addopts
├── Procfile                # uvicorn app.main:app --host 0.0.0.0 --port $PORT
└── runtime.txt             # python-3.11.9
```

## Key Locations

| Need to change... | Go to |
|-------------------|-------|
| Bot message handling / hard commands | `app/routers/whatsapp.py` |
| Session / customer / order DB helpers | `app/routers/whatsapp_helpers.py` |
| AI prompt, tools, knowledge injection | `app/services/ai_service.py` (ONLY AI file) |
| Any database access | `app/db/database.py` (ONLY DB file) |
| DB schema reference | `app/db/schema.sql` |
| Product search / catalog cache | `app/ai/retriever.py` |
| Env vars / config | `app/services/config.py` (`Config` class) |
| Dashboard pages (routes) | `app/routers/ui.py` |
| Dashboard JSON APIs | `app/routers/ui_api.py` |
| Dashboard HTML | `app/templates/*.html` |
| Scheduled jobs | `app/main.py` + `app/services/{followup,monthly_report,retry_queue}.py` |
| WhatsApp send (real) | `app/services/whatsapp_meta.py` |
| WhatsApp send (mock) | `app/services/whatsapp_dev.py` |
| Invoice PDF | `app/services/pdf_invoice.py` |
| AI knowledge base | `app/data/knowledge/*.md` |
| Operator session/device/pending-login CRUD (Phase 5) | `app/services/sessions.py` (opaque token store — `operator_sessions`/`trusted_devices`/`pending_logins`) |

## Module Breakdown

### `app/routers/` — HTTP entry points
- `whatsapp.py` — bot brain: webhook GET verify + POST handler, hard commands, agentic tool handlers
- `whatsapp_helpers.py` — DB-backed session/chat-history/customer/order helpers + legacy `_CATALOG` + `STATUS_LABELS`
- `ui.py` — login/logout + page routes (`/orders`, `/dashboard`, `/products`, `/broadcast`); cookie auth
- `ui_api.py` — JSON APIs for orders, dashboard stats, product CRUD
- `broadcast.py` — broadcast message tab (uses `ai_service.improve_message`)
- `debug.py` — dev endpoints (`/dev/test_order`, `/dev/chat`), loaded in try/except

### `app/services/` — logic + integrations
- `config.py` — `Config` class (all env vars + JSON config loading)
- `ai_service.py` — Claude layer: system prompt, 4 tool defs, catalog/knowledge injection, agentic loop, broadcast improver
- `followup.py` / `monthly_report.py` / `retry_queue.py` — scheduled jobs
- `retry_actions.py` — concrete retryable actions (WhatsApp/invoice)
- `pdf_invoice.py` — fpdf2 + python-bidi invoice generation
- `whatsapp_meta.py` / `whatsapp_dev.py` — interchangeable sender implementations
- `sessions.py` (Phase 5) — opaque operator-session store: `create_session`/`lookup_session`/`revoke_session`/`revoke_all_for_user`/`list_sessions_for_user`/`list_active_sessions` (operator_sessions), `find_trusted_device`/`remember_device` (trusted_devices, 30-day MFA remember-device), `create_pending_login`/`consume_pending_login`/`purge_expired` (pending_logins, single-use AAL1->AAL2 bridge). Only `sha256(raw_token)` ever reaches the DB.

### `app/db/`
- `database.py` — `query` / `execute` / `execute_returning` / `ping` via Supabase RPC
- `schema.sql` — 8 tables (products, customers, orders, order_lines, sessions, chat_history, follow_ups, retry_queue)

### `app/ai/`
- `retriever.py` — `_catalog()` cache, `search_products()`, `describe_product()`, `invalidate_catalog()`

### `app/shared/`
- `constants.py`, `gatekeeper.py` (rate-limit helper — currently unused), `version.py`

## Naming Conventions

- **Files:** `snake_case.py`; one router per surface; tests mirror as `test_<module>.py`
- **Private helpers:** leading underscore (`_escape`, `_build`, `_session_token`, `_tool_add_to_cart`, `_make_tool_executor`)
- **Tool handlers:** `_tool_<action>` in `whatsapp.py`
- **DB helpers:** verb-first (`load_session`, `save_session`, `upsert_customer`, `get_latest_order`)
- **Order names:** `ORD-NNNN` (zero-padded order id)
- **Status keys:** `to_do` / `ready` / `delivered` / `done` (English keys, Arabic labels in `STATUS_LABELS`)
- **Arabic text** is intentional throughout customer-facing strings

## Where to Add New Code

- **New bot command** → add a hard-command branch in `app/routers/whatsapp.py::webhook_post`, before the AI fallback
- **New AI tool** → add tool def to `_TOOLS` in `ai_service.py` + handler `_tool_*` + wire in `_make_tool_executor` (whatsapp.py)
- **New dashboard page** → route in `ui.py` + template in `app/templates/` (follow design system in `CLAUDE.md`)
- **New JSON API** → add to `ui_api.py` with cookie auth check
- **New scheduled job** → service in `app/services/` + `_scheduler.add_job(...)` in `main.py`
- **New DB query** → use `app/db/database.py` helpers with `%s` params (never f-strings)

---

*Structure analysis: 2026-06-13*
