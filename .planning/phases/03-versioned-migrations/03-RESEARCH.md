# Phase 3: Versioned Migrations - Research

**Researched:** 2026-06-15
**Domain:** Database Schema Management & Supabase CLI
**Confidence:** HIGH

## Summary

This phase transitions the ALYASMEEN project from manual, idempotent SQL scripts (`app/db/schema.sql`) to a versioned migration system using the Supabase CLI. This ensures that schema changes are tracked in Git, peer-reviewed, and applied consistently across development, staging, and production environments.

**Primary recommendation:** Use a "Remote-as-Local" workflow (Staging Project) to bypass the missing local Docker dependency, ensuring full migration testing capability without environment blockers.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Schema Definition | Developer Local | — | Migrations are authored locally in `.sql` files. |
| Version Tracking | Git | Supabase `_migrations` | Git is the source of truth for code; Supabase tracks execution state. |
| Environment Sync | Supabase CLI | — | Standardizes the push of local migrations to remote projects. |
| Local Testing | Supabase CLI (Docker) | Remote Staging | Docker is preferred but Remote Staging is the viable fallback here. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `supabase` (CLI) | 2.106.0 | Migration management | Official tool; supports baselining, repair, and pushing. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|--------------|
| `docker` | — | Local DB & Diffing | **MISSING in current environment.** Required for `supabase start` and local diffing. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Local Docker | Remote Staging Project | Requires internet and an additional Supabase project (Free Tier), but works without local Docker. |
| Manual SQL | Prisma / Alembic | Overkill; Supabase CLI is native and handles RLS/Functions better for this stack. |

**Installation:**
```bash
# Verify CLI availability
npx supabase --version
```

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `supabase` | npm | 4+ yrs | 200k+/wk | github.com/supabase/cli | [OK] | Approved |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### Recommended Project Structure
```
supabase/
├── migrations/
│   ├── 20240615000000_remote_schema.sql  # The Baseline
│   └── 20240615000001_add_new_table.sql # Subsequent changes
└── config.toml                          # Project configuration
```

### Pattern 1: The Baselining Workflow
**What:** Capturing the remote state as a starting point.
**When to use:** Transitioning an existing live project to migrations.
**Example:**
```bash
# 1. Initialize
supabase init

# 2. Link to Production
supabase link --project-ref <prod-ref>

# 3. Pull Schema (creates first migration)
supabase db pull

# 4. Repair (Mark as applied on remote to prevent "already exists" errors)
supabase migration repair --status applied <timestamp_of_pulled_file>
```

### Anti-Patterns to Avoid
- **Dashboard Edits:** Never use the Supabase Dashboard UI to create tables or columns once migrations are enabled. This causes "schema drift" where local files don't match reality.
- **Manual Migration Editing:** Once a migration is pushed to production, do NOT edit its SQL file. Create a new migration for changes.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Schema diffing | Custom scripts | `supabase db diff` | Correctly handles Postgres types, constraints, and RLS policies. |
| Migration Tracking | `schema_version` table | `supabase migration` | Built-in CLI commands handle "repair" and "status" gracefully. |

## Runtime State Inventory

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | Supabase `_migrations` table | Automatically managed by CLI after "repair" command. |
| Live service config | Supabase Dashboard | No config change; just stop editing schema via UI. |
| OS-registered state | None | — |
| Secrets/env vars | Project Ref / DB Password | Required for `supabase link`. |
| Build artifacts | `app/db/schema.sql` | Move to `legacy/` or delete after verification. |

## Common Pitfalls

### Pitfall 1: Missing Docker
**What goes wrong:** Commands like `supabase start` or `supabase db reset` fail immediately.
**Why it happens:** Supabase CLI uses Docker containers to simulate the backend locally.
**How to avoid:** Use a separate **Staging Project** on Supabase Cloud. Use `--db-url` or `supabase link` to target the staging project for testing migrations.

### Pitfall 2: Baseline Conflict
**What goes wrong:** `supabase db push` fails because "table X already exists".
**Why it happens:** The baseline migration contains SQL to create tables that are already on production.
**How to avoid:** Execute `supabase migration repair --status applied <timestamp>` immediately after baselining.

## Code Examples

### Migration Content (Standard SQL)
```sql
-- Source: Official Supabase Docs
-- Example of a safe migration for adding a column
ALTER TABLE products ADD COLUMN IF NOT EXISTS inventory_count INT DEFAULT 0;
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `schema.sql` (manual) | Sequential Migrations | Mid-2022 (CLI v1) | Guaranteed reproducibility; Git history for DB. |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `supabase db pull` works without local Docker | Baselining | May need to manually dump schema if CLI blocks execution. |
| A2 | Staging project replaces local Docker | Common Pitfalls | Slightly slower dev cycle due to network latency. |

## Open Questions

1. **Does `db pull` strictly require Docker?**
   - What we know: Standard `db pull` often uses a shadow DB in Docker to generate the diff.
   - What's unclear: If providing a `--db-url` bypasses the shadow DB check for pulls.
   - Recommendation: If `db pull` fails, use `supabase db dump --linked -f supabase/migrations/<timestamp>_init.sql` as a fallback.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Supabase CLI | Core Workflow | ✓ | 2.106.0 | — |
| Docker | Local Dev | ✗ | — | Remote Staging Project |

**Missing dependencies with no fallback:**
- None (Remote Staging is a viable fallback).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Supabase CLI Verification |
| Config file | `supabase/config.toml` |
| Quick run command | `npx supabase migration list` |
| Full suite command | `npx supabase db push` (to staging) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MIG-01 | Baseline Creation | Smoke | `npx supabase db pull` | ❌ Wave 0 |
| MIG-02 | Staging Sync | Integration | `npx supabase db push` (Staging) | ❌ Wave 0 |
| MIG-03 | Migration Repair | Integration | `npx supabase migration repair` | ❌ Wave 0 |

## Sources

### Primary (HIGH confidence)
- [Official Supabase CLI Docs](https://supabase.com/docs/guides/cli/local-development)
- [Supabase Migrations Guide](https://supabase.com/docs/guides/deployment/database-migrations)

### Secondary (MEDIUM confidence)
- [Community guide: Supabase CLI without Docker](https://dev.to/supabase/supabase-cli-without-docker-local-development-migration-workflow)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Verified locally (npx) and via npm.
- Architecture: HIGH - Standard Supabase pattern.
- Pitfalls: HIGH - Docker absence is a known community topic.

**Research date:** 2026-06-15
**Valid until:** 2026-07-15
