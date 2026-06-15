# Roadmap: ALYASMEEN AuntOps M2

## Milestone Archive
- [v1.0 (M1 Roadmap)](.planning/milestones/v1.0-ROADMAP.md)

## Active Roadmap: M2 — FastAPI → Production

### Phase 07: Inbox/Outbox Schema & Core Transport (M2-P1) [COMPLETE]
**Goal**: Implement the durable data structures and basic signature verification.
**Plans:** 1 plan
- [x] 07-01-PLAN.md — Implement durable inbox/outbox schema and Meta transport security.

### Phase 08: Worker Process & Durable Loops (M2-P2) [COMPLETE]
**Goal**: Move processing logic out of the request loop and into a dedicated worker.
**Plans:** 4/4 plans executed
- [x] 08-01-PLAN.md — Create worker.py entry point with event/job claiming loops.
- [x] 08-02-PLAN.md — Migrate AI processing logic to worker claim handlers.
- [x] 08-03-PLAN.md — Standardize on Outbox Jobs and migrate PDF generation.
- [x] 08-04-PLAN.md — Move APScheduler from main.py to worker.py and wire scheduled jobs to outbox.

### Phase 09: Template Integration & Service Migration (M2-P3)
**Goal**: Fix the out-of-window messaging risk and finalize transport.
**Plans:** 3 plans
- [ ] 09-01-PLAN.md — Implement template transport layer in services and worker.
- [ ] 09-02-PLAN.md — Migrate Follow-up and Monthly Report services to templates.
- [ ] 09-03-PLAN.md — Create onboarding docs and verify real-number transport.

### Phase 10: Observability & Production Readiness (M2-P4)
**Goal**: Hardening, logging, and deployment.
- [ ] **10-01-LOGGING**: Integrate `structlog` and correlation IDs across web/worker.
- [ ] **10-02-HEALTH**: Add `/livez` and `/readyz` endpoints.
- [ ] **10-03-LIFESPAN**: Migrate to FastAPI Lifespan and clean up startup/shutdown.
- [ ] **10-04-DEPLOY**: Update `Procfile` and Railway config for web+worker split.

## Success Criteria
- [x] Real Meta webhook acknowledged in < 1s.
- [x] AI processing occurs in worker without blocking webhook.
- [ ] Follow-ups sent via templates succeed outside 24h window.
- [x] No duplicate orders on message replay.
- [ ] Web and Worker logs correlated by `wamid`.
