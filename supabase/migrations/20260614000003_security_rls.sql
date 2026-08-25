-- ============================================================
-- ALYASMEEN AuntOps — Security Hardening (RLS & Least Privilege)
-- ============================================================

-- 1. Enable Row-Level Security on all tables
ALTER TABLE products ENABLE ROW LEVEL SECURITY;
ALTER TABLE customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE order_lines ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE follow_ups ENABLE ROW LEVEL SECURITY;
ALTER TABLE retry_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE webhook_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE outbox_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE handoffs ENABLE ROW LEVEL SECURITY;

-- 2. Define Policies

-- Products: Everyone can read active products
CREATE POLICY "Products are viewable by everyone" ON products
  FOR SELECT USING (active = true);

-- Customers: Bot/System can manage, customers can see their own (if auth existed)
-- For now, we allow the service_role full access and restrict anon/authenticated
CREATE POLICY "Service role full access on customers" ON customers
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Orders: Service role full access; anon can see nothing (unless we add specific rules)
CREATE POLICY "Service role full access on orders" ON orders
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Order Lines: Service role full access
CREATE POLICY "Service role full access on order_lines" ON order_lines
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Sessions: Service role full access
CREATE POLICY "Service role full access on sessions" ON sessions
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Chat History: Service role full access
CREATE POLICY "Service role full access on chat_history" ON chat_history
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Webhook Events, Outbox, Audit, Handoffs: Service role ONLY
CREATE POLICY "Service role full access on webhook_events" ON webhook_events FOR ALL TO service_role USING (true);
CREATE POLICY "Service role full access on outbox_jobs" ON outbox_jobs FOR ALL TO service_role USING (true);
CREATE POLICY "Service role full access on audit_logs" ON audit_logs FOR ALL TO service_role USING (true);
CREATE POLICY "Service role full access on handoffs" ON handoffs FOR ALL TO service_role USING (true);

-- 3. Decommission Generic SQL RPCs
-- We revoke execution from anon and authenticated roles.
-- service_role still has access for maintenance if needed, but the app should stop using them.
DO $$ 
BEGIN
  IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'run_query') THEN
    REVOKE EXECUTE ON FUNCTION run_query(TEXT) FROM anon, authenticated, public;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'run_exec') THEN
    REVOKE EXECUTE ON FUNCTION run_exec(TEXT) FROM anon, authenticated, public;
  END IF;
END $$;
