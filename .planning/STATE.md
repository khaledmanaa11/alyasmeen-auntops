# Project State: ALYASMEEN AuntOps Production Readiness

## Project Reference
**Core Value**: Customers can reliably place and manage real orders through WhatsApp, while the aunt retains clear control over exceptions and can operate the business without technical assistance.
**Current Focus**: Phase 3 (Agent Dependability & Safety) — plans need re-verification first; Phase 4 (Reliability & Ops Completion) needs planning.

## Current Position
- **Phase**: 3 (Agent Dependability & Safety) — planned, NOT yet executed; Phase 4 inserted 2026-08-25.
- **Status**: 🟡 Phase 3 plans stale — re-verify before executing (see below).
- **Progress**: [██████----] ~45%

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
- Migrations not yet applied to live Supabase; anon-vs-service_role key decision open → Phase 4 criterion 2.
- Worker job store falls back to MemoryJobStore without `DATABASE_URL` → Phase 4 criterion 3. **Mechanism now proven** (`tests/integration/test_scheduler_persistence.py`, plan 04-03); the live Railway `DATABASE_URL` step itself is still pending — operator checkpoint in plan 04-07.
- No dashboard visibility for dead-lettered events / failed outbox jobs → Phase 4 criterion 4. **Backend API done** (plan 04-05): `GET /api/alerts` + retry endpoints in `ui_api.py`. Dashboard UI to consume it is plan 04-06.
- Async latency: outbox adds ≤2s to replies (poll interval) on top of the 3s inbox poll; acceptable at current volume, monitor in pilot.

## Todos & Blockers
- [ ] **TODO**: Merge/push `fix/production-hardening` (user decision).
- [ ] **TODO**: Continue `/gsd:execute-phase 4` — plans 04-01/04-02/04-03/04-04/04-05 done, 04-06 and 04-07 remain.
- [ ] **TODO**: Re-verify Phase 3 plans against the hardening branch, then `/gsd:execute-phase 3`.
- [ ] **TODO** (deploy): Set `DASHBOARD_PASSWORD`, `SECRET_KEY` in Railway — app now refuses to start without them. Set `CLAUDE_MODEL` or accept new default. Update `WA_META_TOKEN`. Set `DATABASE_URL` (Session Pooler, postgresql:// — see .env.example) so the worker job store survives restarts.
- [ ] **BLOCKER**: Meta WABA registration still pending.

## Session Continuity
- **Last Action**: Executed Phase 4 Plan 05 (alerts API — `GET /api/alerts` + `POST /api/alerts/{webhook_events,outbox_jobs}/{id}/retry` in `ui_api.py`, backing Success Criterion 4) — 254 passed/3 skipped, commits `4d9bc25`, `b37c207`.
- **Next Step**: `/gsd:execute-phase 4` to continue with remaining plans (04-06 dashboard alerts UI, 04-07 operator checkpoints).
