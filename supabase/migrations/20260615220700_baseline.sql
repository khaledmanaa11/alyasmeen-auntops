-- ============================================================
-- ALYASMEEN AuntOps — Database Schema
-- Run this once against your Supabase project to set up all tables.
-- Safe to re-run (CREATE TABLE IF NOT EXISTS + ALTER TABLE ... ADD COLUMN IF NOT EXISTS).
-- ============================================================

-- Products (managed via /products dashboard page)
CREATE TABLE IF NOT EXISTS products (
  id          SERIAL PRIMARY KEY,
  name        TEXT           NOT NULL,
  price       NUMERIC(10,2)  NOT NULL,
  description TEXT           DEFAULT '',
  tags        TEXT           DEFAULT '',
  aliases     TEXT           DEFAULT '',  -- comma-separated synonyms (e.g. "hand cream, كريم اليد")
  active      BOOLEAN        DEFAULT true,
  created_at  TIMESTAMPTZ    DEFAULT NOW()
);
ALTER TABLE products ADD COLUMN IF NOT EXISTS name TEXT NOT NULL;
ALTER TABLE products ADD COLUMN IF NOT EXISTS price NUMERIC(10,2) NOT NULL;
ALTER TABLE products ADD COLUMN IF NOT EXISTS description TEXT DEFAULT '';
ALTER TABLE products ADD COLUMN IF NOT EXISTS tags TEXT DEFAULT '';
ALTER TABLE products ADD COLUMN IF NOT EXISTS aliases TEXT DEFAULT '';
ALTER TABLE products ADD COLUMN IF NOT EXISTS active BOOLEAN DEFAULT true;
ALTER TABLE products ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

-- Customers (one row per WhatsApp phone number)
CREATE TABLE IF NOT EXISTS customers (
  phone        TEXT PRIMARY KEY,
  name         TEXT DEFAULT '',
  saved_address TEXT DEFAULT '',
  created_at   TIMESTAMPTZ DEFAULT now(),
  updated_at   TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS name TEXT DEFAULT '';
ALTER TABLE customers ADD COLUMN IF NOT EXISTS saved_address TEXT DEFAULT '';
ALTER TABLE customers ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();
ALTER TABLE customers ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();

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
ALTER TABLE orders ADD COLUMN IF NOT EXISTS order_name TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS phone TEXT NOT NULL;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS fulfillment TEXT DEFAULT 'pickup';
ALTER TABLE orders ADD COLUMN IF NOT EXISTS address TEXT DEFAULT '';
ALTER TABLE orders ADD COLUMN IF NOT EXISTS total NUMERIC(12,2) DEFAULT 0;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'to_do';
ALTER TABLE orders ADD COLUMN IF NOT EXISTS channel TEXT DEFAULT 'whatsapp';
ALTER TABLE orders ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();
ALTER TABLE orders ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();

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
ALTER TABLE order_lines ADD COLUMN IF NOT EXISTS order_id INT NOT NULL;
ALTER TABLE order_lines ADD COLUMN IF NOT EXISTS product_name TEXT NOT NULL;
ALTER TABLE order_lines ADD COLUMN IF NOT EXISTS qty INT DEFAULT 1;
ALTER TABLE order_lines ADD COLUMN IF NOT EXISTS unit_price NUMERIC(12,2) DEFAULT 0;
ALTER TABLE order_lines ADD COLUMN IF NOT EXISTS line_total NUMERIC(12,2) DEFAULT 0;

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
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS stage TEXT DEFAULT 'root';
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS cart JSONB DEFAULT '[]'::jsonb;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS fulfillment TEXT;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS menu_products JSONB DEFAULT '[]'::jsonb;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS address TEXT DEFAULT '';
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();

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
ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS phone TEXT NOT NULL;
ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS role TEXT NOT NULL;
ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS content TEXT;
ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();

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
ALTER TABLE follow_ups ADD COLUMN IF NOT EXISTS phone TEXT NOT NULL;
ALTER TABLE follow_ups ADD COLUMN IF NOT EXISTS order_id TEXT NOT NULL;
ALTER TABLE follow_ups ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMPTZ DEFAULT now();
ALTER TABLE follow_ups ADD COLUMN IF NOT EXISTS sent BOOLEAN DEFAULT FALSE;
ALTER TABLE follow_ups ADD COLUMN IF NOT EXISTS sent_at TIMESTAMPTZ;

-- Error retry queue (failed WhatsApp / PDF-invoice calls)
CREATE TABLE IF NOT EXISTS retry_queue (
  id            SERIAL PRIMARY KEY,
  action        TEXT NOT NULL,             -- 'send_text_ready' | 'send_text_done' | 'send_text_delivered' | 'pdf_invoice'
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
ALTER TABLE retry_queue ADD COLUMN IF NOT EXISTS action TEXT NOT NULL;
ALTER TABLE retry_queue ADD COLUMN IF NOT EXISTS order_id INT NOT NULL;
ALTER TABLE retry_queue ADD COLUMN IF NOT EXISTS phone TEXT NOT NULL;
ALTER TABLE retry_queue ADD COLUMN IF NOT EXISTS payload JSONB DEFAULT '{}'::jsonb;
ALTER TABLE retry_queue ADD COLUMN IF NOT EXISTS attempts INT DEFAULT 0;
ALTER TABLE retry_queue ADD COLUMN IF NOT EXISTS max_attempts INT DEFAULT 3;
ALTER TABLE retry_queue ADD COLUMN IF NOT EXISTS last_error TEXT;
ALTER TABLE retry_queue ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMPTZ DEFAULT now() + INTERVAL '15 minutes';
ALTER TABLE retry_queue ADD COLUMN IF NOT EXISTS resolved BOOLEAN DEFAULT FALSE;
ALTER TABLE retry_queue ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();

-- Monthly snapshots (business metrics for the dashboard)
CREATE TABLE IF NOT EXISTS monthly_snapshots (
  year       INT NOT NULL,
  month      INT NOT NULL,
  data       JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (year, month)
);
CREATE INDEX IF NOT EXISTS idx_monthly_snapshots_date ON monthly_snapshots(year, month);
ALTER TABLE monthly_snapshots ADD COLUMN IF NOT EXISTS year INT NOT NULL;
ALTER TABLE monthly_snapshots ADD COLUMN IF NOT EXISTS month INT NOT NULL;
ALTER TABLE monthly_snapshots ADD COLUMN IF NOT EXISTS data JSONB NOT NULL;
ALTER TABLE monthly_snapshots ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();
