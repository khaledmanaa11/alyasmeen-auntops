# ALYASMEEN AuntOps — Project Learnings

Everything learned from a deep read of the codebase while implementing the
performance optimizations (June 2026). Complements `CLAUDE.md` — that file says
*what the project is*; this one records *how it actually behaves*, the
non-obvious design decisions, the gotchas, and the performance anatomy.

---

## 1. What this is, in one paragraph

A single FastAPI monolith (one `uvicorn` process on Railway, `alyasmeen.org`)
serving three concerns from one process: a WhatsApp ordering bot (Meta Cloud
API webhook + Claude Haiku), a server-rendered Arabic admin dashboard for the
aunt, and an in-process APScheduler running follow-ups / monthly reports /
retry queue. All state lives in Supabase PostgreSQL (project
`ppwcfmuetgczclmnzvqr`, region **ap-southeast-1**), accessed over HTTPS RPC —
no connection pool, no psycopg2, no cache, no queue broker.

---

## 2. Architecture map

```
Customer ──WhatsApp──► Meta Cloud API ──POST /whatsapp/webhook──┐
                                                                ▼
                    uvicorn app.main:app  (ONE process, ONE replica)
                    ├── routers/whatsapp.py      bot brain (hard commands → AI fallback)
                    ├── routers/whatsapp_helpers.py  session/customer/history DB helpers
                    ├── routers/ui.py + ui_api.py    dashboard pages + JSON APIs
                    ├── routers/broadcast.py         broadcast page + AI message improver
                    ├── routers/debug.py             dev endpoints (/dev/test_order)
                    ├── services/ai_service.py       THE ONLY AI FILE (Claude Haiku, 4 tools)
                    ├── services/whatsapp_meta.py    real sender │ whatsapp_dev.py mock
                    ├── services/{followup,monthly_report,retry_queue,retry_actions,
                    │             pdf_invoice}.py    scheduled/deferred work
                    ├── shared/gatekeeper.py         outbound API rate limiter (Claude+Meta)
                    ├── ai/retriever.py              in-memory product catalog cache
                    └── db/database.py               THE ONLY DB FILE (Supabase HTTPS RPC)
                                │
                                ▼ HTTPS, per-query
                    Supabase PostgreSQL — 8 tables:
                    products, customers, sessions, orders, order_lines,
                    chat_history, follow_ups, retry_queue
```

Reading order to internalize the system: `app/main.py` (wiring) →
`routers/whatsapp.py` (state machine) → `services/ai_service.py` (agentic
loop) → `db/database.py` (the unusual DB pattern). Everything else is leaf.

---

## 3. The bot's two-tier dispatch (the core design idea)

Deterministic **hard commands** are matched first and never touch the LLM:
`cart`, `clear`, `menu`, `pickup`, `delivery`, `confirm`, numeric picks
(`1`, `2x1`, `3*2`), `info N`, order-tracking keywords, plus Arabic aliases
(`_AR_ALIASES` maps e.g. `سلة` → `cart`). Anything unmatched falls through to
`ai_service.generate_reply()` with 4 tools:

| Tool | What it actually does (executes in whatsapp.py, has full DB access) |
|---|---|
| `add_to_cart` | fuzzy-matches a product, mutates session cart in place |
| `show_menu` | loads catalog, stores `menu_products` in session (enables numeric picks) |
| `get_order_status` | latest order row for the phone |
| `save_address` | writes to customers + session |

The critical path (order confirmation, money) is deliberately LLM-free.

**Agentic loop cost:** 1 Claude call when no tool fires; 2 calls when one does
— except `show_menu` / `get_order_status`, whose tool output is already a
complete customer-ready message, so since the June 2026 optimization the
second call is skipped (`_DIRECT_REPLY_TOOLS` in `ai_service.py`).

---

## 4. The database layer — unusual, understand before touching

`app/db/database.py` does **not** use a Postgres driver. Every query is an
HTTPS RPC to one of two Postgres functions living in Supabase:

- `run_query(sql) → json` — SELECTs (and INSERT…RETURNING via CTE)
- `run_exec(sql) → void` — INSERT / UPDATE / DELETE

Parameters use `%s` placeholders, but they are substituted **client-side** by
`_escape()`/`_build()` before the RPC — there is no server-side parameter
binding. Safety rests entirely on the convention that SQL text is never
user-derived (CLAUDE.md rule #3). `_escape` handles None/bool/numbers/dict/list
(json) /str with quote-doubling.

Consequences:
- **Every query is a full HTTPS round trip.** With Railway (likely US/EU) and
  Supabase in Singapore, that's ~200–400 ms *per query*. This was the single
  biggest latency source — hence the batching work (see §7).
- Multi-statement work should be folded into one statement (CTEs, multi-row
  `VALUES`) — Postgres data-modifying CTEs all run in one snapshot, and
  **sub-statements cannot see each other's writes** (this is why
  `whatsapp.py`'s confirm path inserts the order first to get the id, then
  stamps `order_name` + inserts all lines in a second, single statement).
- The Supabase client is a module-level singleton (`_get_client()`).

---

## 5. Gotchas & quirks discovered (the valuable part)

1. **Single-replica constraint.** APScheduler runs in-process
   (`main.py` startup hook). Scaling to 2+ replicas would double-send
   follow-ups, monthly reports, and retries. Any horizontal-scaling plan must
   first extract the scheduler.

2. **Webhook swallows errors on purpose.** The global exception handler in
   `main.py` returns HTTP **200** with `{"ok": false}` for any exception under
   `/whatsapp/*` — so Meta never disables the webhook over transient bugs.
   Don't "fix" this to a 500.

3. **`catalog.json` is dead but not fully dead — and it's coffee.** Products
   live in Supabase; `app/ai/retriever.py` is the live source. BUT
   `whatsapp_helpers._CATALOG` still loads `app/data/catalog.json` at import
   time, and the **`info N` hard command still serves from it**. The file
   contains leftover template data (Latte, Americano, Almond Latte). A
   customer who types `menu` then `info 1` gets coffee details in a skincare
   shop. → TODO: point `info` at the retriever catalog and delete the JSON.

4. **History-duplication bug (fixed June 2026).** The old AI path appended the
   user message to `chat_history` *before* loading history, so Claude saw the
   current message twice (once in history, once as the new turn). The new flow
   loads history first (via `load_context`) and persists both turns after the
   reply is sent.

5. **The catalog cache is process-local.** `retriever._CATALOG` caches the
   Supabase products in memory; `invalidate_catalog()` is called by the
   products API on create/update/delete. This only works because there is
   exactly one process (see #1).

6. **`webhook_post` is a sync `def`** — FastAPI runs it in a threadpool.
   Fine at 10–30 orders/day; it means blocking I/O inside doesn't block the
   event loop, but each in-flight message holds a thread.

7. **Mock/real WhatsApp seam.** `USE_MOCK_WHATSAPP=1` (default) swaps
   `whatsapp_meta` for `whatsapp_dev`, whose `send_text` returns
   `{"dev": True, "to": ..., "text": ...}` — the tests assert on exactly that
   shape, and the webhook *returns the sender's return value* as its HTTP
   response. Changing the mock's return shape breaks the test suite.

8. **Test seams live on the `whatsapp` module namespace.**
   `tests/conftest.py` (autouse) monkeypatches `wa.load_context`,
   `wa.save_session`, `wa.execute`, `wa.search_products`, etc. *on
   `app.routers.whatsapp`* — so the webhook must keep calling these as module
   globals (not via `whatsapp_helpers.xxx` attribute access), and any new DB
   touchpoint on the hot path needs a matching conftest fake. Before June 2026
   the conftest did NOT fake `search_products`, so 20 tests silently required
   live Supabase credentials; now the suite runs fully offline (226 passing).

9. **Gatekeeper exists but isn't on the webhook hot path.**
   `app/shared/gatekeeper.py` is a centralized rate limiter/queue for outbound
   Claude + Meta calls (config in `config/rate_limits.json`). Services like
   broadcast use it; the bot's direct `send_text` calls don't all route
   through it. Be aware both paths exist.

10. **Order numbering is cosmetic.** `order_name = ORD-{id:04d}` derives from
    the serial id after insert; the dashboard and notifications use it, but
    `orders.id` is the real key everywhere.

11. **The aunt's notification must never block or fail an order** — it's
    fire-and-forget (now a FastAPI BackgroundTask; previously try/except
    inline). Same philosophy for Wave invoicing: status→done enqueues into
    `retry_queue` rather than calling Wave synchronously.

12. **Prompt-cache minimum.** Claude Haiku 4.5 only caches prefixes ≥ ~4096
    tokens. The bot's static prefix (system prompt + catalog + 4 tool schemas)
    may sit *below* that with a small catalog — the `cache_control` marker is
    then a silent no-op (no error, no write). Verify with
    `usage.cache_read_input_tokens` in production; it becomes effective as the
    catalog/knowledge base grows.

13. **`agents/` is offline dev tooling**, not runtime: a 4-agent
    (PM→Dev→QA→DevOps) and a 2-agent frontend pipeline driven by
    `CLAUDE_API_KEY`. Never imported by `app/`.

14. **`app/data/knowledge/` is empty** but wired: `.md` files there are
    injected into the AI system prompt, optionally gated by a first-line
    `# triggers: word1, word2` comment (trigger-matched files win; untriggered
    files are the fallback). 20k-char cap.

---

## 6. Latency anatomy of the hot path

Per AI-handled message, **before** the June 2026 optimization:

| Step | Round trips |
|---|---|
| load_session + upsert_customer(SELECT) + append_history + load_history (+ get_customer_name) | 4–5 × Supabase RPC, sequential |
| Claude call 1 (tool pick) + call 2 (reply) | 2 × Anthropic, sequential, no caching, new client per request |
| save_session + append_history | 2 × RPC **before** the customer reply was sent |
| send_text | 1 × Meta |

≈ 5–9 s perceived. `confirm` additionally did 2 + N(line items) sequential RPCs.

**After:** 1 batched RPC for context (`load_context` — session + customer +
history via JSON subqueries), 1–2 Claude calls (prompt-cached, pooled client,
second call skipped for menu/status), reply sent immediately, all persistence
(history, session, customer upsert, aunt alert, session clear) deferred to
`BackgroundTasks`. `confirm` is now exactly 2 RPCs regardless of cart size.
≈ 1.5–3 s perceived; hard commands ~1 RPC + 1 Meta call.

**The remaining big lever is infra, not code:** Supabase is in `ap-southeast-1`
while Railway is presumably US/EU. Co-locating them cuts every remaining RPC
from ~300 ms to ~10–30 ms — and speeds up the dashboard and scheduler too.
The floor after that is one Claude Haiku call (~1–2 s).

---

## 7. What was changed in the June 2026 performance pass

1. `whatsapp_helpers.load_context()` — session + customer + last-8 history in
   ONE `run_query` round trip (JSON subqueries). Replaces 4–5 sequential RPCs.
2. `webhook_post` reordered — customer reply is sent first; all writes
   (`save_session`, `append_history` ×2, `create_customer`,
   `update_customer_name`, `save_customer_address`, `clear_session`, aunt
   notification) moved to FastAPI `BackgroundTasks`.
3. `confirm` batched — `order_name` stamp + all `order_lines` inserted in one
   CTE statement (2 RPCs total, was 2 + N + clear).
4. `ai_service` — Anthropic client reused across requests (cache keyed on
   class+key so test monkeypatching still works); system prompt split into a
   cached static block (role + catalog, `cache_control: ephemeral` — also
   covers the tool schemas) and an uncached dynamic block (customer name,
   knowledge, cart); `show_menu`/`get_order_status` reply directly from tool
   output, skipping the second Claude call.
5. Fixed the duplicate-current-message bug in Claude's prompt (see §5.4).
6. Test suite made fully offline (`search_products` faked in conftest;
   stale `ai_generate_reply` lambda and a buttons-vs-text assertion fixed).
   226/226 pass with no Supabase credentials.

### Recommended next steps (not done)
- **Co-locate Railway and Supabase regions** (biggest single win, zero code).
- Point the `info N` command at the live catalog; delete `catalog.json`.
- Verify prompt-cache hits in production (`cache_read_input_tokens`).
- If volume ever grows: extract APScheduler before scaling replicas.

---

## 8. Operational reference

- **Run locally:** `uvicorn app.main:app --reload --port 8000`; dashboard at
  `/login`; test order via `POST /dev/test_order`. `USE_MOCK_WHATSAPP=1` for dev.
- **Tests:** `python -m pytest tests/` — no credentials needed.
- **Env vars:** all via `Config` (`app/services/config.py`). Required:
  `SUPABASE_URL`, `SUPABASE_KEY`, `DASHBOARD_PASSWORD`, `SECRET_KEY`,
  `AUNT_PHONE`, `CLAUDE_API_KEY`; prod adds the `WA_META_*` trio.
- **Dashboard auth:** single shared-password cookie = SHA-256 of
  `SECRET_KEY:DASHBOARD_PASSWORD`. One user, no roles.
- **Scheduler:** follow-ups every 6 h, monthly report 1st @ 8 AM, retry queue
  every 15 min (max 3 attempts, DB-backed in `retry_queue` table).
- **Blast radius:** Supabase down = everything down. Anthropic down = bot
  degrades to hard commands. Meta down = inbound stops, outbound queues into
  retry. Wave down = invoices retry.
