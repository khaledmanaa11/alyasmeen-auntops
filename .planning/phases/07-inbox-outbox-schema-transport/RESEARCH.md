# Phase 7: Inbox/Outbox Schema & Core Transport - Research

**Researched:** 2026-06-15
**Domain:** Distributed Systems / Webhook Security / PostgreSQL
**Confidence:** HIGH

## Summary

This phase transitions the project from a simple "request-response" webhook to a durable "ingest-and-ack" architecture. The primary goal is to ensure that no Meta webhook event is lost and that no duplicate processing occurs due to Meta's retry policy. We implement a Transactional Outbox pattern to ensure atomicity between business logic and outbound messaging.

**Primary recommendation:** Use a dedicated `webhook_events` table for the inbox and `outbox_jobs` for the outbox, leveraging PostgreSQL `FOR UPDATE SKIP LOCKED` for high-concurrency worker claiming.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Signature Verification | API / Backend | — | Must happen at the edge before any processing or persistence. |
| Webhook Ingestion | API / Backend | Database | Receive, verify, and persist to `webhook_events`. |
| Message Parsing | Worker | — | Complex Meta envelope parsing is deferred to the worker to keep the ingest loop < 1s. |
| Outbound Transport | Worker | Meta API | Decoupled from the web request via `outbox_jobs`. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi | 0.115.6 | Web framework | Current project standard, handles async request body reading well. |
| supabase | 2.x | Data layer | Project standard for PostgreSQL access via RPC. |
| requests | 2.34.2 | Outbound API calls | Standard for synchronous API calls in the worker process. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|--------------|
| hmac | stdlib | Signature verification | Timing-safe comparison of SHA256 hashes. |

## Architecture Patterns

### Recommended Project Structure
```
app/
├── routers/
│   └── whatsapp.py      # Refactored for ingest-only
├── services/
│   ├── transport.py     # New: Signature verification & envelope parsing
│   └── worker.py        # New: Background job processor
└── db/
    └── migrations/      # New: Inbox/Outbox schema definitions
```

### Pattern 1: Transactional Inbox (Durable Ingest)
**What:** Write raw webhook payload to `webhook_events` immediately after signature verification.
**When to use:** All production webhooks to prevent data loss.
**Example:**
```python
# In whatsapp.py
async def ingest(request: Request):
    body = await request.body()
    verify_signature(body, request.headers)
    execute("INSERT INTO webhook_events (raw_payload, status) VALUES (%s, 'pending')", (body.decode(),))
    return {"ok": True}
```

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Task Scheduling | Custom cron | APScheduler | Handles intervals, persistent stores, and misfire instructions. |
| Unique IDs | Random strings | wamid (Meta) | Meta provides a unique ID for every message; use it for idempotency. |

## Common Pitfalls

### Pitfall 1: Reading Request Body Twice
**What goes wrong:** Calling `request.json()` after `request.body()` can fail if not handled correctly in FastAPI.
**How to avoid:** Use `await request.body()` first; FastAPI/Starlette caches this, so subsequent calls to `.json()` work.

### Pitfall 2: Double-Processing on Meta Retry
**What goes wrong:** Meta retries webhooks if no 200 OK is received in ~10s. If processing takes 15s, you'll process twice.
**How to avoid:** Use a `UNIQUE` constraint on `wamid` in the `webhook_events` table.

## Code Examples

### Timing-Safe HMAC Verification
```python
import hmac
import hashlib

def verify_meta_signature(body: bytes, signature: str, secret: str):
    expected = "sha256=" + hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")
```

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Meta `wamid` is globally unique per WABA. | Architecture Patterns | Low; Meta documentation guarantees this for deduplication. |
| A2 | `SKIP LOCKED` is available in Supabase Postgres. | Architecture Patterns | Low; standard in Postgres 9.5+. |

## Open Questions (RESOLVED)
1. **Batching**: Does Meta still batch multiple messages in a single `entry`? (RESOLVED) Yes, Meta's Webhook architecture is designed to batch multiple `changes` within an `entry` array. Our parsing logic in `transport.py` must iterate through `entry`, then `changes`, and then potentially multiple `messages` if present in the value object.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest |
| Full suite command | `pytest tests/integration/test_transport.py` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command |
|--------|----------|-----------|-------------------|
| REQ-M2-02 | Signature Verification | integration | `pytest tests/integration/test_security.py` |
| REQ-M2-01 | Inbox Persistence | integration | `pytest tests/integration/test_inbox.py` |
