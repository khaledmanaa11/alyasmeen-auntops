# Phase 02: Schema Correctness & Integrity - Research

**Researched:** 2026-06-15
**Domain:** Database Schema Management & Validation
**Confidence:** HIGH

## Summary

This phase focuses on ensuring that the database schema in Supabase matches the `app/db/schema.sql` file and is strictly enforced at application startup. We identified that the `monthly_snapshots` table is currently missing from `schema.sql` but required by the application. We also researched the best way to implement a "startup check" in FastAPI using PostgreSQL's `information_schema` without requiring a direct TCP/psycopg2 connection.

**Primary recommendation:** Update `schema.sql` to include the `monthly_snapshots` table and add `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` statements for all existing tables. Implement a `validate_schema()` function in `app/db/database.py` that queries `information_schema.columns` and call it during FastAPI startup to ensure environment integrity.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Schema Definition | Database (Supabase) | Git (schema.sql) | SQL file is the source of truth, Supabase is the host. |
| Schema Validation | Backend (FastAPI) | — | Ensures the app only runs on a compatible schema. |
| Data Integrity | Database (Supabase) | — | Handled via constraints (PK, FK, Unique) and types. |
| Snapshot Storage | Database (Supabase) | — | `monthly_snapshots` stores historical business data. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Supabase (RPC) | — | SQL execution | Existing project adapter uses HTTPS-RPC (`run_query`/`run_exec`). |
| PostgreSQL | 15+ | Data persistence | Standard Supabase backend. |
| FastAPI | 0.93+ | Application host | Project framework. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|--------------|
| `pydantic` | 2.x | Data validation | Used for internal schema representations. |

## Package Legitimacy Audit

No new external packages are required for this phase. Schema validation will be implemented using raw SQL via the existing Supabase client.

## Architecture Patterns

### Recommended Project Structure
```
app/
├── db/
│   ├── schema.sql       # SQL source of truth (Idempotent)
│   └── database.py      # Added: validate_schema() function
└── main.py              # Added: startup event call to validate_schema()
```

### Pattern 1: Idempotent Schema Script
Instead of just `CREATE TABLE IF NOT EXISTS`, use a combination of table creation and column addition to handle existing tables in Supabase.

```sql
-- Source: [Standard Postgres Pattern]
CREATE TABLE IF NOT EXISTS monthly_snapshots (
  year       INT,
  month      INT,
  data       JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (year, month)
);

-- Ensure columns exist in older deployments
ALTER TABLE orders ADD COLUMN IF NOT EXISTS order_name TEXT;
```

### Pattern 2: Startup Schema Validation
Querying `information_schema.columns` is the most reliable way to check schema without a direct connection.

```python
# app/db/database.py

REQUIRED_SCHEMA = {
    "products": {"id", "name", "price", "description", "tags", "aliases", "active"},
    "orders": {"id", "order_name", "phone", "fulfillment", "total", "status"},
    # ...
}

def validate_schema():
    rows = query("""
        SELECT table_name, column_name 
        FROM information_schema.columns 
        WHERE table_schema = 'public'
    """)
    actual = {}
    for r in rows:
        actual.setdefault(r["table_name"], set()).add(r["column_name"])
    
    for table, req_cols in REQUIRED_SCHEMA.items():
        if table not in actual:
            raise RuntimeError(f"Missing table in Supabase: {table}")
        missing = req_cols - actual[table]
        if missing:
            raise RuntimeError(f"Table '{table}' missing columns: {missing}")
```

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Schema Migrations | Custom DSL | Raw SQL / Alembic | DB state is complex; SQL is standard for Supabase. |
| Startup Retries | Loop in main | DB Adapter Retries | `database.py` already has a circuit breaker. |

## Common Pitfalls

### Pitfall 1: `IF NOT EXISTS` limitation
**What goes wrong:** `CREATE TABLE IF NOT EXISTS` skip the entire statement if the table exists, meaning new columns added to `schema.sql` later won't be applied to existing tables.
**How to avoid:** Always include `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for columns added after the initial table creation.

### Pitfall 2: Async Startup
**What goes wrong:** Fastapi startup events are async, but some DB operations might be synchronous or misconfigured.
**How to avoid:** Ensure `validate_schema` uses the same `query` helper which handles retries and circuit breaking.

## Code Examples

### Monthly Snapshots Table Definition
```sql
-- Derived from app/services/monthly_report.py usage
CREATE TABLE IF NOT EXISTS monthly_snapshots (
  year       INT NOT NULL,
  month      INT NOT NULL,
  data       JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (year, month)
);
CREATE INDEX IF NOT EXISTS idx_monthly_snapshots_date ON monthly_snapshots(year, month);
```

### Schema Inspection Query
```sql
-- Verified via Postgres Official Docs
SELECT table_name, column_name 
FROM information_schema.columns 
WHERE table_schema = 'public' 
ORDER BY table_name, ordinal_position;
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `on_event("startup")` | `lifespan` context manager | FastAPI 0.93.0 | More robust startup/shutdown handling. |
| Direct psycopg2 | Supabase HTTPS RPC | Phase 1 | Removes need for connection pooling and TCP firewalling. |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `run_query` can access `information_schema` | Architecture Patterns | Validation fails with permission error. |
| A2 | `run_exec` supports multi-statement SQL | Summary | Reconciling script needs to split by semicolon. |

## Open Questions

1. **Should we use `lifespan` instead of `on_event`?**
   - Recommendation: Use `lifespan` if FastAPI version allows (it's the modern standard).

2. **Should we enforce column types in validation?**
   - Recommendation: Start with column presence; add types in a later phase if needed.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Supabase | Database | ✓ | Cloud | — |
| information_schema | Validation | ✓ | Standard | — |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest |
| Quick run command | `pytest tests/unit/test_database.py` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DB-01 | `monthly_snapshots` existence | Integration | `pytest tests/integration/test_schema.py` | ❌ Wave 0 |
| DB-02 | Startup validation failure | Unit | `pytest tests/unit/test_startup.py` | ❌ Wave 0 |

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | yes | SQL parameter escaping in `database.py`. |
| V14 Configuration | yes | Validation of environment at startup. |

### Known Threat Patterns for Supabase RPC

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL Injection | Tampering | Parameterized queries (using `%s` and `_escape`). |
| Arbitrary SQL Execution | Escalation | Revoke `run_query` from `anon`; use service role. |

## Sources

### Primary (HIGH confidence)
- `app/services/monthly_report.py`: Usage of `monthly_snapshots`.
- `app/routers/ui_api.py`: Usage of `monthly_snapshots`.
- `app/db/database.py`: DB adapter implementation.
- [Postgres Docs](https://www.postgresql.org/docs/current/infoschema-columns.html): `information_schema.columns` definition.

### Secondary (MEDIUM confidence)
- [FastAPI Docs](https://fastapi.tiangolo.com/advanced/events/): Startup events vs Lifespan.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH
- Architecture: HIGH
- Pitfalls: MEDIUM

**Research date:** 2026-06-15
**Valid until:** 2026-07-15
