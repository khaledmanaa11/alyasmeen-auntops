# ALYASMEEN AuntOps — Production Readiness

## What This Is

A WhatsApp ordering bot + web dashboard for **ALYASMEEN**, a natural & handmade skincare
business (lotions, creams, candles) in Palestine. Customers order over WhatsApp in Arabic or
English; Claude powers the conversation; the aunt manages orders, products, and broadcasts from
a built-in dashboard. The system already works end-to-end in development/mock mode — this
program turns it into a **real production system the aunt can rely on, unattended**.

## Core Value

A real customer can place an order on the **live** WhatsApp number and the aunt can fulfill it —
reliably and unattended. If everything else fails, the message-in → order-out → aunt-notified
spine must work in production.

## Requirements

### Validated

<!-- Existing capabilities inferred from the codebase (works in dev/mock today). -->

- ✓ WhatsApp conversation: hard commands (cart/clear/pickup/delivery/confirm/menu/tracking) + agentic AI fallback with 4 tools — existing
- ✓ Cart → order flow: `confirm` writes order + lines to Supabase, clears session, messages customer — existing
- ✓ New-order notification to the aunt on every confirm (`AUNT_PHONE`) — existing
- ✓ Web dashboard: login, orders, dashboard stats, product management, broadcast (5 templates) — existing
- ✓ Products live in Supabase `products` table (catalog.json retired) with live cache invalidation — existing
- ✓ Supabase access via HTTPS RPC (`run_query`/`run_exec`) through a single DB adapter with retry + circuit breaker — existing
- ✓ PDF invoice generated and sent to customer on status → done — existing
- ✓ Scheduler: follow-ups (6h), monthly report (1st @ 08:00), retry queue (15m) — existing
- ✓ Eval dataset foundation: 75 labeled customer messages (`tests/data/whatsapp_agent_dataset.json`) — existing

### Active

<!-- The production-readiness program. Five milestones, each its own GSD milestone cycle,
     planned from the real current state when we reach it. M1 is the current focus. -->

**Strategy:** Smoke-thread first (vertical MVP) — prove the real spine lives before hardening
layers underneath it.

- [ ] **M0/M1 spine (current):** one real Meta-format WhatsApp message → parsed → order created → aunt notified, against live Supabase
- [ ] **M1 — Supabase → prod:** complete schema (add missing `monthly_snapshots`), migration discipline, secure the RPC/key surface (not cargo-culted RLS), data-loss insurance (scripted export now → Pro PITR ~July 2026), retention/cleanup for unbounded tables
- [ ] **M2 — FastAPI → prod:** webhook signature verification, real Meta-envelope parsing, rate limiting, health checks, deploy hardening, webhook idempotency (dedupe Meta retries)
- [ ] **M3 — Agent → prod:** AI reliability + fallbacks, Claude cost control, eval harness over the labeled dataset, knowledge base (`app/data/knowledge/`)
- [ ] **M4 — UI → prod (lean):** kill insecure defaults, `secure` cookie, login rate-limiting, input validation — sized for a single trusted operator, not a hostile multi-user app
- [ ] **M5 — Go-live:** end-to-end test, monitoring/alerting, Meta WABA approval, SSL/custom domain, cutover to real customers

### Out of Scope

<!-- Explicit boundaries with reasoning. -->

- **Website (new build)** — it's a new product, not productionizing this one; its own future project
- **Microservices / message-queue rearchitecture** — the single-process monolith is adequate at current+near-term volume; revisit only if scale forces it
- **Multi-tenant / serving other businesses** — this is one aunt's system; generality is wasted effort now
- **Gold-plated multi-user auth (heavy CSRF/session infra)** — the dashboard has one trusted operator; over-building auth is wasted effort (see Key Decisions)
- **Anything not in service of go-live** — feature ideas wait until the aunt has a working system

## Context

- **Brownfield, mature.** All 14 original improvement-plan steps are complete; AppSheet removed; custom dashboard live. Rich knowledge already captured in `.planning/codebase/` (map), `.planning/intel/` (ingested PRD/PLAN/decisions), and `ALYASMEEN/` (wiki + graph).
- **Deployment:** hosted on Railway at `alyasmeen.org` (SSL pending); Meta WABA business review pending approval.
- **Known critical gaps (`.planning/codebase/CONCERNS.md`):** webhook can't parse real Meta payloads (🔴 — no real message works today), `monthly_snapshots` table queried but missing from schema (🔴), `info N` reads a dead legacy catalog (🔴); plus webhook has no auth, insecure default secrets (`admin123`/`change-me`), no login rate-limiting, unbounded `chat_history`/`retry_queue` growth.
- **Builder:** Khaled — solo student, budget-conscious, wants to be directed and challenged, learning as he builds.

## Constraints

- **Tech stack**: FastAPI + Supabase (PostgreSQL over HTTPS RPC, supabase-py — no psycopg2) + Claude (Anthropic SDK) + APScheduler — established; do not re-architect away from it
- **Architecture**: single-process modular monolith; one AI file (`ai_service.py`), one DB file (`database.py`); all config via `Config` — enforced by convention
- **Access model**: server-side only — browser never touches Supabase; security work targets the RPC/key surface, not client RLS
- **Locale**: Arabic-first (primary) + English; Palestine market
- **Operator**: a single non-technical user (the aunt) — UX and ops must assume that
- **Budget**: student; Supabase free tier now, Pro (~$25/mo) attainable in ~1 month
- **Scale**: variable / growing — design for growth, no fixed-volume assumption

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Smoke-thread first (vertical MVP), then harden layers | A real order doesn't flow until M5 under pure layering — prove the spine in week one to de-risk the whole program | — Pending |
| Supabase free tier now → upgrade to Pro for backups + 7-day PITR ~July 2026 | Honest budget staging; script a nightly export now as cheap insurance until real orders justify the spend | — Pending |
| Secure the RPC/key surface, not cargo-culted RLS | Access is server-side only via arbitrary-SQL `run_query`/`run_exec`; classic row-level policies buy little, the real risk is key leak → full DB compromise | — Pending |
| Keep M4 (UI auth) lean | Single trusted operator on one device; heavy multi-user auth infra is wasted effort — fix insecure defaults + secure cookie + rate-limit only | — Pending |
| 5 milestones = 5 GSD milestone cycles, each planned from the current point | User wants to discuss/challenge each milestone freshly rather than pre-plan M2–M5 blind | — Pending |
| Website is a separate future project | Productionizing ≠ new build; keep scope clean | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-14 after initialization*
