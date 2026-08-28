# ALYASMEEN AuntOps — Project Brief for Claude

## ⚡ Knowledge layers — READ FIRST (token discipline)

This repo carries a curated knowledge vault so you can understand the project **without
re-exploring it every session**. The vault IS the retrieval layer — there is no vector DB
and you should not build one. Orient through the vault before grepping or reading code.

**Workflow for any task:**
1. Open `ALYASMEEN/wiki/index.md` (the Map of Content) → find the relevant concept page.
2. Read that `ALYASMEEN/wiki/*.md` page → it summarizes the area and lists exact
   `(source: path)` citations. Jump straight to those files.
3. For "what connects to what / what's safe to change", read
   `ALYASMEEN/graph/graph-overview.md` (god nodes = core abstractions, communities = clusters).
4. Only then read code. Make **targeted** reads guided by the citations — do NOT broad-grep
   or re-map the codebase when the vault already answers the question.
5. After a meaningful change, update the relevant `ALYASMEEN/wiki/*.md` page (and `log.md`)
   so the next session inherits the knowledge instead of rediscovering it.

**Rules:** the vault documents the project but is not the code — verify a wiki claim against
its `(source:)` before acting. Never hand-edit `ALYASMEEN/graph/` or `ALYASMEEN/raw/`
(generated / immutable). `.planning/` is GSD's working memory; `ALYASMEEN/` is durable human
knowledge — keep durable lessons in the vault, not buried in `.planning/`.

---

## What This Project Is
A WhatsApp ordering bot for ALYASMEEN — a natural & handmade skincare products business
(lotions, creams, candles) in Palestine. Customers order via WhatsApp in Arabic or English.
The aunt manages orders via a built-in web dashboard. Claude Haiku powers the AI conversation.

**Owner:** Khaled (building this for his aunt)
**Market:** Palestine | **Volume:** 10–30 orders/day
**Languages:** Arabic (primary) + English

---

## Current State (March 2026)

### Done ✅
- All 14 original improvement plan steps are complete
- AppSheet fully removed — replaced with custom web dashboard (`ui.py` + Jinja2 templates)
- Supabase connected via HTTPS (`supabase-py`) — no psycopg2, no pooler issues
- End-to-end tested locally: orders API, dashboard stats, test order creation all working
- Orders page redesigned: customer name as headline, inline products, WhatsApp link, live counts, auto-refresh
- **Aunt gets a WhatsApp notification the moment a customer confirms an order**
- Monthly report and follow-up scheduler wired and running (`app/worker.py`); the old
  retry-queue mechanism was retired in Phase 4 — see Scheduler section below
- PDF invoice generated and sent to the customer on status → done (`pdf_invoice.py`; no external invoicing service)
- **Product management page** — `/products` dashboard tab; aunt can add, edit, toggle, delete products herself
- **Products moved to Supabase** — `products` table replaces `catalog.json` as live source of truth; bot picks up changes instantly
- **Full dashboard UI redesign** — all 5 templates rebuilt with premium design system (see Frontend Design System below)
- WhatsApp webhook GET verification fixed (dotted query params via `request.query_params`)
- Webhook challenge returns `PlainTextResponse` (not JSON)
- WhatsApp phone number registered via Meta Cloud API
- Custom domain `alyasmeen.org` configured on Railway (DNS via Namecheap)
- Meta business review submitted to lift WABA restriction

### Still To Do 🔲
1. **Deploy** — hosted on Railway (`alyasmeen.org`), SSL cert pending
2. **Add real products** — use the `/products` dashboard page to add real ALYASMEEN products (live in the Supabase `products` table)
3. **Wait for Meta business review** — WABA restriction pending approval
4. **Update `WA_META_TOKEN`** in Railway env vars — new system user token
5. **Add real product images** — upload to Cloudinary, add `image_url` column to `products` table, update template
6. **Add FAQ/store info** — `app/data/knowledge/` is empty; add `.md` files for AI context
7. **Before any release that touches the agent's message-handling code**, run the command in
   `docs/EVAL_GATE.md` — the opt-in eval suite (`tests/eval/`, real Claude API calls,
   `RUN_AGENT_EVAL=1`) compares against the measured baseline in
   `.planning/phases/03-agent-dependability-safety/03-EVAL-BASELINE.md`.

---

## Frontend Design System (all 5 templates)

All dashboard templates (`login`, `orders`, `dashboard`, `products`, `broadcast`) share a consistent premium design language:

| Token | Value | Usage |
|-------|-------|-------|
| Primary green | `#006948` | Buttons, active nav, badges, chart colors |
| Primary dark | `#004d33` | Hover states |
| Primary light | `#e6f3ee` | Card backgrounds, tints |
| Page background | `#f0f7f4` | `<body>` background |
| Card border | `#e8f3ee` | All card borders |

**Icons:** Material Symbols Outlined — loaded from Google Fonts CDN
```html
<link href="https://fonts.googleapis.com/css2?family=Cairo:...&family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0&display=swap" rel="stylesheet">
<span class="material-symbols-outlined">icon_name</span>
```

**Navbar:** Glassmorphism — `background: rgba(255,255,255,0.92); backdrop-filter: blur(16px)`

**Cards:** `border-radius: 20px`, `border: 1px solid #e8f3ee`, `box-shadow: 0 2px 12px rgba(0,0,0,0.04)`

**When editing templates:** Keep this design system consistent. Do not revert to the old `#059669` green or DaisyUI component classes.

---

## Tech Stack
- **Backend:** FastAPI (Python) — `uvicorn app.main:app`
- **WhatsApp:** Meta Cloud API — `app/services/whatsapp_meta.py` (mock: `whatsapp_dev.py`)
- **AI:** Claude Haiku via Anthropic SDK — `app/services/ai_service.py`
- **Database:** Supabase (PostgreSQL) via HTTPS — `app/db/database.py` uses `supabase-py`
- **Dashboard:** Custom web UI in FastAPI — `app/routers/ui.py` + `app/templates/`
- **Scheduler:** APScheduler — follow-up, monthly report, webhook/outbox pollers (wired in `app/worker.py`, its own Railway worker process — see Scheduler section below)

---

## Project Structure
```
auntops_fixed/
├── app/
│   ├── main.py                  # FastAPI app, router registration, APScheduler
│   ├── routers/
│   │   ├── whatsapp.py          # Webhook receiver ONLY — HMAC verify, persist to webhook_events (bot brain moved to services/processor.py in the 2026-08-25 hardening session)
│   │   ├── ui.py                # Web dashboard — login, orders, dashboard, JSON APIs
│   │   └── debug.py             # Dev endpoints (POST /dev/test_order)
│   ├── templates/
│   │   ├── login.html           # Password login (Arabic RTL)
│   │   ├── orders.html          # Order management — customer name headline, inline products, action buttons
│   │   ├── dashboard.html       # Monthly stats, daily chart, status donut, top 5 products
│   │   └── products.html        # Product management — add/edit/toggle/delete products
│   ├── services/
│   │   ├── config.py            # All env vars — import Config everywhere
│   │   ├── ai_service.py        # ONLY AI file — Claude Haiku, 5 tools (incl. request_human_handoff), chat history
│   │   ├── processor.py         # Bot brain (moved out of whatsapp.py, 2026-08-25) — hard commands, session state machine, agentic AI loop + tool executor, outbox enqueue/poller, webhook poller
│   │   ├── policy.py            # Deterministic, zero-I/O policy gate — validates every AI tool call before it executes (REQ-prod-policy-gate)
│   │   ├── handoff.py           # trigger()/resolve() — pauses/unpauses the bot, aunt WhatsApp alert via the outbox
│   │   ├── audit.py             # Best-effort operator action trail (OPERATOR_ACTIONS allowlist)
│   │   ├── followup.py          # Post-delivery follow-up (every 6 hours)
│   │   ├── monthly_report.py    # Monthly summary sent to aunt on 1st of each month
│   │   ├── pdf_invoice.py       # Generates the PDF invoice sent to the customer on DONE
│   │   ├── whatsapp_meta.py     # Real WhatsApp sender (Meta Cloud API)
│   │   └── whatsapp_dev.py      # Mock WhatsApp sender (prints to console)
│   ├── ai/
│   │   └── retriever.py         # Product search — loads from Supabase `products` table (active=true)
│   ├── db/
│   │   ├── database.py          # Supabase HTTPS client — query / execute / execute_returning
│   │   └── schema.sql           # DB schema reference (baseline tables only — see Database Tables below for the full live set)
│   └── data/
│       ├── fonts/               # PDF invoice fonts (David, Heebo)
│       └── knowledge/           # AI knowledge base — store info, shipping, returns, FAQ .md files
├── tests/
│   ├── eval/                    # Opt-in, real-Claude-API agent release gate — see docs/EVAL_GATE.md
│   └── data/
│       └── whatsapp_agent_dataset.json  # Agent eval dataset — 75 labeled customer messages (intent, entities, edge-case tags)
├── .env                         # Secrets — NEVER commit
├── .env.example                 # Template for .env
├── Procfile                     # uvicorn app.main:app --host 0.0.0.0 --port $PORT
├── requirements.txt             # supabase, fastapi, anthropic, apscheduler, etc.
└── CLAUDE.md                    # This file
```

---

## Database Connection (Supabase via HTTPS)

`database.py` uses `supabase-py` — **not psycopg2**. Two helper functions live in Supabase:
- `run_query(sql text) → json` — SELECT or INSERT...RETURNING via CTE
- `run_exec(sql text) → void` — INSERT / UPDATE / DELETE

SQL uses `%s` placeholders throughout. `_escape()` + `_build()` in `database.py` substitute them before the RPC call. All SQL is written by us, never from user input.

**Resilience (single seam):** Every DB call funnels through `query` / `execute` / `execute_returning`, which route the RPC through `_call()` — a retry + circuit-breaker wrapper. Reads (`query`) retry transient failures with exponential backoff; writes (`execute`, `execute_returning`) are **not** retried (a lost response after commit would double-apply). After enough consecutive failures the circuit opens and calls fail fast for a cooldown. Tunables live in `config/rate_limits.json` under `"supabase"` (`max_retries`, `retry_after_seconds`, `circuit_threshold`, `circuit_cooldown_seconds`) — never hardcoded.

**Required env vars:**
```
SUPABASE_URL=https://ppwcfmuetgczclmnzvqr.supabase.co
SUPABASE_KEY=<service_role key>
```

**Security note:** `SUPABASE_KEY` is the `service_role` (secret) key, not the anon key — it
bypasses RLS entirely. It is only ever read via `Config.SUPABASE_KEY` inside `database.py`,
which runs exclusively in the FastAPI/worker server processes on Railway. It must never be
sent to any client-side/browser code and is never shipped to the dashboard's HTML/JS.

---

## Web Dashboard (ui.py + templates/)

| URL | What it does |
|-----|-------------|
| `/login` | Email+password login (Arabic UI); TOTP challenge at `/login/mfa` when MFA is enrolled and the device isn't remembered |
| `/orders` | Orders list — customer name, inline products, WhatsApp link, big action button |
| `/dashboard` | Monthly stats, 30-day chart, status donut, top 5 products |
| `/products` | Product management — add, edit, toggle active/inactive, delete |
| `/logout` | Clear this session only (other signed-in devices stay signed in) |

**JSON APIs:**
| Endpoint | Purpose |
|----------|---------|
| `GET /api/orders?status=...` | Fetch orders (filtered or all) |
| `GET /api/orders/{id}/lines` | Line items for one order |
| `POST /api/orders/{id}/status` | Update status + WhatsApp customer |
| `GET /api/dashboard/stats` | All dashboard data |
| `GET /api/products` | List all products |
| `POST /api/products` | Create product |
| `POST /api/products/{id}` | Update product |
| `POST /api/products/{id}/toggle` | Toggle active/inactive |
| `POST /api/products/{id}/delete` | Delete product |

**Auth:** Per-operator email+password (Supabase Auth) + TOTP MFA, resolved to an opaque
server-side session cookie (`app/routers/auth_routes.py` + `app/routers/auth_deps.py` +
`app/services/sessions.py`). See `docs/OPERATOR_ACCOUNTS.md` for account management.

**Orders page labels (Arabic):**
- `to_do` → يجب التجهيز
- `ready` → جاهز
- `delivered` → في الطريق
- `done` → مكتمل

---

## Database Tables (Supabase — project `ppwcfmuetgczclmnzvqr`, ap-southeast-1)

| Table | Purpose |
|-------|---------|
| `products` | Product catalog — name, price, description, tags, active flag |
| `customers` | One row per customer — name, saved_address |
| `sessions` | WhatsApp cart + stage per customer (also `paused` — see [[agent-safety]]) |
| `orders` | Every confirmed order |
| `order_lines` | Line items inside each order |
| `chat_history` | AI conversation memory (last 6 turns to Claude) |
| `follow_ups` | 3-day post-delivery follow-up tracking |
| `webhook_events` | Durable inbox — raw inbound WhatsApp payloads, polled by the worker |
| `outbox_jobs` | Durable outbox — every outbound send (message/buttons/invoice) is queued here first, then delivered by the poller with bounded retries |
| `handoffs` | Human-handoff state — opened by `handoff.trigger()`, closed by `handoff.resolve()` |
| `audit_logs` | Best-effort operator/bot action trail, read via the `/audit` dashboard page |
| `operator_sessions` | Opaque per-device dashboard login sessions (Supabase Auth + TOTP, not the shared `DASHBOARD_PASSWORD` cookie) |

`retry_queue` still exists as a table (migration `20260825000003_retire_retry_queue.sql`
comments it, doesn't drop it — RLS-locked deny-all) but is **retired, not live**: the outbox
poller's bounded per-job attempts + `notify_permanent_failure()` replaced it in Phase 4.
Nothing in the running app writes to or reads it.

---

## How the Bot Works

See [[agent-safety]] in the knowledge vault for the full architecture (policy gate, the five
handoff triggers, the handoff lifecycle). Compact version:

```
Meta webhook (real) / mock sender (dev)
        │
   POST /whatsapp/webhook           app/routers/whatsapp.py — webhook receiver ONLY
        │  HMAC verify → parse defensively → INSERT INTO webhook_events
        │  returns immediately; no reply is computed here
        ▼
app/worker.py — BlockingScheduler, "webhook_processor" job, every 3s
        │
   process_webhook_events() → process_event()      app/services/processor.py
        │  text / button click  → handle_message(phone, text, name)
        │  anything else (voice, image, sticker…)  → handle_unsupported_media()
        │                                              (a reply + a handoff — not a silent drop)
        ▼
   handle_message(phone, text, name)                app/services/processor.py
        │  1. paused gate   — a human owns this chat; record the message, send nothing
        │  2. keyword gate  — policy.detect_handoff_keyword() → open a handoff, one Arabic ack
        │  3. hard commands — menu/cart/clear/confirm/pickup/delivery, Arabic variants, numbers
        │  4. AI fallback   → ai_service.generate_reply(), 5 tools, each gated by policy.validate()
        │       add_to_cart · show_menu · get_order_status · save_address · request_human_handoff
        │       an AI failure (AIUnavailableError) → Arabic fallback reply AND a handoff
        ▼
   queue_text(phone, reply) → INSERT INTO outbox_jobs   (never a direct send from this path)
        ▼
app/worker.py — "outbox_processor" job, every 2s → process_outbox_jobs() → send_text/send_buttons
```

**Agentic loop (2 API calls when a tool fires):**
1. First call → Claude picks a tool (stop_reason = "tool_use")
2. `policy.validate()` gates the call BEFORE it executes — a denial becomes the tool result,
   Claude phrases the reply around it; an allowed call dispatches to the real tool implementation
3. Tool executes in `processor.py` (has full DB/session access)
4. Result sent back to Claude as tool_result
5. Second call → Claude writes the conversational reply

Hard commands, the paused gate, and the keyword-handoff gate all intercept before AI. If a
customer types `confirm`, `cart`, `clear`, etc. the hard handler runs and Claude is never
called; if the session is paused or the message matches a handoff phrase, Claude is never
called either.

**New-order notification to aunt** (fires on every `confirm`):
```
🛍️ طلب جديد! ORD-0008
👤 فاطمة — 972599123456
  • كريم اليدين × 2
💰 الإجمالي: 85.00₪
📦 توصيل 🚚
📍 شارع النصر، رام الله
```
Only fires if `AUNT_PHONE` is set. Queued into `outbox_jobs` via `queue_text` — the same
durable outbox every customer-facing send uses, retried by the outbox poller up to its bounded
attempts — not a bare try/except that silently drops the alert on a WhatsApp API failure. A
permanent failure (attempts exhausted) triggers `processor.notify_permanent_failure()`: a
dashboard alert (`/alerts`) plus a proactive WhatsApp alert to the aunt/admin.

---

## Scheduler (app/worker.py)

A `BlockingScheduler` running as its own Railway **worker** process (separate from the
`web` process serving FastAPI) — not `main.py`.

| Job | Schedule | What it does |
|-----|----------|-------------|
| `followup.send_followups` | Every 6 hours | Sends follow-up to customers 3+ days after delivery (queued via the outbox — see [[agent-safety]]) |
| `monthly_report.send_monthly_report` | 1st of month, 8 AM | Arabic summary sent to `AUNT_PHONE` |
| `webhook_processor` (`process_webhook_events`) | Every 3s | Durable inbox poller — the entry point into the bot brain (`processor.handle_message`) |
| `outbox_processor` (`process_outbox_jobs`) | Every 2s | Durable outbox poller — the only place that calls `send_text`/`send_buttons` from the message pipeline |

There is no `retry_queue` job — that mechanism was retired in Phase 4; the outbox poller's
bounded per-job attempts are what REQ-sched-retry-queue now maps to.

---

## Key Rules
1. Never hardcode secrets — always `Config.VARIABLE_NAME` from `config.py`
2. Never commit `.env`
3. SQL params always use `%s` — never f-strings (SQL injection)
4. Arabic text is intentional
5. One AI file only — `ai_service.py`
6. One DB file only — `database.py`. No psycopg2, no direct supabase imports elsewhere
7. No AppSheet — fully removed
8. All bot logic lives in `app/services/processor.py` / `ai_service.py` / `policy.py` /
   `handoff.py`. `app/routers/whatsapp.py` is a webhook receiver only — it persists the raw
   payload to `webhook_events` and nothing else.
9. Every outbound customer message goes through `queue_text`/`queue_buttons` (the durable
   outbox) — never `send_text`/`send_buttons` directly, outside `process_job` and the
   standalone scheduler services.

---

## Env Vars Reference

| Var | Required | Purpose |
|-----|----------|---------|
| `SUPABASE_URL` | ✅ | Supabase project URL |
| `SUPABASE_KEY` | ✅ | Supabase **service_role** key (server-side only — never expose to the dashboard's client-side code) |
| `DATABASE_URL` | prod | Postgres Session Pooler connection string — persists the APScheduler job store across worker restarts (see .env.example for the exact shape) |
| `SUPABASE_ANON_KEY` | ✅ | Operator sign-in/MFA via Supabase Auth (`app/services/auth.py`) |
| `SECRET_KEY` | ✅ | Session cookie signing |
| `AUNT_PHONE` | ✅ | New-order alerts + monthly report |
| `CLAUDE_API_KEY` | ✅ | AI replies |
| `WA_META_TOKEN` | prod | WhatsApp sender |
| `WA_META_PHONE_ID` | prod | WhatsApp phone ID |
| `WA_META_VERIFY_TOKEN` | prod | Webhook verification |
| `WA_META_APP_SECRET` | optional | Webhook signature check |
| `CLAUDE_MODEL` | optional | Default: claude-haiku-4-5-20251001 |
| `USE_MOCK_WHATSAPP` | dev | 1=mock, 0=real (default: 1) |

---

## Running Locally
```bash
pip install -r requirements.txt
# fill .env from .env.example
uvicorn app.main:app --reload --port 8000
# dashboard: http://localhost:8000/login
# test order: POST http://localhost:8000/dev/test_order
```

## Deployment Checklist (Railway / Render)
1. Push to GitHub
2. Set env vars (see table above) — minimum: `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_ANON_KEY`, `SECRET_KEY`, `AUNT_PHONE`, `CLAUDE_API_KEY`
3. Set `USE_MOCK_WHATSAPP=0`
4. Set WhatsApp webhook: `https://your-app-url/whatsapp/webhook`
5. Add real products via `/products` dashboard page (products live in the Supabase `products` table)
6. Add `.md` files to `app/data/knowledge/` for AI context
