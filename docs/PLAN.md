# Architecture & Planning Document — ALYASMEEN AuntOps

**Version:** 1.0
**Date:** 2026-03-27

---

## 1. C4 Model Overview

### Level 1 — Context

```
[Customer]  --WhatsApp--> [Meta Cloud API] --webhook--> [AuntOps Backend]
[Aunt]      <--WhatsApp-- [Meta Cloud API] <-----------  [AuntOps Backend]
[Aunt]      --browser-->  [AuntOps Dashboard]  <-------> [AuntOps Backend]
[AuntOps Backend] <-----> [Supabase (PostgreSQL)]
[AuntOps Backend] <-----> [Anthropic Claude Haiku API]
```

### Level 2 — Containers

| Container | Technology | Responsibility |
|-----------|-----------|----------------|
| FastAPI Backend | Python / uvicorn | WhatsApp webhook, web dashboard, JSON APIs, scheduled jobs |
| Supabase Database | PostgreSQL (hosted) | All persistent data: orders, customers, products, sessions, chat history |
| Claude Haiku | Anthropic API | AI conversation and product recommendations |
| APScheduler | Python (in-process) | Follow-ups, monthly report, retry queue |
| Meta Cloud API | External | Receive and send WhatsApp messages |

### Level 3 — Components (FastAPI Backend)

| Component | File | Responsibility |
|-----------|------|----------------|
| WhatsApp Router | `app/routers/whatsapp.py` | Bot logic, command parsing, session/cart/order management |
| UI Router | `app/routers/ui.py` | Web dashboard pages, auth, JSON APIs |
| Debug Router | `app/routers/debug.py` | Dev-only endpoints (test order creation) |
| AI Service | `app/services/ai_service.py` | Claude Haiku integration, prompt building, history |
| Database Client | `app/db/database.py` | Supabase HTTPS client, `query` / `execute` / `execute_returning` |
| Config | `app/services/config.py` | All environment variables, single import point |
| Follow-up | `app/services/followup.py` | Post-delivery follow-up scheduler |
| Monthly Report | `app/services/monthly_report.py` | Monthly Arabic summary to aunt |
| PDF Invoice | `app/services/pdf_invoice.py` | PDF invoice generation on order completion |
| Retry Queue | `app/services/retry_queue.py` | Retry failed WhatsApp / invoice calls |
| WhatsApp Meta | `app/services/whatsapp_meta.py` | Real Meta Cloud API sender |
| WhatsApp Dev | `app/services/whatsapp_dev.py` | Mock sender (prints to console) |
| Product Retriever | `app/ai/retriever.py` | Product search from Supabase `products` table |

---

## 2. Architecture Overview

### Request Flow — Customer Order

```
1. Customer types on WhatsApp
2. Meta Cloud API receives message
3. Meta POSTs to /whatsapp/webhook
4. whatsapp.py loads session from Supabase (cart, stage, address)
5. Hard commands checked first (cart, clear, confirm, etc.)
6. If no match: ai_service.py called with message + last 6 turns history
7. ai_service.py fetches matching products from retriever.py (Supabase)
8. Claude Haiku API called with system prompt + product context + history
9. Reply sent back to customer via Meta API (or printed in dev mode)
10. History saved to Supabase chat_history table
```

### Request Flow — Order Confirmation

```
1. Customer types "confirm"
2. whatsapp.py validates cart is not empty, fulfillment is set
3. For delivery: validates address is present
4. INSERT into orders table (returns order ID)
5. INSERT into order_lines for each cart item
6. Session deleted from sessions table
7. Confirmation message sent to customer
8. New-order notification sent to AUNT_PHONE (wrapped in try/except)
```

### Request Flow — Dashboard Status Update

```
1. Aunt clicks status button on /orders page
2. Browser POSTs to /api/orders/{id}/status
3. ui.py looks up order + customer from Supabase
4. WhatsApp notification sent to customer
5. For "delivered": follow-up record created in follow_ups table
6. For "done": PDF invoice generated and sent to customer
7. Order status updated in database
8. JSON response confirms success
```

---

## 3. Component Descriptions

### `app/routers/whatsapp.py`

The bot brain. Every incoming WhatsApp message hits `POST /whatsapp/webhook`. The function:

1. Loads the customer's session from Supabase (cart state, conversation stage, fulfillment, address)
2. Runs through hard-coded command handlers in order (cart, clear, pickup, delivery, confirm, address input, menu, number selection, quantity pattern, order tracking)
3. Falls back to `ai_service.generate_reply()` for anything not matched
4. Saves updated session back to Supabase

Key design: commands are checked as simple string matches or regex patterns before AI is ever called. This keeps the bot fast and predictable for the most common actions.

### `app/routers/ui.py`

The web dashboard. Handles:
- Auth: per-operator email+password (Supabase Auth) + TOTP MFA, resolved to an opaque
  server-side session (see `app/routers/auth_routes.py`, `app/routers/auth_deps.py`)
- HTML pages rendered via Jinja2 templates
- JSON APIs consumed by those pages via JavaScript fetch calls
- Broadcast messaging: audience count preview + bulk send

All routes require authentication. Unauthenticated requests redirect to `/login`.

### `app/services/ai_service.py`

The only AI file in the project. Exports two functions:
- `generate_reply(user_message, previous_messages, cart, customer_name, tool_executor)` — calls Claude Haiku and returns reply text
- `ai_available()` — returns True if `CLAUDE_API_KEY` is set

The system prompt (`_SYSTEM_PROMPT`) is a fixed Arabic string that positions the AI as "عمة ALYASMEEN". Product context is injected inline in the user message (not the system prompt) so it stays fresh per request. Cart state is appended to the system prompt so Claude can guide the customer toward checkout.

**Agentic tool use:** `_TOOLS` defines 4 tools (`add_to_cart`, `show_menu`, `get_order_status`, `save_address`) in Anthropic's tool schema format. When `tool_executor` is passed by the caller, tools are enabled and the full loop runs:
1. First API call — Claude decides to use a tool (`stop_reason == "tool_use"`)
2. `tool_executor(name, input)` is called — executes in `whatsapp.py` which has session/DB access
3. Tool result is appended as a `tool_result` message
4. Second API call — Claude writes the final reply with the result in context

`ai_service.py` is tool-agnostic: it knows the tool schemas but not their implementation. The `tool_executor` callback is the only coupling point.

### `app/db/database.py`

The only database file. Uses `supabase-py` to call Supabase via HTTPS. Three public functions:
- `query(sql, params)` — SELECT statements, returns list of dicts
- `execute(sql, params)` — INSERT/UPDATE/DELETE
- `execute_returning(sql, params)` — INSERT...RETURNING, returns single dict

Params use `%s` placeholders. The `_escape()` and `_build()` helpers substitute them before the RPC call. No psycopg2, no direct TCP — all via HTTPS using two Supabase RPC helper functions (`run_query` and `run_exec`) defined in the database.

### `app/services/config.py`

Single import point for all environment variables. Every other file imports `from app.services.config import Config` — no other file calls `os.environ` directly.

### `app/services/followup.py`

Runs every 6 hours via APScheduler. Queries `follow_ups` table for records where `delivered_at` is 3+ days ago and `sent = false`. For each, sends a satisfaction follow-up message via WhatsApp and marks the record as sent.

`record_delivery(phone, order_id)` is called from `ui.py` when status is set to `delivered`.

### `app/services/monthly_report.py`

Runs on the 1st of each month at 8 AM. Queries Supabase for prior month totals: order count, revenue, top products. Formats an Arabic summary message and sends it to `AUNT_PHONE`.

### `app/services/pdf_invoice.py`

Generates a PDF invoice using ReportLab (or similar). Called from `ui.py` when status is set to `done`. PDF is sent to the customer via WhatsApp as a document attachment.

### `app/services/retry_queue.py`

Runs every 15 minutes. Queries `retry_queue` table for unresolved items where `next_retry_at <= now()` and `attempts < max_attempts`. For each, retries the original action (WhatsApp send or invoice). On failure, increments `attempts` and sets `next_retry_at = now() + 15 minutes`. After `max_attempts` failures, marks as resolved (abandoned).

### `app/ai/retriever.py`

Searches the Supabase `products` table for products matching a user's message. Only returns products where `active = true`. Result is used by `ai_service.py` to inject catalog context into the AI prompt. Maintains an in-memory cache that is invalidated whenever the `/products` API creates, updates, toggles, or deletes a product.

---

## 4. API Documentation

### WhatsApp Endpoints

| Method | Path | Input | Output | Notes |
|--------|------|-------|--------|-------|
| GET | `/whatsapp/webhook` | Query: `hub.mode`, `hub.challenge`, `hub.verify_token` | 200 + challenge or 403 | Meta webhook verification |
| POST | `/whatsapp/webhook` | Body: `{from_number, text, wa_name}` | JSON response or send_text call | Main bot entry point |

### Dashboard Pages

| Method | Path | Auth | Output |
|--------|------|------|--------|
| GET | `/login` | None | HTML login form |
| POST | `/login` | None | Redirect to /orders on success |
| GET | `/logout` | Cookie | Redirect to /login |
| GET | `/orders` | Cookie | HTML orders page |
| GET | `/dashboard` | Cookie | HTML dashboard page |
| GET | `/products` | Cookie | HTML products page |
| GET | `/broadcast` | Cookie | HTML broadcast page |

### JSON APIs

| Method | Path | Input | Output |
|--------|------|-------|--------|
| GET | `/api/orders` | Query: `status` (optional) | `{orders: [...]}` |
| GET | `/api/orders/{id}/lines` | Path: `id` | `{lines: [...]}` |
| POST | `/api/orders/{id}/status` | Body: `{status}` | `{ok, status, order_id}` |
| GET | `/api/dashboard/stats` | Query: `month` (optional, YYYY-MM) | Stats object |
| GET | `/api/reports/months` | None | `{months: [{year, month}]}` |
| GET | `/api/products` | None | `{products: [...]}` |
| POST | `/api/products` | Body: `{name, price, description, tags}` | `{ok, product}` |
| POST | `/api/products/{id}` | Body: `{name, price, description, tags}` | `{ok}` |
| POST | `/api/products/{id}/toggle` | None | `{ok, active}` |
| POST | `/api/products/{id}/delete` | None | `{ok}` |
| GET | `/api/broadcast/audience` | Query: `filter` (all/month/top) | `{count}` |
| POST | `/api/broadcast/send` | Body: `{message, filter}` | `{sent, failed, total}` |

### Dev Endpoints

| Method | Path | Notes |
|--------|------|-------|
| POST | `/dev/test_order` | Creates a test order; only registered in dev mode |

---

## 5. Architecture Decision Records

### ADR-001: Supabase over direct PostgreSQL connection

**Context:** The original version used psycopg2 for direct database connections. This caused connection pooling issues on hosted platforms (Railway, Render) where long-lived TCP connections time out or hit connection limits.

**Decision:** Use Supabase as the database host and connect via HTTPS using `supabase-py`. All SQL is executed via two Supabase RPC functions (`run_query` and `run_exec`).

**Consequences:**
- No psycopg2 dependency, no connection pool configuration needed
- Works reliably on any HTTPS-capable host
- All SQL is written manually — no ORM magic
- Slight overhead per query from HTTPS round-trip vs. direct TCP (acceptable at this volume)

### ADR-002: Claude Haiku as the AI model

**Context:** The bot needs to handle natural Arabic and English conversation, suggest products, and give skincare advice. Multiple AI models were considered.

**Decision:** Use Claude Haiku (the smallest and fastest Claude model).

**Reasons:**
- Strong Arabic language support
- Low cost per token — critical for 10–30 messages per order at this volume
- Fast response time (< 1 second typical)
- Sufficient capability for product recommendation and skincare Q&A
- Easy to upgrade to Sonnet or Opus later without code changes (just change `CLAUDE_MODEL` env var)

**Consequences:**
- AI replies are shorter and less nuanced than larger models
- Haiku works best with clear, focused prompts — our 400 token limit is well-suited

### ADR-003: FastAPI over Flask or Django

**Context:** The project needed a Python web framework for the WhatsApp webhook and dashboard.

**Decision:** Use FastAPI.

**Reasons:**
- Native async support — important for WhatsApp webhook that must respond quickly
- Automatic request validation via Pydantic models
- Built-in OpenAPI docs at `/docs` — useful for debugging
- Jinja2 templates supported natively for the dashboard
- Simple routing, no magic or heavy ORM

**Consequences:**
- Slightly more verbose than Flask for simple endpoints
- Async context requires care when mixing sync and async code (APScheduler jobs are sync)

### ADR-005: Agentic tool use via callback instead of embedding DB logic in ai_service.py

**Context:** To make Claude capable of taking real actions (add to cart, look up orders), the AI layer needed access to session state and the database. Two approaches were considered: put DB calls directly in `ai_service.py`, or pass a callback from the caller.

**Decision:** `generate_reply` accepts an optional `tool_executor: Callable[[str, dict], str]` parameter. The caller (`whatsapp.py`) provides a closure that captures `phone`, `st`, and `cart` and routes tool calls to the appropriate handler functions.

**Reasons:**
- `ai_service.py` stays as the "one AI file" rule demands — no DB imports, no session logic
- Tool implementations (`_tool_add_to_cart`, `_tool_show_menu`, etc.) live in `whatsapp.py` alongside the session handling they depend on
- Callers that don't need tools (broadcast message improvement) pass no executor and get the original single-call behavior
- Easy to add new tools: define schema in `_TOOLS`, add handler in `whatsapp.py`, route in `_make_tool_executor`

**Consequences:**
- Each tool call that Claude makes costs one extra API call (first call → tool use, second call → final reply)
- At 10–30 orders/day with Claude Haiku, this is negligible cost

### ADR-004: SQL via Supabase RPC instead of Supabase Python client query builder

**Context:** `supabase-py` has a query builder API (`supabase.table("orders").select("*")`), but complex queries with joins, aggregations, and conditional filtering are cumbersome to express with it.

**Decision:** Write raw SQL and execute it via two Supabase RPC helper functions (`run_query` for SELECT, `run_exec` for writes). `database.py` handles the `%s` → escaped-string substitution before the RPC call.

**Reasons:**
- SQL is readable, debuggable, and easy to test directly in Supabase SQL editor
- Complex dashboard queries (joins, GROUP BY, window functions) are natural in SQL
- No risk of ORM query builder bugs

**Consequences:**
- SQL injection prevention depends on our `_escape()` function — must never use raw f-strings in SQL
- All SQL is internal; no user input ever reaches a raw SQL string

---

## 6. Database Schema

All tables live in the Supabase project `ppwcfmuetgczclmnzvqr` (ap-southeast-1 region).

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `products` | Product catalog — source of truth for bot and dashboard | `id`, `name`, `price`, `description`, `tags`, `active` |
| `customers` | One row per WhatsApp phone number | `phone` (PK), `name`, `saved_address` |
| `sessions` | WhatsApp conversation state per customer | `phone` (PK), `stage`, `cart` (JSONB), `fulfillment`, `menu_products` (JSONB), `address` |
| `orders` | Every confirmed order | `id`, `order_name`, `phone`, `fulfillment`, `address`, `total`, `status`, `channel` |
| `order_lines` | Line items for each order | `id`, `order_id` (FK), `product_name`, `qty`, `unit_price`, `line_total` |
| `chat_history` | AI conversation memory | `id`, `phone`, `role`, `content`, `created_at` |
| `follow_ups` | Post-delivery follow-up tracking | `id`, `phone`, `order_id`, `delivered_at`, `sent`, `sent_at` |
| `retry_queue` | Failed API call queue | `id`, `action`, `order_id`, `phone`, `payload`, `attempts`, `max_attempts`, `last_error`, `next_retry_at`, `resolved` |

### Status Flow (orders.status)

```
to_do --> ready --> delivered --> done
```

Each transition sends a WhatsApp notification to the customer. The `delivered` transition also creates a `follow_ups` record. The `done` transition generates and sends a PDF invoice.

---

## 7. Deployment Diagram

```
+------------------+     HTTPS      +------------------------+
|  Meta Cloud API  | <-----------> |   Railway / Render     |
|  (WhatsApp)      |               |   FastAPI + uvicorn    |
+------------------+               |   APScheduler          |
                                   |   (single process)     |
+------------------+     HTTPS     +------------------------+
|  Customer        | <----------->          |
|  (WhatsApp app)  |                        | supabase-py HTTPS
+------------------+                        v
                                   +------------------------+
+------------------+     HTTPS     |  Supabase              |
|  Aunt            | <-----------> |  PostgreSQL            |
|  (Dashboard)     |               |  (ap-southeast-1)      |
+------------------+               +------------------------+
                                            ^
+------------------+     HTTPS             |
|  Anthropic API   | <-----------------------
|  (Claude Haiku)  |   (from FastAPI)
+------------------+
```

**Notes:**
- The entire backend runs as a single uvicorn process
- APScheduler runs inside that process (no separate worker needed)
- Supabase is the only external stateful dependency
- All environment variables are set in the hosting platform's dashboard
- The `Procfile` specifies the start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
