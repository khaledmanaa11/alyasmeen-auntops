---
phase: 04-reliability-operations-completion
plan: 03
subsystem: infra
tags: [apscheduler, sqlalchemy, worker, job-store, testing, railway, supabase]

# Dependency graph
requires:
  - phase: 04-reliability-operations-completion
    provides: "app/worker.py's existing SQLAlchemyJobStore/MemoryJobStore wiring (pre-existing code, not built by this plan)"
provides:
  - "Automated proof that SQLAlchemyJobStore persists job scheduling state (next_run_time) across independent scheduler instances sharing one on-disk database"
  - "Control test ruling out an in-process-caching false positive for that persistence claim"
  - "DATABASE_URL documented in .env.example and CLAUDE.md: Session Pooler (not Direct connection), postgresql:// scheme (not postgres://)"
affects: ["04-07 (live DATABASE_URL Railway checkpoint depends on this documentation)"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Module-level (picklable) job callables required for SQLAlchemyJobStore — lambdas/closures cannot be pickled to a textual module:function reference"
    - "tmp_path-scoped sqlite files simulate a real Postgres-backed jobstore restart without live credentials"

key-files:
  created: [tests/integration/test_scheduler_persistence.py]
  modified: [.env.example, CLAUDE.md]

key-decisions:
  - "Used a module-level _noop_job function instead of the plan's literal lambda: None — SQLAlchemyJobStore pickles jobs via a textual module:function reference, which a lambda has no such reference for; this is also more representative of real jobs like send_monthly_report"
  - "New test file left unmarked with @pytest.mark.integration (matching the existing tests/integration/ convention, none of which use that marker) so it runs under the default `python -m pytest -q` filter, which excludes marker \"integration\" via pyproject.toml addopts — a marked test would have made the 'full suite stays green' verification trivially true without actually proving anything"

patterns-established: []

# Metrics
duration: 10min
completed: 2026-08-28
---

# Phase 4 Plan 3: Scheduler Persistence Proof Summary

**Automated test proves APScheduler's SQLAlchemyJobStore genuinely persists job scheduling state across a simulated worker restart, plus DATABASE_URL's exact required connection-string shape (Session Pooler, postgresql://) is now documented in .env.example and CLAUDE.md.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-08-28T~11:55Z
- **Completed:** 2026-08-28T12:05:43Z
- **Tasks:** 2
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments
- New integration test (`tests/integration/test_scheduler_persistence.py`) proves the exact SQLAlchemy jobstore code path `app/worker.py` uses (`SQLAlchemyJobStore(url=...)`) survives a process restart: a job added by one `BackgroundScheduler` instance is read back with an identical `next_run_time` by a second, independent instance pointed at the same on-disk sqlite store.
- Control test rules out a false positive: a scheduler pointed at a different, freshly-created empty sqlite file does NOT see the job — proving the persistence is genuinely coming from the shared store, not some in-process cache.
- `.env.example` and `CLAUDE.md` now document `DATABASE_URL`'s required shape (Supabase Session Pooler, port 5432, `postgresql://` scheme — not the IPv6-only Direct connection string, not the SQLAlchemy-2.0-rejected `postgres://` scheme) for whoever sets it in Railway.

## Task Commits

Each task was committed atomically:

1. **Task 1: Automated proof that SQLAlchemyJobStore persists across a restart** - `dc4bdf1` (test)
2. **Task 2: Document DATABASE_URL's required shape** - `201d606` (docs)

**Plan metadata:** _pending — see final commit below_

## Files Created/Modified
- `tests/integration/test_scheduler_persistence.py` - Two tests: persistence across a simulated restart, and isolation-per-database control case
- `.env.example` - New "Worker job-store persistence (APScheduler)" section documenting `DATABASE_URL`
- `CLAUDE.md` - `DATABASE_URL` row added to the Env Vars Reference table

## Decisions Made
- **Module-level `_noop_job` instead of a lambda**: the plan's literal instruction (`lambda: None`) fails at `scheduler.add_job()` — `SQLAlchemyJobStore.add_job()` pickles the job via a textual `module:function` reference, which a lambda/closure cannot provide (`ValueError: This Job cannot be serialized...`). A module-level function fixes this and is also a more faithful stand-in for the real scheduled jobs (`send_monthly_report`, etc.) than a lambda would have been.
- **No `@pytest.mark.integration` marker on the new test**: `pyproject.toml`'s `addopts = '-m "not integration"'` excludes that marker from the default `python -m pytest -q` run, and none of the existing files under `tests/integration/` use it either (directory name only, not a marker convention here). Marking the new test would have made the plan's "full suite stays green" verification pass trivially by skipping it — leaving it unmarked means it actually runs as part of the standard suite and its 2 assertions are real coverage.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Plan's literal `lambda: None` job callable does not work with SQLAlchemyJobStore**
- **Found during:** Task 1 (writing/running the persistence test)
- **Issue:** The plan specified `scheduler_a.add_job(lambda: None, "cron", ...)`. Running it raised `ValueError: This Job cannot be serialized since the reference to its callable (...) could not be determined` — `SQLAlchemyJobStore` requires a picklable `module:function` reference, which lambdas and closures cannot provide.
- **Fix:** Introduced a module-level `_noop_job()` function in the test file and used it as the scheduled callable in both tests instead of the lambda.
- **Files modified:** `tests/integration/test_scheduler_persistence.py`
- **Verification:** `python -m pytest tests/integration/test_scheduler_persistence.py -q` — both tests pass.
- **Committed in:** `dc4bdf1` (Task 1 commit)

**2. [Rule 3 - Blocking] Task commit accidentally staged unrelated pre-existing changes**
- **Found during:** Task 1 commit
- **Issue:** The working tree had pre-existing uncommitted modifications (`app/shared/gatekeeper.py`, `tests/unit/test_gatekeeper.py`, and others) from outside this plan's scope, already sitting in the git index before this session started. `git add tests/integration/test_scheduler_persistence.py` only staged the new file, but the commit unexpectedly also included the two already-staged gatekeeper files.
- **Fix:** `git reset --soft HEAD^` to undo the commit without losing any changes, `git restore --staged` on the two out-of-scope files to unstage them, then re-committed with only `tests/integration/test_scheduler_persistence.py` staged. The gatekeeper files remain as pre-existing uncommitted working-tree changes, untouched and out of this plan's scope.
- **Files modified:** none (commit history correction only)
- **Verification:** `git show --stat HEAD` confirmed the corrected commit contains exactly one file.
- **Committed in:** `dc4bdf1` (corrected)

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking)
**Impact on plan:** Both fixes were necessary to produce a working, correctly-scoped commit. No scope creep — the gatekeeper.py/test_gatekeeper.py/followup.py/monthly_report.py/test_followup.py changes already present in the working tree before this session are left untouched and uncommitted, as they belong to unrelated prior work.

## Issues Encountered
None beyond the deviations documented above.

## User Setup Required
None - no external service configuration required. (The live Railway `DATABASE_URL` setup step itself is a separate operator checkpoint in plan 04-07, per this plan's objective.)

## Next Phase Readiness
- Success Criterion 3 ("the worker's APScheduler job store is persistent... verified") now has a repeatable, automated, credential-free proof of the persistence mechanism.
- `DATABASE_URL`'s exact required shape is documented in both places (`.env.example`, `CLAUDE.md`) a deployer would look before setting it in Railway — ready for plan 04-07's live operator checkpoint.
- Full suite green: 256 passed, 3 skipped.

---
*Phase: 04-reliability-operations-completion*
*Completed: 2026-08-28*

## Self-Check: PASSED

- FOUND: tests/integration/test_scheduler_persistence.py
- FOUND: .env.example
- FOUND: CLAUDE.md
- FOUND commit: dc4bdf1 (test(04-03): prove SQLAlchemyJobStore persists jobs across a restart)
- FOUND commit: 201d606 (docs(04-03): document DATABASE_URL's required shape for job-store persistence)
