# Supabase Backup & Restore Drill

**Date:** 2026-06-14 (procedure written); revised 2026-08-25 for the verified no-Docker sequence
**Status:** Procedure verified — the installed Supabase CLI does NOT require Docker for the
commands this drill actually needs (`supabase link`, `db push`, `db dump` all work without
Docker; only local-dev-stack commands like `supabase start`/`db diff` need it, and this drill
doesn't use those). Live execution is a Phase 4 operator checkpoint — see Drill Log below.

## Overview
This document describes the procedure for backing up the ALYASMEEN AuntOps production database and performing a verified restoration drill. Production readiness requires that we can recover from total data loss within a defined RTO (Recovery Time Objective) of 4 hours.

## 1. Backup Procedure

### Automated (Supabase Managed)
Supabase provides daily backups on the Pro tier.
- **Retention:** 7 days (Free tier does not include automated backups).
- **Location:** Supabase Dashboard -> Project -> Database -> Backups.

### Manual (Off-site / Local)
To ensure we have a portable backup outside of Meta/Supabase, run the following weekly:
```bash
# Export the entire database schema and data
npx supabase db dump --linked --output backup_$(date +%F).sql

# Export roles and permissions
npx supabase db dump --linked --role-only --output roles_$(date +%F).sql
```
Store these files in a secure, encrypted cloud bucket.

## 2. Restoration Drill Procedure

This drill should be performed quarterly to verify backup integrity.

### Step 1: Link to the live project and take the backup
No Docker and no local Supabase stack are needed — `link`, `db push`, and `db dump` all talk
directly to the hosted project over its Postgres connection.
```bash
# Link the CLI to the live project (prompts for the DB password:
# Supabase Dashboard -> Settings -> Database)
npx supabase link --project-ref ppwcfmuetgczclmnzvqr

# Apply every migration not yet on the live project — this is also how
# Phase 4's "all migrations applied to the live project" criterion gets satisfied
npx supabase db push --linked

# Dump schema+data and roles separately
npx supabase db dump --linked -f backup_$(date +%F).sql
npx supabase db dump --linked --role-only -f roles_$(date +%F).sql
```

### Step 2: Restore into a throwaway project and apply the backup
```bash
# Create a new, throwaway FREE-TIER Supabase project in the dashboard to use as the
# restore target, then link the CLI to it
npx supabase link --project-ref <new-throwaway-ref>

# Push migrations to build the schema on the empty project (schema only, no data yet)
npx supabase db push --linked

# Load the data dump — psql/pg_dump come from the official PostgreSQL Windows installer,
# typically under C:\Program Files\PostgreSQL\<version>\bin\, not on PATH by default.
# Use the new project's Session Pooler connection string (Dashboard -> Settings ->
# Database -> Connection string -> Session pooler).
psql "<new-project-session-pooler-url>" -f backup_YYYY-MM-DD.sql
```

### Step 3: Verification Check
Run the following queries to confirm data presence:
- `SELECT COUNT(*) FROM products;` (Should match production count)
- `SELECT * FROM orders ORDER BY created_at DESC LIMIT 5;` (Recent orders should be present)
- `SELECT * FROM audit_logs LIMIT 1;` (Audit logs should be present)

## 3. Disaster Recovery Plan (Production Outage)

In the event of a production database failure:
1. Notify stakeholders of the outage.
2. Create a new Supabase project.
3. Link the CLI to the new project: `npx supabase link --project-ref <new-ref>`.
4. Push the latest migrations: `npx supabase db push`.
5. Restore data from the latest manual backup: `npx supabase db dump --linked | npx supabase db push`.
6. Update application environment variables (`SUPABASE_URL`, `SUPABASE_KEY`) to point to the new project.
7. Verify system functionality.

## 4. Drill Log

| Date | Performed By | Result | Notes |
|------|--------------|--------|-------|
| 2026-06-14 | Claude (Agent) | N/A | Procedure documented; drill pending Docker availability. |

_A new row will be added here once the drill above is actually executed for real against the
live project and a throwaway restore target (Phase 4 plan 04-07, Task 4) — until that row
exists, no restore has actually been performed or verified._
