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
- Monthly report, follow-up scheduler, retry queue all wired and running
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
- **Scheduler:** APScheduler — follow-up, monthly report, retry queue (wired in `app/main.py`)

---

## Project Structure
```
auntops_fixed/
├── app/
│   ├── main.py                  # FastAPI app, router registration, APScheduler
│   ├── routers/
│   │   ├── whatsapp.py          # Bot brain — all WhatsApp message handling + aunt notification
│   │   ├── ui.py                # Web dashboard — login, orders, dashboard, JSON APIs
│   │   └── debug.py             # Dev endpoints (POST /dev/test_order)
│   ├── templates/
│   │   ├── login.html           # Password login (Arabic RTL)
│   │   ├── orders.html          # Order management — customer name headline, inline products, action buttons
│   │   ├── dashboard.html       # Monthly stats, daily chart, status donut, top 5 products
│   │   └── products.html        # Product management — add/edit/toggle/delete products
│   ├── services/
│   │   ├── config.py            # All env vars — import Config everywhere
│   │   ├── ai_service.py        # ONLY AI file — Claude Haiku, product context, chat history
│   │   ├── followup.py          # Post-delivery follow-up (every 6 hours)
│   │   ├── monthly_report.py    # Monthly summary sent to aunt on 1st of each month
│   │   ├── pdf_invoice.py       # Generates the PDF invoice sent to the customer on DONE
│   │   ├── retry_queue.py       # Failed WhatsApp/invoice calls — retries every 15 min
│   │   ├── retry_actions.py     # Re-sends a queued WhatsApp message or PDF invoice (action dispatch)
│   │   ├── whatsapp_meta.py     # Real WhatsApp sender (Meta Cloud API)
│   │   └── whatsapp_dev.py      # Mock WhatsApp sender (prints to console)
│   ├── ai/
│   │   └── retriever.py         # Product search — loads from Supabase `products` table (active=true)
│   ├── db/
│   │   ├── database.py          # Supabase HTTPS client — query / execute / execute_returning
│   │   └── schema.sql           # DB schema reference (7 tables, already applied on Supabase)
│   └── data/
│       ├── fonts/               # PDF invoice fonts (David, Heebo)
│       └── knowledge/           # AI knowledge base — store info, shipping, returns, FAQ .md files
├── tests/
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
SUPABASE_KEY=<anon key>
```

---

## Web Dashboard (ui.py + templates/)

| URL | What it does |
|-----|-------------|
| `/login` | Password login (Arabic UI) |
| `/orders` | Orders list — customer name, inline products, WhatsApp link, big action button |
| `/dashboard` | Monthly stats, 30-day chart, status donut, top 5 products |
| `/products` | Product management — add, edit, toggle active/inactive, delete |
| `/logout` | Clear session |

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

**Auth:** Cookie — SHA-256 of `SECRET_KEY:DASHBOARD_PASSWORD`.

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
| `sessions` | WhatsApp cart + stage per customer |
| `orders` | Every confirmed order |
| `order_lines` | Line items inside each order |
| `chat_history` | AI conversation memory (last 6 turns to Claude) |
| `follow_ups` | 3-day post-delivery follow-up tracking |
| `retry_queue` | Failed WhatsApp/PDF-invoice calls queued for retry |

---

## How the Bot Works

```
Customer sends WhatsApp message
        │
  whatsapp.py  (hard commands first)
        │
   "cart"      → show cart
   "clear"     → empty cart
   "pickup"    → set fulfillment
   "delivery"  → ask address, save to DB
   "confirm"   → write order to DB
                 → send confirmation to customer
                 → send new-order notification to AUNT_PHONE
   "وين طلبي" → look up latest order status
   number      → add product from last menu
   2x1, 3*2   → add product with quantity
        │
   no match → ai_service.py → Claude Haiku (with 4 tools)
                │
                ├── tool: add_to_cart(product_name, qty)  → actually updates cart in DB
                ├── tool: show_menu(category)              → loads Supabase, sets menu_products in session
                ├── tool: get_order_status()               → queries orders table, returns status
                └── tool: save_address(address)            → saves to customers + session
                │
                Claude writes final reply knowing what the tools returned
```

**Agentic loop (2 API calls when a tool fires):**
1. First call → Claude picks a tool (stop_reason = "tool_use")
2. Tool executes in `whatsapp.py` (has full DB/session access)
3. Result sent back to Claude as tool_result
4. Second call → Claude writes the conversational reply

Hard commands always intercept before AI. If customer types `confirm`, `cart`, `clear`, etc. the hard handler runs and Claude is never called.

**New-order notification to aunt** (fires on every `confirm`):
```
🛍️ طلب جديد! ORD-0008
👤 فاطمة — 972599123456
  • كريم اليدين × 2
💰 الإجمالي: 85.00₪
📦 توصيل 🚚
📍 شارع النصر، رام الله
```
Only fires if `AUNT_PHONE` is set. Wrapped in try/except — order never fails if notification fails.

---

## Scheduler (main.py)

| Job | Schedule | What it does |
|-----|----------|-------------|
| `followup.send_followups` | Every 6 hours | Sends follow-up to customers 3+ days after delivery |
| `monthly_report.send_monthly_report` | 1st of month, 8 AM | Arabic summary sent to `AUNT_PHONE` |
| `retry_queue.process_retries` | Every 15 min | Retries failed WhatsApp/PDF-invoice calls (max 3x) |

---

## Key Rules
1. Never hardcode secrets — always `Config.VARIABLE_NAME` from `config.py`
2. Never commit `.env`
3. SQL params always use `%s` — never f-strings (SQL injection)
4. Arabic text is intentional
5. One AI file only — `ai_service.py`
6. One DB file only — `database.py`. No psycopg2, no direct supabase imports elsewhere
7. No AppSheet — fully removed

---

## Env Vars Reference

| Var | Required | Purpose |
|-----|----------|---------|
| `SUPABASE_URL` | ✅ | Supabase project URL |
| `SUPABASE_KEY` | ✅ | Supabase anon key |
| `DATABASE_URL` | prod | Postgres Session Pooler connection string — persists the APScheduler job store across worker restarts (see .env.example for the exact shape) |
| `DASHBOARD_PASSWORD` | ✅ | Web dashboard login |
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
2. Set env vars (see table above) — minimum: `SUPABASE_URL`, `SUPABASE_KEY`, `DASHBOARD_PASSWORD`, `SECRET_KEY`, `AUNT_PHONE`, `CLAUDE_API_KEY`
3. Set `USE_MOCK_WHATSAPP=0`
4. Set WhatsApp webhook: `https://your-app-url/whatsapp/webhook`
5. Add real products via `/products` dashboard page (products live in the Supabase `products` table)
6. Add `.md` files to `app/data/knowledge/` for AI context
