---
phase: 04-reliability-operations-completion
plan: 06
subsystem: ui
tags: [fastapi, jinja2, alpinejs, dashboard, alerts, outbox, webhook-events]

# Dependency graph
requires:
  - phase: 04-reliability-operations-completion
    provides: "GET /api/alerts + retry endpoints (plan 04-05) backing this page"
provides:
  - "GET /alerts — operator-facing dashboard page listing dead-lettered webhook_events and permanently-failed outbox_jobs, each one-click retryable"
  - "5th nav tab (تنبيهات) added consistently across all 5 dashboard templates"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "New dashboard pages follow the exact products.html structural template: Cairo + Material Symbols Outlined font links, Tailwind CDN, Alpine.js CDN, shared design tokens (#006948/#004d33/#e6f3ee/#f0f7f4/#e8f3ee), card radius 20px, loading/empty-state/toast Alpine patterns"
    - "Retry buttons optimistically remove the row from the local Alpine list on success rather than re-fetching the full list"

key-files:
  created: [app/templates/alerts.html]
  modified: [app/routers/ui.py, app/templates/orders.html, app/templates/dashboard.html, app/templates/products.html, app/templates/broadcast.html, tests/integration/test_ui_api.py]

key-decisions:
  - "Alerts rows rendered as full-width list cards (not a grid) since the data is text-dense (phone, trimmed error, attempts, timestamp) rather than image-led like products"
  - "Each retry button carries a small caption surfacing the partial-retry caveat documented in 04-05's SUMMARY, so the operator isn't surprised by a possible repeated side effect"

# Metrics
duration: 15min
completed: 2026-08-28
---

# Phase 4 Plan 06: Alerts Dashboard UI Summary

**New `/alerts` Jinja2+Alpine.js dashboard page consuming plan 04-05's `/api/alerts` API, with a 5th "تنبيهات" nav tab wired into all 5 existing templates, completing Success Criterion 4.**

## Performance

- **Duration:** 15 min
- **Started:** 2026-08-28T12:10:00Z (approx)
- **Completed:** 2026-08-28T12:25:01Z
- **Tasks:** 2
- **Files modified:** 7 (1 created, 6 modified)

## Accomplishments
- `GET /alerts` page route added to `ui.py`, identical auth-guard pattern to every other dashboard page (redirect to `/login` when unauthenticated).
- `app/templates/alerts.html` built on `products.html`'s exact structural template — same font/CDN head block, same design tokens, same loading/empty-state/toast Alpine.js patterns.
- Two sections: "رسائل واردة معلّقة" (dead-lettered `webhook_events` — phone, trimmed error, attempts, created_at) and "رسائل صادرة فشلت" (permanently-failed `outbox_jobs` — phone, kind, last_error, attempts/max_attempts, created_at).
- One-click retry button per row posts to `/api/alerts/webhook_events/{id}/retry` or `/api/alerts/outbox_jobs/{id}/retry`, removes the row from the local list and shows a toast on success.
- Each retry button carries a caption noting a retry may repeat some actions if the original message partially failed — surfaces the caveat documented in plan 04-05's SUMMARY.
- Combined empty state ("لا توجد رسائل معلّقة 🎉") shown only when both lists are empty.
- The new nav tab (Material Symbols `warning` icon + "تنبيهات") added after `/broadcast` and before `/logout` in all 5 templates — `nav-active` in `alerts.html` itself, `nav-link` in the other 4. `login.html` untouched (no navbar).
- Two new page-route tests (auth redirect + authenticated render), following the exact pattern of the existing `TestPageRoutes` tests.

## Task Commits

Each task was committed atomically:

1. **Task 1: Alerts page — route + template** - `ba326cb` (feat)
2. **Task 2: Page-route tests** - `b71072b` (test)

**Plan metadata:** (this commit, docs)

## Files Created/Modified
- `app/templates/alerts.html` - New Alpine.js dashboard page rendering both dead-letter lists with retry buttons, toast, loading and empty states.
- `app/routers/ui.py` - Added `GET /alerts` page route (auth-guarded, same pattern as `products_page`).
- `app/templates/orders.html`, `app/templates/dashboard.html`, `app/templates/products.html`, `app/templates/broadcast.html` - Added the تنبيهات nav-link to each navbar.
- `tests/integration/test_ui_api.py` - Added `test_alerts_page_redirects_to_login_unauthenticated` and `test_alerts_page_renders_when_authenticated` to `TestPageRoutes`.

## Decisions Made
- Rendered alerts as full-width list cards rather than a product-style grid, since the content (phone, error text, attempt counts, timestamps) is text-dense rather than image-led — the grid pattern from `products.html` doesn't fit this data shape, so only the shared design tokens/CSS classes/Alpine idioms were reused, not the grid layout itself.
- Retry mutates the local Alpine array in place (filter out the retried id) instead of re-fetching `/api/alerts`, avoiding an extra round trip while still reflecting the change instantly.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Success Criterion 4 (dashboard visibility + one-click retry for dead-lettered events/failed jobs) is now fully delivered end-to-end: backend (04-05) + UI (04-06).
- Full test suite green: 256 passed, 3 skipped (up from 254 passed / 3 skipped after 04-05, +2 for the new page-route tests).
- Ready for plan 04-07 (remaining operator checkpoints for Phase 4).

---
*Phase: 04-reliability-operations-completion*
*Completed: 2026-08-28*

## Self-Check: PASSED

- FOUND: app/templates/alerts.html
- FOUND commit: ba326cb
- FOUND commit: b71072b
