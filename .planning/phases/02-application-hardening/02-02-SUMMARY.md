# Wave 2 Summary: Worker Processing & Infrastructure

**Status:** Completed
**Date:** 2026-06-14

## Work Completed

### Task 1: Process Separation & Scheduler Migration
- Created `app/worker.py` to host background tasks and scheduling.
- Configured `BlockingScheduler` with `SQLAlchemyJobStore` for persistent state (REQ-nfr-uptime).
- Migrated `send_followups`, `send_monthly_report`, and `process_retries` from `app/main.py` to `app/worker.py`.
- Removed `AsyncIOScheduler` from `app/main.py`, successfully separating Web and Worker processes.

### Task 2: Worker Processing Loop & Idempotency
- Created `app/services/processor.py` to house the decoupled bot brain.
- Implemented `process_webhook_events` polling loop (every 3s) in the worker to process messages from the Inbox.
- Implemented `process_outbox_jobs` polling loop (every 2s) to handle outgoing messages.
- Enforced idempotency using the unique `wamid` from Meta (REQ-prod-idempotency).
- Updated `Config.CLAUDE_MODEL` with a stable default and validation (REQ-prod-pinned-model).

### Task 3: Process Orchestration & CI/CD
- Created `Procfile` defining `web` and `worker` roles for Railway deployment (REQ-prod-cicd).
- Verified that both processes can run independently and communicate via the database.

## Success Criteria Status
1. Web and Worker processes run independently. [YES]
2. APScheduler runs exactly once in the Worker process. [YES]
3. Duplicate webhooks are ignored by the worker. [YES]
4. Outgoing messages are sent via the outbox pattern. [YES]

## Next Steps
Phase 2 is now complete. The application is hardened and architecturally ready for production. Proceed to **Phase 3: Agent Dependability & Safety (M3)** to refine AI behavior and implement human handoffs.
