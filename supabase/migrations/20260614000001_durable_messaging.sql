-- ============================================================
-- ALYASMEEN AuntOps — Durable Messaging & Audit Schema
-- ============================================================

-- Durable Inbox: Store raw webhook payloads before processing
CREATE TABLE IF NOT EXISTS webhook_events (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  phone       TEXT NOT NULL,
  payload     JSONB NOT NULL,
  processed   BOOLEAN DEFAULT FALSE,
  error       TEXT,
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  processed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_webhook_events_processed ON webhook_events(processed) WHERE processed = FALSE;
CREATE INDEX IF NOT EXISTS idx_webhook_events_phone ON webhook_events(phone);

-- Durable Outbox: Side effects to be processed by background workers
CREATE TABLE IF NOT EXISTS outbox_jobs (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  kind        TEXT NOT NULL,   -- e.g., 'whatsapp_message', 'pdf_invoice'
  phone       TEXT NOT NULL,
  payload     JSONB NOT NULL,
  status      TEXT DEFAULT 'pending', -- 'pending', 'processing', 'sent', 'failed'
  attempts    INT DEFAULT 0,
  max_attempts INT DEFAULT 3,
  last_error  TEXT,
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  updated_at  TIMESTAMPTZ DEFAULT NOW(),
  processed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_outbox_jobs_status ON outbox_jobs(status) WHERE status IN ('pending', 'failed');

-- Audit Logs: Record critical business and security events
CREATE TABLE IF NOT EXISTS audit_logs (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  actor       TEXT NOT NULL,   -- 'system', 'aunt', or phone number
  action      TEXT NOT NULL,   -- 'order_created', 'status_changed', 'login_failed'
  details     JSONB DEFAULT '{}'::jsonb,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor ON audit_logs(actor);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);

-- Handoffs: Durable state for human intervention
CREATE TABLE IF NOT EXISTS handoffs (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  phone       TEXT NOT NULL REFERENCES customers(phone),
  reason      TEXT NOT NULL,
  status      TEXT DEFAULT 'active', -- 'active', 'resolved'
  assigned_to TEXT,                  -- 'aunt'
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  resolved_at TIMESTAMPTZ,
  metadata    JSONB DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_handoffs_phone ON handoffs(phone);
CREATE INDEX IF NOT EXISTS idx_handoffs_status ON handoffs(status) WHERE status = 'active';
