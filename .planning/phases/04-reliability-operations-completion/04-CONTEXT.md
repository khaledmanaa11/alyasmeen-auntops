# Phase 4 Context: Reliability & Operations Completion

**Captured**: 2026-08-25 (inline during /gsd:plan-phase 4 — three targeted questions in lieu of full discuss-phase)

## Decisions (LOCKED — user chose these explicitly)

1. **Delete `retry_queue.py`** (and `retry_actions.py` if nothing else uses it after migration).
   The outbox (`outbox_jobs` + `process_outbox_jobs`) becomes the single retry mechanism.
   Scheduler services (PDF invoice on done, follow-ups, monthly report) must enqueue into
   `outbox_jobs` instead of calling senders directly + queueing failures into `retry_queue`.
   Note: this needs a new outbox job kind for PDF invoices (payload can't hold raw bytes —
   store order_id and regenerate the PDF in `process_job`, or store a reference). Remove the
   `retry_queue` table from active use (drop or deprecate via migration comment) and the
   15-min scheduler job.

2. **Rewrite `gatekeeper.py` synchronous and wire it in.** The user explicitly wants real
   rate limiting on outbound Claude and Meta calls (chose this over deletion). Requirements:
   - Synchronous API callable from the worker's blocking loops (no asyncio).
   - Bounded waiting — must never stall the single worker indefinitely (the current
     unbounded `while not bucket.is_allowed(): sleep(...)` loop is unacceptable; fail or
     defer the job instead).
   - Config stays in `config/rate_limits.json` (services: `claude_ai`, `whatsapp`).
   - Wire into `ai_service.generate_reply`/`improve_message` (Claude) and the four
     `whatsapp_meta` senders (Meta). Keep the existing unit tests' intent; port them to
     the sync API.

3. **Switch the app to the Supabase `service_role` key.**
   - Railway env `SUPABASE_KEY` will hold the service_role key (user action; plan must
     include the checklist item and verification step).
   - Revert the anon re-grant: new migration that revokes EXECUTE on `run_query`/`run_exec`
     from `anon`/`authenticated` again (undoing `20260825000001_fix_rpc_grants.sql`),
     leaving RLS locked for anon. Document the decision in the migration header and
     CLAUDE.md's DB section.
   - Local dev/.env gets the service_role key too (single code path).

## Claude's Discretion

- Dead-letter dashboard UX: where the dead-lettered `webhook_events` and failed
  `outbox_jobs` surface (existing orders page card vs. new tab), and the retry interaction —
  follow the existing design system (#006948, Material Symbols, Arabic RTL).
- Outbox kind/payload design for invoice jobs.
- How the worker-restart persistence check is verified (script vs documented manual drill).
- Backup drill execution details (Supabase CLI vs dashboard export) — but the drill must
  actually run and the Drill Log must record a real result.

## Deferred Ideas (out of scope for Phase 4)

- MFA / session hardening (Phase 5), CSRF, security headers.
- Policy gate / handoffs / eval harness (Phase 3).
- CI/CD pipeline (tracked for go-live phase).
- The 69MB `tests/data/whatsapp_agent_dataset_noisy.json` in git history (flagged during
  push; cleanup is a separate chore, not a Phase 4 criterion).
