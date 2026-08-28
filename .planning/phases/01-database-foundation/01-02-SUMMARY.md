# Wave 2 Summary: Atomic Logic & Security Hardening

**Status:** Completed
**Date:** 2026-06-14

## Work Completed

### Task 1: Create `create_order_atomic` pgSQL function
- Created `supabase/migrations/20260614000002_atomic_order.sql`.
- Implemented a transactional pgSQL function that creates an order, its line items, and an audit log entry in a single transaction.
- Automatically generates the 'ORD-XXXX' order name within the function.

### Task 2: Enable RLS & Define Least Privilege Policies
- Created `supabase/migrations/20260614000003_security_rls.sql`.
- Enabled RLS on all 12 tables.
- Defined policies for `service_role` (full access) and restricted `anon` (read-only for active products).
- Revoked execution of generic `run_query` and `run_exec` RPCs from `anon` and `authenticated` roles.

### Task 3: Update Application Layer
- Refactored `app/db/database.py` to support calling specific RPCs via a new `rpc()` function.
- Updated `app/routers/whatsapp.py` to use `create_order_atomic` for order creation.
- Updated `app/routers/debug.py` to use `create_order_atomic` for test order creation.
- Decommissioned manual SQL building for order creation in both routers.

## Success Criteria Status
1. Atomic logic for order creation is implemented. [YES]
2. RLS is enabled and policies are defined. [YES]
3. Application layer uses specific RPCs for sensitive operations. [YES]
4. Generic SQL RPCs are restricted. [YES]

## Next Steps
Proceed to **Wave 3: Verification & Disaster Recovery**, which involves unit/integration tests and a documented backup/restore drill.
