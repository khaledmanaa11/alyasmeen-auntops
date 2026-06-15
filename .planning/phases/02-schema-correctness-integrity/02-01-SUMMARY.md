# Summary: Phase 02, Plan 01 — Schema Hardening and Core Validation

## Results

Wave 1 of Phase 2 is COMPLETE. The database schema has been hardened for idempotency, and the core validation logic is now implemented in the application's database layer.

### Schema Hardening (`app/db/schema.sql`)
- **Idempotency:** Added `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for all columns in all 9 tables. This ensures the schema script can be safely re-run against the live Supabase instance to reconcile drift without data loss.
- **Missing Table:** Added the `monthly_snapshots` table definition, including indexes on `(year, month)`. This fixes the known gap where monthly reports and dashboard stats would crash due to the missing table.

### Validation Core (`app/db/database.py`)
- **REQUIRED_SCHEMA:** Defined a comprehensive map of all tables and columns that the application expects to find in the database.
- **validate_schema():** Implemented a new function that:
    1. Queries `information_schema.columns` via the existing HTTPS-RPC bridge.
    2. Compares the live schema against `REQUIRED_SCHEMA`.
    3. Raises a `RuntimeError` with a detailed error message (listing missing tables or columns) if drift is detected.

## Success Criteria Verification

| Criterion | Status | Notes |
|-----------|--------|-------|
| `monthly_snapshots` in `schema.sql` | ✅ PASS | Verified table and index definitions |
| Idempotent `ADD COLUMN` for all tables | ✅ PASS | Added to all 9 tables |
| `REQUIRED_SCHEMA` in `database.py` | ✅ PASS | Includes all 9 tables and their columns |
| `validate_schema()` implemented | ✅ PASS | Uses `information_schema.columns` |

## Next Steps
- **Wave 2 (Plan 02):**
    - Migrate `app/main.py` to use the FastAPI `lifespan` context manager.
    - Wire `validate_schema()` into the application startup so it fails fast on schema drift.
    - Add unit and integration tests to verify the validation logic and the live database state.
