# Project State: ALYASMEEN AuntOps Production Readiness

## Project Reference
**Core Value**: Customers can reliably place and manage real orders through WhatsApp, while the aunt retains clear control over exceptions and can operate the business without technical assistance.
**Current Focus**: Phase 4 (Reliability & Ops Completion) is COMPLETE (7/7 plans). Phase 3 (Agent Dependability & Safety) plans need re-verification before execution.

## Current Position
- **Phase**: 4 (Reliability & Ops Completion) — COMPLETE (7/7 plans, all 5 success criteria true in production). Phase 3 (planned, NOT yet executed) is next up, pending plan re-verification.
- **Status**: 🟢 Phase 4 done — live rollout (service_role, migrations, worker persistence, backup drill) verified against production. 🟡 Phase 3 plans stale — re-verify before executing (see below).
- **Progress**: [███████---] ~55%

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
- [ ] **TODO** (deploy): Update `WA_META_TOKEN` (new system user token). `DASHBOARD_PASSWORD`/`SECRET_KEY`/`DATABASE_URL`/`SUPABASE_KEY` are already set live on Railway (confirmed in plan 04-07).
- [ ] **BLOCKER**: Meta WABA registration still pending.

## Session Continuity
- **Last Action**: Closed out Phase 4 Plan 07 (live rollout checkpoint) — verified commit `d7bc7e0` (Task 1: revert-anon-grants migration + doc updates), documented the three live operator checkpoints (Task 2: Railway worker service + `DATABASE_URL` persistence proof; Task 3: `service_role` switch verified end-to-end; Task 4: all 11 migrations applied live + real backup/restore drill), wrote `04-07-SUMMARY.md`. **Phase 4 is now 7/7 complete — all 5 success criteria genuinely true in production.**
- **Next Step**: `/gsd:plan-phase 3` (re-verify/re-plan against the hardening branch — `03-01/02/03-PLAN.md` predate it) then `/gsd:execute-phase 3`. Phase 5 (Operator Security & UX) can also now be planned, since it depended on Phase 4's live-credential/migration work being real.
