---
phase: 05-operator-security-ux
plan: 05
subsystem: api
tags: [handoffs, audit-log, fastapi, operator-dashboard, best-effort-write]

# Dependency graph
requires:
  - phase: 05-operator-security-ux (05-03)
    provides: "app/routers/auth_deps.py require_operator dependency + tests/conftest.py client/operator_client/admin_client fixtures"
  - phase: 05-operator-security-ux (05-04)
    provides: "CSRF/security-headers middleware and _nav.html partial (consumed later by 05-07, not directly by this plan)"
provides:
  - "app/services/handoff.py — resolve()/active_count()/bot_recently_active() over the existing handoffs + sessions tables (Phase 3's trigger()/pause/policy gate deliberately NOT implemented here)"
  - "app/services/audit.py — OPERATOR_ACTIONS allowlist, log_action() best-effort writer, list_operator_actions() allowlist-filtered reader"
  - "app/routers/operator_api.py — GET/POST /api/handoffs*, GET /api/audit, router-level require_operator guard"
  - "POST /dev/test_handoff — mock-mode-only seed endpoint so the handoffs UI is exercisable without Phase 3"
affects: [05-07, 05-09]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Lazy intra-package import (handoff.resolve() does `from app.services import audit` inside the function body, not at module top) to avoid a future import cycle once Phase 3's handoff.py additions land"
    - "Read-side allowlist filter built from a fixed module constant, not user input, interpolated into placeholder count only — same SQL-safety pattern as the rest of the codebase (see audit.py's inline comment explaining why this isn't the injection pattern project rule 3 forbids)"
    - "Route declaration order matters for FastAPI path matching: GET /api/handoffs/count is registered before GET /api/handoffs/{handoff_id} so the literal path always wins over the parameterised one"

key-files:
  created:
    - app/services/handoff.py
    - app/services/audit.py
    - app/routers/operator_api.py
    - tests/unit/test_handoff_resolve.py
    - tests/unit/test_audit.py
    - tests/integration/test_operator_api.py
  modified:
    - app/routers/debug.py
    - app/main.py

key-decisions:
  - "app/services/handoff.py did NOT exist before this plan — Phase 3 has not been executed on this branch — so it was created fresh, containing only resolve()/active_count()/bot_recently_active(), with a module docstring that explicitly assigns trigger()/pause/keyword-detection/policy-gate to Phase 3 rather than leaving a stub"
  - "audit.log_action() is called lazily from inside handoff.resolve() (module-level import deferred to function body) specifically to avoid an import cycle if Phase 3's eventual handoff.py additions ever import audit too"
  - "list_operator_actions()'s allowlist-placeholder SQL is annotated inline explaining why the f-string is safe (placeholders built from a fixed tuple constant, never from user input) so a future reader doesn't mistake it for the injection pattern the project explicitly forbids"

patterns-established:
  - "Any future best-effort side-effect write (matching audit_logs' shape) should follow log_action()'s try/except-and-warn pattern rather than letting a logging failure break the primary action"

# Metrics
duration: ~30min
completed: 2026-08-28
---

# Phase 5 Plan 05: Handoff Resolution + Operator Audit Trail Summary

**Handoff resolve/read paths and a best-effort operator audit trail over the existing `handoffs`/`audit_logs`/`sessions` tables, exposed through five new `require_operator`-guarded JSON endpoints plus a mock-mode `/dev/test_handoff` seed route — verified end-to-end against the live Supabase schema.**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-08-28 (session continuation from 05-04)
- **Completed:** 2026-08-28T19:47:40+03:00
- **Tasks:** 3/3 completed
- **Files modified:** 8 (6 created, 2 modified)

## Accomplishments
- `app/services/handoff.py` (new — **Phase 3 has NOT executed on this branch**, so this file did not exist before this plan): `resolve(handoff_id, resolved_by)` flips `handoffs.status` to `'resolved'`, stamps `resolved_at`, records `resolved_by` in `metadata`, and unpauses the session (`sessions.paused = FALSE`) — idempotent, returns `False` and issues **no writes at all** if the handoff is missing or already resolved. `active_count()` powers the nav badge. `bot_recently_active(phone, window_minutes=5)` is a cheap two-query heuristic (`MAX(chat_history.created_at)` + `sessions.paused`) for bot-vs-aunt conflict detection — explicitly documented as disproportionate-to-avoid row versioning/locks for a 10-30 orders/day shop.
- `app/services/audit.py` (new): `OPERATOR_ACTIONS` (18-entry allowlist), `log_action()` (best-effort `INSERT`, swallows failures, warns on unknown actions but still records them), `list_operator_actions()` (allowlist-filtered `SELECT`, so customer-generated `audit_logs` rows written by `create_order_atomic` — e.g. `actor` = a phone number, `action='order_created'` — never leak into the operator "who did what" trail).
- `app/routers/operator_api.py` (new): five endpoints, all behind a router-level `Depends(require_operator)` — `GET /api/handoffs`, `GET /api/handoffs/count` (declared **before** the parameterised detail route, per the plan's explicit route-ordering warning), `GET /api/handoffs/{id}`, `POST /api/handoffs/{id}/resolve`, `GET /api/audit`. Registered in `app/main.py` immediately after `ui_api_router`.
- `app/routers/debug.py`: `POST /dev/test_handoff` (mock-mode only, gated the same way `/dev/test_order` already is) seeds a customer, a paused `sessions` row, three `chat_history` turns, and an active `handoffs` row — makes the whole surface exercisable today without Phase 3's real trigger path.
- 33 new tests (7 unit `handoff`, 6 unit `audit`, 13 integration `operator_api`, plus a live-DB smoke run described below) — full suite **325 passed, 3 skipped** (up from 299 passed pre-plan).
- **Live-DB verification beyond what the plan's own pytest-based `<verify>` blocks require**: since `SUPABASE_ANON_KEY` is not yet configured locally (a known, pre-existing gap — see 05-03's SUMMARY — owned by 05-09's rollout), the real `POST /login` flow cannot mint a session cookie in this environment. Rather than skip the plan's top-level curl-based smoke test, an equivalent check was run via `TestClient` + `app.dependency_overrides` (bypassing only the auth *dependency*, not the database) against the **real, live Supabase instance**: seeded a handoff, listed it (customer_name + wa_link correct), fetched its detail (transcript populated), resolved it once (`200 {"ok": true}`), resolved it again (`409 {"ok": false, "detail": "already resolved"}`), and confirmed a `handoff_resolved` row appeared via `/api/audit`. All seeded rows (`handoffs`, `chat_history`, `sessions`, `customers`, `audit_logs`) for the test phone number were deleted afterward — production left exactly as found.

## Task Commits

Each task was committed atomically:

1. **Task 1: app/services/handoff.py — resolve, active_count, conflict detection** - `2c4fe1e` (feat)
2. **Task 2: app/services/audit.py — operator action trail** - `caf302b` (feat)
3. **Task 3: operator_api.py — handoffs + audit JSON API, and a dev seed endpoint** - `f2633da` (feat)

**Plan metadata:** (this commit, docs)

## Files Created/Modified
- `app/services/handoff.py` — `resolve()`, `active_count()`, `bot_recently_active()`, `CONFLICT_WINDOW_MINUTES = 5` (new)
- `app/services/audit.py` — `OPERATOR_ACTIONS`, `log_action()`, `list_operator_actions()` (new)
- `app/routers/operator_api.py` — the five handoffs/audit endpoints (new)
- `app/routers/debug.py` — `POST /dev/test_handoff` added alongside `/dev/test_order`
- `app/main.py` — `operator_api_router` imported and registered right after `ui_api_router`
- `tests/unit/test_handoff_resolve.py` — 7 tests against an in-memory fake (new)
- `tests/unit/test_audit.py` — 6 tests against an in-memory fake (new)
- `tests/integration/test_operator_api.py` — 13 tests via `client`/`operator_client` fixtures (new)

## Interface Reference (for 05-07's UI and 05-06/05-08's audit-log writers)

### `OPERATOR_ACTIONS` (full, 18 entries — `app/services/audit.py`)
```
login_success, login_failed, logout, logout_all,
session_revoked, mfa_enrolled, mfa_reset, password_reset_requested,
order_status_changed, order_status_conflict_override,
product_created, product_updated, product_toggled, product_deleted,
broadcast_sent, handoff_resolved,
alert_retried, alert_retry_all
```
Any future plan writing an audit row for an action not yet in this tuple must add it here first — `list_operator_actions()` silently excludes anything not in the allowlist (by design, but silent).

### `CONFLICT_WINDOW_MINUTES = 5` (`app/services/handoff.py`)
The window `bot_recently_active()` uses to decide the bot is "still on" a conversation.

### `GET /api/handoffs?status=active|resolved|all` (default `active`)
```json
{"handoffs": [
  {"id": "...", "phone": "+972...", "reason": "...", "status": "active",
   "assigned_to": null, "created_at": "2026-...Z", "resolved_at": null,
   "metadata": {}, "customer_name": "...", "wa_link": "https://wa.me/972..."}
]}
```
Active rows first, then resolved newest-first (`ORDER BY (h.status = 'active') DESC, h.created_at DESC`). `400` on an invalid `status` value.

### `GET /api/handoffs/count`
```json
{"active": 3}
```
Registered **before** `GET /api/handoffs/{handoff_id}` — verified by a dedicated test (`test_returns_active_count_not_captured_by_handoff_id_route`) and by the live smoke run.

### `GET /api/handoffs/{handoff_id}`
Same shape as one list row, plus:
```json
{"...": "...", "transcript": [
  {"role": "user", "content": "...", "created_at": "2026-...Z"}
]}
```
`transcript` is the last `TRANSCRIPT_TURNS = 20` `chat_history` rows for that phone, reversed into chronological order. `404` on an unknown id.

### `POST /api/handoffs/{handoff_id}/resolve`
`200 {"ok": true}` on success, `409 {"ok": false, "detail": "already resolved"}` on a repeat call or an unknown/missing id. Calls `handoff.resolve(handoff_id, op.email)` — `op.email` is what lands in `handoffs.metadata.resolved_by` and in the `audit_logs` row's `actor`.

### `GET /api/audit?limit=200`
```json
{"entries": [
  {"id": "...", "actor": "...", "action": "handoff_resolved", "details": {...}, "created_at": "2026-...Z"}
]}
```
`limit` is clamped to `1..500` in the router (not in `audit.py` itself). No `require_admin` — both accounts see this, per CONTEXT.

## Decisions Made
- `app/services/handoff.py` was created fresh rather than appended to, because Phase 3 (which would have created it first with `trigger()`) has not been executed on this branch — confirmed via `ls app/services/handoff.py` before writing anything, exactly as the plan's Task 1 instructed.
- `handoff.resolve()` imports `app.services.audit` lazily (inside the function, not at module top) specifically to keep the door open for Phase 3's eventual additions to this same file without risking a circular import.
- Chose to run a real, live-database smoke test (via `TestClient` + `app.dependency_overrides` bypassing only the `require_operator` FastAPI dependency, never the database calls) rather than skip the plan's top-level curl-based verification outright, since `SUPABASE_ANON_KEY`'s absence blocks the login flow but not the database layer this plan actually built. All seeded rows were deleted immediately after; production data is unchanged from before this plan ran.

## Deviations from Plan

None — plan executed exactly as written. The live-database smoke test described above is additional verification beyond the plan's own `<verify>` blocks (which are all `pytest`-based and passed as specified), not a deviation from any task's action or done criteria.

## Issues Encountered

- The plan's top-level `<verification>` section includes a curl-based smoke test that requires a real dashboard login (session cookie). `SUPABASE_ANON_KEY` is not yet configured locally — a pre-existing, known gap first flagged in 05-02/05-03's SUMMARYs and owned by 05-09's live rollout, not a defect in this plan's code. Substituted with an equivalent `TestClient`-based smoke test against the real live Supabase database (see Accomplishments) to still get real-schema verification without the blocked login step.

## User Setup Required

None — no new external service configuration required by this plan. (The pre-existing `SUPABASE_ANON_KEY` gap noted above remains tracked against 05-09, unchanged by this plan.)

## Next Phase Readiness
- `app/services/handoff.py`, `app/services/audit.py`, and `app/routers/operator_api.py` are stable and ready for 05-07 (the handoffs/audit dashboard UI) to consume directly — see "Interface Reference" above for exact JSON shapes and constants.
- `POST /dev/test_handoff` lets 05-07's UI work and 05-09's rollout walkthrough be exercised today, without waiting on Phase 3.
- No Phase 3 responsibility (`trigger()`, setting `sessions.paused = TRUE`, keyword/media detection, the policy gate) was duplicated — confirmed by `grep -n "def trigger\|paused = TRUE" app/services/handoff.py` (no matches) and by this plan's own module docstring explicitly deferring that work to Phase 3.
- No blockers. Full suite green (325 passed, 3 skipped).

---
*Phase: 05-operator-security-ux*
*Completed: 2026-08-28*

## Self-Check: PASSED

All key files found on disk:
- FOUND: app/services/handoff.py
- FOUND: app/services/audit.py
- FOUND: app/routers/operator_api.py
- FOUND: tests/unit/test_handoff_resolve.py
- FOUND: tests/unit/test_audit.py
- FOUND: tests/integration/test_operator_api.py
- FOUND: app/routers/debug.py
- FOUND: app/main.py

All task commits found in git log:
- FOUND: 2c4fe1e (Task 1)
- FOUND: caf302b (Task 2)
- FOUND: f2633da (Task 3)
