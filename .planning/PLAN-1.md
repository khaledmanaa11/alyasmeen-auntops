# Phase 1: Database Foundation - Master Plan

Goal: Establish a reproducible and recoverable data foundation.

## Overview
This phase moves ALYASMEEN AuntOps from manual database management to a production-ready, versioned, and secure data layer.

## Execution Waves

### Wave 1: Setup & Messaging Schema
**Plan: 01-01-PLAN.md**
- Task 1: Initialize Supabase CLI & Baseline Migration.
- Task 2: Implement Durable Messaging (Inbox/Outbox) & Audit Tables.
- Task 3: Migration Integrity Verification.

### Wave 2: Atomic Logic & Security Hardening
**Plan: 01-02-PLAN.md**
- Task 1: Create `create_order_atomic` pgSQL function.
- Task 2: Enable RLS & define Least Privilege policies.
- Task 3: Update application layer to decommission generic SQL RPCs.

### Wave 3: Verification & Disaster Recovery
**Plan: 01-03-PLAN.md**
- Task 1: Unit & Integration tests for atomic operations.
- Task 2: Integration test for Durable Outbox pattern.
- Task 3: Documented Backup/Restore Drill.

## Requirements Addressed
- REQ-prod-migrations
- REQ-prod-atomic-orders
- REQ-prod-backup-restore
- REQ-prod-data-foundation
- REQ-bot-session-persist

## Success Criteria
1. System can be rebuilt from scratch using migrations.
2. Database restore is verified and documented.
3. No raw SQL-over-RPC remains in the application.
4. Reliable messaging schema is present and enforced.
