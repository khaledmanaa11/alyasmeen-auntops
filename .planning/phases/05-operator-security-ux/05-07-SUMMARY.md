---
phase: 05-operator-security-ux
plan: 07
subsystem: ui
tags: [alpinejs, jinja2, handoffs, audit-log, fastapi, dashboard]

# Dependency graph
requires:
  - phase: 05-operator-security-ux (05-04)
    provides: "app/static/js/csrf.js + the self-highlighting app/templates/_nav.html partial (New-Template Checklist) this plan's two new pages and nav entries follow"
  - phase: 05-operator-security-ux (05-05)
    provides: "app/services/handoff.py + app/services/audit.py + app/routers/operator_api.py's 5 endpoints (GET/POST /api/handoffs*, GET /api/audit) this plan's UI consumes directly, plus POST /dev/test_handoff for exercising it without Phase 3"
provides:
  - "app/templates/handoffs.html — active/resolved handoff lists, per-item WhatsApp link, expandable last-20-turn transcript, one-button أعد للبوت resolve wired to POST /api/handoffs/{id}/resolve"
  - "app/templates/audit.html — read-only operator action trail rendered as plain-Arabic sentences (describe(entry) switch covering all 18 OPERATOR_ACTIONS) with a raw-JSON details toggle and a client-side actor+sentence filter"
  - "app/templates/_nav.html — three new entries (محادثات with a live red badge polling GET /api/handoffs/count every 30s, السجل, حسابي) added to the single shared partial; no page template touched"
  - "app/routers/ui.py — GET /handoffs and GET /audit page routes, both behind the existing router-level require_operator_page guard"
  - "tests/integration/test_ui_pages.py — page-level auth coverage (200 signed-in + shared-nav markers, 303->[/login] signed-out) for /handoffs, /audit, /orders, /alerts"
affects: [05-10]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Nav badge as a plain global <script> function (pollHandoffBadge) defined by _nav.html, reused by handoffs.html after a resolve — a page-level Alpine app calling a nav-partial global function rather than duplicating the fetch/update logic"
    - "Client-side describe(entry) switch/map for audit-log sentences, with an explicit fallback to the raw action string for anything not yet mapped, so a future action added to OPERATOR_ACTIONS never renders a blank row"
    - "RTL-aware chat-bubble alignment via plain Tailwind justify-start/justify-end (no dir override needed — flexbox's flex-start/flex-end already resolve against the inherited dir=rtl)"

key-files:
  created:
    - app/templates/handoffs.html
    - app/templates/audit.html
    - tests/integration/test_ui_pages.py
  modified:
    - app/templates/_nav.html
    - app/routers/ui.py

key-decisions:
  - "حسابي (/account) link added to _nav.html per the plan even though this plan built no account-page logic itself — 05-09 already shipped GET /account in the prior wave; this plan only makes it reachable from the nav, matching 05-09 SUMMARY's own 'Next Phase Readiness' note that it was reachable only by direct URL until 05-07 landed"
  - "Verified the seed -> list -> transcript -> resolve -> 409-on-repeat -> badge-drops -> audit-row-appears round trip against the real, live Supabase schema via TestClient + app.dependency_overrides (same pattern 05-05 used) rather than a real browser login, since SUPABASE_ANON_KEY is still not configured locally (pre-existing, known gap owned by 05-10's rollout) — all seeded rows (handoffs/chat_history/sessions/customers/audit_logs) were deleted immediately after and reconfirmed absent by direct query"
  - "audit.html's describe() maps all 18 OPERATOR_ACTIONS entries (not just the 7 the plan spells out literally), so every action currently in the allowlist renders a real sentence today; the plan's fallback-to-raw-string path remains as the safety net for any future action added to the allowlist without a matching audit.html update"

patterns-established:
  - "Any future nav tab addition is a single-file change to app/templates/_nav.html only (confirmed again by this plan: three new tabs, zero page templates edited, verified via grep -c 'set active' app/templates/*.html == 0 everywhere)"

# Metrics
duration: ~25min
completed: 2026-08-28
---

# Phase 5 Plan 07: Handoffs Tab, Audit Trail Page, Shared Nav Badge Summary

**A محادثات nav tab with a live red badge polling `/api/handoffs/count`, a full handoffs page (active/resolved lists, expandable transcript, one-button `أعد للبوت` resolve) and a read-only `/audit` trail rendering all 18 operator actions as plain-Arabic sentences — both new pages and three new nav entries added without touching any existing page template.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-08-28 (session continuation, wave 6, parallel with 05-08 in the same working directory)
- **Completed:** 2026-08-28T20:32:17+03:00
- **Tasks:** 3/3 completed
- **Files modified:** 5 (3 created, 2 modified)

## Accomplishments
- `app/templates/_nav.html`: three new entries after the existing تنبيهات link — محادثات (`/handoffs`, icon `forum`, a `#handoffCount` badge styled `background:#ef4444` that polls `GET /api/handoffs/count` every `BADGE_POLL_MS = 30000` and once immediately, hidden when `active === 0`, wrapped in try/catch so a network hiccup never breaks the page it sits on), السجل (`/audit`, icon `history`), and حسابي (`/account`, icon `account_circle`, placed just before خروج — 05-09's account page was reachable only by direct URL until this link). Every new link reuses the partial's existing `_p == request.url.path` self-highlighting expression; no `{% set active = ... %}` variable was introduced and no page template was touched (`grep -c "set active" app/templates/*.html` returns 0 everywhere).
- `app/routers/ui.py`: `GET /handoffs` -> `handoffs.html` and `GET /audit` -> `audit.html`, both inheriting the router-level `require_operator_page` guard already applied to every route in this router — an unauthenticated request 303s to `/login` (verified by curl and by the new test file).
- `app/templates/handoffs.html` (265 lines): Alpine.js page (`handoffsApp()`) modeled on `alerts.html`'s structure. Two filter pills (نشطة default / محلولة, each showing a live count), one card per handoff with the customer's name as the bold headline (falls back to phone), the reason as an `#e6f3ee`/`#006948` tinted pill, a relative-time caption, a green وا واتساب `افتحي واتساب` link (`:href="item.wa_link"`), a شوفي المحادثة toggle that lazily `fetch`es `/api/handoffs/{id}` and renders the last 20 `chat_history` turns as RTL-aware chat bubbles (`justify-start`/`justify-end` — no `dir` override needed), and — for active handoffs only — a `#006948` أعد للبوت button. Resolving calls `POST /api/handoffs/{id}/resolve`; on success it moves the item into the resolved list locally, toasts `رجّعت المحادثة للبوت ✅`, and calls the nav's own `pollHandoffBadge()` to refresh the badge immediately rather than waiting for the next 30s tick; a `409` (already resolved by someone else) toasts a distinct message and reloads both lists from the server. Every DB-sourced value (`customer_name`, `reason`, transcript `content`) is bound via `x-text`, never `x-html`.
- `app/templates/audit.html` (202 lines): read-only Alpine.js page, a single `fetch('/api/audit')` on load, no mutations. `describe(entry)` is an explicit switch mapping all 18 `OPERATOR_ACTIONS` entries to a plain-Arabic sentence (e.g. `order_status_changed` -> `"غيّرت حالة الطلب #{id} إلى {to}"`, `broadcast_sent` -> `"أرسلت رسالة جماعية لـ {sent} زبونة"`), falling back to the raw action string for anything unmapped so a row is never blank. `iconFor(action)` picks a Material Symbols icon per action family (login/logout, order, product, broadcast, handoff, alert, mfa/session/password). A client-side text filter searches actor + rendered sentence; each row has a التفاصيل toggle revealing the raw `details` JSON in a `<pre>`. `x-text` everywhere.
- `tests/integration/test_ui_pages.py` (new, 2 tests): using the shared `client`/`operator_client` fixtures (no locally-declared `TestClient`) — `operator_client` gets 200 + shared-nav markers (`/handoffs`, `/audit`, `handoffCount`) on `/handoffs`, `/audit`, `/orders`, `/alerts`; plain `client` gets a `303` to `/login` on `/handoffs` and `/audit`. No DB mocking needed — these page handlers issue no DB calls themselves.
- **Additional live-DB verification beyond the plan's pytest-based `<verify>` blocks** (same reasoning and technique as 05-05's SUMMARY: `SUPABASE_ANON_KEY` is still not configured locally, so a real browser `/login` session cannot be minted in this sandbox): via `TestClient` + `app.dependency_overrides` bypassing only the `require_operator`/`require_operator_page` dependencies (never the database), seeded a real handoff through `POST /dev/test_handoff`, confirmed it appeared in `GET /api/handoffs?status=active` with the correct `customer_name`, confirmed its transcript had all 3 seeded turns, confirmed the badge count was `1`, resolved it (`200 {"ok": true}`), confirmed a repeat resolve returned `409 {"detail": "already resolved"}`, confirmed the badge dropped to `0`, and confirmed a `handoff_resolved` row appeared in `GET /api/audit` attributed to the test operator's email. All seeded rows (`handoffs`, `chat_history`, `sessions`, `customers`, `audit_logs`) were deleted immediately after and reconfirmed absent by a direct follow-up query — production left exactly as found.

## Task Commits

Each task was committed atomically:

1. **Task 1: Shared nav — handoffs tab with live badge, audit tab, account link** - `be16ea8` (feat)
2. **Task 2: handoffs.html — active/resolved lists, transcript, return-to-bot** - `6f2173a` (feat)
3. **Task 3: audit.html — operator action trail + page-auth tests** - `c26d0ff` (feat)

**Plan metadata:** (this commit, docs)

## Files Created/Modified
- `app/templates/_nav.html` — three new entries (محادثات + badge, السجل, حسابي) added after تنبيهات; badge-polling script at the bottom
- `app/routers/ui.py` — `GET /handoffs`, `GET /audit` page routes
- `app/templates/handoffs.html` — active/resolved handoff lists, transcript, resolve action (new)
- `app/templates/audit.html` — operator action trail, plain-Arabic sentences, details toggle (new)
- `tests/integration/test_ui_pages.py` — page-level auth coverage (new)

## Decisions Made
- `حسابي` was added to the nav even though this plan built no account-page code — 05-09 already shipped `/account` in the prior wave and explicitly noted it was "reachable only by direct URL until 05-07 adds the حسابي nav entry"; this plan closes that gap as instructed by its own task list.
- Used the same `TestClient` + `app.dependency_overrides` live-DB smoke-test technique 05-05 established, for the same reason (missing `SUPABASE_ANON_KEY` blocks a real login locally) — not a deviation, additional verification beyond the plan's own pytest-based `<verify>` blocks.
- `audit.html`'s `describe()` covers all 18 allowlist entries rather than only the 7 the plan spells out literally, so the page renders a real sentence for every action currently possible today; the plan's required fallback-to-raw-string path is preserved for future allowlist additions.

## Deviations from Plan

None — plan executed exactly as written. The live-database smoke test described above is additional verification beyond the plan's own `<verify>` blocks (all of which are pytest/grep/curl-based and passed as specified), not a deviation from any task's action or done criteria.

## Issues Encountered

None. A sibling agent (plan 05-08) executed concurrently in the same working directory (per the orchestrator's wave-6 parallelization), touching `app/templates/alerts.html`, `app/templates/orders.html`, and (at completion) `.planning/STATE.md`/`.planning/ROADMAP.md`. Every `git add` in this plan was scoped explicitly to this plan's own files (confirmed via `git status --short` and `git diff --cached --stat` before each commit); `.planning/STATE.md` was re-read immediately before this plan's own edit to it, after 05-08's docs commit had already landed.

## User Setup Required

None — no new external service configuration required by this plan. The pre-existing `SUPABASE_ANON_KEY` gap (blocks real dashboard login locally) remains tracked against 05-10's rollout, unchanged by this plan.

## Next Phase Readiness
- `_nav.html` now carries all seven tabs (الطلبات، الإحصائيات، المنتجات، رسائل، تنبيهات، محادثات، السجل) plus حسابي and خروج — every dashboard surface built across phase 5 is reachable from the nav.
- `/handoffs` and `/audit` are fully functional today via `POST /dev/test_handoff` (no Phase 3 dependency); real handoff triggers arrive only once Phase 3 executes.
- Wave 6 is complete (05-07 + 05-08 both have SUMMARYs and commits). Ready for the 05-10 checkpoint plan (human-gated: operator emails, `SUPABASE_ANON_KEY`, live rollout).
- No blockers. Full suite green (353 passed, 3 skipped) at this plan's final commit.

---
*Phase: 05-operator-security-ux*
*Completed: 2026-08-28*

## Self-Check: PASSED

All key files found on disk:
- FOUND: app/templates/handoffs.html
- FOUND: app/templates/audit.html
- FOUND: tests/integration/test_ui_pages.py
- FOUND: app/templates/_nav.html
- FOUND: app/routers/ui.py

All task commits found in git log:
- FOUND: be16ea8 (Task 1)
- FOUND: 6f2173a (Task 2)
- FOUND: c26d0ff (Task 3)
