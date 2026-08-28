-- Migration: Add 'paused' column to 'sessions' table
-- Created: 2026-06-15

ALTER TABLE sessions ADD COLUMN IF NOT EXISTS paused BOOLEAN DEFAULT FALSE;
