---
phase: 04-reliability-operations-completion
plan: 01
subsystem: reliability
tags: [outbox, whatsapp, pdf-invoice, followup, monthly-report, dashboard-api]

# Dependency graph
requires:
  - phase: 03 (Agent Dependability & Safety, pre-Phase-4 hardening)
    provides: "outbox_jobs table + process_outbox_jobs() poller + queue_text/queue_buttons already wired as the single send path for the bot's own message pipeline (processor.py's handle_message())"
provides:
  - "queue_pdf_invoice() helper + pdf_invoice outbox job kind in processor.py, regenerating the invoice fresh from order_id at send time"
  - "followup.py and monthly_report.py enqueue via queue_text() instead of calling the WhatsApp sender directly"
  - "ui_api.py's order-status endpoint (ready/delivered/done) enqueues every customer-facing send instead of sending/generating inline in the HTTP request"
affects: [04-04 (retry_queue.py/retry_actions.py deletion), 04-reliability-operations-completion (criterion 1: no dead code claiming to run)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Outbox job payload stores the minimal reference (order_id) needed to regenerate a document/message fresh at send time, not the rendered artifact itself — a retried job always reflects current DB state."
    - "DB-insert-only queue functions (queue_text/queue_buttons/queue_pdf_invoice) are not wrapped in try/except at call sites that used to swallow send failures — a failure here is a real DB problem (already covered by database.py's own retry/circuit-breaker) and should surface as an error, not vanish silently."

key-files:
  created: []
  modified:
    - app/services/processor.py
    - app/services/followup.py
    - app/services/monthly_report.py
    - app/routers/ui_api.py
    - tests/unit/test_processor.py
    - tests/unit/test_followup.py
    - tests/unit/test_monthly_report.py
    - tests/integration/test_orders_api.py

key-decisions:
  - "Broadcast endpoint's send_text (app/routers/ui_api.py's api_broadcast_send) intentionally left un-migrated — out of this task's explicit scope, and its sent/failed synchronous-count contract doesn't map onto the outbox's fire-and-forget-then-poll model without a separate design decision (deferred, not part of Phase 4 decision 1's retry_queue.py replacement)."
  - "retry_actions.py and its execute_action('pdf_invoice', ...) branch, and tests/unit/test_retry_actions_pdf.py, were NOT deleted here — per plan 04-01's explicit instruction, that cleanup is plan 04-04's job, after this replacement exists and is tested."

patterns-established:
  - "New outbox job kind: add the enqueue helper next to queue_text/queue_buttons in processor.py, then a matching elif branch in process_job(), porting body logic without deleting the old call site until a later cleanup plan."

# Metrics
duration: 20min
completed: 2026-08-28
---

# Phase 4 Plan 01: Outbox migration for follow-ups, monthly report, and order-status sends Summary

**Follow-up messages, the monthly report, and the dashboard's ready/delivered/done order-status sends (including PDF invoice generation) now enqueue into `outbox_jobs` instead of calling the WhatsApp API inline — closing the last three direct-send call sites `retry_queue.py` used to catch failures for.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-08-28T11:50:00Z (approx.)
- **Completed:** 2026-08-28T12:09:00Z
- **Tasks:** 3
- **Files modified:** 8

## Accomplishments
- `processor.py` gained a `pdf_invoice` outbox job kind: `queue_pdf_invoice(phone, order_id)` enqueues just the order reference, and `process_job()`'s new `elif kind == "pdf_invoice":` branch regenerates the PDF fresh from current order/order_lines data and sends it via `send_document_bytes` — so a retried job always reflects up-to-date order data, never stale cached bytes.
- `followup.py` and `monthly_report.py` no longer import/branch on `Config.USE_MOCK_WHATSAPP` themselves — that decision now lives entirely in the outbox poller (`processor.py`'s conditional sender import). Both now call `queue_text()`.
- `ui_api.py`'s `api_update_status()` (`ready`/`delivered`/`done`) enqueues every customer-facing send via `queue_text`/`queue_pdf_invoice` instead of generating/sending inline in the request handler. The `try/except: logger.warning(...)` swallow around each send was deliberately removed — a `queue_text`/`queue_pdf_invoice` failure is now a real DB write failure (already covered by `database.py`'s retry/circuit-breaker), so it surfaces as a 500 instead of vanishing silently.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add the pdf_invoice outbox job kind to processor.py** - `69f6ccd` (feat)
2. **Task 2: Migrate followup.py and monthly_report.py to queue_text** - `0775654` (feat)
3. **Task 3: Migrate ui_api.py's status-update endpoint to the outbox** - `228c57f` (feat)
4. **Fix-up: remove unused Config import from followup.py** - `0e2a0d1` (fix — see Deviations)

_Note: commits 69f6ccd and 0775654 were briefly bundled with an unrelated concurrent plan's (04-02) changes to `ai_service.py`/`test_ai_service.py` due to parallel-wave execution writing to the same working tree; this was caught immediately via `git diff --cached --stat` review before the second commit and corrected with `git reset HEAD~1` + a clean re-stage. No unrelated files ended up in this plan's final commit history — see Deviations._

## Files Created/Modified
- `app/services/processor.py` — `queue_pdf_invoice()` helper + `pdf_invoice` job kind in `process_job()`; imports `generate_invoice_pdf` and `send_document_bytes` (mock/real, same pattern as `send_text`/`send_buttons`)
- `app/services/followup.py` — `send_followups()` now calls `queue_text()`; removed the mock/real sender conditional import (and its now-dangling `Config` import)
- `app/services/monthly_report.py` — `send_monthly_report()` now calls `queue_text()`; removed the mock/real sender conditional import
- `app/routers/ui_api.py` — `api_update_status()`'s three branches (`ready`/`delivered`/`done`) enqueue via `queue_text`/`queue_pdf_invoice`; removed the now-unused `from datetime import date` and the inline `send_text`/`generate_invoice_pdf`/`send_document_bytes` imports
- `tests/unit/test_processor.py` — new `TestPdfInvoiceJobKind` class (2 tests) covering the new job kind, ported from `test_retry_actions_pdf.py`
- `tests/unit/test_followup.py` / `tests/unit/test_monthly_report.py` — monkeypatch targets renamed `send_text` → `queue_text`; behavioral assertions unchanged
- `tests/integration/test_orders_api.py` — `mock_order` fixture now patches `execute` on both `ui_api` and `processor` (queue functions bind to `processor`'s own `execute` reference) and exposes `execute_calls`; `test_update_to_ready_succeeds`/`test_update_to_delivered_succeeds` rewritten to assert on outbox inserts instead of a `send_text` monkeypatch; new `test_update_to_done_succeeds` asserts both a `whatsapp_message` and a `pdf_invoice` job (with `{"order_id": 42}` payload) are queued

## Decisions Made
- Broadcast's `send_text` (`api_broadcast_send`) was NOT migrated — out of this task's scope (not listed in must_haves/task instructions), and its synchronous sent/failed count contract is architecturally incompatible with the outbox's async fire-and-poll model without a separate design decision.
- `retry_actions.py` (and its `pdf_invoice` action, and `test_retry_actions_pdf.py`) were left in place — deletion is explicitly plan 04-04's job, after this replacement is proven out.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed unused `Config` import from followup.py**
- **Found during:** Task 2 (post-task cleanup, before final full-suite run)
- **Issue:** After removing the `if Config.USE_MOCK_WHATSAPP: ... else: ...` conditional sender import, `Config` had no remaining references in `followup.py` — a dangling unused import.
- **Fix:** Removed `from app.services.config import Config` from `followup.py`.
- **Files modified:** `app/services/followup.py`
- **Verification:** `python -m pytest tests/unit/test_followup.py -q` — 5 passed; full suite re-run green (259 passed, 3 skipped).
- **Committed in:** `0e2a0d1`

**2. [Process — not a code deviation] Concurrent parallel-wave commit contamination, corrected before pushing**
- **Found during:** Task 2's commit step
- **Issue:** This repo has `parallelization: true` in config.json — plans 04-02 and 04-03 were being executed by concurrent agents against the same working tree while this plan ran. A `git add <4 explicit paths>` followed by `git commit` unexpectedly included two files (`app/services/ai_service.py`, `tests/unit/test_ai_service.py`) that belonged to the concurrent 04-02 gatekeeper-wiring plan, apparently staged by that other process between my `git status` check and `git commit`.
- **Fix:** Caught via `git show --stat HEAD` immediately after commit; ran `git reset HEAD~1` (mixed reset — unstages, keeps working tree), verified my own diff was untouched with `git diff app/services/followup.py app/services/monthly_report.py`, re-staged only the 4 intended files, verified with `git diff --cached --stat`, and recommitted.
- **Files affected:** None of this plan's tracked files — the correction only removed `app/services/ai_service.py`/`tests/unit/test_ai_service.py` from this plan's commit; those files' actual changes were left untouched in the working tree for the 04-02 executor to commit itself.
- **Verification:** `git show --stat` on the corrected commit `0775654` confirms exactly 4 files.
- **Committed in:** `0775654` (corrected)

---

**Total deviations:** 1 code auto-fix (unused import), 1 process correction (no code impact).
**Impact on plan:** Minimal — the unused-import fix is a direct, necessary side effect of task 2's own change. The commit-contamination correction has zero effect on shipped code; it only ensured plan boundaries stayed clean in git history for accurate per-plan attribution during concurrent wave execution.

## Issues Encountered
None beyond the process note above (Deviation 2), which was resolved without any impact on test results or shipped behavior.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `retry_queue.py`/`retry_actions.py` are now fully redundant for every call site they used to cover (bot pipeline sends were already on the outbox pre-Phase-4; follow-ups, monthly report, and dashboard order-status sends are now migrated too) — plan 04-04 can delete both files plus `test_retry_actions_pdf.py` and drop their APScheduler registration in `main.py` with confidence that no functionality is lost.
- Full suite green: 259 passed, 3 skipped (up from a 252-passing baseline at plan start; the delta includes this plan's 4 new/rewritten tests plus tests added concurrently by plans 04-02/04-03 in the same wave).
- Broadcast's direct `send_text` call remains as the one deliberately-out-of-scope direct-send call site in the dashboard router; flag for a future phase/decision if it needs outbox coverage too.

---
*Phase: 04-reliability-operations-completion*
*Completed: 2026-08-28*

## Self-Check: PASSED

All 8 modified files + this SUMMARY.md confirmed present on disk. All 4 commit hashes
(69f6ccd, 0775654, 228c57f, 0e2a0d1) confirmed present in git history.
