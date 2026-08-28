-- Add wamid column to webhook_events for deduplication
ALTER TABLE webhook_events ADD COLUMN IF NOT EXISTS wamid TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_webhook_events_wamid ON webhook_events(wamid);
