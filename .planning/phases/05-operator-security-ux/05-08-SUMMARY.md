---
phase: 05-operator-security-ux
plan: 08
subsystem: ui
tags: [alpinejs, jinja2, alerts-ux, conflict-dialog, arabic-rtl]

# Dependency graph
requires:
  - phase: 05-operator-security-ux (05-06)
    provides: "GET /api/alerts {alerts, counts} action-card payload; POST /api/alerts/retry_all; POST /api/orders/{id}/status 409 conflict payload + force:true override"
  - phase: 05-operator-security-ux (05-04)
    provides: "app/static/js/csrf.js window.fetch wrapper, app/templates/_nav.html shared nav partial, design system tokens"
provides:
  - "app/templates/alerts.html — severity-grouped (customer_facing/internal) plain-Arabic action cards consuming 05-06's payload, with collapsed technical-details toggle, per-item retry, confirmed retry-all"
  - "app/templates/orders.html — bot-vs-aunt conflict modal on POST /api/orders/{id}/status 409, pick-the-winner UI (take over with force:true vs leave the bot alone)"
affects: [05-10]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Alpine.js item-local x-data (`{ open: false }`) inside x-for for a per-card details-toggle, avoiding a parent-level open-id map"
    - "Vanilla-JS modal (orders.html, matches file's existing non-Alpine style) built via textContent assignment for any string containing user/customer data, never innerHTML concatenation — same stored-XSS-safe convention as the rest of the file"

key-files:
  created: []
  modified:
    - app/templates/alerts.html
    - app/templates/orders.html

key-decisions:
  - "Alerts detail-toggle icon rotation implemented via a dedicated `.details-icon.is-open { transform: rotate(180deg) }` CSS class bound with Alpine :class, instead of inline Tailwind arbitrary-rotate utility strings, for readability"
  - "retry-all's success toast count is read from the retry_all response's own {webhook_events, outbox_jobs} counts (matching the same WHERE criteria as the GET), not recomputed client-side, so the number can never drift from what the server actually reset"
  - "Conflict modal's title/body text is the plan's literal hardcoded Arabic copy, not the server's own `message` field from the 409 payload — the server's `message` is kept only for API consumers who don't have a bespoke UI (e.g. future clients), the dashboard renders richer, plan-specified copy instead"

patterns-established:
  - "Any HTML injected from an untrusted/dynamic string (customer_name, phone, etc.) into a non-Alpine page must use textContent/DOM property assignment, never string-templated innerHTML — orders.html's conflict modal follows the same convention as the rest of that file post-hardening-session"

# Metrics
duration: ~15min
completed: 2026-08-28
---

# Phase 5 Plan 08: Alerts UX Rework + Bot-vs-Aunt Conflict Dialog Summary

**`/alerts` now renders 05-06's action-card payload as two severity-grouped plain-Arabic sections (WhatsApp-first for customer-facing failures, retry-first for internal ones) with a collapsed technical-details toggle and confirmed retry-all; `/orders` now shows a two-choice modal naming the customer whenever a status change collides with a live bot conversation, instead of silently overwriting.**

## Performance

- **Duration:** ~15 min
- **Tasks:** 2/2 completed
- **Files modified:** 2 (0 created, 2 modified)

## Accomplishments
- `alerts.html` fully rewritten against 05-06's `{alerts, counts}` payload: `customerFacingAlerts`/`internalAlerts` Alpine getters split the flat `alerts` array by `severity`; customer-facing cards lead with a green "افتحي المحادثة" WhatsApp link (`:href="item.wa_link"`, `rel="noopener"`, new tab) plus a secondary outlined retry; internal cards lead with retry only. Every card's headline is `item.what_happened`, sub-line `item.what_to_do`, both rendered with `x-text` (never `x-html`).
- Technical detail (`kind`, `attempts`/`max_attempts`, raw `error`, `<pre>` of `payload`) sits behind a collapsed `تفاصيل تقنية` toggle with a rotating `expand_more` icon, per-card local Alpine state (`x-data="{ open: false }"` inside the `x-for`). The existing "قد يكرر هذا..." caveat now lives inside that details block instead of under every button.
- Header gained a `{{counts.total}} عنصر يحتاج مراجعة` summary line and a confirmed `"إعادة المحاولة للكل"` button (disabled when `counts.total === 0`) that POSTs `/api/alerts/retry_all`, reloads the list, and toasts the exact count of items reset.
- `orders.html`'s `updateStatus()` now branches on `res.status === 409`: instead of a generic failure toast it opens a new conflict modal (same card styling as the rest of the dashboard, `rgba(0,0,0,0.4)` backdrop) whose title/body are built via `textContent` (never `innerHTML` string concatenation) so `customer_name` can never be a stored-XSS vector. `"كمّلي أنتِ"` re-POSTs the same endpoint with `force: true`, then toasts the exact takeover copy the plan specified and reloads the orders list; `"اتركي البوت"` and a backdrop-click/`Escape` all just close the modal with no request sent. A footnote links to `/handoffs`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Rework alerts.html into action cards** - `ff01cdc` (feat)
2. **Task 2: Bot-vs-aunt conflict dialog on the orders page** - `c32464b` (feat)

**Plan metadata:** (this commit, docs)

## Files Created/Modified
- `app/templates/alerts.html` — severity-grouped Arabic action cards, details toggle, retry/retry-all
- `app/templates/orders.html` — 409-conflict modal in `updateStatus()`, `openConflictModal`/`closeConflictModal`/`takeOverConflict` helpers

## Decisions Made
See `key-decisions` in frontmatter — notably: retry-all's toast count comes from the server's own response counts (not recomputed client-side), and the conflict modal uses the plan's literal hardcoded copy rather than the server's `message` field (the server field remains for non-dashboard API consumers).

## Deviations from Plan

None - plan executed exactly as written. Both tasks matched the plan's exact payload shapes (verified directly against `app/routers/ui_api.py`'s `_frame_alert`/`api_alerts`/`api_retry_all_alerts`/`api_update_status` before writing any template code) and both `<verify>` commands passed unmodified.

## Issues Encountered

None. This plan was template-only (no Python changes), so the full test suite was expected to be unaffected — confirmed: 351 passed, 3 skipped, same as before this plan's commits.

A sibling agent was executing plan 05-07 concurrently in the same working directory (per the wave-6 parallelization). Their in-progress work (`app/templates/handoffs.html`, `app/templates/audit.html`, `app/templates/_nav.html`, `app/routers/ui.py`, `tests/integration/test_ui_pages.py`) was visible in `git status` throughout but was never staged, committed, read, or relied upon — every `git add` in this plan was scoped explicitly to `app/templates/alerts.html` and `app/templates/orders.html`.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `/alerts` and `/orders` are both stable, template-only changes on top of 05-06's already-shipped and tested API surface — no backend changes were needed or made.
- Manual/visual verification (per the plan's `<verification>` section: browser check of both severity groups with zero/one/many items, and that the conflict modal is keyboard-dismissible and silent when the bot is not active) was not run against a live browser in this session — recommend a quick manual pass before the 05-10 checkpoint plan's live rollout, though the automated `python -c` structural checks and the full green test suite give high confidence.
- No blockers. Ready for 05-10 (the human-gated checkpoint plan) once the remaining wave-6 sibling plan (05-07) also lands.

---
*Phase: 05-operator-security-ux*
*Completed: 2026-08-28*

## Self-Check: PASSED

All key files found on disk:
- FOUND: app/templates/alerts.html
- FOUND: app/templates/orders.html

All task commits found in git log:
- FOUND: ff01cdc (Task 1)
- FOUND: c32464b (Task 2)
