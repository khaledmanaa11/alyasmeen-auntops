---
phase: 05-operator-security-ux
plan: 09
subsystem: auth
tags: [totp, mfa-enrollment, sessions, pkce, password-reset, account-page, supabase-auth]

# Dependency graph
requires:
  - phase: 05-operator-security-ux (05-01)
    provides: "app/services/sessions.py — list/revoke/revoke_all_for_user session lifecycle this page exposes"
  - phase: 05-operator-security-ux (05-02)
    provides: "app/services/auth.py — enroll_totp/verify_enrollment/send_password_reset primitives"
  - phase: 05-operator-security-ux (05-03)
    provides: "auth_deps.py guards + auth_routes.py login/MFA flow these routes extend"
  - phase: 05-operator-security-ux (05-04)
    provides: "csrf.js + _nav.html new-template checklist both new templates follow"
  - phase: 05-operator-security-ux (05-05)
    provides: "audit.log_action + OPERATOR_ACTIONS allowlist the login/reset trail writes through"
provides:
  - "GET /account + app/templates/account.html — MFA enrollment card (QR + manual secret), my-sessions list with per-device revoke, logout-everywhere, admin cross-account session view"
  - "POST /account/mfa/enroll + /account/mfa/enroll/verify + GET /account/mfa/status — assisted TOTP enrollment; successful verify revokes every OTHER session via revoke_all_for_user"
  - "GET /api/account/sessions, POST /api/account/sessions/{id}/revoke, POST /api/account/logout-all — operator session self-management"
  - "GET /api/admin/sessions, POST /api/admin/sessions/{id}/revoke — admin-only (require_admin) cross-account view; non-admin gets 403"
  - "POST /login/reset-request + GET /login/reset + app/templates/reset_password.html — PKCE password-reset landing that sets the new password and revokes all sessions"
  - "New-device WhatsApp alert: first successful sign-in from an unknown device queues a plain-Arabic message to Config.ADMIN_PHONE only (durable outbox via processor.queue_text)"
affects: [05-07, 05-10]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Credential change (TOTP enrollment, password reset) always ends in sessions.revoke_all_for_user with the current session preserved only for enrollment — the CONTEXT-locked revoke-on-credential-change rule"
    - "PKCE reset flow: Supabase emails a ?code= link -> auth.exchange_code_for_session(code) -> auth.update_password(access, refresh, new) — no service_role involvement in the user-facing path"
    - "New-device alert fires ONLY when a trusted_devices row is newly created at MFA success, keyed off the `created` flag — no alert on re-challenge of a known device"

key-files:
  created:
    - app/templates/account.html
    - app/templates/reset_password.html
    - tests/integration/test_account.py
  modified:
    - app/routers/auth_routes.py
    - app/services/auth.py
    - app/services/audit.py
    - tests/conftest.py
    - tests/unit/test_audit.py

key-decisions:
  - "password_reset_completed added to OPERATOR_ACTIONS in audit.py (the one-line change this plan makes there) — per the 05-05/05-06 rule that any new audit row kind must be allowlisted first or list_operator_actions() silently drops it"
  - "auth.py gained exchange_code_for_session(code) and update_password(access, refresh, new) so the PKCE redemption stays inside the single identity module — auth_routes.py never touches the supabase client directly"
  - "tests/conftest.py autouse-patches app.services.audit.log_action for route tests: log_action is best-effort and swallows failures, so an unpatched call would not fail a test — it would silently write a real row to the LIVE production project (verified empirically during this plan; the stray row was cleaned up by hand). Same hazard class 05-06 hit and fixed in its own test files."

patterns-established:
  - "Both new templates follow 05-04's binding checklist: csrf.js in <head> right after the Tailwind CDN script; account.html includes _nav.html (no arguments), reset_password.html is a pre-auth page like login.html and carries no nav"

# Metrics
duration: ~45min (two agent sessions; the executor dropped twice on ECONNRESET after its final feature commit — orchestrator ran the final gate and wrote this summary)
completed: 2026-08-28
---

# Phase 5 Plan 09: Account Page — MFA Enrollment, Session Management, Password Reset Summary

**The حسابي page and its routes: assisted TOTP enrollment with QR + manual secret that revokes every other session on success, per-device session visibility/revocation and logout-everywhere, the admin's cross-account session view, a new-device WhatsApp alert to the admin only, and the PKCE password-reset landing page.**

## Performance

- **Duration:** ~45 min across two agent sessions (executor's connection dropped twice at the final gate; all feature work was already committed — the orchestrator re-ran the full suite and completed the docs)
- **Tasks:** 3/3 completed
- **Files modified:** 8 (3 created, 5 modified)

## Accomplishments
- `app/routers/auth_routes.py` grew from the 05-03 login core to the full account surface (16 routes total): `GET /account`, `POST /account/mfa/enroll`, `POST /account/mfa/enroll/verify`, `GET /account/mfa/status`, `GET /api/account/sessions`, `POST /api/account/sessions/{session_id}/revoke`, `POST /api/account/logout-all`, `GET /api/admin/sessions`, `POST /api/admin/sessions/{session_id}/revoke` (admin-only via `require_admin`; non-admin → 403), `POST /login/reset-request`, `GET /login/reset`.
- **Enrollment revokes everything else:** `POST /account/mfa/enroll/verify` calls `sessions.revoke_all_for_user(...)` keeping only the current session — the plan's key link, present at 3 call sites (`grep -c revoke_all_for_user` = 3, covering enrollment, logout-all, and password reset).
- **New-device alert:** at MFA success, when the `trusted_devices` insert reports `created=True` and `Config.ADMIN_PHONE` is set, a plain-Arabic message is queued to the admin **only** via `processor.queue_text` (durable outbox — a WhatsApp failure can never break login). Known devices re-challenging produce no alert.
- **PKCE password reset:** `POST /login/reset-request` sends the Supabase reset email; the emailed link lands on `GET /login/reset` → `app/templates/reset_password.html` (163 lines), which redeems the `?code=` via the new `auth.exchange_code_for_session()`, sets the new password via `auth.update_password()`, revokes all of the user's sessions, and audit-logs `password_reset_completed`.
- `app/templates/account.html` (395 lines): MFA card with amber "غير مفعّل" / green enrolled states, QR + manual-entry secret during enrollment, الأجهزة المتصلة session list (device, created, last-used, "هذا الجهاز" marker) with per-row revoke, logout-everywhere button, and the admin-only جلسات المشغّلين cross-account card. Fetches `/api/account/sessions` on load (plan's key link verified).
- 8 new integration tests in `tests/integration/test_account.py` (300 lines) covering enrollment flow, session list/revoke, logout-all, admin view + 403 for non-admin, and the reset landing; `tests/unit/test_audit.py` extended for the new allowlist entry. Full suite at completion: **351 passed, 3 skipped**.

## Task Commits

1. **Task 1: MFA enrollment routes, new-device admin alert, login audit trail** - `a8c5982` (feat)
2. **Task 2: Session management + PKCE password-reset routes** - `9aad12f` (feat)
3. **Task 3: account.html — MFA enrollment, sessions, admin session view** - `21ad84f` (feat)

**Plan metadata:** (this commit, docs)

## Deviations from Plan

- **Executor connection loss (process, not code):** the executing agent was terminated twice by `ECONNRESET` after its last feature commit (`21ad84f`), before the final gate/SUMMARY. The orchestrator verified the working tree was clean, re-ran the full suite (351 passed / 3 skipped), verified every plan must-have (key-link greps, template min-lines, route inventory, csrf.js checklist) and wrote this SUMMARY. No code deviation.
- **[Rule 2] `tests/conftest.py` and `tests/unit/test_audit.py` touched beyond the declared `files_modified` list:** conftest gained an autouse patch of `app.services.audit.log_action` after this plan's route tests demonstrated the same live-production-write hazard 05-06 found — `log_action` is best-effort, so an unpatched call silently INSERTs into the live `audit_logs` (one real row was written and hand-deleted during this plan). Test-isolation fix only; no endpoint behavior changed.

## Issues Encountered
- The live-DB hazard above is now a **standing convention** (see STATE.md): every test touching a route that audit-logs must run under the conftest autouse patch; a structural pytest guard against production `SUPABASE_URL` has been proposed as a follow-up task.

## User Setup Required
None beyond what 05-10 already schedules: `SUPABASE_ANON_KEY`, `ADMIN_PHONE`, `DASHBOARD_BASE_URL` must be set (locally + both Railway services) before the reset-email and new-device-alert paths work live.

## Next Phase Readiness
- `/account` is fully functional but reachable only by direct URL until 05-07 adds the حسابي nav entry to `_nav.html`.
- 05-10 (live rollout) can now enroll the aunt: every primitive it walks through (enrollment, revoke-on-enroll, remember-device, admin session view, reset page) exists and is tested.

---
*Phase: 05-operator-security-ux*
*Completed: 2026-08-28*

## Self-Check: PASSED

All key files found on disk:
- FOUND: app/templates/account.html (395 lines ≥ 200)
- FOUND: app/templates/reset_password.html (163 lines ≥ 60)
- FOUND: tests/integration/test_account.py

All task commits found in git log:
- FOUND: a8c5982 (Task 1)
- FOUND: 9aad12f (Task 2)
- FOUND: 21ad84f (Task 3)

Must-have key links verified by grep:
- `revoke_all_for_user` in auth_routes.py (3 occurrences)
- `ADMIN_PHONE` new-device alert in auth_routes.py (guarded by `created` flag)
- `api/account/sessions` fetched by account.html
- `mfa/enroll` routes present
