# Requirements: ALYASMEEN AuntOps — M1 (Supabase → prod)

**Defined:** 2026-06-14
**Core Value:** A real customer can place an order on the live WhatsApp number and the aunt can fulfill it — reliably and unattended.
**Milestone:** M1 of 5 (production-readiness program — see PROJECT.md). Built smoke-thread-first (vertical MVP).

## v1 Requirements (M1)

Requirements for "Supabase ready for production." Each maps to a roadmap phase. Phase 1 is the
vertical smoke-thread that proves the spine before the foundation is hardened underneath it.

### Spine (smoke-thread — Phase 1)

- [ ] **SPINE-01**: A real Meta Cloud API webhook payload (nested envelope) is parsed into `(from_number, text, wa_name)` and reaches the existing message handler (minimal parser only; full webhook hardening is M2)
- [ ] **SPINE-02**: An order placed from a real WhatsApp message is written to live Supabase and the aunt receives the new-order notification — proven end-to-end

### Schema

- [ ] **SCH-01**: `monthly_snapshots` table exists in `schema.sql` and on Supabase (fixes the missing-table crash)
- [ ] **SCH-02**: `schema.sql` is verified to match the live Supabase schema (one source of truth)
- [ ] **SCH-03**: A startup check fails loudly if a required table or column is missing

### Migrations

- [ ] **MIG-01**: A repeatable, versioned migration mechanism exists (ordered SQL migrations, not ad-hoc edits)
- [ ] **MIG-02**: Applying migrations to a fresh Supabase project reproduces the full schema

### Database Security Surface

- [ ] **SEC-01**: The Supabase key in use is the deliberately-chosen least-privilege key for server-side access, documented (anon vs service_role decided, not defaulted)
- [ ] **SEC-02**: The `run_query`/`run_exec` arbitrary-SQL RPC surface is assessed and constrained (function privileges; tables not directly reachable via the public key)

### Data-loss Insurance

- [ ] **BAK-01**: A nightly automated export of critical tables runs to durable storage (free-tier insurance)
- [ ] **BAK-02**: A tested restore runbook exists — recovery from the export is proven, not assumed

### Bounded Growth

- [ ] **RET-01**: A retention job prunes old `chat_history` rows
- [ ] **RET-02**: A retention job prunes resolved/old `retry_queue` rows

## v2 Requirements (later milestones — deferred, not in this roadmap)

Planned fresh as their own GSD milestone cycles when reached (see PROJECT.md).

### M2 — FastAPI → prod
- Webhook signature verification; full Meta-envelope parsing; rate limiting; health checks; deploy hardening; webhook idempotency (dedupe Meta retries)

### M3 — Agent → prod
- AI reliability + fallbacks; Claude cost control; eval harness over the 75-message labeled dataset; knowledge base (`app/data/knowledge/`); fix `info N` dead-catalog bug; **agent observability + eval feedback loop** (the "learn from mistakes" idea — an evidence table designed around real measured failures)

### M4 — UI → prod (lean)
- Kill insecure defaults (`admin123`/`change-me`); `secure` cookie; login rate-limiting; input validation — sized for a single trusted operator

### M5 — Go-live
- End-to-end test; monitoring/alerting; Meta WABA approval; SSL/custom domain; cutover to real customers

## Out of Scope

| Feature | Reason |
|---------|--------|
| Website (new build) | New product, not productionizing this one — its own future project |
| Microservices / message-queue rearchitecture | Single-process monolith is adequate at near-term volume |
| Multi-tenant / serving other businesses | This is one aunt's system; generality is wasted effort now |
| Gold-plated multi-user auth (heavy CSRF/session infra) | Dashboard has one trusted operator |
| Agent self-learning / "memory" tables now | The model doesn't train on your data; build an evidence table in M3 driven by real measured failures (YAGNI) |
| Supabase Pro / PITR upgrade as a build task | Tracked as a dated decision (~July 2026), not built in M1 |

## Traceability

Populated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| SPINE-01 | — | Pending |
| SPINE-02 | — | Pending |
| SCH-01 | — | Pending |
| SCH-02 | — | Pending |
| SCH-03 | — | Pending |
| MIG-01 | — | Pending |
| MIG-02 | — | Pending |
| SEC-01 | — | Pending |
| SEC-02 | — | Pending |
| BAK-01 | — | Pending |
| BAK-02 | — | Pending |
| RET-01 | — | Pending |
| RET-02 | — | Pending |

**Coverage:**
- M1 requirements: 13 total
- Mapped to phases: 0 (roadmapper to fill)
- Unmapped: 13 ⚠️

---
*Requirements defined: 2026-06-14*
*Last updated: 2026-06-14 after initialization*
