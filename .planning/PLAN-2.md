# Phase 2: Application Hardening - Master Plan

Goal: Secure and durable application boundary with separate web/worker roles.

## Overview
This phase transitions the ALYASMEEN AuntOps application from a single-process development setup to a robust, production-ready architecture. We focus on security (HMAC), reliability (Inbox/Outbox), and observability (Structured Logging).

## Execution Waves

### Wave 1: Boundary Hardening & Observability
**Plan: 02-01-PLAN.md**
- **Task 1: Structured Logging & Health Check**: Integrate `structlog` for machine-parsable JSON logs and add a `/health` endpoint for monitoring.
- **Task 2: HMAC Webhook Verification**: Enforce Meta's signature verification on all incoming webhooks to prevent spoofing.
- **Task 3: Durable Webhook Ingestion**: Implement the Inbox pattern where webhooks are persisted to the database and acknowledged immediately (200 OK), improving latency and reliability.

### Wave 2: Worker Processing & Infrastructure
**Plan: 02-02-PLAN.md**
- **Task 1: Process Separation & Scheduler**: Extract background tasks and scheduling to a dedicated `worker.py` process with a persistent JobStore.
- **Task 2: Worker Processing Loop**: Implement the async loop that processes ingested webhooks and handles outgoing messages via the Outbox pattern, including `wamid` deduplication.
- **Task 3: Process Orchestration & CI/CD**: Configure `Procfile` for Railway to run both Web and Worker services and ensure production-pinned configurations.

## Requirements Addressed
- **Security**: REQ-prod-raw-hmac, REQ-prod-idempotency
- **Reliability**: REQ-prod-inbox, REQ-prod-outbox, REQ-nfr-latency, REQ-nfr-uptime
- **Observability**: REQ-prod-struct-log, REQ-prod-metrics
- **Infrastructure**: REQ-prod-cicd, REQ-bot-webhook, REQ-prod-pinned-model

## Success Criteria
1. Meta webhooks are signature-verified and durably persisted before processing.
2. Web and worker processes are separated, with exactly one scheduler owner.
3. Automated CI/CD deploys and rolls back services predictably to Railway.
4. Real-time alerts can be driven by structured logs and health check failures.
