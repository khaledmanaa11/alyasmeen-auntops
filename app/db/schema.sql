-- ============================================================
-- ALYASMEEN AuntOps — Database Schema
-- Run this once against your Supabase project to set up all tables.
-- Safe to re-run (CREATE TABLE IF NOT EXISTS).
-- ============================================================

-- Products (managed via /products dashboard page)
CREATE TABLE IF NOT EXISTS products (
  id          SERIAL PRIMARY KEY,
  name        TEXT           NOT NULL,
  price       NUMERIC(10,2)  NOT NULL,
  description TEXT           DEFAULT '',
  tags        TEXT           DEFAULT '',
  active      BOOLEAN        DEFAULT true,
  created_at  TIMESTAMPTZ    DEFAULT NOW()
);

-- Customers (one row per WhatsApp phone number)
CREATE TABLE IF NOT EXISTS customers (
  phone        TEXT PRIMARY KEY,
  name         TEXT DEFAULT '',
  saved_address TEXT DEFAULT '',
  created_at   TIMESTAMPTZ DEFAULT now(),
  updated_at   TIMESTAMPTZ DEFAULT now()
);

-- Orders
CREATE TABLE IF NOT EXISTS orders (
  id           SERIAL PRIMARY KEY,
  order_name   TEXT,
  phone        TEXT NOT NULL,
  fulfillment  TEXT DEFAULT 'pickup',   -- 'pickup' | 'delivery'
  address      TEXT DEFAULT '',
  total        NUMERIC(12,2) DEFAULT 0,
  status       TEXT DEFAULT 'to_do',   -- 'to_do' | 'ready' | 'delivered' | 'done'
  channel      TEXT DEFAULT 'whatsapp',
  created_at   TIMESTAMPTZ DEFAULT now(),
  updated_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_orders_phone    ON orders(phone);
CREATE INDEX IF NOT EXISTS idx_orders_status   ON orders(status);

-- Order lines (one row per product per order)
CREATE TABLE IF NOT EXISTS order_lines (
  id           SERIAL PRIMARY KEY,
  order_id     INT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  product_name TEXT NOT NULL,
  qty          INT DEFAULT 1,
  unit_price   NUMERIC(12,2) DEFAULT 0,
  line_total   NUMERIC(12,2) DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_order_lines_order_id ON order_lines(order_id);

-- WhatsApp sessions (cart, stage, fulfillment — persisted across restarts)
CREATE TABLE IF NOT EXISTS sessions (
  phone          TEXT PRIMARY KEY,
  stage          TEXT DEFAULT 'root',
  cart           JSONB DEFAULT '[]'::jsonb,
  fulfillment    TEXT,
  menu_products  JSONB DEFAULT '[]'::jsonb,
  address        TEXT DEFAULT '',
  created_at     TIMESTAMPTZ DEFAULT now(),
  updated_at     TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions(updated_at);

-- AI conversation history (last N messages per customer)
CREATE TABLE IF NOT EXISTS chat_history (
  id         SERIAL PRIMARY KEY,
  phone      TEXT NOT NULL,
  role       TEXT NOT NULL,   -- 'user' | 'assistant'
  content    TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chat_history_phone      ON chat_history(phone);
CREATE INDEX IF NOT EXISTS idx_chat_history_created_at ON chat_history(created_at);

-- Post-purchase follow-ups (sent 3 days after delivery)
CREATE TABLE IF NOT EXISTS follow_ups (
  id           SERIAL PRIMARY KEY,
  phone        TEXT NOT NULL,
  order_id     TEXT NOT NULL,
  delivered_at TIMESTAMPTZ DEFAULT now(),
  sent         BOOLEAN DEFAULT FALSE,
  sent_at      TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_follow_ups_sent ON follow_ups(sent);

-- Error retry queue (failed WhatsApp / Wave API calls)
CREATE TABLE IF NOT EXISTS retry_queue (
  id            SERIAL PRIMARY KEY,
  action        TEXT NOT NULL,             -- 'send_text_ready' | 'send_text_done' | 'send_text_delivered' | 'wave_invoice'
  order_id      INT NOT NULL,
  phone         TEXT NOT NULL,
  payload       JSONB DEFAULT '{}'::jsonb, -- extra context if needed
  attempts      INT DEFAULT 0,
  max_attempts  INT DEFAULT 3,
  last_error    TEXT,
  next_retry_at TIMESTAMPTZ DEFAULT now() + INTERVAL '15 minutes',
  resolved      BOOLEAN DEFAULT FALSE,
  created_at    TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_retry_queue_pending ON retry_queue(resolved, next_retry_at)
  WHERE resolved = FALSE;
