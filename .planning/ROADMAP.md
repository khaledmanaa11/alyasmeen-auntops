# Roadmap - ALYASMEEN AuntOps Production Readiness

This roadmap transitions ALYASMEEN AuntOps from a development implementation to a production-ready WhatsApp service.

## Phases

- [x] **Phase 1: Database Foundation (M1)** - Establish a reproducible and recoverable data foundation.
- [x] **Phase 2: Application Hardening (M2)** - Secure and durable application boundary with separate web/worker roles.
- [ ] **Phase 3: Agent Dependability & Safety (M3)** - Safe, autonomous customer service with deterministic policy and human fallbacks.
- [x] **Phase 4: Reliability & Operations Completion (M4)** - Finish the reliability story: no dead code claiming to run, live-DB verification, operator-visible failures.
- [ ] **Phase 5: Operator Security & UX (M5)** - Secure and operator-friendly dashboard with MFA and handoff management.
- [ ] **Phase 6: Production Go-Live (M6)** - Integrated system validation, pilot operation, and final cutover.

## Phase Details

### Phase 1: Database Foundation (M1)
**Goal**: Establish a reproducible and recoverable data foundation.
**Depends on**: Nothing
**Requirements**: REQ-prod-atomic-orders, REQ-prod-backup-restore, REQ-prod-migrations, REQ-nfr-data, REQ-bot-session-persist
**Success Criteria** (what must be TRUE):
  1. System can be rebuilt from scratch using only migrations (no manual dashboard edits).
  2. Database restore from backup is verified and documented with a successful drill.
  3. No raw SQL-over-RPC remains callable from the frontend; all DB access is typed.
  4. Schema for webhook inbox, outbox, audit, and handoffs is present and enforced.
**Plans**:
- [x] 01-01-PLAN.md — Setup & Messaging Schema
- [x] 01-02-PLAN.md — Atomic Logic & Security
- [x] 01-03-PLAN.md — Verification & DR

### Phase 2: Application Hardening (M2)
**Goal**: Secure and durable application boundary with separate web/worker roles.
**Depends on**: Phase 1
**Requirements**: REQ-bot-webhook, REQ-prod-raw-hmac, REQ-prod-inbox, REQ-prod-outbox, REQ-prod-idempotency, REQ-prod-struct-log, REQ-prod-metrics, REQ-prod-cicd, REQ-prod-pinned-model, REQ-nfr-latency, REQ-nfr-uptime
**Success Criteria** (what must be TRUE):
  1. Meta webhooks are signature-verified and durably persisted before processing.
  2. Web and worker processes are separated, with exactly one scheduler owner.
  3. Automated CI/CD deploys and rolls back services predictably to Railway.
  4. Real-time alerts detect service failures, processing delays, or provider errors.
**Plans**:
- [x] 02-01-PLAN.md — Boundary Hardening & Observability
- [x] 02-02-PLAN.md — Worker Processing & Infrastructure

### Phase 3: Agent Dependability & Safety (M3)
**Goal**: Safe, autonomous customer service with deterministic policy and human fallbacks.
**Depends on**: Phase 2
**Requirements**: REQ-prod-policy-gate, REQ-prod-handoff, REQ-prod-eval-gate, REQ-bot-ai-fallback, REQ-ai-no-hallucination, REQ-ai-tools, REQ-bot-aunt-notification, REQ-sched-followup, REQ-sched-retry-queue
**Success Criteria** (what must be TRUE):
  1. AI-proposed actions are validated by a deterministic policy gate before execution.
  2. Risky or uncertain customer messages trigger a durable human handoff state.
  3. AI evaluation scores meet release thresholds on representative Arabic/English datasets.
  4. Automated `to_do` order changes work reliably while later statuses block agent mutation.
**Plans**:
- [ ] 03-01-PLAN.md — Safety Foundation
- [ ] 03-02-PLAN.md — Integration & Triggers
- [ ] 03-03-PLAN.md — Evaluation & Resilience

### Phase 4: Reliability & Operations Completion (M4)
**Goal**: Every reliability mechanism either genuinely works in production or is deleted — no dead code that claims to run, no failure invisible to the operator.
**Depends on**: Phase 3 (can run in parallel — no shared files except dashboard templates)
**Context**: The 2026-08-25 hardening session (branch `fix/production-hardening`) already delivered part of this phase outside GSD: webhook poison-pill dead-lettering, the outbox wired as the single send path for the bot pipeline (`queue_text`/`queue_buttons` in `app/services/processor.py`), and `whatsapp_meta.py` senders raising `WhatsAppSendError` on failure.
**Requirements**: REQ-prod-outbox (done), REQ-prod-backup-restore, REQ-prod-metrics, REQ-nfr-uptime
**Success Criteria** (what must be TRUE):
  1. `retry_queue.py` and `gatekeeper.py` are each either wired into a real call path or deleted — nothing in the repo claims to provide a guarantee it does not provide.
  2. All `supabase/migrations/*.sql` are applied to the live Supabase project and the deployed app is verified working end-to-end against it with the key it actually ships with (anon vs service_role decided and documented).
  3. The worker's APScheduler job store is persistent in production (`DATABASE_URL` set on Railway) and survives a worker restart, verified.
  4. Dead-lettered `webhook_events` rows and `status='failed'` outbox jobs are visible on the dashboard with a one-click retry, so a stuck message is an operator decision, not a silent loss.
  5. The backup restore drill in `docs/BACKUP_DRILL.md` has been executed once for real and its Drill Log records a successful result.
**Plans**: 7 plans in 4 waves — ALL COMPLETE
- [x] 04-01-PLAN.md — Outbox migration: followup/monthly_report/ui_api enqueue + pdf_invoice job kind
- [x] 04-02-PLAN.md — Gatekeeper: synchronous rewrite + wiring into Claude/Meta calls
- [x] 04-03-PLAN.md — Scheduler persistence proof (SQLAlchemyJobStore) + DATABASE_URL docs
- [x] 04-04-PLAN.md — Retire retry_queue.py/retry_actions.py + retirement migration
- [x] 04-05-PLAN.md — Dead-letter dashboard: /api/alerts backend
- [x] 04-06-PLAN.md — Dead-letter dashboard: Alerts UI tab
- [x] 04-07-PLAN.md — Live rollout: DATABASE_URL persistence, service_role switch, migrations, backup drill (checkpoints) — completed 2026-08-28

### Phase 5: Operator Security & UX (M5)
**Goal**: Secure and operator-friendly dashboard with MFA and handoff management.
**Depends on**: Phase 3 (soft — the `handoffs` / `audit_logs` tables and `sessions.paused` already exist from Phase 1, so Phase 5 builds the resolution + UI half against live schema. Phase 3 still owns `HandoffService.trigger()`/pause; until it ships there is no producer of active handoffs, and `POST /dev/test_handoff` seeds them for verification.)
**Requirements**: REQ-prod-auth-mfa, REQ-prod-session-opaque, REQ-prod-csrf, REQ-prod-sec-headers, REQ-prod-handoff (UI), REQ-dash-login, REQ-dash-orders-list, REQ-dash-orders-filter, REQ-dash-status-update, REQ-dash-products-crud
**Success Criteria** (what must be TRUE):
  1. Dashboard access requires Supabase Auth with MFA (TOTP).
  2. Aunt can manage handoffs, see audit history, and resolve conflicts from the UI.
  3. All dashboard mutations are protected against CSRF and session hijacking.
  4. The operator can clearly see and recover from failed communications or dead-letter jobs.
**Plans**: 10 plans in 7 waves
- [x] 05-01-PLAN.md — Opaque session store: operator_sessions/trusted_devices/pending_logins migration + sessions.py — completed 2026-08-28
- [x] 05-02-PLAN.md — Supabase Auth service wrapper (AAL/MFA) + operator account management CLI — completed 2026-08-28
- [x] 05-03-PLAN.md — Replace the shared-password guard: auth deps, email+password+TOTP login, test seam — completed 2026-08-28
- [x] 05-04-PLAN.md — CSRF (starlette-csrf) + security headers + shared `_nav.html` partial — completed 2026-08-28
- [ ] 05-05-PLAN.md — Handoff resolve + audit service + operator JSON API + dev handoff seed
- [ ] 05-06-PLAN.md — Audited mutations, bot-vs-aunt conflict guard, alerts API rework, failure alerts
- [ ] 05-07-PLAN.md — Handoffs tab (transcript, return-to-bot, live badge) + audit trail page
- [ ] 05-08-PLAN.md — Alerts page reworked into Arabic action cards + conflict picker on orders
- [ ] 05-09-PLAN.md — Account page: MFA enrollment, session management, admin session view, password reset
- [ ] 05-10-PLAN.md — Live rollout + assisted TOTP enrollment + operator walkthrough (checkpoints)

### Phase 6: Production Go-Live (M6)
**Goal**: Integrated system validation, pilot operation, and final cutover.
**Depends on**: Phase 5
**Requirements**: REQ-nfr-test-coverage, Meta WABA registration, Staged pilot, Training
**Success Criteria** (what must be TRUE):
  1. Real Meta WABA number is receiving and sending messages in production environment.
  2. Staged pilot with selected customers completes with zero critical defects.
  3. Aunt demonstrates ability to operate all daily workflows independently using documentation.
  4. Final production readiness check (monitoring, rollback, DR) is signed off.
**Plans**: TBD

## Progress Table

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Database Foundation | 3/3 | ✅ Completed | 2026-06-14 |
| 2. Application Hardening | 2/2 | ✅ Completed | 2026-06-14 |
| 3. Agent Dependability | 0/3 | 🏗️ In Progress | - |
| 4. Reliability & Ops Completion | 7/7 | Complete    | 2026-08-28 |
| 5. Operator Security | 4/10 | 🏗️ In Progress | - |
| 6. Production Go-Live | 0/1 | Not started | - |
