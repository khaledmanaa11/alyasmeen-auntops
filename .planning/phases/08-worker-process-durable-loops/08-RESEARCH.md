# Phase 08: Worker Process & Durable Loops - Research

**Researched:** 2026-06-16
**Domain:** Asynchronous background processing, durable job loops, reliable outbox.
**Confidence:** HIGH

## Summary

Phase 08 transitions AuntOps from a synchronous request-response architecture to an asynchronous "ingest-and-ack" model. Currently, the system processes AI replies and generates PDF invoices directly within the FastAPI request thread (for webhooks and UI actions). This leads to slow responses, potential timeouts, and message loss if the process crashes mid-execution.

This phase introduces a dedicated `worker.py` that handles heavy lifting (AI, PDF, Meta API) via two primary loops:
1. **Inbox Loop:** Claims and processes `webhook_events` (parsing commands, calling Claude AI).
2. **Outbox Loop:** Claims and executes `outbox_jobs` (sending WhatsApp messages, documents, and buttons).

The FastAPI `webhook_post` endpoint is already refactored (in Phase 07) to only ingest and return 200 OK. This phase completes the circuit by making the worker process those ingested events.

**Primary recommendation:** Use the **Transactional Outbox Pattern** combined with **Postgres RPC functions** for atomic job claiming (`FOR UPDATE SKIP LOCKED`).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Webhook Ingestion | API (FastAPI) | Database | Must be fast/reliable to meet Meta's 1-sec ack requirement. |
| AI Reasoning | Worker | AI Service | Computationally heavy and network-dependent (Anthropic API). |
| PDF Generation | Worker | Database | High CPU/Memory usage; requires access to order data. |
| Message Sending | Worker | Meta API | Network-dependent; requires retry logic and backoff. |
| Job Scheduling | Worker | — | APScheduler moves out of the web process to ensure durability. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `apscheduler` | 3.11.2 [VERIFIED: npm registry] | Recurring tasks (backups, follow-ups) | Industry standard for Python scheduling. |
| `supabase` | 2.28.3 [VERIFIED: npm registry] | Data persistence & RPC | Existing project data layer. |
| `asyncio` | Built-in | Concurrent worker loops | Native, high-performance concurrency. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|--------------|
| `fpdf2` | 2.8.7 [VERIFIED: npm registry] | PDF Generation | Existing invoice generator library. |
| `anthropic` | 0.84.0 [VERIFIED: npm registry] | AI Reasoning | Primary LLM provider (Claude). |
| `requests` | 2.34.2 [VERIFIED: npm registry] | Meta API calls | Reliable HTTP client for outbox handlers. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `asyncio` loop | `Celery` | Celery is overkill for this scale and requires Redis/RabbitMQ. |
| `APScheduler` | `cron` | Cron is harder to manage in containerized/cloud environments. |

**Installation:**
```bash
pip install apscheduler supabase fpdf2 anthropic requests
```

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| apscheduler | PyPI | 11 yrs | 15M/mo | github.com/agronholm/apscheduler | [OK] | Approved |
| supabase | PyPI | 2 yrs | 200k/mo | github.com/supabase-community/supabase-py | [OK] | Approved |
| fpdf2 | PyPI | 3 yrs | 500k/mo | github.com/fpdf2/fpdf2 | [OK] | Approved |
| anthropic | PyPI | 1 yr | 2M/mo | github.com/anthropics/anthropic-sdk-python | [OK] | Approved |
| requests | PyPI | 13 yrs | 1B/mo | github.com/psf/requests | [OK] | Approved |
| fastapi | PyPI | 5 yrs | 30M/mo | github.com/tiangolo/fastapi | [OK] | Approved |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
[Meta/User] -> (HTTP POST) -> [FastAPI] -> (INSERT) -> [DB: webhook_events]
                                   |
                                   └─> (200 OK Response)

[Worker: Inbox Loop] <-> (Claim/Update) <-> [DB: webhook_events]
         |
         ├─> [AI Service] -> [Anthropic Claude]
         └─> (INSERT) -> [DB: outbox_jobs]

[Worker: Outbox Loop] <-> (Claim/Update) <-> [DB: outbox_jobs]
         |
         └─> [Meta API] -> [Meta Cloud API]

[Worker: Scheduler] -> (INSERT) -> [DB: outbox_jobs]
```

### Recommended Project Structure
```
app/
├── services/
│   ├── outbox.py       # Helper for queueing messages
│   └── worker_tasks.py # Business logic extracted from whatsapp.py
worker.py               # Main entry point (durable loops + scheduler)
```

### Pattern 1: Atomic Job Claiming (Postgres RPC)
**What:** Use a PL/pgSQL function to claim the next pending job atomically using `SKIP LOCKED`.
**When to use:** In both Inbox and Outbox loops to prevent multiple worker instances (or loops) from processing the same event.
**Example:**
```sql
-- Source: [ASSUMED] - Standard Postgres pattern for queues
CREATE OR REPLACE FUNCTION claim_outbox_job()
RETURNS SETOF outbox_jobs AS $$
BEGIN
    RETURN QUERY
    UPDATE outbox_jobs
    SET status = 'processing', processed_at = now()
    WHERE id = (
        SELECT id
        FROM outbox_jobs
        WHERE status = 'pending'
        ORDER BY created_at
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING *;
END;
$$ LANGUAGE plpgsql;
```

### Anti-Patterns to Avoid
- **Implicit Retries in API Endpoints:** Never retry a network call (Meta/AI) inside a FastAPI request. Queue it and let the worker retry.
- **Polling without Sleep:** Ensure loops have a small `asyncio.sleep(1)` to avoid hammering the database when idle.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Task Scheduling | Custom `while` timers | `APScheduler` | Handles edge cases like misfires, persistence, and complex cron syntax. |
| Job Queue | Redis/RabbitMQ | `outbox_jobs` table | Using the existing DB (Supabase) simplifies the stack and allows for atomic transactions. |
| Lock Management | File locks or flags | `FOR UPDATE SKIP LOCKED` | Postgres provides native, highly-efficient concurrency control. |

## Common Pitfalls

### Pitfall 1: Zombie Jobs
**What goes wrong:** A worker claims a job but crashes before finishing. The job stays in `processing` forever.
**How to avoid:** Implement a "Cleanup" task (via APScheduler) that resets jobs in `processing` status if their `processed_at` is > 10 minutes ago.

### Pitfall 2: DB Call Overhead
**What goes wrong:** Polling two tables every second creates 172k calls/day, potentially hitting Supabase free-tier limits.
**How to avoid:** Use a dynamic sleep — if a loop finds a job, it polls again immediately. If no job is found, it sleeps for 2-5 seconds.

## Code Examples

### Unified Outbox Enqueue (app/services/outbox.py)
```python
# [ASSUMED] - Pattern for reliable outbox insertion
def enqueue_outbox(recipient: str, payload: dict, transport: str = "whatsapp_meta"):
    from app.db.database import execute
    execute(
        "INSERT INTO outbox_jobs (transport, recipient, payload) VALUES (%s, %s, %s)",
        (transport, recipient, payload)
    )
```

### Worker Loop Template (worker.py)
```python
async def process_inbox():
    while True:
        event = execute_returning("SELECT * FROM claim_webhook_event()")
        if event:
            try:
                # Business logic...
                execute("UPDATE webhook_events SET status='processed' WHERE id=%s", (event['id'],))
            except Exception as e:
                execute("UPDATE webhook_events SET status='failed', error=%s WHERE id=%s", (str(e), event['id']))
        else:
            await asyncio.sleep(2)
```

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `FOR UPDATE SKIP LOCKED` works in Supabase RPC | Architecture Patterns | If not, workers must use a `claimed_at` timestamp with a manual update lock. |
| A2 | `payload` JSONB can hold PDF data or metadata | Architecture Patterns | If too large, worker must re-generate the PDF from order_id in the payload. |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Runtime | ✓ | 3.12 | — |
| Supabase | Database | ✓ | Cloud | — |
| Anthropic | AI Replies | ✓ | API | — |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | pytest.ini |
| Quick run command | `pytest tests/unit/test_worker.py` |
| Full suite command | `pytest tests/integration/test_bot_flow.py` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| WRK-01 | worker.py claims and processes events | Integration | `pytest tests/integration/test_transport.py` | ✅ |
| WRK-02 | outbox_jobs handle text/buttons/PDF | Integration | `pytest tests/integration/test_transport.py` | ✅ |
| WRK-03 | APScheduler triggers follow-ups | Unit | `pytest tests/unit/test_backup.py` | ✅ |

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | yes | Webhook verification (HMAC) must remain in the web process. |
| V10 Malicious Code | yes | Worker should not execute any dynamic code from `payload`. |

### Known Threat Patterns for Worker Process

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Poison Pill | Denial of Service | Max attempt limit and error trapping in loops. |
| Race Condition | Data Integrity | Atomic claiming (`SKIP LOCKED`). |

## Sources

### Primary (HIGH confidence)
- `app/routers/whatsapp.py` - Current webhook logic.
- `app/main.py` - Current scheduler setup.
- `app/db/database.py` - Supabase client and schema validation.
- `supabase/migrations/20260616000000_inbox_outbox.sql` - Table schemas.

### Secondary (MEDIUM confidence)
- [Official APScheduler docs] - Async usage patterns.
- [Postgres Documentation] - `SKIP LOCKED` behavior for queues.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Verified via slopcheck and existing usage.
- Architecture: HIGH - Standard "ingest-and-ack" / Outbox pattern.
- Pitfalls: HIGH - Common distributed systems issues.

**Research date:** 2026-06-16
**Valid until:** 2026-07-16
