-- Inbox/Outbox Tables
-- Transition to asynchronous "ingest-and-ack" architecture.

-- Webhook Ingestion (Inbox)
CREATE TABLE IF NOT EXISTS webhook_events (
  id           SERIAL PRIMARY KEY,
  wamid        TEXT UNIQUE,
  payload      JSONB NOT NULL,
  status       TEXT DEFAULT 'pending', -- 'pending', 'processed', 'failed'
  error        TEXT,
  created_at   TIMESTAMPTZ DEFAULT now(),
  processed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_webhook_events_wamid ON webhook_events(wamid);
CREATE INDEX IF NOT EXISTS idx_webhook_events_status ON webhook_events(status);

-- Reliable Message Sending (Outbox)
CREATE TABLE IF NOT EXISTS outbox_jobs (
  id           SERIAL PRIMARY KEY,
  transport    TEXT NOT NULL,          -- 'whatsapp_meta', 'email', etc.
  recipient    TEXT NOT NULL,
  payload      JSONB NOT NULL,
  status       TEXT DEFAULT 'pending', -- 'pending', 'sent', 'failed'
  attempts     INT DEFAULT 0,
  max_attempts INT DEFAULT 3,
  error        TEXT,
  created_at   TIMESTAMPTZ DEFAULT now(),
  processed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_outbox_jobs_status ON outbox_jobs(status);

-- Required columns check for app/db/database.py validate_schema()
ALTER TABLE webhook_events ADD COLUMN IF NOT EXISTS wamid TEXT UNIQUE;
ALTER TABLE webhook_events ADD COLUMN IF NOT EXISTS payload JSONB NOT NULL;
ALTER TABLE webhook_events ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending';
ALTER TABLE webhook_events ADD COLUMN IF NOT EXISTS error TEXT;
ALTER TABLE webhook_events ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();
ALTER TABLE webhook_events ADD COLUMN IF NOT EXISTS processed_at TIMESTAMPTZ;

ALTER TABLE outbox_jobs ADD COLUMN IF NOT EXISTS transport TEXT NOT NULL;
ALTER TABLE outbox_jobs ADD COLUMN IF NOT EXISTS recipient TEXT NOT NULL;
ALTER TABLE outbox_jobs ADD COLUMN IF NOT EXISTS payload JSONB NOT NULL;
ALTER TABLE outbox_jobs ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending';
ALTER TABLE outbox_jobs ADD COLUMN IF NOT EXISTS attempts INT DEFAULT 0;
ALTER TABLE outbox_jobs ADD COLUMN IF NOT EXISTS max_attempts INT DEFAULT 3;
ALTER TABLE outbox_jobs ADD COLUMN IF NOT EXISTS error TEXT;
ALTER TABLE outbox_jobs ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();
ALTER TABLE outbox_jobs ADD COLUMN IF NOT EXISTS processed_at TIMESTAMPTZ;
