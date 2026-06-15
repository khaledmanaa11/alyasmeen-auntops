---
phase: 08-worker-process-durable-loops
plan: 01
subsystem: worker
tags: [worker, durable-loops, inbox, outbox]
requirements: [REQ-M2-01]
tech-stack: [python, supabase, asyncio]
key-files: [worker.py, app/services/worker_utils.py, supabase/migrations/20260616000001_worker_rpcs.sql]
decisions:
  - "Atomic job claiming implemented via PL/pgSQL RPCs using FOR UPDATE SKIP LOCKED."
  - "Worker uses asyncio to run concurrent inbox and outbox loops."
  - "Naive splitting in apply_migration.py replaced with whole-file execution to support PL/pgSQL."
metrics:
  duration: 15m
  completed_date: "2026-06-15"
---

# Phase 08 Plan 01: Core Worker Infrastructure Summary

Established the foundation for asynchronous job processing in AuntOps. This plan implemented the worker process, utility functions for job management, and the necessary database-level atomic claiming logic.

## Key Accomplishments

- **Atomic Claiming RPCs:** Created `claim_webhook_event` and `claim_outbox_job` PL/pgSQL functions in Supabase. These functions use `FOR UPDATE SKIP LOCKED` to ensure that multiple worker instances can operate safely without double-processing jobs.
- **Worker Process:** Implemented `worker.py` as a standalone entry point. It runs two concurrent `asyncio` loops:
  - `inbox_loop`: Polls for pending webhook events.
  - `outbox_loop`: Polls for pending outgoing messages.
- **Worker Utilities:** Created `app/services/worker_utils.py` to encapsulate database interactions for the worker, including job claiming and status updates.
- **Migration Tooling:** Updated `scripts/apply_migration.py` to handle complex SQL files (like those containing PL/pgSQL functions) by executing them as a single batch.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Naive SQL splitting in apply_migration.py**
- **Found during:** Task 1
- **Issue:** The original script split SQL by `;`, which breaks PL/pgSQL function definitions.
- **Fix:** Updated the script to execute the entire file content as a single batch.
- **Files modified:** `scripts/apply_migration.py`
- **Commit:** `4640b77`

## Verification Results

- **Dry Run:** `python worker.py --dry-run` successfully validated the environment and database schema.
- **Integration Test:** Verified that `worker.py` successfully claims pending records from both `webhook_events` and `outbox_jobs` tables and moves them to terminal states (`processed` and `sent`).
- **Concurrency Safety:** The use of `FOR UPDATE SKIP LOCKED` in the database RPCs was validated via research and ensures safe multi-worker operation.

## Self-Check: PASSED
- [x] worker.py created and functional.
- [x] claim_webhook_event and claim_outbox_job RPCs deployed.
- [x] worker_utils.py implemented.
- [x] Verification successful.
