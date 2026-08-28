-- ============================================================
-- ALYASMEEN AuntOps — Operator Auth: opaque sessions, trusted
-- devices, pending MFA logins (Phase 5)
-- ============================================================
-- Replaces the deterministic SHA-256(SECRET_KEY:DASHBOARD_PASSWORD) dashboard
-- cookie with an app-owned opaque session store. None of these tables are
-- named "sessions" — that name is already the WhatsApp cart-state table and
-- colliding here would break the bot.

-- operator_sessions: one row per logged-in browser/device. The cookie only
-- ever carries a random opaque token; token_hash is the ONLY thing this
-- table stores, so a leaked DB row can never be replayed as a live cookie.
CREATE TABLE IF NOT EXISTS operator_sessions (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      UUID NOT NULL,               -- Supabase auth.users.id
  email        TEXT NOT NULL,               -- denormalized for the admin session list
  is_admin     BOOLEAN NOT NULL DEFAULT FALSE,
  token_hash   TEXT NOT NULL UNIQUE,        -- sha256(raw token); raw token lives only in the cookie
  device_id    UUID,                        -- FK-by-convention to trusted_devices.id (nullable)
  user_agent   TEXT,
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  last_seen_at TIMESTAMPTZ DEFAULT NOW(),
  expires_at   TIMESTAMPTZ NOT NULL,
  revoked_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_operator_sessions_user ON operator_sessions(user_id, revoked_at);

COMMENT ON TABLE operator_sessions IS
  'Opaque server-side dashboard sessions. 30-day fixed expiry, multi-device, '
  'logout-everywhere and credential-change revocation all work by updating '
  'revoked_at here — the cookie itself never carries any trust.';

-- trusted_devices: remembers a browser that has already passed TOTP so it
-- isn't re-challenged on every login within the trust window.
CREATE TABLE IF NOT EXISTS trusted_devices (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id            UUID NOT NULL,
  device_token_hash  TEXT NOT NULL,
  label              TEXT,                  -- trimmed user-agent, for the admin session list
  mfa_verified_until TIMESTAMPTZ,
  created_at         TIMESTAMPTZ DEFAULT NOW(),
  last_seen_at       TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (user_id, device_token_hash)
);

COMMENT ON TABLE trusted_devices IS
  '"Remember this device" for MFA: a device is trusted (TOTP skipped) while '
  'mfa_verified_until is in the future, keyed by (user_id, sha256(device cookie)). '
  'The device cookie itself lives ~1 year so a returning-but-expired device is '
  'recognised and re-challenged rather than looking brand new.';

-- pending_logins: bridges the password step (AAL1) to the TOTP step (AAL2)
-- without round-tripping the AAL1 Supabase tokens through the browser.
-- Rows are single-use (consuming deletes the row) and short-lived (5 min).
CREATE TABLE IF NOT EXISTS pending_logins (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  token_hash    TEXT NOT NULL UNIQUE,
  user_id       UUID NOT NULL,
  email         TEXT NOT NULL,
  is_admin      BOOLEAN NOT NULL DEFAULT FALSE,
  factor_id     TEXT NOT NULL,
  access_token  TEXT NOT NULL,   -- AAL1 Supabase tokens, needed to run challenge_and_verify
  refresh_token TEXT NOT NULL,
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  expires_at    TIMESTAMPTZ NOT NULL
);

COMMENT ON TABLE pending_logins IS
  'Single-use, 5-minute bridge between the password step and the TOTP step. '
  'Holds AAL1 Supabase tokens at rest so they never round-trip through the '
  'browser between the two steps; consuming a row deletes it immediately.';

-- Row-Level Security: these tables are reached exclusively through the
-- service_role-keyed app.db.database client, never directly by anon/authenticated.
ALTER TABLE operator_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE trusted_devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE pending_logins ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access on operator_sessions" ON operator_sessions
  FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "Service role full access on trusted_devices" ON trusted_devices
  FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "Service role full access on pending_logins" ON pending_logins
  FOR ALL TO service_role USING (true) WITH CHECK (true);
