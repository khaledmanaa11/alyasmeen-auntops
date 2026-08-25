-- ============================================================
-- ALYASMEEN AuntOps — webhook_events poison-pill guard
-- ============================================================
-- Adds an attempts counter to the durable inbox so a webhook event that
-- keeps failing (e.g. a malformed payload, a downstream outage) is
-- dead-lettered after MAX_WEBHOOK_EVENT_ATTEMPTS retries instead of being
-- re-picked-up by process_webhook_events() forever — which used to re-send
-- WhatsApp messages and re-bill the Claude API on every poll.

ALTER TABLE webhook_events ADD COLUMN IF NOT EXISTS attempts INT NOT NULL DEFAULT 0;

-- Speeds up spotting events that are retrying but not yet dead-lettered.
CREATE INDEX IF NOT EXISTS idx_webhook_events_attempts
  ON webhook_events(attempts)
  WHERE processed = FALSE;
