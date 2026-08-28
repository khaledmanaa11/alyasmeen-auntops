-- ============================================================
-- ALYASMEEN AuntOps — Retire retry_queue (superseded by outbox_jobs)
-- ============================================================
--
-- retry_queue (created in 20260614000000_baseline.sql) was the original
-- error-retry mechanism for failed WhatsApp API calls and PDF-invoice
-- dispatch — enqueue() wrote rows here and app/services/retry_actions.py
-- dispatched them via a 15-minute scheduler job in app/worker.py.
--
-- Phase 4 built outbox_jobs (added in 20260614000001_durable_messaging.sql)
-- as the single durable-send mechanism for every outbound message and
-- action, including the PDF invoice action retry_queue used to dispatch.
-- Plan 04-01 migrated every retry_queue caller (follow-ups, the monthly
-- report, and the dashboard's ready/delivered/done order-status sends) onto
-- outbox_jobs's pdf_invoice job kind and queue_text calls. Plan 04-04 then
-- deleted app/services/retry_queue.py and app/services/retry_actions.py
-- entirely and unwired the 15-minute job from app/worker.py. As of this
-- migration, no application code reads or writes the retry_queue table.
--
-- This migration is intentionally NOT a DROP TABLE. The table is already
-- RLS-locked with no anon/authenticated policies (deny-all per
-- 20260614000003_security_rls.sql), so leaving it in place with zero
-- application code touching it is zero functional risk, while DROP TABLE
-- is irreversible and untestable against the live production database from
-- this repo's current tooling. Instead, the retirement is documented in the
-- database itself via COMMENT ON TABLE, keeping this phase's migrations
-- additive/reversible.
-- ============================================================

COMMENT ON TABLE retry_queue IS
  'RETIRED as of Phase 4 (2026-08-25+) — superseded by outbox_jobs. No application code '
  'reads or writes this table anymore. Safe to DROP in a future migration once confirmed '
  'unused in production for a safe period; not dropped here to keep this phase''s '
  'migrations additive/reversible.';
