-- ============================================================
-- ALYASMEEN AuntOps — monthly_snapshots table
-- ============================================================
-- app/services/monthly_report.py reads and writes this table
-- (save_snapshot() / api_reports_months() / api_reports_month() in
-- ui_api.py) but no prior migration created it and it is missing from
-- app/db/schema.sql. This backfills it to match exactly what the app
-- code uses:
--   - save_snapshot() INSERTs (year, month, data) with
--     ON CONFLICT (year, month) DO UPDATE SET data = EXCLUDED.data,
--     created_at = now()  → requires a UNIQUE(year, month) constraint.
--   - ui_api.py SELECTs year, month, and data (JSON blob) back out.

-- Monthly business snapshots (one row per year/month, dashboard history)
CREATE TABLE IF NOT EXISTS monthly_snapshots (
  id         SERIAL PRIMARY KEY,
  year       INT NOT NULL,
  month      INT NOT NULL,
  data       JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (year, month)
);
CREATE INDEX IF NOT EXISTS idx_monthly_snapshots_year_month ON monthly_snapshots(year, month);

-- RLS, consistent with sibling internal-data tables (chat_history,
-- follow_ups, retry_queue) in 20260614000003_security_rls.sql:
-- service_role full access, nothing granted to anon/authenticated by
-- policy. Reads happen through the run_query/run_exec RPCs (see
-- 20260825000001_fix_rpc_grants.sql), not direct table access.
ALTER TABLE monthly_snapshots ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access on monthly_snapshots" ON monthly_snapshots
  FOR ALL TO service_role USING (true) WITH CHECK (true);
