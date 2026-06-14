# Supabase Backup & Restore Drill

**Date:** 2026-06-14
**Status:** Documented (Drill pending local environment setup)

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

### Step 1: Initialize a clean local environment
```bash
npx supabase init
npx supabase start
```

### Step 2: Apply the backup
```bash
npx supabase db reset # Ensures a clean state
psql -h localhost -p 54322 -U postgres -d postgres -f backup_YYYY-MM-DD.sql
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
