# Roadmap: ALYASMEEN AuntOps — M1 (Supabase → prod)

## Overview

This roadmap makes the Supabase data foundation production-ready for the ALYASMEEN
WhatsApp ordering bot. It is built **smoke-thread-first**: Phase 1 proves the real spine
(a live Meta-format WhatsApp message creates a real order and notifies the aunt against live
Supabase) before any hardening underneath it. The remaining phases then harden the data
foundation that spine sits on — a correct and verified schema, repeatable migrations, a
deliberately-secured database access surface, automated backups with a proven restore, and
retention jobs that keep unbounded tables in check. This is brownfield work: the app already
runs end-to-end in mock/dev; these phases close the production gaps, they do not rebuild the
system. Scope is M1 only — M2–M5 are future GSD milestone cycles.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Spine Smoke-Thread** - A real Meta-format WhatsApp message creates a live order and notifies the aunt, end-to-end
- [x] **Phase 2: Schema Correctness & Integrity** - The live schema is complete, matches `schema.sql`, and missing-table drift fails loudly at startup
- [ ] **Phase 3: Versioned Migrations** - Ordered, repeatable migrations reproduce the full schema on a fresh project
- [ ] **Phase 4: Database Security Surface** - The Supabase key and arbitrary-SQL RPC surface are deliberately chosen and constrained
- [ ] **Phase 5: Data-Loss Insurance** - Nightly automated exports run and a tested restore runbook proves recovery
- [ ] **Phase 6: Bounded Growth (Retention)** - Retention jobs prune unbounded `chat_history` and `retry_queue` growth

## Phase Details

### Phase 1: Spine Smoke-Thread
**Goal**: Prove the production spine lives — a real Meta Cloud API webhook payload (nested `entry[].changes[].value.messages[]` envelope) is parsed into `(from_number, text, wa_name)` and reaches the existing message handler without returning HTTP 422
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: SPINE-01, SPINE-02
**Success Criteria** (what must be TRUE):
  1. A real Meta Cloud API webhook payload (nested `entry[].changes[].value.messages[]` envelope) is parsed into `(from_number, text, wa_name)` and reaches the existing message handler without returning HTTP 422
  2. An order placed from that real WhatsApp message is written to the live Supabase `orders` + `order_lines` tables and is visible in the dashboard `/orders` page
  3. The aunt receives the new-order WhatsApp notification for that order (`AUNT_PHONE`), proven against the live path — not mock
  4. The parser is minimal (proves the path only); full webhook hardening/signature verification is explicitly left to M2
**Plans**: 2 plans
  - [x] 01-01-PLAN.md — Meta-envelope parse seam fix + fixtures + parser/flow tests (SPINE-01, SPINE-02 automated)
  - [x] 01-02-PLAN.md — D-02 Meta token prerequisite + D-01 live proof + D-07 cleanup (SPINE-02 live, human-gated)

### Phase 2: Schema Correctness & Integrity
**Goal**: Make `schema.sql` the single, complete, verified source of truth for the live database, and make any schema drift fail loudly at startup instead of crashing mid-operation.
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: SCH-01, SCH-02, SCH-03
**Success Criteria** (what must be TRUE):
  1. The `monthly_snapshots` table exists in `schema.sql` and on live Supabase, so the monthly-report job and dashboard stat no longer crash on the missing table
  2. `schema.sql` is verified to match the live Supabase schema (tables, columns, types) — one documented source of truth with no silent divergence
  3. A startup check fails loudly (clear error, refuses to run) if a required table or column is missing, instead of failing silently at runtime
**Plans**: 2 plans
  - [x] 02-01-PLAN.md — Idempotent schema.sql hardening + validate_schema() core (SCH-01, SCH-02, SCH-03)
  - [x] 02-02-PLAN.md — FastAPI lifespan integration + unit/integration validation tests (SCH-03)

### Phase 3: Versioned Migrations
**Goal**: Replace ad-hoc schema edits with an ordered, repeatable migration mechanism that can rebuild the entire schema from scratch.
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: REQ-prod-migrations, MIG-01, MIG-02, MIG-03
**Success Criteria** (what must be TRUE):
  1. A versioned migration mechanism exists — schema changes are captured as ordered, numbered SQL migrations rather than hand edits to `schema.sql`
  2. Applying the migrations in order to a fresh Supabase project reproduces the full, verified schema (all 9 tables incl. `monthly_snapshots`, indexes, constraints)
  3. The migration set is documented so the builder can run it against a new project from the runbook alone
**Plans**: 1 plan
  - [ ] 03-01-PLAN.md — Transition to versioned migrations by baselining the current live schema (REQ-prod-migrations, MIG-01, MIG-02, MIG-03)

### Phase 4: Database Security Surface
**Goal**: Make the Supabase access surface a deliberate, documented security decision — the right least-privilege key and a constrained arbitrary-SQL RPC surface — rather than a defaulted one.
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: SEC-01, SEC-02
**Success Criteria** (what must be TRUE):
  1. The Supabase key in use is the deliberately-chosen least-privilege key for server-side access (anon vs service_role decided on purpose), and the choice is documented with its rationale
  2. The `run_query`/`run_exec` arbitrary-SQL RPC surface is assessed and constrained — function privileges reviewed, and base tables are not directly reachable via the public key
  3. The decision is recorded so a future reader understands why this surface is safe given the server-side-only access model (no client RLS)
**Plans**: TBD

### Phase 5: Data-Loss Insurance
**Goal**: Insure against data loss on the free tier with an automated nightly export and a restore that has actually been proven, not assumed.
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: BAK-01, BAK-02
**Success Criteria** (what must be TRUE):
  1. A nightly automated export of the critical tables runs to durable storage (free-tier insurance until Pro PITR ~July 2026)
  2. A restore runbook exists and has been executed at least once — recovery from an export into a working database is demonstrated, not assumed
  3. The runbook documents exactly which tables are covered, where exports land, and the step-by-step recovery procedure
**Plans**: TBD

### Phase 6: Bounded Growth (Retention)
**Goal**: Keep the two unbounded tables from growing forever by running retention jobs that prune old rows safely.
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: RET-01, RET-02
**Success Criteria** (what must be TRUE):
  1. A retention job prunes old `chat_history` rows on a schedule, keeping the table bounded without breaking the AI's recent-turn memory
  2. A retention job prunes resolved/old `retry_queue` rows on a schedule, keeping the table bounded without dropping still-pending retries
  3. Both jobs run inside the existing APScheduler setup and their retention windows are configured (not hardcoded magic numbers)
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Spine Smoke-Thread | 2/2 | Complete | 2026-06-15 |
| 2. Schema Correctness & Integrity | 2/2 | Complete | 2026-06-15 |
| 3. Versioned Migrations | 0/1 | Not started | - |

| 4. Database Security Surface | 0/TBD | Not started | - |
| 5. Data-Loss Insurance | 0/TBD | Not started | - |
| 6. Bounded Growth (Retention) | 0/TBD | Not started | - |
