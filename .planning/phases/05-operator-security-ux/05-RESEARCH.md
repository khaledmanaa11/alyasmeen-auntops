# Phase 5: Operator Security & UX (M5) - Research

**Researched:** 2026-08-28
**Domain:** Supabase Auth (email+password + TOTP MFA) from a server-rendered FastAPI/Jinja2 app; opaque server-side sessions; CSRF; security headers; operator UX (handoffs/audit/alerts) on top of a Phase-3 schema that exists but whose services are not yet built.
**Confidence:** HIGH for codebase facts and Supabase Auth Python API surface (read directly from installed package + official docs). MEDIUM for CSP/CSRF library specifics (WebFetch/WebSearch verified against official sources). MEDIUM-LOW for anything depending on Phase 3 execution timing (Phase 3 is planned but not executed, and its own plans are flagged stale in STATE.md).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Accounts & login (REQ-prod-auth-mfa, REQ-dash-login)**
- Two accounts: the aunt (operator) + Khaled (admin). Admin can help remotely and owns recovery.
- Real email addresses as login identifiers — standard Supabase Auth flow, password-reset emails work.
- TOTP enrollment is assisted: Khaled sets it up with her (in person or on a call). The dashboard shows the QR only during an explicit enrollment step — not a self-serve forced flow.
- Lost phone / MFA recovery: admin removes her MFA factor (Supabase admin / script), she re-enrolls. No printed recovery codes.

**Sessions (REQ-prod-session-opaque)**
- 30-day session lifetime; sign in roughly monthly.
- MFA remember-device for 30 days per device — TOTP prompted only on new devices or after 30 days.
- Multi-device allowed — phone + laptop sessions coexist; logout on one doesn't kill the other.
- No idle timeout.
- "Log out everywhere" button for both accounts (kills all of that user's sessions).
- Any credential change (password change, MFA reset) revokes ALL sessions for that user.
- Admin session view: Khaled's account can list and revoke the aunt's active sessions from the UI (lost/stolen phone scenario).
- New-device login sends a WhatsApp alert to Khaled (admin) — the aunt is not bothered.

**Handoff & audit UI (success criterion 2)**
- New dedicated nav tab for handoffs (e.g. محادثات) — becomes the 6th dashboard tab, wired into all templates like the alerts tab was.
- Handoff detail view = reason + recent chat transcript (from chat_history) so she has context before opening WhatsApp; include the wa.me link.
- Single resolution action: "return to bot" (أعد للبوت) — resolves the handoff and unpauses the session. She converses with the customer in WhatsApp itself; no dashboard reply box.
- Resolved handoffs stay visible as recent history (active on top, resolved below / behind a filter).
- Live count badge of active handoffs on the nav tab, refreshed with the dashboard's auto-refresh.
- Conflicts = bot-vs-aunt overlap: when she and the bot both act on the same customer/order (e.g. she changes a status while the bot is mid-conversation), the UI should detect the overlap and let her pick the winner — not just a silent last-write-wins.
- Audit history covers ALL operator actions: handoffs, order status changes, product edits, broadcasts, logins — one chronological who-did-what trail.
- Audit history visible to both accounts (shown in her UI too, not admin-only).

**Failure recovery UX (success criterion 4)**
- Rework the /alerts page — don't keep the current technical presentation.
- Action-oriented plain Arabic cards with customer names: each failure reads as a call to action — "تحتاج انتباهك الآن — رسالة لم تصل إلى فلانة، تابعي المحادثة معها" — telling her what happened and what to do next (continue the conversation herself). Technical detail (job type, attempts, payload) collapsed behind a details toggle.
- Proactive WhatsApp alerts on permanent failure, to BOTH: the aunt gets customer-facing failures (a message to a customer didn't arrive); Khaled gets everything.
- Retry controls: per-item retry + a bulk "retry all" (post-outage recovery).

### Claude's Discretion
- All purely technical design: opaque session store mechanics, CSRF token mechanism, exact security-header set (CSP/HSTS/etc.), conflict-detection implementation, audit-log storage design.
- Alerts-page card visual design and whether retry or "take over yourself" is the primary action per failure type.
- Handoff tab naming, layout details, and transcript length shown.
- How "remember this device" is persisted/identified.

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

## Summary

This phase replaces a genuinely minimal auth scheme (one shared cookie = `SHA-256(SECRET_KEY:DASHBOARD_PASSWORD)`, duplicated verbatim in **three** router files — `ui.py`, `ui_api.py`, `broadcast.py`) with real per-operator identity via Supabase Auth, TOTP MFA, an app-owned opaque session store, CSRF protection, and security headers — then builds three new/reworked UI surfaces (handoffs tab, audit trail, reworked /alerts) on top of DB schema that (surprisingly) **already exists** from Phase 1's baseline migration: `handoffs`, `audit_logs`, and `sessions.paused` are all live in Supabase today. What does **not** exist yet is any code that writes to them — `app/services/handoff.py`, `app/services/policy.py`, and the processor.py integration are Phase 3 deliverables, and Phase 3 is planned-but-not-executed (its own plans are flagged stale in STATE.md, predating the Aug 25 hardening session). This is the single most important sequencing fact for the planner: Phase 5's handoff UI has a real, live table to query, but no producer writing "active" rows to it until Phase 3 runs and until Phase 5 itself adds a *resolution* path (Phase 3's plan only ever calls `HandoffService.trigger()` — nothing in Phase 3 as currently planned closes a handoff).

Supabase Auth's Python client (`supabase-auth` 2.28.3, installed) exposes exactly the primitives this phase needs: `auth.sign_in_with_password()`, `auth.mfa.enroll/challenge/verify/challenge_and_verify/get_authenticator_assurance_level()`, and on a service-role-keyed client, `auth.admin.mfa.list_factors()/delete_factor()` plus `auth.admin.list_users()/create_user()/update_user_by_id()`. Because `sign_in_with_password` succeeds and returns a full session **even when the user has a verified TOTP factor** (it only reaches AAL1), the login flow must explicitly check `get_authenticator_assurance_level()` and gate access on AAL2 — skipping this check is the single most dangerous and easiest-to-miss implementation mistake in this phase. Because REQ-prod-session-opaque asks for a server-authoritative session (not a client-held JWT), the cleanest architecture discards Supabase's own JWT/refresh-token pair immediately after login+MFA and mints the app's own opaque token in a new DB table — which also means every session-lifecycle requirement in the CONTEXT (30-day expiry, multi-device, logout-everywhere, revoke-on-credential-change, admin session listing) becomes plain CRUD against that one table via the existing `database.py` seam, with zero dependency on Supabase's own session semantics.

**Primary recommendation:** Build a single `app/services/auth.py` module (Supabase Auth calls: password sign-in, MFA enroll/challenge/verify, admin factor removal) plus a single `app/services/sessions.py` module (opaque session + trusted-device CRUD against two new tables, `operator_sessions` and `trusted_devices`), expose them as FastAPI dependencies (`require_operator`, `require_admin`), and use those dependencies to replace all three duplicated `_is_authenticated()` copies in `ui.py`/`ui_api.py`/`broadcast.py`. Add `starlette-csrf` (double-submit cookie, scoped via `sensitive_cookies` to the new session cookie so webhook/dev routes need no explicit exemption list) and a small custom headers middleware for CSP/HSTS/etc. — accept `'unsafe-inline'`/`'unsafe-eval'` in `script-src`/`style-src` because the app's Tailwind Play CDN and Alpine.js core genuinely cannot run under a strict CSP without a larger frontend rework that is out of scope for this phase.

## Codebase Reality Check

### Current auth (what Phase 5 replaces)

Three separate files each hand-roll the identical scheme:

```python
# app/routers/ui.py, app/routers/ui_api.py, app/routers/broadcast.py — all three, verbatim
COOKIE_NAME = "alyasmeen_session"

def _session_token() -> str:
    raw = f"{Config.SECRET_KEY}:{Config.DASHBOARD_PASSWORD}"
    return hashlib.sha256(raw.encode()).hexdigest()

def _is_authenticated(request: Request) -> bool:
    return request.cookies.get(COOKIE_NAME) == _session_token()
```

Every route handler individually does `if not _is_authenticated(request): raise HTTPException(401)` (API routes) or `return RedirectResponse("/login")` (page routes). There is exactly one token value possible (deterministic from two env vars) — logging in as "the aunt" is really just knowing the shared password; there is no per-user identity, no revocation, no expiry, and the same token is valid forever until `SECRET_KEY`/`DASHBOARD_PASSWORD` change. `/login` (`ui.py`) is a classic form POST; every mutating dashboard action (`orders.html`, `products.html`, `broadcast.html`, `alerts.html`) is a `fetch()` JSON call relying on the browser auto-sending the cookie — none of them include or expect a CSRF token today. **Confidence: HIGH** (read directly from `app/routers/ui.py`, `app/routers/ui_api.py`, `app/routers/broadcast.py`).

Tests mirror this duplication: `tests/integration/test_ui_api.py`, `test_orders_api.py`, and `test_alerts_api.py` each define their **own local** `auth_client` fixture that computes the same SHA-256 token and calls `client.cookies.set("alyasmeen_session", token)`. None of this is centralized in `conftest.py`. When Phase 5 replaces the auth scheme, every one of these tests breaks unless a new shared fixture is introduced. **Confidence: HIGH.**

### Phase 3 schema already exists; Phase 3 services do not

`supabase/migrations/20260614000001_durable_messaging.sql` (Phase 1, already applied live per STATE.md) already creates:

```sql
CREATE TABLE IF NOT EXISTS audit_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  actor TEXT NOT NULL,      -- 'system', 'aunt', or phone number
  action TEXT NOT NULL,     -- 'order_created', 'status_changed', 'login_failed'
  details JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS handoffs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  phone TEXT NOT NULL REFERENCES customers(phone),
  reason TEXT NOT NULL,
  status TEXT DEFAULT 'active',   -- 'active', 'resolved'
  assigned_to TEXT,               -- 'aunt'
  created_at TIMESTAMPTZ DEFAULT NOW(),
  resolved_at TIMESTAMPTZ,
  metadata JSONB DEFAULT '{}'::jsonb
);
```

`supabase/migrations/20260615000000_add_paused_to_sessions.sql` already adds `sessions.paused BOOLEAN DEFAULT FALSE`. RLS (`20260614000003_security_rls.sql`) already locks both tables to `service_role` only. **Confidence: HIGH** (read migrations directly).

However, `grep -rl "handoff\|Handoff" app/` and `grep -rl "audit_log" app/` both return **zero files**. `app/services/policy.py` and `app/services/handoff.py` — the files `03-01-PLAN.md` specifies — do not exist. `app/services/processor.py` has no `paused` gate, no keyword-trigger logic, no media-type handoff logic. **Confirmed: Phase 3 has not been executed**, matching STATE.md ("Phase 3 (planned, NOT yet executed) is next up, pending plan re-verification... `03-01/02/03-PLAN.md` were written BEFORE the hardening session... re-run `/gsd:plan-phase 3`... before executing").

Critically, `03-01-PLAN.md`'s `HandoffService` only ever specifies a `trigger(phone, reason, metadata)` method — **nothing in the Phase 3 plans closes a handoff**. Phase 5's "return to bot" action (resolve handoff + unpause session) has no Phase-3-provided method to call. **Confidence: HIGH** (read `03-01-PLAN.md`/`03-02-PLAN.md`/`03-03-PLAN.md` in full).

**Sequencing implication for the planner:** ROADMAP.md already declares `Phase 5 depends_on: Phase 3`, so by the time Phase 5 is *executed* Phase 3 should be done — but Phase 5 is being *planned* now, before Phase 3 has run or been re-verified. Two safe paths:
1. Plan Phase 5 assuming `app/services/handoff.py` exports `HandoffService` with `trigger(phone, reason, metadata)` (per the current, if stale, Phase 3 plan) — and have Phase 5 **add** a `resolve(handoff_id, resolved_by)` method to that same service (updates `handoffs.status='resolved'`, `resolved_at`, writes `resolved_by` into `metadata`, and sets `sessions.paused = FALSE`) rather than inventing a parallel code path. Verify the actual signature against Phase 3's SUMMARY.md (once it exists) before writing the Phase 5 plan's task bodies.
2. If Phase 3 truly has not executed by the time Phase 5 plans need to lock file contents, Phase 5's plan should include an explicit pre-check task ("read `app/services/handoff.py`; if absent, STOP — Phase 3 must execute first") rather than silently duplicating handoff-writing logic into `ui_api.py`. Do **not** have Phase 5 re-implement `trigger()`/pause-gating — that would create two competing sources of truth for `sessions.paused`.

Either way, Phase 5's own new code is additive: a `resolve`/`return_to_bot` method, an audit-log write on resolution, and read-only queries against `handoffs`/`chat_history`/`audit_logs` for the UI. **Confidence: MEDIUM** (the schema fact is HIGH; the exact Phase 3 method signature at Phase-5-execution time is unknowable now).

### Alerts page (what Phase 5 reworks)

`GET /api/alerts` (`ui_api.py`) returns two arrays: dead-lettered `webhook_events` (`processed=TRUE AND error LIKE 'dead-letter:%'`) and permanently-failed `outbox_jobs` (`status='failed' AND attempts >= max_attempts`), each capped at 100 rows, newest first. Two retry endpoints exist: `POST /api/alerts/webhook_events/{id}/retry` and `POST /api/alerts/outbox_jobs/{id}/retry` — both single-item, no bulk "retry all" endpoint exists today. `alerts.html` is an Alpine.js single-file page (Tailwind Play CDN, `x-data="alertsApp()"`) showing raw technical fields (`phone`, `attempts`, `error`/`last_error`, `kind`) with no customer name join and no plain-Arabic call-to-action framing — this whole page's content model needs a customer-name join (`outbox_jobs.phone`/`webhook_events.phone` → `customers.name`) and a "what happened / what to do" phrasing layer, which today doesn't exist anywhere in the code. **Confidence: HIGH** (read `ui_api.py` alerts section and `alerts.html` in full).

### Dashboard nav / template pattern

Each of the 5 existing pages (`login`, `orders`, `dashboard`, `products`, `broadcast`, `alerts` — 6 files) repeats an identical `<nav class="nav-glass">` block with hardcoded links; adding the handoffs tab means editing this block in **every** template (no shared partial/include exists — Jinja2 macros/`{% include %}` are not currently used for the nav). All pages: Tailwind Play CDN (`<script src="https://cdn.tailwindcss.com">`), Google Fonts CDN, Alpine.js CDN (only on `alerts.html`; `orders.html`/`products.html` use vanilla `fetch()` + string-templated `innerHTML`, not Alpine), inline `<style>` blocks, inline `<script>` blocks with no CSP nonces. `orders.html` builds action buttons with `onclick="updateStatus(...)"` inline handlers. **Confidence: HIGH.**

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `supabase` (→ `supabase-auth`, `postgrest`, etc.) | 2.28.3 (already installed, already a dependency) | Email+password auth, TOTP MFA, admin user/factor management | Already the project's only DB/Auth client; adding Supabase Auth reuses the existing dependency instead of a new auth stack |
| `starlette-csrf` | 3.0.0 (latest on PyPI as of this research; requires `itsdangerous>=2.0.1,<3.0.0`, Starlette >=0.14.2, Python >=3.8) | Double-submit-cookie CSRF middleware for Starlette/FastAPI | Purpose-built for exactly this framework combo; implements the double-submit pattern correctly (signed token via `itsdangerous`) instead of hand-rolling comparison logic |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| stdlib `secrets` | builtin | Opaque session token / device token generation (`secrets.token_urlsafe(32)`) | Every new opaque token minted (session token, device cookie token) |
| stdlib `hashlib` | builtin | Hash opaque tokens before storing (`sha256(token).hexdigest()`), so a DB read never exposes a usable raw token | Session table storage; already the pattern the current cookie scheme uses (just applied correctly this time — hash stored, not compared as a shared secret) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `starlette-csrf` | Hand-rolled double-submit cookie check | The library already handles signing (`itsdangerous`), safe comparison, and cookie/URL exemption plumbing; hand-rolling CSRF comparison logic is exactly the kind of security-critical, easy-to-get-subtly-wrong code the "Don't Hand-Roll" principle exists for |
| `starlette-csrf` | Synchronizer-token pattern (per-form hidden `<input>`, server-side token store) | Would require injecting a token into every Jinja2 template that has a form/fetch call and a server-side per-session token store; double-submit cookie needs no template `<input>` changes and works uniformly for the existing `fetch()`-based JSON POST pattern — much less template churn |
| Custom headers middleware | `Secweb` (PyPI package for FastAPI/Starlette CSP/HSTS middleware) | Security headers here are ~8 static string values plus one dynamic CSP nonce; this is not "deceptively complex" the way CSRF/session/MFA are, so a ~30-line custom middleware function keeps the dependency count down and matches the codebase's existing minimal-dependency style — reasonable to hand-roll |
| App-owned opaque session table | A session library (e.g. `starlette-session`, `fastapi-sessions`) | The specific lifecycle rules here (30-day fixed expiry, multi-device rows, per-device MFA-remember, admin cross-user listing, revoke-on-credential-change) are custom business logic that doesn't map cleanly onto a generic session library's API, and the app already has a working DB-seam (`database.py`) that a library would bypass or duplicate |

**Installation:**
```bash
pip install starlette-csrf
# requirements.txt / pyproject.toml: add "starlette-csrf>=3.0.0"
```

## Architecture Patterns

### Recommended module layout
```
app/
├── services/
│   ├── auth.py           # NEW — Supabase Auth wrapper: sign_in, mfa enroll/challenge/verify,
│   │                        admin.mfa.delete_factor, admin.create_user (setup script only)
│   └── sessions.py        # NEW — opaque session + trusted-device CRUD via database.py seam
├── routers/
│   ├── auth_deps.py        # NEW — require_operator()/require_admin() FastAPI dependencies,
│   │                          replaces the 3 duplicated _is_authenticated() copies
│   ├── ui.py                # MODIFIED — pages use Depends(require_operator); + /handoffs page
│   ├── ui_api.py             # MODIFIED — APIs use Depends(require_operator)/Depends(require_admin);
│   │                            + handoffs/audit/admin-sessions endpoints; alerts reworked
│   └── broadcast.py          # MODIFIED — drop its private _is_authenticated(), use the shared dep
└── templates/
    ├── handoffs.html          # NEW — 6th nav tab
    ├── alerts.html             # REWORKED — plain-Arabic action cards
    ├── enroll_mfa.html          # NEW — QR/secret shown only during explicit enrollment
    ├── mfa_challenge.html        # NEW — TOTP code entry step of login
    └── (all 6 existing templates get the nav block + CSP nonce touch)
```

### Pattern 1: FastAPI dependency instead of per-route `if not _is_authenticated()`
**What:** A single `require_operator(request: Request) -> Operator` dependency that reads the opaque session cookie, looks up the session row, validates `revoked_at IS NULL AND expires_at > now()`, and returns an `Operator(id, email, is_admin)`. A second `require_admin` dependency wraps it and additionally checks `is_admin`.
**When to use:** Every dashboard page route and every `/api/*` mutation/read route currently doing manual cookie checks.
**Example:**
```python
# app/routers/auth_deps.py
from fastapi import Depends, HTTPException, Request
from app.services.sessions import lookup_session  # returns Operator | None

async def require_operator(request: Request) -> "Operator":
    token = request.cookies.get(SESSION_COOKIE_NAME)
    op = lookup_session(token) if token else None
    if op is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return op

async def require_admin(op: "Operator" = Depends(require_operator)) -> "Operator":
    if not op.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return op
```
This also gives every mutation an `op.email`/`op.id` for free to write into `audit_logs.actor` — solving the "who did this" requirement without extra plumbing.

### Pattern 2: Supabase password + TOTP login as two HTTP round-trips
**What:** Because a server-rendered app has no persistent Supabase JS client, and MFA is a second network call to a *different* endpoint (`factors/{id}/challenge` then `verify`), login is naturally two POSTs: `POST /login` (password) → if the account has a verified TOTP factor **and** the device isn't currently "remembered," render an MFA code-entry page; `POST /login/mfa` (code) → mint the opaque session.
**Verified from the installed `supabase_auth` package (2.28.3):**
```python
# Step 1 — password (app/services/auth.py)
from supabase import create_client, ClientOptions

def sign_in(email: str, password: str):
    client = create_client(Config.SUPABASE_URL, Config.SUPABASE_ANON_KEY)  # anon key, not service_role
    resp = client.auth.sign_in_with_password({"email": email, "password": password})
    # resp.session.access_token / refresh_token — AAL1 even if TOTP is enrolled.
    aal = client.auth.mfa.get_authenticator_assurance_level()
    # aal.current_level == "aal1", aal.next_level == "aal2"  →  MFA challenge still required.
    return resp.session, aal

# Step 2 — TOTP code, using the tokens bridged from step 1 (short-lived signed cookie or temp DB row)
def verify_mfa(access_token: str, refresh_token: str, factor_id: str, code: str):
    client = create_client(Config.SUPABASE_URL, Config.SUPABASE_ANON_KEY)
    client.auth.set_session(access_token, refresh_token)     # rehydrate the AAL1 session on a fresh client
    result = client.auth.mfa.challenge_and_verify({"factor_id": factor_id, "code": code})
    # result.access_token/.refresh_token are now AAL2 — discard them; mint our own opaque session instead.
    return result.user
```
**Why the AAL check matters:** `sign_in_with_password` does **not** refuse to return a session just because the user has TOTP enrolled — skipping the `get_authenticator_assurance_level()` check (or the equivalent "does this user have a verified factor, and did we just verify it in *this* login" check) makes MFA silently optional. This is the single highest-value correctness check in this phase. Source: read directly from `supabase_auth/_sync/gotrue_client.py` (`sign_in_with_password`, lines ~292-342) and `supabase_auth/_sync/gotrue_mfa_api.py`; cross-checked against Supabase's official TOTP guide (`supabase.com/docs/guides/auth/auth-mfa/totp`), which states the same AAL1→AAL2 model and confirms it's the app's job to enforce (the docs' worked examples are React/SPA; there is no first-party server-rendered example, so the two-round-trip bridging design above is this research's own synthesis, not copied from an official sample — flag as such to the planner).

### Pattern 3: MFA enrollment (assisted, explicit step — not forced self-serve)
**What:** `auth.mfa.enroll({"factor_type": "totp", "issuer": "ALYASMEEN", "friendly_name": "..."})` requires an active session on the calling client (`self.get_session()` internally) — i.e. the aunt must already be logged in (AAL1 is enough, since there's nothing to challenge yet) before this page is reachable. The Python client already prefixes the returned SVG with `data:image/svg+xml;utf-8,`, so `<img src="{{ totp.qr_code }}">` works with no extra encoding.
```python
enroll = client.auth.mfa.enroll({"factor_type": "totp", "issuer": "ALYASMEEN"})
# enroll.totp.qr_code  -> ready-to-use data: URI for <img src="...">
# enroll.totp.secret   -> manual-entry fallback, show once
# enroll.id            -> factor_id, needed for the immediately-following challenge_and_verify
```
Per the library's own docstring: "The first successful verification of an unverified factor activates the factor. **All other sessions are logged out** and the current one gets an `aal2` authenticator level." That log-out is Supabase's *own* session bookkeeping, not the app's opaque sessions — replicate the intent by having the enrollment-success handler also revoke all of that user's *other* `operator_sessions` rows (keep the current one), satisfying the "credential change revokes all sessions" decision without depending on Supabase-side behavior at all.

### Pattern 4: Admin removes a lost-phone MFA factor
```python
# app/services/auth.py — uses the service_role-keyed client's admin surface
admin_client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)  # service_role
factors = admin_client.auth.admin.mfa.list_factors({"user_id": aunt_user_id})
for f in factors.all:
    admin_client.auth.admin.mfa.delete_factor({"user_id": aunt_user_id, "id": f.id})
```
Source: read directly from `supabase_auth/_sync/gotrue_admin_mfa_api.py` and `gotrue_admin_api.py` (`_list_factors`/`_delete_factor`, calling `GET/DELETE admin/users/{user_id}/factors[/{id}]`). Confidence: HIGH (installed package source, not docs).

### Pattern 5: Opaque session store — the single source of truth for "is this dashboard session valid"
**What:** Two new tables (avoid the name `sessions` — already the WhatsApp cart-state table):
```sql
CREATE TABLE operator_sessions (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID NOT NULL,       -- Supabase auth.users.id
  email         TEXT NOT NULL,       -- denormalized for display / admin session list
  token_hash    TEXT NOT NULL UNIQUE,-- sha256(opaque token); raw token never stored
  device_id     UUID REFERENCES trusted_devices(id),
  user_agent    TEXT,
  created_at    TIMESTAMPTZ DEFAULT now(),
  last_seen_at  TIMESTAMPTZ DEFAULT now(),
  expires_at    TIMESTAMPTZ NOT NULL,   -- created_at + 30 days, fixed (not sliding)
  revoked_at    TIMESTAMPTZ
);

CREATE TABLE trusted_devices (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id            UUID NOT NULL,
  device_token_hash  TEXT NOT NULL,      -- sha256 of a separate long-lived device cookie
  mfa_verified_until TIMESTAMPTZ,        -- now() + 30 days on each successful TOTP verify on this device
  created_at         TIMESTAMPTZ DEFAULT now(),
  last_seen_at       TIMESTAMPTZ DEFAULT now(),
  UNIQUE (user_id, device_token_hash)
);
```
**Why this satisfies every session decision without touching Supabase's own session internals:**
- 30-day lifetime / "sign in monthly" → `expires_at = created_at + interval '30 days'`, checked in `require_operator`.
- Multi-device → each device gets its own `operator_sessions` row; logging out one doesn't touch the others' `revoked_at`.
- Logout-everywhere → `UPDATE operator_sessions SET revoked_at = now() WHERE user_id = %s AND revoked_at IS NULL`.
- Credential-change revokes all → same statement, triggered from the password-change/MFA-enroll/MFA-reset handlers.
- Admin session view → `SELECT * FROM operator_sessions WHERE email = %s AND revoked_at IS NULL AND expires_at > now()` — **no Supabase admin API call needed**, since this app never delegated session storage to Supabase in the first place.
- MFA remember-device (30 days) → on login, hash the `alyasmeen_device` cookie (separate from the session cookie; ~1 year expiry, httponly, secure), look up `trusted_devices` by `(user_id, device_token_hash)`; if found and `mfa_verified_until > now()`, skip the TOTP challenge page entirely.
- New-device WhatsApp alert to admin → "new device" = no matching `trusted_devices` row at login time. After a successful TOTP verification (or a skip because the device was already trusted), upsert the row; if it was an **insert** (not an update), call `queue_text(Config.ADMIN_PHONE, ...)` — same durable outbox pattern already used for `AUNT_PHONE` new-order alerts in `processor.py`.

Both tables need RLS `ENABLE ROW LEVEL SECURITY` + a service-role-only policy, mirroring the pattern already used for `audit_logs`/`handoffs` in `20260614000003_security_rls.sql`.

### Pattern 6: CSRF — double-submit cookie scoped to the session cookie, not exempted routes
```python
# app/main.py
from starlette_csrf import CSRFMiddleware

app.add_middleware(
    CSRFMiddleware,
    secret=Config.SECRET_KEY,
    cookie_secure=not Config.USE_MOCK_WHATSAPP,
    sensitive_cookies={SESSION_COOKIE_NAME},   # only enforce CSRF when our session cookie is present
)
```
Because `sensitive_cookies` scopes enforcement to requests carrying the dashboard session cookie, the WhatsApp webhook (`POST /whatsapp/webhook`, no browser cookie, verified instead by Meta's `X-Hub-Signature-256`) and the dev-only `POST /dev/*` routes need **no explicit `exempt_urls` regex** — they simply never carry that cookie. This is less template churn than the alternative (per-route allowlisting).

To get the CSRF token into every existing `fetch()` call with minimal template edits, add one shared script (referenced from every template's `<head>`, not injected per-callsite) that monkey-patches `window.fetch`:
```html
<!-- app/static/csrf.js, included once per template: <script src="/static/csrf.js"></script> -->
<script>
(function () {
  const orig = window.fetch;
  function readCookie(name) {
    const m = document.cookie.match('(?:^|; )' + name + '=([^;]*)');
    return m ? decodeURIComponent(m[1]) : null;
  }
  window.fetch = function (input, init = {}) {
    const method = (init.method || 'GET').toUpperCase();
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
      init.headers = { ...(init.headers || {}), 'x-csrftoken': readCookie('csrftoken') || '' };
    }
    return orig(input, init);
  };
})();
</script>
```
This means **zero changes** to the 9 existing individual `fetch()` call sites across `orders.html`/`products.html`/`broadcast.html`/`alerts.html` — only one `<script src="/static/csrf.js">` tag added per template (already touching every template anyway, for the new nav tab).

### Pattern 7: Security headers middleware
```python
# app/middleware/security_headers.py (new, ~30 lines, no new dependency)
import secrets
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        nonce = secrets.token_urlsafe(16)
        request.state.csp_nonce = nonce   # available in Jinja2 as request.state.csp_nonce
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' "
            "https://cdn.tailwindcss.com https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; connect-src 'self'; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; "
            "object-src 'none'; upgrade-insecure-requests"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["X-Frame-Options"] = "DENY"
        if not Config.USE_MOCK_WHATSAPP:
            response.headers["Strict-Transport-Security"] = "max-age=15552000; includeSubDomains"
        return response
```
The `nonce` is generated but **not** required by the CSP above (since `'unsafe-inline'` is already granted) — keep it wired through `request.state` anyway so a future, stricter CSP (post frontend-build migration) is a config change, not a re-plumb.

### Anti-Patterns to Avoid
- **Trusting `sign_in_with_password` success as "logged in":** must always follow with the AAL check (Pattern 2) — otherwise TOTP is effectively decorative.
- **Storing raw opaque tokens in the DB:** always store `sha256(token)`; the cookie holds the raw value, the DB holds only the hash — a DB read (e.g. via a future reporting query) can never leak a usable session token.
- **Re-deriving `sensitive_cookies`/`exempt_urls` per environment by hand:** keep the webhook and `/dev/*` routes exempt *by construction* (no session cookie ever sent to them) rather than maintaining a regex allowlist that has to be remembered every time a new route is added.
- **Hand-rolling TOTP verification:** never implement your own `pyotp`-based code check — Supabase Auth owns the TOTP secret and verification state entirely; a parallel implementation would immediately desync from what `auth.mfa.list_factors()` reports as enrolled.
- **Adding `HTTPSRedirectMiddleware` / relying on `request.url.scheme` for HSTS enforcement without also enabling uvicorn's proxy-headers handling:** the Procfile (`uvicorn app.main:app --host 0.0.0.0 --port $PORT`) does not currently pass `--proxy-headers`/`--forwarded-allow-ips`, so behind Railway's TLS-terminating edge, `request.url.scheme` will read `http` unless that's added — a redirect middleware under those conditions creates a redirect loop. Setting the `Strict-Transport-Security` *header* (no redirect) sidesteps this entirely and is what Pattern 7 does.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Password storage/hashing | Custom bcrypt/argon2 handling | Supabase Auth (`sign_in_with_password`, `admin.create_user`) | Supabase Auth already hashes and stores passwords server-side; the app never needs to see or store one beyond the transient POST body |
| TOTP secret generation/verification | `pyotp` + a custom `totp_secrets` table | `auth.mfa.enroll/challenge/verify` | Supabase Auth is the system of record for which factors exist and are verified — a parallel implementation creates two sources of truth |
| CSRF token generation/comparison | Manual `secrets.compare_digest` + a hand-rolled cookie/header pair | `starlette-csrf` | Signing (`itsdangerous`) and safe comparison are already correctly implemented; the current codebase's own auth cookie comparison (`==` on a SHA-256 hex digest) is exactly the kind of subtly-not-quite-right pattern this phase should retire, not repeat |
| "Who can see this account's active sessions" | Calling Supabase's admin API to enumerate sessions per user | Query the app's own `operator_sessions` table | Supabase Auth's public admin surface (verified against the installed 2.28.3 client) exposes `admin.sign_out(jwt, scope)` and MFA factor list/delete, but no "list sessions for user X" endpoint — irrelevant anyway once the opaque table is the source of truth |

**Key insight:** every "Don't Hand-Roll" item above is really the same lesson: this phase's job is to make the app's own opaque-session table the single authoritative store for "is this operator currently logged in," and to delegate everything about *identity verification* (password, TOTP) to Supabase Auth without trying to also track or replicate Supabase's internal session state. Mixing the two (e.g., trying to use Supabase's JWT as the dashboard cookie, or trying to enumerate Supabase's sessions for the admin view) creates two sources of truth for the same question.

## Common Pitfalls

### Pitfall 1: MFA silently bypassed because AAL is never checked
**What goes wrong:** Login "works" (password correct) and the operator is let straight into the dashboard even though they have a TOTP factor enrolled.
**Why it happens:** `sign_in_with_password` returns a valid `session`/`access_token` regardless of MFA enrollment — GoTrue only *elevates* the AAL on successful MFA verification, it doesn't *block* the initial password grant.
**How to avoid:** After password sign-in, always call `auth.mfa.get_authenticator_assurance_level()` (or check `auth.mfa.list_factors()` for a verified TOTP factor) and only mint the opaque session if `current_level == next_level` (no MFA required or already satisfied) — otherwise render the MFA challenge page.
**Warning signs:** Any code path that mints the opaque session cookie directly inside the `/login` POST handler (password step) instead of only inside the `/login/mfa` POST handler (or after an explicit "no MFA factor enrolled yet" check).

### Pitfall 2: Test suite breaks wholesale because auth is currently cookie-value-equality
**What goes wrong:** All of `test_ui_api.py`, `test_orders_api.py`, `test_alerts_api.py` (and any new handoff/audit tests) fail immediately once the SHA-256 cookie scheme is removed, because each file computes that exact token locally.
**Why it happens:** Auth-bypass-for-tests was never centralized; `conftest.py`'s `mock_db` fixture pattern (patch DB/WhatsApp seams) was never extended to auth.
**How to avoid:** Convert auth to a FastAPI dependency (`require_operator`) as in Pattern 1, then add a `conftest.py` fixture using `app.dependency_overrides[require_operator] = lambda: fake_operator` — this is the idiomatic FastAPI test pattern and requires editing three test files' fixtures once, centrally, instead of hand-computing a new token scheme in each.
**Warning signs:** Any new test file still importing `hashlib` to compute a session token.

### Pitfall 3: Tailwind Play CDN + Alpine.js core cannot run under a strict CSP
**What goes wrong:** Setting `script-src`/`style-src` to a nonce-only, no-`unsafe-inline`/no-`unsafe-eval` policy silently breaks the entire dashboard (Tailwind classes stop applying, Alpine components throw "Refused to evaluate a string as JavaScript" in the console) because `cdn.tailwindcss.com` (the Play CDN) injects `<style>` tags at runtime without a nonce, and Alpine core evaluates `x-data`/`x-show`/`x-on` expressions via `new Function()`.
**Why it happens:** Both are dev-convenience/runtime-JIT tools not designed for strict-CSP production use; Tailwind's own docs discourage the Play CDN in production for this and other reasons.
**How to avoid:** Accept `'unsafe-inline'` (style-src) and `'unsafe-inline' 'unsafe-eval'` (script-src) scoped to a tight `default-src 'self'` + explicit host allowlist for this phase (Pattern 7); treat migrating off the Play CDN (precompiled Tailwind CSS) and/or Alpine's dedicated CSP build (`@alpinejs/csp`, which requires switching from inline `x-data="alertsApp()"` functions to `Alpine.data()` registration) as a follow-up, not part of this phase's scope.
**Warning signs:** A CSP that looks "textbook strict" (nonce-only, no unsafe-*) — verify it against the actual rendered `alerts.html`/`orders.html` in a browser before considering the security-headers task done, not just against a CSP linter.

### Pitfall 4: Built-in Supabase email has a 2-emails-per-hour project-wide limit
**What goes wrong:** Testing the "forgot password" flow (or MFA-recovery-adjacent flows that send email) repeatedly during development/QA hits `over_email_send_rate_limit` almost immediately, which can look like a bug in the app rather than a platform limit.
**Why it happens:** Supabase's built-in email provider intentionally rate-limits to 2 emails/hour per project unless a custom SMTP provider is configured (verified via `supabase.com/docs/guides/auth/rate-limits`).
**How to avoid:** With only 2 operator accounts, this limit is unlikely to matter in steady-state production use, but plan/test password-reset flows with this in mind (don't write an automated test that repeatedly triggers real reset emails against the live project); if reset emails become a recurring dev friction point, configure custom SMTP in the Supabase dashboard (a platform-config change, not app code).
**Warning signs:** `AuthApiError` with `code == "over_email_send_rate_limit"`.

### Pitfall 5: `audit_logs.actor` already has a different meaning for existing rows
**What goes wrong:** The operator-facing "who did what" audit trail accidentally includes existing `order_created` rows where `actor` is a **customer's phone number** (written by the `create_order_atomic` Postgres function in `20260614000002_atomic_order.sql`), confusing operator actions with customer actions in the same table.
**Why it happens:** `audit_logs` predates this phase and is already in use for a broader "business + security events" purpose, not exclusively operator actions.
**How to avoid:** Filter the audit-trail UI query by an explicit allowlist of operator-action `action` values (e.g. `login_success`, `login_failed`, `order_status_changed`, `product_created`, `product_updated`, `product_deleted`, `broadcast_sent`, `handoff_resolved`, `mfa_enrolled`, `session_revoked`) rather than trying to distinguish "operator" vs "customer" rows by the shape of `actor`.
**Warning signs:** The audit page showing a phone number as the actor for an entry that isn't a login.

### Pitfall 6: Conflict detection has no existing locking primitive to build on
**What goes wrong:** Attempting a "proper" distributed lock (row versioning across `orders` + `sessions` + the AI tool-call path) turns into a disproportionately large sub-project for a 10-30-orders/day shop.
**Why it happens:** Nothing in the current schema tracks "who/what last touched this record and when" beyond `updated_at`; there's no `version` column, no advisory locks, no per-order actor.
**How to avoid:** Use a cheap heuristic instead of true locking: before applying a dashboard status change, check `sessions.updated_at` (or `chat_history.created_at`) for that phone — if the bot has been active in the last few minutes, surface a "the bot is currently talking to this customer" confirmation to the operator rather than silently applying the change. This satisfies "detect the overlap and let her pick the winner" without a schema redesign. An optimistic-concurrency `UPDATE ... WHERE id = %s AND updated_at = %s` (checking affected-row-count) is a reasonable, low-cost complement for the pure "two operators/two dashboard tabs" race, if desired.
**Warning signs:** A plan task that proposes adding row-level locking or a distributed lock manager for this — disproportionate for the actual failure mode described in CONTEXT.md (a human and a bot, not two concurrent humans).

## Code Examples

### Reading TOTP factor id for challenge_and_verify (after password step)
```python
# Source: supabase_auth/_sync/gotrue_mfa_api.py (installed package, read directly)
factors = client.auth.mfa.list_factors()
totp_factor = next((f for f in factors.totp), None)  # verified TOTP factors only
if totp_factor is None:
    # No MFA enrolled yet — this account has skipped assisted enrollment; decide product
    # behavior explicitly (block login vs. allow + prompt enrollment) rather than defaulting.
    ...
```

### Admin: create the two operator accounts (one-off setup script, not a dashboard feature)
```python
# scripts/create_operator_accounts.py — run once, manually, by Khaled
from supabase import create_client
admin = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)  # service_role
admin.auth.admin.create_user({
    "email": "aunt@example.com",
    "password": "<temporary — she resets via emailed link>",
    "email_confirm": True,           # skip confirmation email; she doesn't need to click a link
    "app_metadata": {"role": "aunt"},
})
admin.auth.admin.create_user({
    "email": "khaled@example.com",
    "password": "<temporary>",
    "email_confirm": True,
    "app_metadata": {"role": "admin"},
})
```
Source: `AdminUserAttributes` fields read directly from `supabase_auth/types.py`.

### Admin sign-out by scope (available, but not the recommended revoke path)
```python
# Source: supabase_auth/_sync/gotrue_admin_api.py
admin.auth.admin.sign_out(jwt, scope="global")  # scope: "global" | "local" | "others"
```
Not used by this phase's recommended design (Pattern 5 makes the opaque table authoritative instead), but documented here because it's the only session-scoped admin primitive Supabase Auth actually exposes — useful context for why "list/revoke sessions via Supabase" was rejected in favor of the app's own table.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Shared-password cookie (`SHA-256(SECRET_KEY:DASHBOARD_PASSWORD)`) | Per-operator Supabase Auth identity + opaque server session | This phase | Enables per-operator audit trail, revocation, MFA — none of which are possible with a single shared secret |
| No CSRF protection on any mutating route | `starlette-csrf` double-submit cookie, scoped via `sensitive_cookies` | This phase | Closes a real gap: every existing `POST /api/...` route is currently forgeable from any page that can get the operator's browser to issue a request |
| `/alerts` shows raw job/event technical fields | Plain-Arabic, customer-named, action-oriented cards with a details toggle | This phase | Matches the aunt's actual workflow (she needs to know *who* to message, not `attempts: 2/3`) |

**Deprecated/outdated:**
- Tailwind's "Play CDN" (`cdn.tailwindcss.com`) is explicitly documented by Tailwind as not intended for production use (no CSP compatibility, larger payload, no purging) — kept in this phase only because migrating off it is out of scope; flagged as a follow-up.

## Open Questions

1. **What is Phase 3's `HandoffService` public interface at the time Phase 5 actually executes?**
   - What we know: the current (stale, per STATE.md) `03-01-PLAN.md` specifies only `HandoffService.trigger(phone, reason, metadata)`.
   - What's unclear: whether Phase 3 gets re-planned before execution, and if so whether the method name/signature changes, and whether a `resolve()`/`return_to_bot()` method gets added there instead of in Phase 5.
   - Recommendation: Phase 5's plan should read `app/services/handoff.py` (or its Phase-3 SUMMARY.md) as a first task step and adapt to whatever interface actually exists, rather than hardcoding an assumed signature; if Phase 3 hasn't executed at all, Phase 5 should hard-stop with a clear message rather than re-implementing pause/trigger logic in parallel.

2. **Should the Supabase Auth calls use the service_role key (already configured) or a new anon key for non-admin operations?**
   - What we know: `Config` today only has `SUPABASE_KEY` (service_role); the app is server-only (browser never talks to Supabase directly), so using service_role for `sign_in_with_password`/MFA calls would technically work since the key never reaches a browser.
   - What's unclear: whether Supabase Auth's rate-limiting/behavioral differences (if any) between anon-keyed and service-role-keyed callers for non-admin endpoints matter here — not verified either way in this research pass.
   - Recommendation: add a `SUPABASE_ANON_KEY` env var and use it for the non-admin auth surface (`sign_in_with_password`, `mfa.enroll/challenge/verify`, `reset_password_email`), reserving the existing service_role key strictly for `auth.admin.*` calls — this is the conventional separation Supabase's own docs assume, and costs one new env var.

3. **Password-reset flow type (implicit vs PKCE) for a server-rendered app.**
   - What we know: `supabase-py`'s `ClientOptions.flow_type` defaults to `"pkce"` in this installed version (2.28.3), and `exchange_code_for_session(params)` exists to handle a `?code=` query param (server-friendly), as opposed to the implicit flow's URL-fragment token (which a server-rendered page cannot read at all, since fragments never reach the server).
   - What's unclear: exact redirect-page wiring (what the `redirect_to` URL in `reset_password_email(email, options={"redirect_to": ...})` should point to, and how that page then calls `exchange_code_for_session`) wasn't traced end-to-end in this research pass.
   - Recommendation: the planner should design the reset-password landing route explicitly around PKCE (`?code=` query param → `exchange_code_for_session` → force a password-change form → mint a fresh opaque session), and treat this as one of the plan's concrete tasks, not an afterthought.

## Sources

### Primary (HIGH confidence)
- Local repository, read directly: `app/routers/ui.py`, `app/routers/ui_api.py`, `app/routers/broadcast.py`, `app/routers/whatsapp.py`, `app/routers/debug.py`, `app/main.py`, `app/db/database.py`, `app/services/config.py`, `app/services/processor.py`, `app/templates/alerts.html`, `app/templates/orders.html`, `app/templates/login.html`, `tests/conftest.py`, `tests/integration/test_ui_api.py`
- Local repository migrations, read directly: `supabase/migrations/20260614000000_baseline.sql`, `20260614000001_durable_messaging.sql`, `20260614000002_atomic_order.sql`, `20260614000003_security_rls.sql`, `20260615000000_add_paused_to_sessions.sql`
- `.planning/phases/03-agent-dependability-safety/03-01-PLAN.md`, `03-02-PLAN.md`, `03-03-PLAN.md` — read in full
- `.planning/STATE.md` — read in full (Phase 3 staleness/non-execution confirmed here)
- Installed package source, read directly (version 2.28.3, matching `requirements.txt`'s `supabase>=2.0.0`): `supabase_auth/_sync/gotrue_client.py`, `gotrue_mfa_api.py`, `gotrue_admin_api.py`, `gotrue_admin_mfa_api.py`, `types.py`, `errors.py`; `supabase/lib/client_options.py`
- `supabase.com/docs/guides/auth/auth-mfa/totp` (WebFetch) — AAL1/AAL2 model, challenge/verify flow
- `supabase.com/docs/guides/auth/rate-limits` (WebFetch) — 2 emails/hour built-in provider limit, 15 req/hour MFA challenge/verify limit

### Secondary (MEDIUM confidence)
- `raw.githubusercontent.com/frankie567/starlette-csrf/master/README.md` (WebFetch) — `CSRFMiddleware` constructor parameters, double-submit cookie mechanics
- `pypi.org/pypi/starlette-csrf/json` (WebFetch) — current version 3.0.0, dependency constraints
- WebSearch, cross-referenced across `alpinejs.dev/advanced/csp`, `securinglaravel.com`, `docs.hyva.io` — Alpine.js core requires `unsafe-eval`; CSP build (`@alpinejs/csp`) exists but requires `Alpine.data()` registration instead of inline expressions
- WebSearch, cross-referenced via `github.com/tailwindlabs/tailwindcss/discussions/13326` and `tailwindcss.com/docs/installation/play-cdn` — Play CDN is not nonce-compatible and not recommended for production

### Tertiary (LOW confidence)
- None retained as authoritative in this document — all findings above were either verified against installed package source/official docs or explicitly flagged as this-research's-own-synthesis (the two-round-trip login bridging design in Pattern 2) rather than a copied official example.

## Metadata

**Confidence breakdown:**
- Standard stack (Supabase Auth API surface, starlette-csrf): HIGH — verified against installed package source and official README/PyPI, not training-data recall
- Architecture (opaque sessions, CSRF scoping, headers middleware): MEDIUM-HIGH — internally consistent with verified primitives, but the exact table/module design is this research's synthesis, not copied from an official Supabase "server-rendered app" reference (none exists)
- Pitfalls: HIGH for codebase-derived pitfalls (test breakage, duplicated auth, audit_logs reuse, Phase 3 non-execution — all read directly); MEDIUM for CSP/Tailwind/Alpine pitfall (WebSearch cross-referenced, not Context7-verified since Context7 was unavailable in this environment)

**Research date:** 2026-08-28
**Valid until:** ~30 days for the codebase facts (re-verify if Phase 3 or the hardening branch merges before Phase 5 executes — STATE.md already flags Phase 3's plans as stale once); Supabase Auth API surface is stable (GA feature) but re-check `supabase-auth` version if `requirements.txt`'s pin changes materially from 2.28.3.
