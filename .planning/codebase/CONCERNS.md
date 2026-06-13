# Concerns & Technical Debt

**Analysis Date:** 2026-06-13

> Severity legend: 🔴 Critical (breaks prod) · 🟠 High (security/correctness) · 🟡 Medium (debt) · 🟢 Low (polish)

## 🔴 Critical Bugs

### 1. Webhook POST cannot parse real Meta payloads
`app/routers/whatsapp.py::webhook_post` accepts a **flat** Pydantic model
`Msg(from_number, text, wa_name)`. The Meta Cloud API delivers a deeply-nested
envelope (`entry[].changes[].value.messages[]`). Real inbound messages will
return **HTTP 422** — the bot only works in mock mode / against the flat dev shape today.
- **Impact:** production WhatsApp messages are never processed.
- **Fix:** add a Meta-envelope parser that flattens to `(from_number, text, wa_name)`
  before the handler, or branch on payload shape.

### 2. `monthly_snapshots` table queried but not in schema
`monthly_snapshots` is written by `app/services/monthly_report.py` and read by
`app/routers/ui_api.py`, but it does **not exist** in `app/db/schema.sql`. A fresh
Supabase deployment crashes the first time the monthly report job runs (or the
dashboard stat is requested).
- **Fix:** add the `monthly_snapshots` table to `schema.sql`.

### 3. `info N` reads from dead legacy catalog
The `info`/`تفاصيل` command in `whatsapp.py` indexes `_CATALOG`, which
`whatsapp_helpers._load_catalog()` loads from the **legacy `app/data/catalog.json`**
(no longer the source of truth — products live in Supabase). `catalog.json` is empty/stale,
so product detail lookups silently fail.
- **Fix:** back `info` with `app/ai/retriever` (Supabase) instead of `_CATALOG`.

## 🟠 Security

| # | Issue | Location |
|---|-------|----------|
| 1 | **Webhook POST has zero authentication** — no signature verification; anyone can POST and trigger order creation + Claude API spend | `whatsapp.py::webhook_post` (`WA_META_APP_SECRET` unused) |
| 2 | **Insecure defaults** — `DASHBOARD_PASSWORD` defaults to `admin123`, `SECRET_KEY` to `change-me-in-production`, with no startup guard | `app/services/config.py:37-38` |
| 3 | **Login cookie lacks `secure=True`** — sent over plain HTTP if TLS misconfigured | `ui.py::login_submit` |
| 4 | **No rate limiting on `/login`** — brute-force unprotected (the `gatekeeper` helper exists but is unused) | `ui.py` |

## 🟡 Technical Debt

- **Dead code:** `app/shared/gatekeeper.py` (`ApiGatekeeper`, ~217 lines) is never imported
  anywhere, while rate limits go unenforced. Either wire it in or delete it.
- **Auth logic duplicated:** `_session_token()` / `_is_authenticated()` / `COOKIE_NAME`
  are copy-pasted across `ui.py`, `ui_api.py`, and `shared/constants.py`. Centralize.
- **Diverged constant:** `WHATSAPP_MENU_LIMIT = 5` in `whatsapp.py` vs `3` in
  `shared/constants.py` — two sources of truth.
- **No production guard on dev endpoints:** `/dev/test_order` and `/dev/chat`
  (`app/routers/debug.py`) are always registered, even in prod.
- **Deprecated FastAPI lifecycle:** `@app.on_event("startup"/"shutdown")` in `main.py`
  is deprecated — should migrate to the `lifespan` context manager.
- **Wrong-language invoice:** `pdf_invoice.py` uses a Hebrew font (`Heebo-Regular.ttf`) /
  Hebrew filename-caption in an Arabic-facing app.
- **Legacy `catalog.json`** still loaded at import in `whatsapp_helpers.py` despite being
  declared dead in `CLAUDE.md`.

## 🟡 Performance

- **Unbounded table growth:** `chat_history` and `retry_queue` have no cleanup/retention
  job. At 10–30 orders/day this is slow-burn, but both grow forever.
- **Template cache disabled:** `ui.py::_NoCache` re-parses every template on every request
  (intentional workaround for a Jinja2 unhashable-key bug; fine at current volume, revisit
  if traffic grows).
- **Catalog cache is process-global** — `retriever._CATALOG` invalidation relies on every
  product-mutation path calling `invalidate_catalog()`; a missed call serves stale products.

## 🟢 Test Gaps

- No test covers the **real Meta webhook envelope** (tests use the flat `Msg` shape — masking bug #1).
- No test for the **missing `monthly_snapshots` table** (bug #2 would surface here).
- No test for **login brute-force / rate limiting**.

## Fragile Areas (handle with care)

- `app/routers/whatsapp.py::webhook_post` — long, branch-heavy hard-command dispatcher;
  order of branches matters (aliases → hard commands → number/qty → AI fallback).
- `app/db/database.py::_build/_escape` — manual `%s` substitution; param-count mismatch
  raises. All safety depends on never passing user-authored SQL.
- `_make_tool_executor` closure — mutates `session`/`cart` by reference; persistence depends
  on the `_tools_ran` flag being honored by the caller.

---

*Concerns analysis: 2026-06-13*
