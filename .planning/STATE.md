# Project State: ALYASMEEN AuntOps Production Readiness

## Project Reference
**Core Value**: Customers can reliably place and manage real orders through WhatsApp, while the aunt retains clear control over exceptions and can operate the business without technical assistance.
**Current Focus**: Phase 4 (Reliability & Ops Completion) is COMPLETE (7/7 plans). Phase 3 (Agent Dependability & Safety) plans need re-verification before execution.

## Current Position
- **Phase**: 5 (Operator Security & UX) — IN PROGRESS (waves 1-2 of 7 COMPLETE — 05-01, 05-02, 05-03 done; 3/10 plans). Phase 4 is COMPLETE (7/7 plans). Phase 3 (planned, NOT yet executed) still pending plan re-verification.
- **Status**: 🟢 Phase 4 done — live rollout (service_role, migrations, worker persistence, backup drill) verified against production. 🟢 Phase 5 waves 1-2 complete: 05-01 (app/services/sessions.py + operator_sessions/trusted_devices/pending_logins migration, not yet applied live), 05-02 (app/services/auth.py Supabase Auth wrapper + scripts/manage_operators.py), and 05-03 (auth_deps.py + auth_routes.py wire the two together into real email+password+TOTP login, replacing the shared-password cookie everywhere) all done. Ready for wave 3 (05-04, CSRF + security headers). 🟡 Phase 3 plans stale — re-verify before executing (see below).
- **Progress**: [██████----] ~58% (15/26 plans across all phases; Phase 5: 3/10)

## Accomplishments (2026-08-25 hardening session — outside GSD, branch `fix/production-hardening`)
A full multi-agent code review rated the implementation 5/10 and found 64 issues; the verified
ones were fixed in two Sonnet waves + follow-ups. All on branch `fix/production-hardening`
(9+ commits, NOT merged to main, NOT pushed). Suite: 250+ green.
- [x] Webhook poison-pill events dead-letter after 3 attempts (`webhook_events.attempts`, migration `20260825000000`).
- [x] Malformed webhook payloads persist instead of crashing; global handler no longer masks /whatsapp/ failures as 200.
- [x] **Outbox wired as the single send path**: `queue_text`/`queue_buttons` in `processor.py` → `outbox_jobs` → poller with bounded attempts. Only `process_job` (and standalone scheduler services) call senders directly.
- [x] `whatsapp_meta.py` senders raise `WhatsAppSendError` on non-2xx (failures were silently swallowed).
- [x] Arabic confirm (تأكيد/اكد/أكد/تم) + restored clear command; order-number unwrap; qty clamp; AI-failure Arabic fallback; address-persistence bug fixed (delivery orders were losing their address).
- [x] Retired model default → `claude-haiku-4-5-20251001`; hardcoded credential fallbacks removed (fail-fast); Anthropic 30s timeout; catalog 60s TTL (worker staleness).
- [x] Dashboard: stored-XSS escaped, broadcast send fixed + authenticated, Secure cookie.
- [x] Invoice fully Arabic (Amiri font + reshaper/bidi, render-verified); RLS grant fix + `monthly_snapshots` migrations.
- [x] Test suite repaired: collection fixed, conftest rewritten for processor architecture, 5 stale files ported, debug router gated to dev.

## ⚠️ Phase 3 plans are stale
`03-01/02/03-PLAN.md` were written BEFORE the hardening session. `processor.py`, `config.py`,
`ai_service.py`, `whatsapp_meta.py`, and the test seams all changed. Before executing:
re-run `/gsd:plan-phase 3` (or at minimum the plan checker) against the current branch.

## Technical Debt / Risks
- ~~`retry_queue.py` (enqueue never called) is dead code claiming to run~~ → **Phase 4 criterion 1 resolved** (plan 04-04): `retry_queue.py`/`retry_actions.py` deleted entirely, the 15-minute scheduler job removed from `app/worker.py`, retirement documented in `supabase/migrations/20260825000003_retire_retry_queue.sql` (COMMENT ON TABLE, not DROP — table is already RLS-locked deny-all). `gatekeeper.py` is **no longer dead code** either — rewritten synchronous (plan 04-02) and wired into every outbound Claude call (`ai_service.py`) and every real-mode WhatsApp send (`whatsapp_meta.py`).
- ~~Migrations not yet applied to live Supabase; anon-vs-service_role key decision open~~ → **Phase 4 criterion 2 resolved** (plan 04-07, live): `SUPABASE_KEY=service_role` on Railway (web+worker) and local `.env`, verified end-to-end before `20260825000004_revert_anon_grants.sql` shipped; all 11 migrations applied live via `supabase db push` after repairing stale remote migration history and non-destructively renaming aside two drifted tables from the retired June architecture (`webhook_events_oldjune`/`outbox_jobs_oldjune`, 8 stale rows preserved — recommend dropping once confident).
- ~~Worker job store falls back to MemoryJobStore without `DATABASE_URL`~~ → **Phase 4 criterion 3 resolved** (plan 04-07, live): a Railway **worker** service now exists (Procfile `worker:` alone didn't auto-provision one — created manually with `python -m app.worker`, fixing a broken `python app/worker.py` invocation along the way) with `DATABASE_URL` set; `apscheduler_jobs.next_run_time` for `monthly_report` verified identical before/after a real worker restart. Cosmetic gap: structlog "Using SQLAlchemyJobStore" line not visible in Railway's log viewer (persistence itself independently confirmed via the live table; logging config fix deferred).
- ~~No dashboard visibility for dead-lettered events / failed outbox jobs~~ → **Phase 4 criterion 4 resolved** (plans 04-05 + 04-06): `GET /api/alerts` + retry endpoints in `ui_api.py`, consumed by `app/templates/alerts.html` (`/alerts` page, 5th nav tab "تنبيهات" wired into all 5 dashboard templates) — operator can see and one-click retry both dead-lettered `webhook_events` and permanently-failed `outbox_jobs`.
- ~~Backup/restore drill never actually executed~~ → **Phase 4 criterion 5 resolved** (plan 04-07, live): real drill run with native `pg_dump -n public` (Docker unavailable for `supabase db dump`) restored into a throwaway project via `psql`; verification counts matched production exactly; row recorded in `docs/BACKUP_DRILL.md`'s Drill Log; throwaway project deleted.
- Async latency: outbox adds ≤2s to replies (poll interval) on top of the 3s inbox poll; acceptable at current volume, monitor in pilot.
- Railway build now pinned to Nixpacks via `railway.json` (Railpack's default builder failed on an unrelated mise python-attestation error) — revisit if Railway fixes Railpack upstream.
- `webhook_events_oldjune`/`outbox_jobs_oldjune` exist live with no corresponding migration file (necessarily a one-off live remediation, not a repeatable schema change) — operator should drop them once confident the 8 old rows aren't needed, or a future light migration can formalize the drop.

## Todos & Blockers
- [ ] **TODO**: Merge `fix/production-hardening`'s final 2 commits (`f8d4bf7`, `780649e`) to `main` — everything through `0f9af1c` is already merged via PRs #5/#6.
- [ ] **TODO**: Re-verify Phase 3 plans against the hardening branch, then `/gsd:execute-phase 3`.
- [ ] **TODO** (deploy): Update `WA_META_TOKEN` (new system user token). `SECRET_KEY`/`DATABASE_URL`/`SUPABASE_KEY` are already set live on Railway (confirmed in plan 04-07); `DASHBOARD_PASSWORD` was retired by plan 05-03 (dashboard auth is now per-operator email+password + TOTP) — `SUPABASE_ANON_KEY` must be set live instead before 05-09's rollout (not yet configured anywhere, including locally — see 05-02/05-03 SUMMARYs).
- [ ] **BLOCKER**: Meta WABA registration still pending.

## Session Continuity
- **Last Action**: Executed plan `05-03-PLAN.md` (wave 2, depends on 05-01+05-02) — wired the two together into the real login flow, replacing the shared-password cookie everywhere it was checked. New `app/routers/auth_deps.py` (`require_operator`/`require_operator_page`/`require_admin`/`optional_operator`) replaces the hand-rolled `_is_authenticated()` copy-pasted in `ui.py`/`ui_api.py`/`broadcast.py` with one router-level `Depends(...)` each. New `app/routers/auth_routes.py` implements `GET+POST /login`, `POST /login/mfa`, `GET /logout`, `POST /logout-all` — a session cookie is minted only after identity is fully established (no MFA enrolled yet, a still-trusted device, or a verified TOTP code); a `mfa_required=True` sign-in with no trusted device never sets it, only a short-lived pending-login cookie (the anti-regression case `test_auth_flow.py` covers explicitly). `login.html` rewritten to email+password; new `mfa_challenge.html` for the TOTP step. `Config.DASHBOARD_PASSWORD` removed entirely (repo-wide grep clean except the immutable `ALYASMEEN/raw/` snapshot). `tests/conftest.py` gained `client`/`operator_client`/`admin_client` fixtures via `app.dependency_overrides`, replacing every hand-computed session cookie across the test suite (three integration files migrated + one new `test_auth_flow.py`, 8 tests). Full suite: 290 passed/3 skipped. Commits: `ec38816`, `26097ea`, `4377d16`. Full interface (route table, dependency names, fixture names) recorded in `05-03-SUMMARY.md` so 05-04/05-05/05-07/05-09 don't need to re-read the source. **Wave 2 is now fully complete.**
- **Next Step**: Continue `/gsd:execute-phase 5` with wave 3 (`05-04-PLAN.md`, depends on 05-03 — CSRF protection + security headers, per REQ-prod-csrf/REQ-prod-sec-headers; note 05-03 left a `sensitive_cookies`-scoped CSRF gap deliberately for 05-04 to fill, plus its own dedicated CSRF test). `/login/reset-request` is referenced by `login.html` but not yet implemented — 05-09 owns it (`app/services/auth.py`'s `send_password_reset()` already exists from 05-02). Also still pending: re-verify Phase 3 plans against the hardening branch (`03-01/02/03-PLAN.md` predate it) then `/gsd:execute-phase 3` — Phase 5's handoff UI works without Phase 3 (soft dependency, seeded via /dev/test_handoff), but real handoff triggers arrive only with Phase 3.
