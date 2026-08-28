-- ============================================================
-- ALYASMEEN AuntOps — Revert Anon RPC Grants (undoes 20260825000001)
-- ============================================================
--
-- 20260825000001_fix_rpc_grants.sql re-granted EXECUTE on run_query(text)
-- and run_exec(text) to anon/authenticated as an emergency fix, because at
-- the time the app connected with the anon key and had no way to reach the
-- database after 20260614000003_security_rls.sql's original REVOKE.
--
-- Phase 4 closed that emergency the durable way: the app now connects with
-- the Supabase service_role key (see CLAUDE.md "Database Connection"),
-- constructed server-side only in app/db/database.py, running exclusively
-- in the FastAPI/worker processes on Railway — never shipped to the
-- dashboard's client-side HTML/JS. service_role was never affected by
-- either the original REVOKE or 20260825000001's re-GRANT — both of those
-- only ever targeted anon/authenticated — so switching credentials and
-- applying this revert are independent of each other in terms of what
-- grants service_role has; they are NOT independent in terms of blast
-- radius, which is exactly why the ordering below is mandatory.
--
-- **APPLY THIS MIGRATION ONLY AFTER confirming SUPABASE_KEY=service_role
-- is live in BOTH Railway and local .env and the app has been verified
-- working end-to-end (see Task 3 of plan 04-07) — applying it first
-- reproduces the exact outage 20260825000001 was written to fix (the app
-- had no way to reach the database at all).**
--
-- This migration is intentionally idempotent (IF EXISTS guards) so it is
-- safe to run whether or not run_query/run_exec still exist.
-- ============================================================

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'run_query') THEN
    REVOKE EXECUTE ON FUNCTION run_query(TEXT) FROM anon, authenticated;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'run_exec') THEN
    REVOKE EXECUTE ON FUNCTION run_exec(TEXT) FROM anon, authenticated;
  END IF;
END $$;
