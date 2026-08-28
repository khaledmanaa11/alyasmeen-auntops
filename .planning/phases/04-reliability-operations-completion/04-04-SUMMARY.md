---
phase: 04-reliability-operations-completion
plan: 04
subsystem: infra
tags: [outbox, scheduler, apscheduler, supabase, dead-code-removal]

# Dependency graph
requires:
  - phase: 04-reliability-operations-completion
    provides: "Plan 04-01's outbox pdf_invoice job kind + queue_text calls, which already replaced every retry_queue caller before this plan ran"
provides:
  - "retry_queue.py and retry_actions.py deleted — no more unwired/dead retry mechanism claiming to run"
  - "app/worker.py scheduler with only followup, monthly_report, webhook_processor, outbox_processor jobs"
  - "Self-documenting migration recording retry_queue's retirement in the database itself"
affects: [phase-4-decision-1, worker-scheduler, outbox-processor]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Retire-in-place via COMMENT ON TABLE instead of DROP TABLE when a table is already RLS-locked deny-all and DROP can't be tested against live prod from repo tooling"]

key-files:
  created:
    - supabase/migrations/20260825000003_retire_retry_queue.sql
  modified:
    - app/worker.py
    - CLAUDE.md
  deleted:
    - app/services/retry_queue.py
    - app/services/retry_actions.py
    - tests/unit/test_retry.py
    - tests/unit/test_retry_actions_pdf.py

key-decisions:
  - "Did not DROP TABLE retry_queue — documented retirement via COMMENT ON TABLE, since the table is already RLS-locked deny-all (zero functional risk) and DROP is irreversible/untestable against live production from this repo's tooling"
  - "Deleted test_retry.py and test_retry_actions_pdf.py outright rather than porting their remaining (non-pdf_invoice) coverage — the retry_queue enqueue/process_retries/action-dispatch mechanism has no replacement need since outbox_jobs's attempts/max_attempts/status='failed' already covers the same retry/backoff intent generically per job kind, not per-action"

patterns-established: []

# Metrics
duration: 5min
completed: 2026-08-28
---

# Phase 4 Plan 04: Retire retry_queue Summary

**Deleted retry_queue.py/retry_actions.py and their 15-minute scheduler job now that outbox_jobs (plan 04-01) fully replaced them; documented the table's retirement in the database via COMMENT ON TABLE instead of an irreversible DROP.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-08-28T12:10:00Z (approx)
- **Completed:** 2026-08-28T12:15:42Z
- **Tasks:** 2
- **Files modified:** 6 (2 modified, 4 deleted, 1 created)

## Accomplishments
- Removed the last unwired/dead-code path Phase 4 decision 1 targeted: `retry_queue.py`'s `enqueue()` was never called by anything after the outbox migration, and now the module doesn't exist at all
- `app/worker.py` scheduler now only lists real, wired jobs: `followup`, `monthly_report`, `webhook_processor`, `outbox_processor`
- Deleted two test files whose exclusive subject (retry_queue/retry_actions) no longer exists; their pdf_invoice-specific coverage was already ported to `test_processor.py::TestPdfInvoiceJobKind` in plan 04-01
- Shipped a self-documenting migration (`COMMENT ON TABLE`) recording the retirement, deliberately avoiding an irreversible `DROP TABLE` in this phase
- `CLAUDE.md`'s Project Structure tree no longer lists the two deleted files

## Task Commits

Each task was committed atomically:

1. **Task 1: Delete retry_queue/retry_actions and unwire worker.py** - `7b145ea` (feat)
2. **Task 2: Retirement migration for the retry_queue table** - `006f1a0` (docs)

_Note: Task 2 used a `docs` commit type since it only adds a documentation-style migration (COMMENT ON TABLE, no schema/data change)._

## Files Created/Modified
- `app/worker.py` - Removed `retry_queue` import, scheduler job, and its entry in the startup log's `jobs=[...]` list
- `CLAUDE.md` - Removed the two stale `retry_queue.py`/`retry_actions.py` lines from the Project Structure tree
- `app/services/retry_queue.py` - Deleted (superseded by outbox_jobs)
- `app/services/retry_actions.py` - Deleted (superseded by outbox_jobs's pdf_invoice job kind)
- `tests/unit/test_retry.py` - Deleted (exclusively tested the deleted modules; pdf_invoice coverage already ported)
- `tests/unit/test_retry_actions_pdf.py` - Deleted (exclusively tested the deleted retry_actions.py pdf_invoice path; coverage already ported to `test_processor.py::TestPdfInvoiceJobKind`)
- `supabase/migrations/20260825000003_retire_retry_queue.sql` - New migration: `COMMENT ON TABLE retry_queue` documenting retirement, no DROP

## Decisions Made
- **No DROP TABLE for retry_queue**: the table is already RLS-locked with no anon/authenticated policies (deny-all per `20260614000003_security_rls.sql`), so leaving it in place with zero application code touching it carries zero functional risk, while `DROP TABLE` is irreversible and can't be tested against the live production database from this repo's current tooling. Migration is additive/reversible per the plan's explicit intent.
- **Deleted rather than ported the non-pdf_invoice retry_queue/retry_actions test coverage**: `enqueue`, `process_retries`, and the `send_text_ready`/`send_text_done`/`send_text_delivered` action dispatch tests had no replacement need — the outbox's own `attempts`/`max_attempts` + `status='failed'` mechanism already covers equivalent retry/backoff behavior generically for every job kind, so there was no missing-critical-functionality gap to fill (verified this reasoning against the plan's explicit statement, not just assumed it).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required. (The migration file is new but is not applied to any live/test database as part of this plan, consistent with the plan's verification note — applying migrations to live Supabase remains a separate Phase 4 concern.)

## Next Phase Readiness
- Phase 4 decision 1 (retire retry_queue) is now fully complete: built in 04-01, wired/tested there, and retired here in 04-04.
- Full test suite green: 247 passed, 3 skipped, no import errors from `app/worker.py` or elsewhere.
- Ready for the next plan in the phase (04-05 onward, per `.planning/phases/04-reliability-operations-completion/`).
- No blockers introduced by this plan.

---
*Phase: 04-reliability-operations-completion*
*Completed: 2026-08-28*

## Self-Check: PASSED

- FOUND: supabase/migrations/20260825000003_retire_retry_queue.sql
- CONFIRMED DELETED: app/services/retry_queue.py
- CONFIRMED DELETED: app/services/retry_actions.py
- CONFIRMED DELETED: tests/unit/test_retry.py
- CONFIRMED DELETED: tests/unit/test_retry_actions_pdf.py
- FOUND commit: 7b145ea (Task 1)
- FOUND commit: 006f1a0 (Task 2)
