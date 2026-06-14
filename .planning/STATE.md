# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-14)

**Core value:** A real customer can place an order on the live WhatsApp number and the aunt can fulfill it — reliably and unattended.
**Current focus:** Phase 1 — Spine Smoke-Thread

## Current Position

Phase: 1 of 6 (Spine Smoke-Thread)
Plan: 0 of TBD in current phase
Status: Ready to plan
Last activity: 2026-06-14 — Roadmap created for M1 (Supabase → prod), 13 requirements mapped to 6 phases

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**
- Total plans completed: 0
- Average duration: — min
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**
- Last 5 plans: —
- Trend: —

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [M1]: Smoke-thread first (vertical MVP) — prove the real spine (Phase 1) before hardening layers underneath it
- [M1]: Secure the RPC/key surface, not cargo-culted RLS — access is server-side only (informs Phase 4)
- [M1]: Supabase free tier now → Pro PITR ~July 2026; script a nightly export now as cheap insurance (informs Phase 5)

### Pending Todos

None yet.

### Blockers/Concerns

Carried from .planning/codebase/CONCERNS.md (drive M1 work):
- 🔴 Webhook POST cannot parse real Meta payloads — addressed in Phase 1
- 🔴 `monthly_snapshots` table queried but missing from schema — addressed in Phase 2
- 🟡 `chat_history` / `retry_queue` grow unbounded — addressed in Phase 6

## Deferred Items

Items acknowledged and carried forward (M2–M5 — future GSD milestone cycles, not this roadmap):

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| M2 FastAPI | Webhook signature verification, full Meta-envelope parsing, rate limiting, health checks, idempotency | Deferred | 2026-06-14 |
| M3 Agent | AI reliability/fallbacks, Claude cost control, eval harness, knowledge base, `info N` fix | Deferred | 2026-06-14 |
| M4 UI | Kill insecure defaults, secure cookie, login rate-limiting, input validation | Deferred | 2026-06-14 |
| M5 Go-live | E2E test, monitoring/alerting, Meta WABA approval, SSL/domain, customer cutover | Deferred | 2026-06-14 |

### Parked branches (M3 inputs — do NOT merge into M1)

Unmerged agent branches found 2026-06-14; evaluated as M3 material, parked to keep M1 focused:

| Branch | Date | Contents | Use in M3 |
|--------|------|----------|-----------|
| `origin/claude/project-architecture-overview-18sf0c` | 2026-06-11 | Latency optimization (batched DB context, reply-first persistence, prompt caching) in `whatsapp.py`/`ai_service.py`/`whatsapp_helpers.py`; `docs/PROJECT_LEARNINGS.md`; tests | AI reliability + Claude cost control; review before M3 planning |
| `origin/claude/project-memory-notes-PRVo7` | 2026-06-06 | Eval-dataset research (Israeli-Arabic dialect, 50K dataset plan); `MEMORY.md` | Eval harness foundation (pairs with `tests/data/whatsapp_agent_dataset.json`) |

Junk (safe to delete): `copilot/vscode-mpshk5w7-eqtp` (2026-05-30) — stale context dump, mangled `AGENTS.md` ("Codex Haiku", "Wave invoicing"), `project_dump.txt`, guidelines PDF.

## Session Continuity

Last session: 2026-06-14
Stopped at: Roadmap + STATE created; REQUIREMENTS traceability filled (13/13 mapped)
Resume file: None
