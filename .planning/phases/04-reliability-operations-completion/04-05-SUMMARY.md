---
phase: 04-reliability-operations-completion
plan: 05
subsystem: api
tags: [fastapi, dashboard, outbox, webhook-events, alerts]

# Dependency graph
requires:
  - phase: 04-reliability-operations-completion
    provides: "outbox_jobs as the single durable send path (plan 04-01) and webhook_events poison-pill dead-lettering (attempts column, hardening session)"
provides:
  - "GET /api/alerts — authenticated JSON listing of dead-lettered webhook_events and permanently-failed outbox_jobs"
  - "POST /api/alerts/webhook_events/{id}/retry — resets a dead-lettered event back to unprocessed/pollable"
  - "POST /api/alerts/outbox_jobs/{id}/retry — resets a permanently-failed job back to pending/pollable"
affects: ["04-06 (dashboard alerts UI consumes this API)"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Alerts endpoints follow the exact auth-guard + query/execute pattern already used by every other /api/* route in ui_api.py — no new abstractions introduced"
    - "Retry endpoints reset the existing row in place (UPDATE, not re-insert), preserving created_at/history for audit"

key-files:
  created: [tests/integration/test_alerts_api.py]
  modified: [app/routers/ui_api.py]

key-decisions:
  - "Retry endpoints mutate the row in place rather than inserting a new one, matching the existing mutation style in this codebase and keeping audit history intact"
  - "Resetting webhook_events.processed = FALSE re-runs handle_message() from scratch on the next poll; the wamid unique constraint blocks duplicate inbound-message inserts, but a retry can still re-run bot-command side effects if the original processing died partway through — a pre-existing narrow gap documented but not closed here, per Phase 4's locked scope"

# Metrics
duration: 8min
completed: 2026-08-28
---

# Phase 4 Plan 05: Alerts API Summary

**GET /api/alerts + two one-click retry endpoints in `ui_api.py`, surfacing dead-lettered webhook_events and permanently-failed outbox_jobs to an authenticated operator.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-08-28T12:12:00Z (approx)
- **Completed:** 2026-08-28T12:20:00Z
- **Tasks:** 2
- **Files modified:** 2 (1 modified, 1 created)

## Accomplishments
- `GET /api/alerts` returns both dead-lettered `webhook_events` (`processed = TRUE AND error LIKE 'dead-letter:%'`) and permanently-failed `outbox_jobs` (`status = 'failed' AND attempts >= max_attempts`), each capped at 100 rows, newest first.
- `POST /api/alerts/webhook_events/{id}/retry` resets a dead-lettered event to `processed = FALSE, attempts = 0, error = NULL`, making it eligible for the next inbox poll.
- `POST /api/alerts/outbox_jobs/{id}/retry` resets a failed job to `status = 'pending', attempts = 0, last_error = NULL`, making it eligible for the next outbox poll.
- All three endpoints require the same cookie-based dashboard auth as every other `/api/*` route.
- New test file covers auth guard, both-list shape, empty state, and both retry mutations (asserting the exact captured SQL/params) — 7 new tests, full suite 254 passed / 3 skipped.

## Task Commits

Each task was committed atomically:

1. **Task 1: GET /api/alerts + retry endpoints** - `4d9bc25` (feat)
2. **Task 2: Tests for the alerts API** - `b37c207` (test)

**Plan metadata:** (this commit, docs)

## Files Created/Modified
- `app/routers/ui_api.py` - Added the Alerts API section (`GET /api/alerts`, two retry POSTs) between Products and Broadcast sections, matching the file's existing auth-guard/query/execute conventions.
- `tests/integration/test_alerts_api.py` - New integration test file (7 tests) covering auth, list shape (populated + empty), and both retry mutations via monkeypatched `query`/`execute`.

## Decisions Made
- Retry endpoints reset the existing row in place (UPDATE) rather than inserting a new one — consistent with the plan's explicit instruction and the codebase's existing mutation style; preserves `created_at` for audit.
- Documented (per the plan) that resetting `webhook_events.processed = FALSE` can re-run bot-command side effects if the original processing died partway through, since the `wamid` unique constraint only blocks duplicate inbound-message inserts, not duplicate command execution. This is a pre-existing, narrow gap — not introduced by this plan and explicitly out of scope per Phase 4's locked decisions.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- The backend API this plan built is ready for `04-06` to wire a dashboard UI on top of it (an "Alerts" tab/page rendering both lists with a retry button per row).
- No blockers introduced; full test suite remains green (254 passed, 3 skipped).

---
*Phase: 04-reliability-operations-completion*
*Completed: 2026-08-28*

## Self-Check: PASSED

- FOUND: app/routers/ui_api.py
- FOUND: tests/integration/test_alerts_api.py
- FOUND commit: 4d9bc25
- FOUND commit: b37c207
