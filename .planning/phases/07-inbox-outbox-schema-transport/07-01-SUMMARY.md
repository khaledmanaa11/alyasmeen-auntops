# Phase 07-01 Summary: Inbox/Outbox Schema & Core Transport

Implemented durable inbox/outbox schema and Meta transport security, transitioning to a reliable "ingest-and-ack" architecture.

## Completed Tasks
- **Schema Migration**: Created `supabase/migrations/20260616000000_inbox_outbox.sql` with `webhook_events` (Inbox) and `outbox_jobs` (Outbox) tables.
- **Database Validation**: Updated `REQUIRED_SCHEMA` in `app/db/database.py` to ensure schema integrity on startup.
- **Transport Security**: Implemented `app/services/transport.py` with HMAC `X-Hub-Signature-256` verification and Meta envelope parsing.
- **Webhook Refactor**: Updated `POST /whatsapp/webhook` to verify signatures, parse events, and persist to `webhook_events` immediately, returning 200 OK without waiting for processing.
- **Integration Testing**: Created `tests/integration/test_transport.py` and fixed a database monkeypatch issue in `conftest.py` to allow end-to-end verification of persistence.

## Verification Results
- **Unit Tests**: `tests/unit/test_transport_logic.py` - 6 passed.
- **Integration Tests**: `tests/integration/test_transport.py` - 5 passed.
- **Schema Validation**: `python -c "from app.db.database import validate_schema; validate_schema()"` - Passed.

## Technical Notes
- **Security**: All Meta webhooks are now strictly verified via HMAC. Requests with missing or invalid signatures are rejected with 403.
- **Idempotency**: The `wamid` is used as a UNIQUE constraint in `webhook_events`, ensuring duplicate events from Meta are ignored gracefully.
- **Architecture**: Inline message processing (`_handle_message`) is currently bypassed in favor of durable ingestion. Phase 08 will introduce the Worker to process these events asynchronously.
