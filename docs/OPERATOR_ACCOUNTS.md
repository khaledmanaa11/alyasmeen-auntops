# Operator Accounts & MFA Runbook

**Status (2026-08-28):** the full identity stack is BUILT and merged on
`fix/production-hardening` — login + TOTP challenge (05-03), CSRF/security headers (05-04),
and the `/account` enrollment/session page (05-09). The `operator_auth` migration
(`20260828000000` — `operator_sessions`/`trusted_devices`/`pending_logins`) is **applied to
the live Supabase project** and verified reachable (three zero counts). `SUPABASE_ANON_KEY`
and `DASHBOARD_BASE_URL` are set in the local `.env`; `DASHBOARD_PASSWORD` is deleted locally.

**Update (2026-08-30):** the **admin account is CREATED live** — k***3@gmail.com, role
`admin`, zero MFA factors yet; the temporary password was delivered out of band and must be
changed at first sign-in. `ADMIN_PHONE` (972545356863) and `AUNT_PHONE` (972548138114) are
set in the local `.env`.

**Still pending (human, plan 05-10):** the aunt's account (waiting on her email address),
the three env vars (`SUPABASE_ANON_KEY`, `ADMIN_PHONE`, `DASHBOARD_BASE_URL`) on BOTH
Railway services, the deploy (push only after the Railway vars are confirmed — the new code
needs the anon key to serve logins), `DASHBOARD_PASSWORD` deletion on Railway (only AFTER
the new build is live — the currently-deployed old code still authenticates with it), and
the assisted TOTP enrollment below.

## The two-account model

| Account | Role | Purpose |
|---------|------|---------|
| The aunt | `aunt` (operator) | Runs the dashboard day to day — orders, products, broadcasts, handoffs. |
| Khaled | `admin` | Everything the aunt can do, plus recovery: creating accounts, resetting a lost-phone MFA factor, viewing/revoking the aunt's active sessions, receiving every failure alert. |

Both are real Supabase Auth users identified by real email addresses — not a shared
password. `app_metadata.role` (`"aunt"` or `"admin"`) is what `app/services/auth.py`'s
`AuthResult.is_admin` reads to decide which surfaces a signed-in operator can reach.

## Creating both accounts

Run once, from the project root, with `SUPABASE_KEY` (service_role) set in your
environment:

```bash
python scripts/manage_operators.py create --email aunt@example.com --role aunt
python scripts/manage_operators.py create --email khaled@example.com --role admin
```

Omit `--password` to auto-generate a strong temporary one — the script prints it exactly
once. `email_confirm=True` is always set, so neither account has to click a confirmation
email before their first login.

Verify both accounts exist:

```bash
python scripts/manage_operators.py list
```

## Assisted TOTP enrollment (the only way factors get added)

TOTP is never a forced self-serve wall. The dashboard only ever shows a QR code during
this explicit, assisted step:

1. Khaled sits with the aunt (in person or on a call).
2. She logs in with her email + temporary password at `/login`.
3. She opens `/account` and starts "enroll authenticator app."
4. The page shows a QR code (and a manual-entry secret as a fallback) — she scans it with
   her authenticator app (Google Authenticator, Authy, etc.).
5. She enters the first 6-digit code the app shows to confirm enrollment.

From this point on, `sign_in()` in `app/services/auth.py` will report
`mfa_required=True` on every future login for her account until a valid TOTP code is
supplied — the login route (05-03) must never mint a session while that flag is true.

There are no printed recovery codes. If she loses the device that holds the code, use the
lost-phone procedure below instead.

## Lost-phone / MFA recovery

If the aunt (or Khaled) loses the phone holding their authenticator app:

```bash
python scripts/manage_operators.py reset-mfa --email aunt@example.com
```

This deletes every MFA factor on that account via the service_role admin API
(`admin_delete_all_factors`) and prints a reminder that **all of that operator's dashboard
sessions must also be revoked** — the account is not fully secured again until both steps
are done. Until 05-09 ships the in-app "revoke all sessions" action tied to this event,
revoke them manually (or wait for that plan to land before running this in production).

After that, repeat the assisted enrollment steps above together — she is not left mid-way
with a factor-less account she can just log into unattended; the next login will simply
have `mfa_required=False` until she re-enrolls, so treat the window between reset and
re-enrollment as "sit down and finish this now," not "leave it open."

## Forgotten password

```bash
python scripts/manage_operators.py reset-password --email aunt@example.com
```

Sends a Supabase Auth password-reset email with a `redirect_to` pointing at
`{DASHBOARD_BASE_URL}/login/reset` (05-09 builds that landing route).

**Rate limit:** Supabase's built-in email provider allows only **2 emails/hour,
project-wide** (not per-account) unless custom SMTP is configured in the Supabase
dashboard. With only two operator accounts this is unlikely to matter in steady state,
but don't script repeated resets during testing — `over_email_send_rate_limit` errors are
a platform limit, not an app bug.

## Env vars this relies on

| Var | Used by |
|-----|---------|
| `SUPABASE_URL` | Both the anon and service_role clients. |
| `SUPABASE_KEY` (service_role) | `admin_*` functions in `app/services/auth.py` — account creation, listing, MFA factor deletion. Required for every `manage_operators.py` subcommand. |
| `SUPABASE_ANON_KEY` | The non-admin surface — `sign_in`, `verify_totp`, `enroll_totp`, `verify_enrollment`, `send_password_reset`. |
| `DASHBOARD_BASE_URL` | The password-reset email's `redirect_to` base. |
| `ADMIN_PHONE` | (05-09) New-device login alerts and every permanent-failure alert go to Khaled here. |
