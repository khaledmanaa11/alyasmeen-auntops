---
phase: 05-operator-security-ux
plan: 06
subsystem: api
tags: [audit-log, conflict-detection, fastapi, dashboard-api, outbox, whatsapp-alerts]

# Dependency graph
requires:
  - phase: 05-operator-security-ux (05-05)
    provides: "app/services/handoff.py (resolve/active_count/bot_recently_active), app/services/audit.py (OPERATOR_ACTIONS/log_action/list_operator_actions)"
provides:
  - "app/routers/ui_api.py — every mutating endpoint writes an attributed audit_logs row via audit.log_action(op.email, ...)"
  - "api_update_status's bot-vs-aunt conflict guard: 409 {conflict, reason, customer_name, phone, last_activity, requested_status, message} unless force=true; force pauses the bot session, opens an operator_takeover handoff, and logs order_status_conflict_override"
  - "GET /api/alerts reframed into {alerts:[...], counts:{total, customer_facing, internal}} — plain-Arabic action cards naming the customer, technical fields kept for a details toggle"
  - "POST /api/alerts/retry_all — bulk post-outage recovery, two UPDATE statements, alert_retry_all audit row"
  - "app/services/processor.py notify_permanent_failure() — proactive WhatsApp alerts to the aunt (customer-facing) and admin (everything) on permanent outbox-job/webhook-event failure, via the outbox, with a loop guard"
affects: [05-07, 05-08]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "_frame_alert(row, source) helper isolates all Arabic phrasing/severity logic in one place so the alerts template (05-08) stays purely presentational"
    - "Conflict guard runs BEFORE any mutation is applied (load order -> check bot_recently_active -> branch), so a 409 response is provably side-effect-free"
    - "audit.log_action/handoff.bot_recently_active are real, unmocked calls into live modules from every integration test's perspective — every test touching a mutating ui_api.py endpoint must monkeypatch them (see Deviations: this was NOT true before this plan and caused a real, now-cleaned-up, production data leak)"

key-files:
  created: []
  modified:
    - app/routers/ui_api.py
    - app/services/processor.py
    - tests/integration/test_orders_api.py
    - tests/integration/test_alerts_api.py
    - tests/integration/test_ui_api.py
    - tests/unit/test_processor.py

key-decisions:
  - "Split ui_api.py's alerts-section work into two commits along the plan's own task boundary (Task 1: audit+conflict-guard on all 8 mutating endpoints, including alert_retried on the two per-item retry endpoints; Task 2: the alerts payload rework + retry_all) by temporarily reverting Task 2's additions, committing Task 1, then reapplying Task 2 — despite both tasks touching the same file/section"
  - "Fixed tests/integration/test_ui_api.py even though it is not in this plan's files_modified: Task 1's audit wiring on product/broadcast endpoints is exercised by that file's existing tests, and leaving audit.log_action unmocked there caused 5 real rows to be written to the live production audit_logs table during this plan's own development (confirmed and deleted — see Deviations)"
  - "notify_permanent_failure's aunt-vs-admin branching keys off kind (whatsapp_message/whatsapp_buttons/pdf_invoice) OR source==webhook_event, matching _frame_alert's severity rules in ui_api.py so the proactive alert and the /alerts card agree on what counts as customer-facing"

patterns-established:
  - "Any new test file that exercises a mutating ui_api.py endpoint MUST monkeypatch app.services.audit.log_action (and, for api_update_status, app.services.handoff.bot_recently_active) — both are real live-DB calls unless patched, confirmed by an actual production data leak during this plan's execution"

# Metrics
duration: ~50min
completed: 2026-08-28
---

# Phase 5 Plan 06: Dashboard Audit Trail, Bot-vs-Aunt Conflict Guard, Reworked Alerts, Proactive Failure Alerts Summary

**Every dashboard mutation now writes an attributed `audit_logs` row, a status change colliding with a live bot conversation returns a 409 conflict payload instead of silently overwriting, `/api/alerts` speaks plain Arabic naming the customer instead of dumping job IDs, and a permanently-failed outbox job or dead-lettered webhook event proactively WhatsApps the aunt and/or admin.**

## Performance

- **Duration:** ~50 min (includes discovering and remediating a live production-data leak — see Deviations)
- **Started:** 2026-08-28 (session continuation from 05-05, wave 5)
- **Completed:** 2026-08-28T17:08:39Z
- **Tasks:** 3/3 completed
- **Files modified:** 6 (0 created, 6 modified)

## Accomplishments
- **Audit wiring (Task 1):** all 8 mutating `ui_api.py` endpoints (`api_update_status`, `api_create_product`, `api_update_product`, `api_toggle_product`, `api_delete_product`, `api_retry_webhook_event`, `api_retry_outbox_job`, `api_broadcast_send`) now take `op: Operator = Depends(require_operator)` and call `audit.log_action(op.email, "<action>", {...})` after every successful mutation, using the exact `OPERATOR_ACTIONS` names from 05-05.
- **Bot-vs-aunt conflict guard (Task 1):** `api_update_status` calls `handoff.bot_recently_active(phone)` immediately after loading the order and BEFORE any write. If the bot is active and the request lacks `force: true`, it returns `409 {"conflict": true, "reason": "bot_active", "customer_name", "phone", "last_activity", "requested_status", "message"}` — no order UPDATE is issued. With `force: true` it applies the status change AND pauses the session (`sessions.paused = TRUE`), opens an `operator_takeover` handoff row (visible in 05-05's handoffs tab with its "return to bot" undo button), and logs `order_status_conflict_override` in addition to the normal `order_status_changed` row.
- **Alerts rework (Task 2):** new `_frame_alert(row, source)` helper turns each dead-lettered `webhook_events` row / permanently-failed `outbox_jobs` row into `{id, source, phone, customer_name, severity, headline, what_happened, what_to_do, wa_link, kind, attempts, max_attempts, error, payload, created_at}`. `GET /api/alerts` now LEFT JOINs `customers` on phone and returns `{"alerts": [...], "counts": {"total", "customer_facing", "internal"}}`. An empty customer name falls back to the phone number in the Arabic sentence — never renders blank. New `POST /api/alerts/retry_all` reads both failure counts, then bulk-resets both tables in exactly two UPDATE statements (no per-row loop), audited as `alert_retry_all`.
- **Proactive failure alerts (Task 3):** `app/services/processor.py` gained `notify_permanent_failure(source, phone, kind, error)`, which queues (via `queue_text` — never a direct send) a plain-Arabic alert to `Config.AUNT_PHONE` for customer-facing failures (`whatsapp_message`/`whatsapp_buttons`/`pdf_invoice`, or any dead-lettered webhook event) and to `Config.ADMIN_PHONE` for everything, with a **mandatory loop guard**: if the failing job's own `phone` equals the aunt's or admin's phone, no alert is queued (prevents an alert-about-a-failed-alert infinite loop). `process_outbox_jobs` now selects and passes through `max_attempts`; `process_job` gained an optional 5th parameter (`max_attempts: int = 3`, backward-compatible) and calls `notify_permanent_failure` only on the job's last attempt (`attempts + 1 >= max_attempts`). `process_webhook_events`' dead-letter branch calls it unconditionally with `kind="inbound_message"`.
- **Production-data-leak discovery and remediation (see Deviations below).**

## Task Commits

Each task was committed atomically (Task 1 and Task 2 both required touching `ui_api.py`'s alerts section — see Decisions for how the split was kept clean):

1. **Task 1: Audit every mutation + bot-vs-aunt conflict guard on status change** - `7e7d229` (feat)
2. **Task 2: Alerts API rework — plain-Arabic action payload + retry-all** - `a8423db` (feat)
3. **Task 3: Proactive WhatsApp alerts on permanent failure** - `a32c237` (feat)

**Plan metadata:** (this commit, docs)

## Files Created/Modified
- `app/routers/ui_api.py` — audit wiring + conflict guard (Task 1), `_frame_alert`/reworked `GET /api/alerts`/`POST /api/alerts/retry_all` (Task 2)
- `app/services/processor.py` — `notify_permanent_failure`, `CUSTOMER_FACING_KINDS`, `process_job`'s new `max_attempts` param, both call sites wired (Task 3)
- `tests/integration/test_orders_api.py` — `mock_order` fixture now defaults `handoff.bot_recently_active` to None and spies on `audit.log_action`; 4 new tests (audit log assertion + 3 conflict-guard tests)
- `tests/integration/test_alerts_api.py` — fully rewritten for the new `{alerts, counts}` shape; autouse fixture no-ops `audit.log_action` for the whole file; new `TestRetryAll` class
- `tests/integration/test_ui_api.py` — **not in this plan's `files_modified`, edited anyway** (see Deviations): `mock_products_db` fixture and `test_send_broadcast_to_all` now no-op `audit.log_action`
- `tests/unit/test_processor.py` — 5 new tests in `TestPermanentFailureAlerts`

## Interface Reference (for 05-07/05-08's UI)

### 409 conflict payload (`POST /api/orders/{id}/status`, no `force`, bot active)
```json
{"conflict": true, "reason": "bot_active", "customer_name": "فاطمة", "phone": "972591234567",
 "last_activity": "2026-08-28T10:00:00+00:00", "requested_status": "ready",
 "message": "البوت يتحدث مع فاطمة الآن"}
```
Retry the same request with `{"status": "...", "force": true}` in the body to apply it anyway.

### `GET /api/alerts` item shape
```json
{"id": "...", "source": "webhook_event" | "outbox_job", "phone": "...", "customer_name": "فاطمة",
 "severity": "customer_facing" | "internal", "headline": "تحتاج انتباهك الآن",
 "what_happened": "رسالة لم تصل إلى فاطمة", "what_to_do": "تابعي المحادثة معها في واتساب",
 "wa_link": "https://wa.me/972...", "kind": "whatsapp_message", "attempts": 3, "max_attempts": 3,
 "error": "<raw>", "payload": {...}, "created_at": "<iso>"}
```
Top-level: `{"alerts": [...], "counts": {"total": n, "customer_facing": n, "internal": n}}`.

### `process_job` new signature
```python
def process_job(job_id: str, kind: str, phone: str, payload: dict, attempts: int, max_attempts: int = 3) -> None
```
`max_attempts` is optional/backward-compatible; `process_outbox_jobs()` always passes it explicitly now.

## Decisions Made
- Split the two tasks' overlapping edits to `ui_api.py`'s alerts section into clean, task-scoped commits by temporarily reverting Task 2's additions (`_frame_alert`, the rejoined `GET /api/alerts`, `POST /api/alerts/retry_all`, `import re`) after writing them, committing Task 1's state (which still includes Task 1's own op+audit wiring on the two per-item retry endpoints, per the plan's own action list), then reapplying Task 2's additions as a second commit.
- Fixed `tests/integration/test_ui_api.py` despite it not being declared in this plan's `files_modified` — Task 1's audit wiring on product/broadcast endpoints is directly exercised by that file's pre-existing tests, and leaving it unpatched caused real writes to the live production `audit_logs` table (see Deviations). This is judged in-scope under Rule 2 (missing critical / safety), not scope creep: it is a direct, unavoidable consequence of this plan's own required change.
- `notify_permanent_failure`'s customer-facing/internal split intentionally mirrors `_frame_alert`'s severity rules (same kind set, same `source == "webhook_event"` special case) so the proactive alert text and the `/alerts` card for the same failure never disagree about whether it's customer-facing.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] `tests/integration/test_ui_api.py` and the two per-item retry tests in `test_alerts_api.py` did not mock `audit.log_action`, causing real writes to the live production `audit_logs` table**
- **Found during:** Task 1, while running `tests/integration/test_ui_api.py` (not in this plan's `files_modified`, but directly exercises the product/broadcast endpoints this task changes) as a sanity check after adding audit wiring.
- **Issue:** `app/routers/ui_api.py` now calls `audit.log_action(op.email, ...)` on every product/broadcast mutation and on both per-item alert retries. `audit.log_action` reaches the real `app.services.audit` module's `execute()`, which is the real `app.db.database.execute()` unless explicitly monkeypatched. This sandbox has both real network egress AND real production Supabase credentials configured locally (`.env`), so an unmocked test run makes a genuine RPC call against the live database. `log_action`'s own try/except swallows any failure, so tests kept passing green — the writes succeeded silently. Confirmed via direct query: 5 real rows landed in the live `audit_logs` table (`product_created`/`product_updated`/`product_toggled`/`product_deleted`/`broadcast_sent`, actor `aunt@example.test`) from a single `pytest tests/integration/test_ui_api.py` run during this plan's own development.
- **Fix:** Deleted the 5 stray rows immediately (verified `SELECT` for that actor returns 0 rows afterward; also verified no real `products` rows were created, since `execute`/`execute_returning` for the `products` table itself were already mocked in that file's fixture — only the audit side-channel leaked). Added `monkeypatch.setattr(audit, "log_action", lambda *a, **k: None)` to `test_ui_api.py`'s `mock_products_db` fixture and to `test_send_broadcast_to_all`, and to the two per-item retry tests in `test_alerts_api.py` (later superseded by Task 2's autouse fixture in that file, which no-ops it for the whole file).
- **Files modified:** `tests/integration/test_ui_api.py` (out-of-scope for this plan's declared `files_modified`, but required — see Decisions), `tests/integration/test_alerts_api.py` (in-scope).
- **Verification:** Re-ran both files; 0 stray rows created; re-queried live `audit_logs`/`products` for the test fixture's exact fake names/actors — 0 matches. Full suite green (343 passed, 3 skipped) with no Supabase client construction warnings (confirming no real network calls occur in the mutation-path tests anymore).
- **Committed in:** `7e7d229` (Task 1 commit) and `a8423db` (Task 2 commit, for the alerts file's autouse fixture).

**2. [Rule 1 - Bug] `api_update_status`'s existing tests would 500 instead of 200 once the conflict guard called the real, unmocked `handoff.bot_recently_active`**
- **Found during:** Task 1, while adding the conflict guard.
- **Issue:** `handoff.bot_recently_active()` has no try/except — an unmocked call in tests would issue a real `SELECT` against the live database (same live-credentials risk as above) and, since it runs inside a FastAPI request handler, any transient failure would surface as a 500, breaking every existing `test_update_to_*` test in `test_orders_api.py`.
- **Fix:** `mock_order` fixture in `test_orders_api.py` now defaults `handoff.bot_recently_active` to `lambda phone, window_minutes=5: None` (no conflict), matching the "no recent bot activity still returns 200" regression requirement; individual conflict tests override it.
- **Files modified:** `tests/integration/test_orders_api.py` (in-scope).
- **Verification:** `pytest tests/integration/test_orders_api.py -q` — 14 passed, no real network calls (no Supabase client warning).
- **Committed in:** `7e7d229` (Task 1 commit).

---

**Total deviations:** 2 auto-fixed (1 missing-critical/safety, 1 bug), both directly caused by this plan's own required audit/conflict-guard wiring and both necessary to prevent tests from corrupting live production data or spuriously failing.
**Impact on plan:** No scope creep in intent — deviation 1 touched one file (`test_ui_api.py`) outside this plan's declared `files_modified`, but only to add test-isolation mocking made necessary by this plan's own Task 1 change; no behavior of that file's endpoints was altered.

## Issues Encountered

- This sandbox has real outbound network access AND real production Supabase credentials loaded from `.env` — a fact not previously exercised by any test file this plan owns before now touching product/broadcast/alert-retry endpoints. See Deviations #1. No production `orders`/`products`/`customers`/`handoffs`/`sessions` rows were affected — only `audit_logs`, and those 5 stray rows were deleted before this plan's tasks were committed.
- A sibling agent (plan 05-09) was executing concurrently in the same working directory during this plan's execution (per the orchestrator's wave-5 parallelization). Their in-progress, uncommitted changes to `app/routers/auth_routes.py`, `app/services/audit.py`, `app/services/auth.py`, `tests/conftest.py`, `tests/unit/test_audit.py` were visible in `git status` throughout but were never staged, committed, read, or relied upon by this plan's work — each `git add` call was scoped explicitly to this plan's own files, confirmed via `git diff --cached --stat` before every commit.

## User Setup Required

None — no external service configuration required by this plan.

## Next Phase Readiness
- `app/routers/ui_api.py` and `app/services/processor.py` are stable and ready for 05-07 (handoffs/audit UI) and 05-08 (alerts UI, order-status conflict UI) to consume — see "Interface Reference" above for the exact 409 payload shape and the `/api/alerts` item shape.
- Any future test file that exercises a mutating `ui_api.py` endpoint (or `api_update_status` specifically) MUST monkeypatch `app.services.audit.log_action` (and, for status changes, `app.services.handoff.bot_recently_active`) — this is now a load-bearing convention across the test suite, not optional cleanup (see patterns-established).
- No blockers. Full suite green (343 passed, 3 skipped) at this plan's final commit.

---
*Phase: 05-operator-security-ux*
*Completed: 2026-08-28*

## Self-Check: PASSED

All key files found on disk:
- FOUND: app/routers/ui_api.py
- FOUND: app/services/processor.py
- FOUND: tests/integration/test_orders_api.py
- FOUND: tests/integration/test_alerts_api.py
- FOUND: tests/integration/test_ui_api.py
- FOUND: tests/unit/test_processor.py

All task commits found in git log:
- FOUND: 7e7d229 (Task 1)
- FOUND: a8423db (Task 2)
- FOUND: a32c237 (Task 3)
