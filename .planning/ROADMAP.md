# Roadmap - ALYASMEEN AuntOps Production Readiness

This roadmap transitions ALYASMEEN AuntOps from a development implementation to a production-ready WhatsApp service.

## Phases

- [x] **Phase 1: Database Foundation (M1)** - Establish a reproducible and recoverable data foundation.
- [x] **Phase 2: Application Hardening (M2)** - Secure and durable application boundary with separate web/worker roles.
- [ ] **Phase 3: Agent Dependability & Safety (M3)** - Safe, autonomous customer service with deterministic policy and human fallbacks.
- [ ] **Phase 4: Operator Security & UX (M4)** - Secure and operator-friendly dashboard with MFA and handoff management.
- [ ] **Phase 5: Production Go-Live (M5)** - Integrated system validation, pilot operation, and final cutover.

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

### Phase 4: Operator Security & UX (M4)
**Goal**: Secure and operator-friendly dashboard with MFA and handoff management.
**Depends on**: Phase 3
**Requirements**: REQ-prod-auth-mfa, REQ-prod-session-opaque, REQ-prod-csrf, REQ-prod-sec-headers, REQ-dash-login, REQ-dash-orders-list, REQ-dash-orders-filter, REQ-dash-status-update, REQ-dash-products-crud
**Success Criteria** (what must be TRUE):
  1. Dashboard access requires Supabase Auth with MFA (TOTP).
  2. Aunt can manage handoffs, see audit history, and resolve conflicts from the UI.
  3. All dashboard mutations are protected against CSRF and session hijacking.
  4. The operator can clearly see and recover from failed communications or dead-letter jobs.
**Plans**: TBD

### Phase 5: Production Go-Live (M5)
**Goal**: Integrated system validation, pilot operation, and final cutover.
**Depends on**: Phase 4
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
| 4. Operator Security | 0/1 | Not started | - |
| 5. Production Go-Live | 0/1 | Not started | - |
