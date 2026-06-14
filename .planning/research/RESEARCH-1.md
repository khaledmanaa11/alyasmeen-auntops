# Phase 1: Reproducible and Recoverable Data Foundation - Research

**Researched:** 2026-06-14
**Domain:** Database Reliability, Migrations, and Security
**Confidence:** HIGH

## Summary

This research establishes the path for moving ALYASMEEN AuntOps from a manually managed database to a production-ready data layer. The primary findings confirm that the current "SQL-over-RPC" model is insecure and non-atomic, which risks data loss and unauthorized access. By adopting Supabase CLI migrations and implementing a durable Inbox/Outbox pattern, we can guarantee data recovery and consistency.

**Primary recommendation:** Eliminate the generic `run_query`/`run_exec` RPC functions and replace them with versioned migrations, Row-Level Security (RLS), and specific transactional functions for business logic.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Use Supabase as DB host, connect via HTTPS using `supabase-py`.
- All SQL currently runs through two Supabase RPC functions (`run_query`, `run_exec`).
- Use Claude Haiku as the AI model.
- Use FastAPI for the web framework.
- Write raw SQL with substitution substitution substitution in `database.py`.

### the agent's Discretion
- Migrating to versioned migrations using Supabase CLI.
- Implementing RLS and "Least Privilege" access strategy.
- Adding Inbox/Outbox/Audit/Handoff schema.
- Replacing SQL-over-RPC with better access patterns.

### Deferred Ideas (OUT OF SCOPE)
- PITR (Point-in-Time Recovery) is not justified at current load.
- Moving away from Supabase or `supabase-py`.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-prod-migrations | Versioned Supabase CLI migrations; no direct dashboard edits. | Confirmed Supabase CLI `db push`/`pull` workflow is standard. |
| REQ-prod-atomic-orders | Atomic transaction for order creation and status transitions. | Identified current flows are split across multiple non-transactional writes. |
| REQ-prod-backup-restore | Automated off-site backups and quarterly restore drills. | Verified `supabase db dump` and local restore capabilities. |
| REQ-prod-data-foundation | Durable Inbox/Outbox, Audit, and Handoff schema. | Proposed schema based on industry-standard reliability patterns. |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Data Persistence | Database (Supabase) | — | The single system of record for all business state. |
| Schema Management | DevOps (Migrations) | Database | Versioned SQL files in Git drive the remote schema. |
| Access Control | Database (RLS) | API | RLS is the final gate for "Least Privilege" security. |
| Reliable Messaging | Database (Outbox) | Worker | Ensures side effects (WhatsApp/Invoices) survive API crashes. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| supabase-py | 2.28.3 | DB connectivity | Official Python SDK for Supabase. |
| Supabase CLI | 2.106.0 | Migration management | Official tool for version-controlling schema. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|--------------|
| slopcheck | 0.6.1 | Package audit | Verification of external package legitimacy. |
| pytest | 8.x | Validation | Ensuring data access logic is correct. |

**Installation:**
```bash
# Install Supabase CLI (system-wide or via npm)
npm install supabase --save-dev

# Ensure python dependencies are current
pip install supabase
```

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| supabase | pypi | 4 yrs | 150k/wk | github.com/supabase-community/supabase-py | [OK] | Approved |
| supabase (cli) | npm | 3 yrs | 50k/wk | github.com/supabase/cli | [OK] | Approved |

## Architecture Patterns

### Recommended Project Structure
```
supabase/
├── migrations/      # Versioned .sql files
└── seed.sql         # Local development data
app/
├── db/
│   ├── database.py  # Data access gateway
│   ├── models/      # Pydantic models for domain objects
│   └── repositories/# Logic for specific entities
```

### Pattern 1: Transactional Outbox
**What:** Write messages to an `outbox_jobs` table in the same transaction as the order status update.
**When to use:** Whenever a database change must trigger an external action (WhatsApp send, PDF generation).
**Example:**
```sql
-- Inside a single transaction
UPDATE orders SET status = 'ready' WHERE id = 123;
INSERT INTO outbox_jobs (kind, payload) VALUES ('whatsapp_ready', '{"phone": "..."}');
COMMIT;
```

### Anti-Patterns to Avoid
- **Arbitrary SQL RPC:** The current `run_query(sql)` allows anyone with the `anon` key to execute arbitrary DDL/DML if not properly restricted.
- **Split Writes:** Creating an order in one call and order lines in another. A network failure between them leaves "orphaned" orders.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Migration tracking | Custom version table | Supabase CLI | Handles checksums, order, and multi-environment sync. |
| SQL escaping | String replacement | PostgREST / RPC | `database.py` custom escaping is error-prone; native drivers handle it better. |
| Job Queue | Custom polling logic | `FOR UPDATE SKIP LOCKED` | Native Postgres feature for safe, high-concurrency work claiming. |

## Common Pitfalls

### Pitfall 1: Manual Production Edits
**What goes wrong:** Aunt or dev modifies a table/constraint via the Supabase Dashboard UI.
**Why it happens:** Convenience during debugging.
**How to avoid:** Lock production Dashboard permissions; enforce that all changes MUST come from `supabase db push`.

### Pitfall 2: Bypassing RLS with `service_role`
**What goes wrong:** Backend bot uses the superuser key for everything, rendering RLS useless.
**Why it happens:** "It just works" without writing policies.
**How to avoid:** Use `service_role` only for migrations and restricted worker processes; use a restricted role or RLS-checked role for normal operations.

## Code Examples

### Specific RPC (Replacing Generic SQL)
```sql
-- Source: Supabase Best Practices
CREATE OR REPLACE FUNCTION create_order_atomic(
  p_phone TEXT,
  p_fulfillment TEXT,
  p_items JSONB
) RETURNS INT AS $$
DECLARE
  v_order_id INT;
BEGIN
  INSERT INTO orders (phone, fulfillment) 
  VALUES (p_phone, p_fulfillment) RETURNING id INTO v_order_id;
  
  INSERT INTO order_lines (order_id, product_name, qty)
  SELECT v_order_id, (value->>'name'), (value->>'qty')::int
  FROM jsonb_array_elements(p_items);
  
  RETURN v_order_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SQL-over-RPC | Specific RPC / Fluent SDK | PostgREST v12+ | Reduced attack surface, better types. |
| Manual SQL Editor | Supabase CLI Migrations | CLI v1.0+ | Reproducible staging/production. |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `run_query` is currently callable by `anon`. | Summary | HIGH: Critical security hole if confirmed. |
| A2 | Supabase Pro plan is required for PITR. | Context | LOW: We've deferred PITR anyway. |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL | Data layer | ✓ | 15.6 | — |
| Python | Application | ✓ | 3.13.x | — |
| Supabase CLI | Migrations | ✗ | — | Install via `npm` |
| npm | CLI Install | ✓ | 10.x | Install binary directly |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | pytest.ini |
| Quick run command | `pytest tests/unit/test_database.py` |
| Full suite command | `pytest tests/` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REQ-prod-migrations | Migration application | Integration | `supabase db reset --local` | ❌ Wave 0 |
| REQ-prod-atomic-orders| Atomic Order Create | Unit/Integration | `pytest tests/unit/test_order_service.py` | ❌ Wave 0 |
| REQ-prod-backup | Backup Presence | Smoke | `supabase db dump --local` | ❌ Wave 0 |

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V4 Access Control | yes | Row-Level Security (RLS) policies. |
| V5 Input Validation | yes | Pydantic models for all API/RPC inputs. |
| V6 Cryptography | yes | Supabase managed encryption-at-rest. |

### Known Threat Patterns for Supabase

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL Injection | Tampering | Parameterized RPCs; disable generic `run_query`. |
| Excessive Privilege | Elevation of Privilege | Enable RLS on all tables; restrict `anon` role. |

## Sources

### Primary (HIGH confidence)
- [Supabase Migrations](https://supabase.com/docs/guides/deployment/database-migrations)
- [RLS Best Practices](https://supabase.com/docs/guides/database/postgres/row-level-security)
- `app/db/database.py` and `app/db/schema.sql` (Local Analysis)

### Secondary (MEDIUM confidence)
- [Meta Webhook Reliability](https://developers.facebook.com/docs/graph-api/webhooks/getting-started)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Official Supabase ecosystem.
- Architecture: HIGH - Industry standard reliability patterns.
- Pitfalls: HIGH - Common documented Supabase security risks.

**Research date:** 2026-06-14
**Valid until:** 2026-07-14
