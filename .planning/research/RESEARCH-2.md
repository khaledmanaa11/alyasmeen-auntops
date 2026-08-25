# Phase 2: Application Hardening - Research

**Researched:** 2026-06-14
**Domain:** Application Security, Reliability, and Infrastructure
**Confidence:** HIGH

## Summary
The phase focuses on moving from a single-process development setup to a secure, multi-process production architecture. Key recommendations include implementing Meta HMAC verification, adopting an Inbox/Outbox pattern for webhooks, and separating the scheduler into a dedicated worker process.

**Primary recommendation:** Split the application into Web and Worker roles on Railway and implement durable webhook persistence.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Webhook Verification | API (Web) | — | Security gate must be at the entry point. |
| Message Ingestion | API (Web) | Database | Durable storage before acknowledgment. |
| Message Processing | Worker | Database | Async/Slow tasks (AI, PDF) belong in workers. |
| Scheduled Tasks | Worker | Database | Single scheduler instance prevents duplicates. |
| Metrics/Health | API (Web) | — | Standard health check endpoints for deployment. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| structlog | 24.1.0+ | Structured Logging | Standard for JSON logging in Python. |
| SQLAlchemy | 2.0.x | JobStore Backend | Required for persistent APScheduler jobs. |
| orjson | 3.10.x | Fast JSON | High-performance JSON serialization for logs/webhooks. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|--------------|
| hmac | (stdlib) | Signature Verify | Security standard for Meta Webhooks. |
| hashlib | (stdlib) | Hashing | Paired with hmac for SHA-256. |

## Architecture Patterns

### Pattern 1: Webhook Inbox (Durable Ingestion)
1. **Receive POST** with `X-Hub-Signature-256`.
2. **Verify HMAC** using `WA_META_APP_SECRET`.
3. **Deduplicate** using Meta `wamid` (WhatsApp Message ID).
4. **Persist** to `webhook_events` table (status='pending').
5. **Return 200 OK** immediately (< 5s).

### Pattern 2: Process Separation (Web/Worker)
- **Web Service:** Runs FastAPI/Uvicorn. Handles webhooks and UI.
- **Worker Service:** Runs `worker.py` with `BlockingScheduler`. Handles AI replies, PDF generation, and retries.
- **Shared State:** Both services connect to the same Supabase Postgres instance.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Signature Verification | Custom string search | `hmac.compare_digest` | Prevents timing attacks. |
| Job Scheduling | `while True` loops | APScheduler | Handles retries, persistence, and complex cron. |
| JSON Logs | `f"log: {data}"` | `structlog` | Human-readable in dev, machine-parsable JSON in prod. |

## Common Pitfalls

### Pitfall 1: Double-Scheduling
**What goes wrong:** Running APScheduler inside FastAPI `startup` while having multiple Uvicorn workers.
**How to avoid:** Move scheduler to a separate process or use a single-instance lock.

### Pitfall 2: Webhook Timeouts
**What goes wrong:** Meta webhooks time out if processing (AI/PDF) takes > 10s.
**How to avoid:** Persistent Inbox pattern; acknowledge first, process later.

## Environment Availability (Railway)

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Runtime | ✓ | 3.13.x | — |
| Postgres | Persistence | ✓ | 15+ | — |
| NIXPACKS | Build | ✓ | — | Dockerfile |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest |
| Quick run command | `pytest -m "not slow"` |
| Full suite command | `pytest` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type |
|--------|----------|-----------|
| REQ-prod-raw-hmac | Signature rejection/acceptance | unit |
| REQ-prod-idempotency | Duplicate wamid handling | integration |

## Sources

### Primary (HIGH confidence)
- Meta Cloud API Docs: Webhook verification and `wamid` uniqueness.
- APScheduler Official Docs: Persistent JobStore configuration.
- Railway Docs: Multiple services per project.
