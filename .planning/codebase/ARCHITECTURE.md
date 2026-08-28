# Architecture

**Analysis Date:** 2026-06-13

## Pattern

**Layered modular monolith** — a single FastAPI ASGI application (`app/main.py`) that
serves three surfaces from one process:

1. **WhatsApp bot** — inbound webhook → command/AI handling → outbound messages
2. **Web dashboard** — server-rendered Jinja2 pages + JSON APIs for the aunt
3. **Background scheduler** — APScheduler jobs (follow-ups, monthly report, retry queue)

There is no microservice split, no message queue, and no separate worker process —
everything runs inside the same uvicorn process. This matches the project scale
(10–30 orders/day, single operator).

## Layers

```
┌──────────────────────────────────────────────────────────┐
│  Router layer  (app/routers/)                              │
│  whatsapp.py · ui.py · ui_api.py · broadcast.py · debug.py │
│  — HTTP entry points, request validation, auth checks      │
├──────────────────────────────────────────────────────────┤
│  Service layer (app/services/)                             │
│  ai_service · followup · monthly_report · retry_queue ·    │
│  retry_actions · pdf_invoice · whatsapp_meta/dev · config  │
│  — business logic, external API calls, scheduled jobs      │
├──────────────────────────────────────────────────────────┤
│  AI layer      (app/ai/)                                   │
│  retriever.py — product catalog load/search/cache          │
├──────────────────────────────────────────────────────────┤
│  Helper/shared layer                                       │
│  app/routers/whatsapp_helpers.py — session/customer/order  │
│  app/shared/ — constants, gatekeeper, version              │
├──────────────────────────────────────────────────────────┤
│  Data adapter  (app/db/database.py)                        │
│  query / execute / execute_returning — the ONLY DB module  │
├──────────────────────────────────────────────────────────┤
│  Supabase (PostgreSQL over HTTPS RPC)                      │
└──────────────────────────────────────────────────────────┘
```

**Layer rules (enforced by convention, see `CLAUDE.md`):**
- One AI file only — `app/services/ai_service.py`
- One DB file only — `app/db/database.py` (no psycopg2, no direct `supabase` imports elsewhere)
- All config via `app/services/config.py::Config` — never `os.getenv()` outside it

## Entry Points

| Entry point | File | Trigger |
|-------------|------|---------|
| ASGI app | `app/main.py::app` | `uvicorn app.main:app` (Procfile) |
| WhatsApp webhook (verify) | `app/routers/whatsapp.py::webhook_get` | Meta GET handshake |
| WhatsApp webhook (messages) | `app/routers/whatsapp.py::webhook_post` | inbound customer message |
| Dashboard pages | `app/routers/ui.py` | aunt's browser |
| Dashboard JSON APIs | `app/routers/ui_api.py` | dashboard fetch() calls |
| Broadcast | `app/routers/broadcast.py` | dashboard broadcast tab |
| Dev/test | `app/routers/debug.py` | `POST /dev/test_order`, `/dev/chat` (always registered) |
| Scheduler startup | `app/main.py::start_scheduler` | FastAPI `@app.on_event("startup")` |

## Key Data Flows

### 1. Inbound WhatsApp message (`POST /whatsapp/webhook`)
```
Msg(from_number, text, wa_name)  [Pydantic flat model]
  → load_session(phone)                    (whatsapp_helpers → DB)
  → upsert_customer → welcome on first contact
  → Arabic alias normalization (_AR_ALIASES)
  → HARD COMMANDS (intercept before AI):
       cart · clear · pickup · delivery · confirm · menu
       number selection · "NxM" quantity · info · order tracking
  → if no hard match → ai_service.generate_reply(...)
       Claude picks a tool (stop_reason="tool_use")
         → executor runs tool in whatsapp.py (DB/session access)
         → tool_result sent back → 2nd Claude call → final reply
  → send_text / send_buttons (whatsapp_meta or whatsapp_dev)
```

### 2. Order confirmation (`confirm` hard command)
```
cart present + fulfillment chosen (+ address if delivery)
  → INSERT orders (status='to_do') RETURNING id      (execute_returning)
  → UPDATE order_name = ORD-NNNN
  → INSERT order_lines per cart item
  → clear_session(phone)
  → send_text confirmation to customer
  → if AUNT_PHONE set → send new-order notification to aunt (try/except)
```

### 3. Dashboard status update (`POST /api/orders/{id}/status`)
```
auth cookie check → UPDATE orders.status
  → WhatsApp customer with status message
  → on 'done' → generate + send PDF invoice (pdf_invoice; failures via retry_actions)
  → failures enqueued to retry_queue
```

### 4. Scheduled jobs (APScheduler, in-process)
```
followup.send_followups      every 6h    → message customers 3+ days post-delivery
monthly_report.send_...      1st @ 08:00  → Arabic monthly summary to AUNT_PHONE
retry_queue.process_retries  every 15min  → retry failed WhatsApp/PDF-invoice calls (max 3x)
```

## Key Abstractions

- **DB adapter** (`app/db/database.py`) — `query` / `execute` / `execute_returning`
  wrap two Supabase RPC functions (`run_query`, `run_exec`). `%s` placeholders are
  substituted client-side by `_build()` + `_escape()`. Single seam for all persistence.
- **WhatsApp sender swap** — `whatsapp.py` imports `send_text`/`send_buttons`/`verify_get`
  from `whatsapp_dev` (mock) or `whatsapp_meta` (real) based on `Config.USE_MOCK_WHATSAPP`.
  This is the primary test/prod toggle.
- **Agentic tool executor** — `_make_tool_executor()` returns a closure bound to the
  current `phone`/`session`/`cart`, passed into `ai_service.generate_reply` so Claude's
  tool calls mutate real state while the AI layer stays DB-agnostic.
- **Catalog cache** — `app/ai/retriever.py` caches the active products list in a module
  global; `invalidate_catalog()` is called after product CRUD so the bot picks up changes.
- **Session as state machine** — `sessions` table (`stage`, `cart`, `fulfillment`,
  `menu_products`, `address`) persists conversation state across restarts; `stage`
  drives the `awaiting_address` branch.

## Cross-Cutting Concerns

- **Logging** — `logging.basicConfig(INFO)` in `main.py`; module loggers throughout.
- **Error handling** — global `@app.exception_handler(Exception)` returns friendly JSON
  for `/whatsapp/*` (status 200 so Meta does not retry-storm) and generic 500 elsewhere.
- **Auth** — dashboard cookie = SHA-256 of `SECRET_KEY:DASHBOARD_PASSWORD`
  (`ui.py::_session_token`); checked per page/API.
- **Config** — centralized in `Config`; `.env` loaded twice in `main.py` (CWD + project).

---

*Architecture analysis: 2026-06-13*
