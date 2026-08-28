# Web Dashboard

**Summary**: The aunt-facing web UI (`app/routers/ui.py` + `app/templates/`) — login, orders, dashboard stats, and product management, sharing one premium RTL design system. Login/logout now live in `app/routers/auth_routes.py`, guarded by `app/routers/auth_deps.py` against the opaque `operator_sessions` store (`app/services/sessions.py`).

**Sources**: raw/project-claude-md.md, app/routers/ui.py, app/routers/ui_api.py, app/routers/auth_routes.py, app/routers/auth_deps.py, app/templates/

**Graph**: community "Web Dashboard UI Router" (pre-Phase-5; `_is_authenticated()` god node retired by the 05-03 auth rewrite — see note below); hyperedge "Five dashboard templates sharing the premium RTL design system"

**Last updated**: 2026-08-28 (05-03: shared-password cookie replaced with per-operator email+password + TOTP MFA)

---

A custom FastAPI + Jinja2 dashboard replaced AppSheet entirely. (source: app/routers/ui.py)

## Pages

| URL | What it does |
|-----|--------------|
| `/login` | Email + password login (Arabic RTL); `POST /login/mfa` handles the TOTP step |
| `/orders` | Order list — customer name headline, inline products, WhatsApp link, action buttons |
| `/dashboard` | Monthly stats, 30-day chart, status donut, top 5 products |
| `/products` | Add / edit / toggle / delete products |
| `/logout` | Revoke only this session (other signed-in devices stay signed in) |
| `/logout-all` | Revoke every session for this operator ("log out everywhere") |

JSON APIs back each page (`/api/orders`, `/api/dashboard/stats`, `/api/products`, …).

## Auth (rewritten in phase 5 / plan 05-03)

As of 2026-08-28 the old scheme — every router hand-computing
`sha256(f"{SECRET_KEY}:{DASHBOARD_PASSWORD}")` and comparing it to the `alyasmeen_session`
cookie via a locally-defined `_is_authenticated()` — is gone. (source: app/routers/auth_deps.py)

The new flow:
1. `POST /login` (email + password) → `app/services/auth.py`'s `sign_in()`, a thin wrapper
   over Supabase Auth's password grant that always follows up with an AAL
   (authenticator-assurance-level) check, so a verified TOTP factor can never be silently
   bypassed by the password grant alone.
2. If a verified TOTP factor exists and the browser has no live "remembered device" cookie,
   the response is the MFA challenge page instead of a session — `POST /login/mfa` verifies
   the code via the same module's `verify_totp()`.
3. Only after identity is fully established (no MFA enrolled, remembered device, or a
   verified code) does `app/services/sessions.py`'s `create_session()` mint an **opaque**
   token; only `sha256(raw_token)` is ever stored, in the new `operator_sessions` table.
4. Every request resolves that cookie back to an `Operator` via
   `app/routers/auth_deps.py`'s `require_operator` (APIs → 401) / `require_operator_page`
   (pages → 303 to `/login`) — both are router-level FastAPI dependencies now, not a
   per-handler `if not _is_authenticated(...)` check repeated in three files.

(source: app/routers/auth_routes.py, app/routers/auth_deps.py, app/services/auth.py,
app/services/sessions.py)

## Design system

All five templates (login, orders, dashboard, products, broadcast) share one premium RTL
design language — primary green `#006948`, Material Symbols icons, glassmorphism navbar,
20px-radius cards. Do not revert to the old `#059669` green or DaisyUI classes.
(graph: hyperedge "Five dashboard templates sharing the premium RTL design system";
source: raw/project-claude-md.md)

## Order status labels (Arabic)

`to_do` → يجب التجهيز · `ready` → جاهز · `delivered` → في الطريق · `done` → مكتمل

## Related pages

- [[database-tables]]
- [[supabase-data-layer]]
- [[alyasmeen-auntops]]
- [[graph-overview]]
