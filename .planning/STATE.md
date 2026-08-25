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
- `retry_queue.py` (enqueue never called) and `gatekeeper.py` (unwired) are dead code claiming to run → Phase 4 criterion 1.
- Migrations not yet applied to live Supabase; anon-vs-service_role key decision open → Phase 4 criterion 2.
- Worker job store falls back to MemoryJobStore without `DATABASE_URL` → Phase 4 criterion 3.
- No dashboard visibility for dead-lettered events / failed outbox jobs → Phase 4 criterion 4.
- Async latency: outbox adds ≤2s to replies (poll interval) on top of the 3s inbox poll; acceptable at current volume, monitor in pilot.

## Todos & Blockers
- [ ] **TODO**: Merge/push `fix/production-hardening` (user decision).
- [ ] **TODO**: `/gsd:plan-phase 4` (Reliability & Ops Completion — success criteria in ROADMAP.md).
- [ ] **TODO**: Re-verify Phase 3 plans against the hardening branch, then `/gsd:execute-phase 3`.
- [ ] **TODO** (deploy): Set `DASHBOARD_PASSWORD`, `SECRET_KEY` in Railway — app now refuses to start without them. Set `CLAUDE_MODEL` or accept new default. Update `WA_META_TOKEN`.
- [ ] **BLOCKER**: Meta WABA registration still pending.

## Session Continuity
- **Last Action**: Outbox wiring completed + Phase 4 inserted into ROADMAP.md (2026-08-25).
- **Next Step**: `/gsd:plan-phase 4`, or re-verify Phase 3 plans (`/gsd:plan-phase 3`) and execute.
