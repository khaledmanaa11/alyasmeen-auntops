---
phase: 05-operator-security-ux
plan: 02
subsystem: auth
tags: [supabase-auth, totp, mfa, aal, service_role, anon-key, argparse]

# Dependency graph
requires: []
provides:
  - "app/services/auth.py — Supabase Auth wrapper: password sign-in with mandatory AAL check, TOTP enroll/verify, admin factor removal, admin user create/list, password reset"
  - "scripts/manage_operators.py — CLI to create operator accounts, list them, reset MFA (lost-phone), and trigger password resets"
  - "Config.SUPABASE_ANON_KEY / Config.ADMIN_PHONE / Config.DASHBOARD_BASE_URL"
  - "docs/OPERATOR_ACCOUNTS.md — account lifecycle runbook"
affects: [05-03, 05-09]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Two Supabase clients per identity call, built fresh each time: _anon_client() (SUPABASE_ANON_KEY) for the non-admin auth surface, _admin_client() (SUPABASE_KEY/service_role) for admin-only operations — never shared/cached across requests"
    - "Every Supabase Auth exception is caught and re-raised as this module's own AuthError(message, code) so callers never import supabase_auth's exception types directly"
    - "Fake-client monkeypatching (_anon_client/_admin_client replaced with SimpleNamespace-based stand-ins) instead of network mocks, mirroring tests/conftest.py's FakeDB pattern for the DB seam"

key-files:
  created:
    - app/services/auth.py
    - scripts/manage_operators.py
    - docs/OPERATOR_ACCOUNTS.md
    - tests/unit/test_auth_service.py
  modified:
    - app/services/config.py
    - .env.example

key-decisions:
  - "sign_in() always calls mfa.get_authenticator_assurance_level() + mfa.list_factors() after the password grant and returns AuthResult.mfa_required instead of ever implying a login — the single highest-value correctness rule in this phase (RESEARCH Pitfall 1)"
  - "admin.mfa.list_factors() returns a plain list[Factor] in the installed supabase-auth 2.28.3 client (not a .all-wrapped object like the non-admin mfa.list_factors()) — verified by reading gotrue_admin_api.py's _list_factors() directly rather than trusting the RESEARCH doc's factors.all example, which describes the non-admin surface's response shape, not the admin one"
  - "enroll_totp(access_token, refresh_token) takes no email parameter — the email for MFA's friendly_name is read back from client.auth.set_session(...).user.email, since set_session's AuthResponse already carries the rehydrated user"

patterns-established:
  - "Any future identity code imports app.services.auth's functions rather than calling supabase.auth.* directly — auth.py is the only module allowed to import supabase for identity"

# Metrics
duration: ~35min
completed: 2026-08-28
---

# Phase 5 Plan 02: Supabase Auth Wrapper Summary

**`app/services/auth.py` wraps Supabase Auth's password + TOTP MFA API behind nine functions built on two per-call clients (anon vs service_role), enforcing the AAL1→AAL2 check that stops MFA from being silently bypassable, plus the `manage_operators.py` CLI that creates/lists/recovers the two operator accounts.**

## Performance

- **Duration:** ~35 min
- **Completed:** 2026-08-28T16:40:00Z
- **Tasks:** 3/3 completed
- **Files modified:** 6 (2 modified, 4 created)

## Accomplishments
- `Config` gained `SUPABASE_ANON_KEY`, `ADMIN_PHONE`, `DASHBOARD_BASE_URL` (all documented in `.env.example`, including the built-in Supabase email provider's 2 emails/hour project-wide cap); `DASHBOARD_PASSWORD` deliberately left untouched — 05-03 owns its removal.
- `app/services/auth.py` — the only module in the codebase allowed to import `supabase` for identity. `sign_in()` performs the password grant then always checks `mfa.get_authenticator_assurance_level()` + `mfa.list_factors()`, returning `AuthResult.mfa_required` rather than ever implying "logged in."
- `scripts/manage_operators.py` — an argparse CLI (`create` / `list` / `reset-mfa` / `reset-password`) that imports only `app.services.auth` (plus `Config` for its own configured-guard check) and refuses to run against an unconfigured project.
- `docs/OPERATOR_ACCOUNTS.md` — runbook covering the two-account model, assisted TOTP enrollment ritual, lost-phone recovery, and the email rate limit.
- `tests/unit/test_auth_service.py` — 16 unit tests against fake Supabase clients (zero network), covering all 5 plan-required scenarios plus extra coverage (AAL-already-satisfied case, `None` app_metadata, enrollment, admin user create/list, password reset).

## Task Commits

Each task was committed atomically:

1. **Task 1: Config + .env.example additions** - `41ecc9a` (feat)
2. **Task 2: app/services/auth.py — Supabase Auth wrapper** - `16f99b5` (feat)
3. **Task 3: manage_operators.py CLI, runbook, and unit tests** - `e9dce89` (feat)

**Plan metadata:** (this commit, docs)

## Files Created/Modified
- `app/services/config.py` — added `SUPABASE_ANON_KEY`, `ADMIN_PHONE`, `DASHBOARD_BASE_URL`
- `.env.example` — documented all three, plus fixed a stale comment (`SUPABASE_KEY` was mislabeled "anon key" — it is the service_role key per `CLAUDE.md`'s own security note)
- `app/services/auth.py` — Supabase Auth wrapper (see Public Interface below)
- `scripts/manage_operators.py` — operator account CLI
- `docs/OPERATOR_ACCOUNTS.md` — account lifecycle runbook
- `tests/unit/test_auth_service.py` — 16 unit tests, fake-client fixtures

## Public Interface (`app/services/auth.py`)

Recorded here in full so plan 05-03 (and 05-09) can import without re-reading the source:

```python
class AuthError(Exception):
    code: str | None   # e.g. "over_email_send_rate_limit", "invalid_credentials"

@dataclass(frozen=True)
class AuthResult:
    user_id: str
    email: str
    is_admin: bool
    mfa_required: bool      # True only when a verified TOTP factor exists AND AAL is still aal1
    factor_id: str | None   # set iff mfa_required is True
    access_token: str       # AAL1 Supabase access token — bridge to verify_totp(), never the app session
    refresh_token: str      # AAL1 Supabase refresh token — same bridge

def sign_in(email: str, password: str) -> AuthResult
def verify_totp(access_token: str, refresh_token: str, factor_id: str, code: str) -> str        # returns verified user_id
def enroll_totp(access_token: str, refresh_token: str) -> dict            # {"factor_id", "qr_code", "secret"}
def verify_enrollment(access_token: str, refresh_token: str, factor_id: str, code: str) -> None
def admin_list_factors(user_id: str) -> list[dict]                        # [{"id","factor_type","status","friendly_name"}, ...]
def admin_delete_all_factors(user_id: str) -> int                         # returns count deleted
def admin_create_user(email: str, password: str, role: str) -> str        # returns new user_id; email_confirm=True, app_metadata={"role": role}
def admin_list_users() -> list[dict]                                      # [{"id","email","role","factor_count"}, ...]
def send_password_reset(email: str) -> None                               # redirect_to = f"{Config.DASHBOARD_BASE_URL}/login/reset"
```

**Critical usage rule for 05-03:** `sign_in()` returning successfully does NOT mean the operator is authenticated. The caller must check `AuthResult.mfa_required`:
- `False` → mint the app-owned opaque session immediately (via 05-01's `sessions.create_session`).
- `True` → do NOT mint a session yet. Bridge `access_token`/`refresh_token`/`factor_id` to the MFA-challenge step (05-01's `pending_logins` table is designed for exactly this), then call `verify_totp(...)` once the operator submits a code, and only mint the session after that succeeds.

`enroll_totp`/`verify_enrollment` both require an active AAL1 session (rehydrated via `set_session`) — call them only from a route reachable after `sign_in()` with `mfa_required=False` handling already at least logged the operator in at AAL1 (i.e., during the "set up MFA now" onboarding step, not before any authentication).

## Decisions Made
- `sign_in()` always performs the AAL1→AAL2 check via `mfa.get_authenticator_assurance_level()` + `mfa.list_factors()` — never trusts a successful `sign_in_with_password()` as proof of full authentication. This is the module's core correctness guarantee; skipping it would make TOTP decorative (RESEARCH Pitfall 1).
- Confirmed by reading `supabase_auth`'s installed 2.28.3 source directly: the **admin** MFA surface (`client.auth.admin.mfa.list_factors({"user_id": ...})`) returns a plain `List[Factor]`, while the **non-admin** surface (`client.auth.mfa.list_factors()`) returns an `AuthMFAListFactorsResponse` with `.all`/`.totp`/`.phone` sub-lists. `admin_list_factors()`/`admin_delete_all_factors()` iterate the admin list directly (no `.all` attribute access) — the RESEARCH doc's own code example (`factors.all` in the admin context) does not match the installed client and was corrected here rather than copied.
- `enroll_totp(access_token, refresh_token)` takes no `email` argument; the email used for TOTP's `friendly_name` comes from `client.auth.set_session(...).user.email` (the rehydrated session's own user), keeping the function signature exactly as specified in the plan's public surface.
- Kept `Config.SUPABASE_KEY` as the service_role key and added `Config.SUPABASE_ANON_KEY` as a genuinely separate value, per the plan and CLAUDE.md's existing security note — never merged or defaulted one from the other.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed a stale/incorrect `.env.example` comment for `SUPABASE_KEY`**
- **Found during:** Task 1 (Config + .env.example additions)
- **Issue:** `.env.example` labeled `SUPABASE_KEY` as `your_anon_key_here`, contradicting `CLAUDE.md`'s explicit documented rule that `SUPABASE_KEY` is the service_role key (`app/db/database.py` and now `app/services/auth.py`'s `admin_*` functions both rely on it bypassing RLS). Left uncorrected, a future operator following `.env.example` literally could paste the anon key into `SUPABASE_KEY` and break every DB write in the app.
- **Fix:** Updated the placeholder to `your_service_role_key_here` with an explanatory comment distinguishing it from the new `SUPABASE_ANON_KEY` line added directly below it.
- **Files modified:** `.env.example`
- **Verification:** Manual read-through; `python -m pytest tests/unit/test_config.py -q` still passes (the test suite doesn't assert on `.env.example` prose, only on `Config` values, which were unaffected).
- **Committed in:** `41ecc9a` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Documentation-only fix; no functional or security code path changed. No scope creep.

## Issues Encountered
None. A separate agent was concurrently executing plan 05-01 (opaque operator session store) on the same branch during this session — visible as interleaved commits (`51b4bfe`/`a5921dc`/`3bd5c8f` for 05-01 sandwiched around this plan's `41ecc9a`/`16f99b5`/`e9dce89`) in `git log`. Expected and harmless: this plan's frontmatter also declares `depends_on: []` and touches no files 05-01 touches. Verified after the fact by diffing a stray `git stash` against the working tree — the concurrent agent's own `.planning/codebase/STRUCTURE.md` update was newer than a stale local snapshot and was left untouched (stash dropped, not popped) rather than risk overwriting it.

## User Setup Required
The plan's `user_setup` block (`SUPABASE_ANON_KEY`, `ADMIN_PHONE`, `DASHBOARD_BASE_URL` values, plus confirming Supabase's Email Auth provider) is **not yet actioned** — it requires values only the project owner has (the Supabase anon key from the dashboard, Khaled's own WhatsApp number, and the production URL). `Config` defaults keep the test suite and local dev green without them (`SUPABASE_ANON_KEY` defaults to `""`, `DASHBOARD_BASE_URL` defaults to `http://localhost:8000`), but `scripts/manage_operators.py` and any real Supabase Auth call will fail until `SUPABASE_URL`/`SUPABASE_KEY`/`SUPABASE_ANON_KEY` are all set with real project values. No `{phase}-USER-SETUP.md` was generated by this specific plan execution — surface these values when 05-09 (live rollout) runs, since that plan is where accounts actually get created against the live project.

## Next Phase Readiness
- `app/services/auth.py`'s full public surface (documented above) is stable and ready for 05-03 to wire into the login/MFA-challenge routes, alongside 05-01's `app/services/sessions.py`.
- `scripts/manage_operators.py` is ready to run once real `SUPABASE_ANON_KEY`/`ADMIN_PHONE`/`DASHBOARD_BASE_URL` values exist in the environment — deliberately not run against the live project in this plan, per the plan's own verification instructions.
- No blockers. Wave 1 (05-01 + 05-02) is now fully complete with zero merge conflicts between the two parallel plans.

---
*Phase: 05-operator-security-ux*
*Completed: 2026-08-28*

## Self-Check: PASSED

All key files found on disk:
- FOUND: app/services/config.py
- FOUND: .env.example
- FOUND: app/services/auth.py
- FOUND: scripts/manage_operators.py
- FOUND: docs/OPERATOR_ACCOUNTS.md
- FOUND: tests/unit/test_auth_service.py
- FOUND: .planning/phases/05-operator-security-ux/05-02-SUMMARY.md

All task commits found in git log:
- FOUND: 41ecc9a (Task 1)
- FOUND: 16f99b5 (Task 2)
- FOUND: e9dce89 (Task 3)
