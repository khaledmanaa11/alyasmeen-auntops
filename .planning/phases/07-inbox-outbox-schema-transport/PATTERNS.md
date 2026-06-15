# Patterns: Phase 7

## New Patterns

### 1. Ingest-and-Ack Webhook
- **Analog**: Classic "Transactional Inbox" pattern.
- **Implementation**: The router handles ONLY verification and persistence. It returns 200 OK as soon as the data is safe in the database.
- **Files**: `app/routers/whatsapp.py`

### 2. Service-Layer Transport
- **Analog**: "Adapter" or "Gateway" pattern.
- **Implementation**: `app/services/transport.py` centralizes the logic for interacting with the Meta protocol (parsing, signing), keeping it separate from business logic.
- **Files**: `app/services/transport.py`

### 3. Transactional Outbox
- **Analog**: "Transactional Outbox" pattern.
- **Implementation**: Business processes (like order confirmation) write their side effects (messages to send) to an `outbox_jobs` table in the same transaction as the state change.
- **Files**: `supabase/migrations/20260616000000_inbox_outbox.sql`

## Analog References
- **FastAPI Dependency Injection**: Used for `verify_meta_signature` to keep route code clean.
- **Postgres `ON CONFLICT`**: Used for idempotency in the `webhook_events` table.
