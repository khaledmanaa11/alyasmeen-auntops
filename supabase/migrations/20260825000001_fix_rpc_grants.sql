-- ============================================================
-- ALYASMEEN AuntOps — Restore RPC Grants (fixes 20260614000003)
-- ============================================================
--
-- 20260614000003_security_rls.sql revoked EXECUTE on run_query(text) and
-- run_exec(text) from anon/authenticated as a "decommission generic SQL
-- RPCs" hardening step. But app/db/database.py — the app's ONLY data
-- path — calls exactly those two RPCs for every read and write, and the
-- documented deployment (see CLAUDE.md "Required env vars") connects with
-- the anon key, not service_role. Since that migration shipped, the app
-- has had no way to reach the database at all.
--
-- HONEST TRADEOFF: this migration re-opens the same broad surface that
-- 20260614000003 was trying to close (any anon-keyed caller who can reach
-- these RPCs can run arbitrary SQL text against the database). That is not
-- fixed here — it is restored to the pre-hardening, working state so the
-- app functions again today. The durable fix is one of:
--   (a) move the app to the service_role key server-side (Supabase client
--       constructed with a secret key on the FastAPI server only, never
--       shipped to a browser/client), or
--   (b) replace these two raw-SQL RPCs with typed, narrow RPCs per
--       operation (e.g. get_order, create_order, update_order_status),
--       each independently grantable and RLS-scoped.
-- Both are out of scope for this fix and are tracked for Phase 4.
--
-- This migration is intentionally additive/idempotent (IF EXISTS guards)
-- so it is safe to run whether or not 20260614000003 already ran.
-- ============================================================

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'run_query') THEN
    GRANT EXECUTE ON FUNCTION run_query(TEXT) TO anon, authenticated;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'run_exec') THEN
    GRANT EXECUTE ON FUNCTION run_exec(TEXT) TO anon, authenticated;
  END IF;
END $$;
