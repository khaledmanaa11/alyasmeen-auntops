# Supabase Backup & Restore Drill

**Date:** 2026-06-14 (procedure written); revised 2026-08-28 after live verification
**Status:** `supabase link` and `db push` are Docker-free, but `supabase db dump` is NOT —
verified failing on CLI 2.116.0 / Windows ("failed to run docker. Docker Desktop is a
prerequisite"). The working no-Docker path for dumps is native `pg_dump` from the official
PostgreSQL Windows installer (Command Line Tools only — the same install provides the `psql`
the restore step needs anyway). Live execution is a Phase 4 operator checkpoint — see Drill
Log below.

## Overview
This document describes the procedure for backing up the ALYASMEEN AuntOps production database and performing a verified restoration drill. Production readiness requires that we can recover from total data loss within a defined RTO (Recovery Time Objective) of 4 hours.

## 1. Backup Procedure

### Automated (Supabase Managed)
Supabase provides daily backups on the Pro tier.
- **Retention:** 7 days (Free tier does not include automated backups).
- **Location:** Supabase Dashboard -> Project -> Database -> Backups.

### Manual (Off-site / Local)
To ensure we have a portable backup outside of Meta/Supabase, run the following weekly.
`pg_dump` comes from the PostgreSQL Windows installer (Command Line Tools), typically at
`C:\Program Files\PostgreSQL\<version>\bin\pg_dump.exe`. Use the live project's **Session
Pooler** connection string (Dashboard -> Settings -> Database -> Connection string ->
Session pooler):
```bash
# Export the app's schema and data (plain SQL, restorable via psql).
# -n public is REQUIRED: without it the dump includes Supabase's internal
# auth/storage schemas, which collide with the target project's own on restore.
pg_dump "<live-session-pooler-url>" -n public --no-owner --no-privileges -f backup_$(date +%F).sql
```
Store these files in a secure, encrypted cloud bucket.

## 2. Restoration Drill Procedure

This drill should be performed quarterly to verify backup integrity.

### Step 1: Link to the live project and take the backup
`link` and `db push` are Docker-free; the dump itself uses native `pg_dump` (see section 1).
```bash
# Link the CLI to the live project (prompts for the DB password:
# Supabase Dashboard -> Settings -> Database)
npx supabase link --project-ref ppwcfmuetgczclmnzvqr

# Apply every migration not yet on the live project — this is also how
# Phase 4's "all migrations applied to the live project" criterion gets satisfied
npx supabase db push --linked

# Dump schema+data with native pg_dump (Session Pooler URL of the LIVE project).
# -n public keeps Supabase's internal auth/storage schemas out of the dump.
pg_dump "<live-session-pooler-url>" -n public --no-owner --no-privileges -f backup_$(date +%F).sql
```

### Step 2 (revised): Restore into a throwaway project
Because the dump above is a FULL public-schema dump (schema + data), do NOT run
`db push` on the throwaway project first — the dump recreates the schema itself:
```bash
psql "<new-project-session-pooler-url>" -f backup_YYYY-MM-DD.sql
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
5. Restore data from the latest manual backup: `psql "<new-project-session-pooler-url>" -f backup_YYYY-MM-DD.sql`.
6. Update application environment variables (`SUPABASE_URL`, `SUPABASE_KEY`) to point to the new project.
7. Verify system functionality.

## 4. Drill Log

| Date | Performed By | Result | Notes |
|------|--------------|--------|-------|
| 2026-06-14 | Claude (Agent) | N/A | Procedure documented; drill pending Docker availability. |
| 2026-08-28 | Khaled (operator), guided by Claude | ✅ PASS | Full public-schema `pg_dump` of live project restored into throwaway project via `psql`; verification counts matched live exactly (products=3, orders=8, order_lines=16, customers=22, chat_history=54). Throwaway project deleted after the drill. RTO comfortably under the 4h target. |
