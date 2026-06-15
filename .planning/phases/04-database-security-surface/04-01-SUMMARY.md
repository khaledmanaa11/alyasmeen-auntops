# Summary: Phase 4 — Database Security Surface

Formalized the Supabase access surface as a deliberate security decision by locking down RPC functions and restricting access to the `service_role` key.

## Accomplishments
- **Secure RPC Migration**: Created `20260615230000_secure_rpc.sql` which formalizes `run_query` and `run_exec` and revokes all public/anon/authenticated permissions.
- **Access Control**: Explicitly granted execution rights only to the `service_role` role.
- **Verification**: Implemented `tests/integration/test_security_surface.py` which proves that the `anon` key is forbidden from executing arbitrary SQL while the `service_role` key succeeds.
- **Documentation**: Updated `.env.example` and internal rationale to reflect the server-side-only access model (bypassing RLS via `service_role`).

## Requirements Covered
- **SEC-01**: Documented choice of `service_role` key for server-side access.
- **SEC-02**: Constrained `run_query`/`run_exec` RPC surface.

## Tech Debt & Gaps
- None. The access model is now deliberate and enforced.
