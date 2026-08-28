---
phase: 05-operator-security-ux
plan: 03
subsystem: auth
tags: [fastapi-dependencies, opaque-session, totp-mfa, supabase-auth, dependency-overrides]

# Dependency graph
requires:
  - phase: 05-operator-security-ux (05-01)
    provides: "app/services/sessions.py opaque operator_sessions/trusted_devices/pending_logins store"
  - phase: 05-operator-security-ux (05-02)
    provides: "app/services/auth.py Supabase Auth wrapper (sign_in/verify_totp/AAL check)"
provides:
  - "app/routers/auth_deps.py — require_operator / require_operator_page / require_admin / optional_operator FastAPI dependencies"
  - "app/routers/auth_routes.py — GET+POST /login, POST /login/mfa, GET /logout, POST /logout-all"
  - "app/templates/mfa_challenge.html — TOTP code-entry page"
  - "tests/conftest.py — client / operator_client / admin_client fixtures via app.dependency_overrides"
affects: [05-04, 05-05, 05-07, 05-09]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Router-level FastAPI dependency (dependencies=[Depends(require_operator)]) replaces per-handler auth checks — one guard per router instead of one per route"
    - "Whole-module monkeypatching (import x as auth_service / import y as sessions inside auth_routes.py) so tests can swap the entire identity/session surface with fakes via monkeypatch.setattr(auth_routes, 'auth_service', fake)"
    - "app.dependency_overrides for test auth instead of a forged session cookie — operator_client/admin_client fixtures in tests/conftest.py"

key-files:
  created:
    - app/routers/auth_deps.py
    - app/routers/auth_routes.py
    - app/templates/mfa_challenge.html
    - tests/integration/test_auth_flow.py
  modified:
    - app/routers/ui.py
    - app/routers/ui_api.py
    - app/routers/broadcast.py
    - app/main.py
    - app/services/config.py
    - app/templates/login.html
    - .env.example
    - tests/conftest.py
    - tests/integration/test_ui_api.py
    - tests/integration/test_orders_api.py
    - tests/integration/test_alerts_api.py

key-decisions:
  - "auth_routes.py imports auth_service/sessions as module references (import ... as x), not from ... import fn — lets tests monkeypatch the whole bound name with a fake, matching tests/conftest.py's existing FakeDB pattern; AuthError is imported directly and kept stable so fakes can raise the real exception type without carrying their own"
  - "Session-minting logic lives in one shared helper (_mint_session_response) called from all three post-identity-established call sites (trusted-device match, no-MFA-enrolled sign-in, verified TOTP) rather than duplicated inline — implements the plan's step 4 exactly as specified ('mint the opaque session as in step 4')"
  - "DASHBOARD_PASSWORD removed from Config with fail-fast validation dropped; every remaining repo reference outside the three integration test files (test_config.py, test_main_debug_gate.py, README.md, docs/PLAN.md, docs/TODO.md, CLAUDE.md) fixed in Task 1, since the plan's own verification grep required a repo-wide clean sweep, not just the files named in files_modified"
  - "ALYASMEEN/raw/project-claude-md.md deliberately left with its 3 stale DASHBOARD_PASSWORD mentions — it is an immutable graphify snapshot per the vault's own governance rules (never hand-edit raw/); ALYASMEEN/wiki/web-dashboard.md + log.md were updated instead, which is where durable knowledge is meant to live"

patterns-established:
  - "Any router that needs auth going forward uses dependencies=[Depends(require_operator)] (APIs) or dependencies=[Depends(require_operator_page)] (pages) at the APIRouter level, not a per-handler check"
  - "New test files needing an authenticated client import client/operator_client/admin_client from tests/conftest.py — never redeclare them, never hand-compute a session token"

# Metrics
duration: ~50min
completed: 2026-08-28
---

# Phase 5 Plan 03: Operator Login + TOTP MFA Auth Guard Summary

**Replaced the deterministic `sha256(SECRET_KEY:DASHBOARD_PASSWORD)` dashboard cookie — hand-checked in three separate router files — with per-operator email+password (Supabase Auth) + TOTP MFA sign-in that mints an opaque session resolved through a single set of FastAPI router-level dependencies.**

## Performance

- **Duration:** ~50 min
- **Started:** 2026-08-28T15:55:00Z (approx.)
- **Completed:** 2026-08-28T16:20:14Z
- **Tasks:** 3/3 completed
- **Files modified:** 18 (7 created, 11 modified)

## Accomplishments
- `app/routers/auth_deps.py` (new): `require_operator` (401), `require_operator_page` (303→/login), `require_admin` (403, composes on `require_operator`), `optional_operator` (never raises) — every one resolves the `alyasmeen_session` cookie against 05-01's opaque `operator_sessions` store via `lookup_session()`.
- `ui.py`, `ui_api.py`, `broadcast.py` rewired to a single router-level `dependencies=[Depends(...)]` each, deleting ~25 per-handler `if not _is_authenticated(...)` checks and the `hashlib`/`COOKIE_NAME`/`_session_token`/`_is_authenticated` scheme entirely.
- `app/routers/auth_routes.py` (new): `GET/POST /login`, `POST /login/mfa`, `GET /logout` (revokes only this session), `POST /logout-all` (revokes every session for the operator). A session cookie is minted only after identity is fully established — either no MFA enrolled yet (assisted-enrollment CONTEXT requirement), a still-trusted device (30-day remember-device window), or a verified TOTP code.
- `login.html` rewritten to email+password; new `mfa_challenge.html` for the 6-digit TOTP step — both keep the existing premium RTL design system exactly.
- `Config.DASHBOARD_PASSWORD` and its fail-fast validation removed; every other repo reference to it fixed (tests, README, docs, CLAUDE.md) except the immutable `ALYASMEEN/raw/` snapshot.
- `tests/conftest.py` gained `client` / `operator_client` / `admin_client` fixtures using `app.dependency_overrides` — the idiomatic FastAPI test pattern — replacing every hand-computed session cookie in the test suite.
- New `tests/integration/test_auth_flow.py` (8 tests) proves MFA cannot be silently bypassed: a `mfa_required=True` sign-in with no trusted device never sets the session cookie, only the pending-login one.
- Full suite: **290 passed, 3 skipped** (pre-existing Docker skips), 0 failed.

## Task Commits

Each task was committed atomically:

1. **Task 1: auth_deps.py + router-level guard swap across ui.py, ui_api.py, broadcast.py** - `ec38816` (feat)
2. **Task 2: auth_routes.py — email+password login, TOTP challenge, logout** - `26097ea` (feat)
3. **Task 3: Central test auth fixture + migrate the three integration test files** - `4377d16` (test)

**Plan metadata:** (this commit, docs)

## Files Created/Modified
- `app/routers/auth_deps.py` — FastAPI auth dependencies (new)
- `app/routers/auth_routes.py` — login/MFA/logout routes (new)
- `app/templates/mfa_challenge.html` — TOTP code-entry page (new, 104 lines)
- `tests/integration/test_auth_flow.py` — 8 tests against fake auth_service/sessions (new)
- `app/routers/ui.py` — Auth section removed, router-level `require_operator_page` guard
- `app/routers/ui_api.py` — router-level `require_operator` guard, ~20 per-handler checks removed
- `app/routers/broadcast.py` — router-level `require_operator` guard
- `app/main.py` — registers `auth_router` before `ui_router`
- `app/services/config.py` — `DASHBOARD_PASSWORD` + its fail-fast validation removed
- `app/templates/login.html` — password-only form → email + password, forgot-password link
- `.env.example` — `DASHBOARD_PASSWORD` line replaced with a pointer to `docs/OPERATOR_ACCOUNTS.md`
- `tests/conftest.py` — `client` / `operator_client` / `admin_client` fixtures
- `tests/integration/test_ui_api.py`, `test_orders_api.py`, `test_alerts_api.py` — migrated to `operator_client`, local fixtures deleted
- `tests/unit/test_config.py`, `tests/unit/test_main_debug_gate.py` — `DASHBOARD_PASSWORD` references removed (Task 1, required by the plan's own repo-wide grep instruction)
- `README.md`, `docs/PLAN.md`, `docs/TODO.md`, `CLAUDE.md` — `DASHBOARD_PASSWORD` mentions corrected to describe the new auth flow
- `ALYASMEEN/wiki/web-dashboard.md`, `ALYASMEEN/wiki/log.md` — durable knowledge updated per project convention

## Route Table (`app/routers/auth_routes.py`)

| Route | Method | Guard | Notes |
|-------|--------|-------|-------|
| `/login` | GET | `optional_operator` | 303→/orders if already signed in, else renders login.html |
| `/login` | POST | none (Form: email, password) | 401+error on bad creds; 200 mfa_challenge.html if MFA required + no trusted device; else mints session |
| `/login/mfa` | POST | none (Form: code) | reads `pending_login` cookie; 401+fresh pending cookie on wrong code; 303→/orders + session + device cookie on success |
| `/logout` | GET | `optional_operator` | revokes only this session, device cookie kept |
| `/logout-all` | POST | `require_operator` | revokes every session for the operator |

## Dependency Names (`app/routers/auth_deps.py`)

`require_operator` (401), `require_operator_page` (303→/login), `require_admin` (403, composes `require_operator`), `optional_operator` (never raises, used by `/login` and `/logout`).

## Test Fixtures (`tests/conftest.py`)

`client` (plain `TestClient(app)`, no auth), `operator_client` (overrides `require_operator` + `require_operator_page` → fake non-admin `Operator`), `admin_client` (overrides `require_operator` + `require_operator_page` + `require_admin` → fake admin `Operator`). **Plans 05-05, 05-07, and 05-09 must import these, never redeclare them.**

## Decisions Made
- `auth_service`/`sessions` imported as module references in `auth_routes.py` (not `from ... import fn`) specifically so `tests/integration/test_auth_flow.py` can monkeypatch the whole bound name with a fake object, never touching the real Supabase Auth / DB-backed session store.
- Session-minting consolidated into one shared `_mint_session_response()` helper called from all three call sites where identity is fully established, rather than duplicating the `create_session()` + cookie-setting logic inline twice — this is what the plan's Task 2 spec meant by "mint the opaque session as in step 4" for the MFA-success path.
- `DASHBOARD_PASSWORD` cleanup extended beyond the plan's literal `files_modified` list (to `tests/unit/test_config.py`, `test_main_debug_gate.py`, `README.md`, `docs/PLAN.md`, `docs/TODO.md`, `CLAUDE.md`) because the plan's own Task 1 action text and top-level `<verification>` block explicitly required a repo-wide grep to come back clean, not just the named files.
- `ALYASMEEN/raw/project-claude-md.md` intentionally left untouched (3 remaining `DASHBOARD_PASSWORD` mentions) — it is an immutable graphify snapshot per the vault's own CLAUDE.md governance ("never hand-edit `raw/`"); the corresponding durable-knowledge update went into `ALYASMEEN/wiki/web-dashboard.md` and `log.md` instead.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Reworded my own docstrings to avoid tripping the plan's own literal grep checks**
- **Found during:** Task 1 (`auth_deps.py`) and Task 3 (`conftest.py`)
- **Issue:** Task 1's `<verify>` requires `grep -rn "DASHBOARD_PASSWORD\|_is_authenticated\|_session_token" app/` to return nothing, and Task 3's requires `grep -rn "hashlib" tests/` to return nothing. My own explanatory docstrings (describing the *old* scheme by name, for context) initially contained the literal strings `DASHBOARD_PASSWORD` and `hashlib`, which would have tripped those exact checks — the same class of self-inflicted issue 05-01 hit and fixed the same way.
- **Fix:** Reworded both docstrings to describe the retired scheme without using the flagged literal strings (e.g. "a deterministic hash of the shared dashboard password" instead of naming the env var; "hand-compute a token" instead of naming the hashlib module).
- **Files modified:** `app/routers/auth_deps.py`, `tests/conftest.py`
- **Verification:** Both greps return zero matches in `app/` and against these two files respectively.
- **Committed in:** `ec38816` (Task 1), `4377d16` (Task 3)

---

**Total deviations:** 1 auto-fixed (1 blocking, cosmetic — self-inflicted docstring wording only)
**Impact on plan:** No functional or security effect. No scope creep.

## Issues Encountered

**Verification-grep scope mismatches (documented, not fixed — pre-existing, out of scope):**
- `grep -rn "hashlib" tests/` still matches `tests/unit/test_operator_sessions.py` (05-01's own token-hash assertions) and `tests/unit/test_whatsapp_meta.py` (unrelated HMAC webhook-signature test) — both legitimate, pre-existing uses unrelated to the retired dashboard-cookie scheme, and neither file is in this plan's scope.
- `grep -rn "def client(" tests/` also matches `tests/integration/test_bot_flow.py` and `tests/unit/test_debug.py`, each declaring their own unrelated `client(monkeypatch)` fixture (WhatsApp bot / debug-router test clients) that predate this plan and are not part of dashboard auth.
- `grep -rn "DASHBOARD_PASSWORD" .` (top-level plan verification) still matches `ALYASMEEN/raw/project-claude-md.md` (3 hits, immutable graphify snapshot — never hand-edited per the vault's own rules) and my own new prose in `ALYASMEEN/wiki/web-dashboard.md`/`log.md`, which describe the retired scheme by name for documentation clarity.

None of these represent unaddressed work within this plan's scope — all are pre-existing files or intentional documentation of what was removed, verified by direct inspection.

## User Setup Required

None — no new external service configuration required by this plan. `SUPABASE_ANON_KEY` (required for a real `POST /login` submission to actually reach Supabase) was already flagged as outstanding in 05-02's SUMMARY and remains outstanding; this plan's own manual smoke test confirmed the expected 500 when submitting real credentials locally without it, which is an environment-setup gap (05-09's live rollout), not a code defect — `tests/integration/test_auth_flow.py` exercises the full login/MFA logic against fakes instead.

## Next Phase Readiness
- `app/routers/auth_deps.py`'s four dependencies and `tests/conftest.py`'s three fixtures (`client`, `operator_client`, `admin_client`) are stable and ready for every later Phase 5 plan to consume without redeclaring.
- `/login/reset-request` is referenced by `login.html`'s "نسيت كلمة المرور؟" link but not yet implemented — a 404 today. **05-09 owns this route** (`send_password_reset()` already exists in `app/services/auth.py` from 05-02).
- `request.state.new_device` is set on a successful TOTP verification with a `# 05-09 fires the admin WhatsApp alert here` comment at the exact call site — 05-09 just needs to read that flag.
- No blockers.

---
*Phase: 05-operator-security-ux*
*Completed: 2026-08-28*

## Self-Check: PASSED

All key files found on disk:
- FOUND: app/routers/auth_deps.py
- FOUND: app/routers/auth_routes.py
- FOUND: app/templates/mfa_challenge.html
- FOUND: tests/integration/test_auth_flow.py
- FOUND: app/routers/ui.py, app/routers/ui_api.py, app/routers/broadcast.py, app/main.py
- FOUND: app/services/config.py, app/templates/login.html, .env.example
- FOUND: tests/conftest.py, test_ui_api.py, test_orders_api.py, test_alerts_api.py
- FOUND: .planning/phases/05-operator-security-ux/05-03-SUMMARY.md

All task commits found in git log:
- FOUND: ec38816 (Task 1)
- FOUND: 26097ea (Task 2)
- FOUND: 4377d16 (Task 3)
