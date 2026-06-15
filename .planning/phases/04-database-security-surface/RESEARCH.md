# Research: Phase 4 — Database Security Surface

## Current State Analysis

### 1. Supabase Connection Mechanism
- The application connects to Supabase via `supabase-py` using HTTPS.
- Two central RPC functions are used to execute all SQL:
    - `run_query(sql text) -> json`: Used for `SELECT` and `INSERT...RETURNING`.
    - `run_exec(sql text) -> void`: Used for `INSERT`, `UPDATE`, `DELETE`.
- These functions are currently "shadow" state; they are not defined in the `supabase/migrations/` or `legacy/schema.sql`.

### 2. Key Usage
- `.env.example` suggests the use of the `anon` key (`SUPABASE_KEY=your_anon_key_here`).
- The application runs server-side, meaning it *could* safely use the `service_role` key if configured to do so.

### 3. Security Vulnerabilities
- **Arbitrary SQL Execution:** Any client with the `SUPABASE_KEY` can call these RPCs with any SQL string.
- **Privilege Escalation:** If the RPC functions are `SECURITY DEFINER` (default when created via some Supabase UI paths), they run with the privileges of the creator (usually `postgres`), bypassing RLS.
- **Information Leakage:** `run_query` can be used to probe `information_schema` or other sensitive system tables if not restricted.

## Requirements Traceability

- **SEC-01: Key Selection**: Decide between `anon` vs `service_role`. 
    - *Research Recommendation*: Use `service_role` for server-side access and disable `anon` access to these RPCs.
- **SEC-02: RPC Constraints**: 
    - *Research Recommendation*: 
        1. Define the functions in a migration.
        2. Set them to `SECURITY INVOKER` or restricted `SECURITY DEFINER`.
        3. Revoke `EXECUTE` from `public` and `anon`.
        4. Grant `EXECUTE` only to `service_role` (or a specific application role).

## Proposed Implementation Path

1. **Baseline RPCs**: Create a migration that formally defines `run_query` and `run_exec` so the project can be rebuilt from scratch.
    
    Expected SQL definitions (to be verified/hardened):
    ```sql
    CREATE OR REPLACE FUNCTION run_query(sql_query text)
    RETURNS json
    LANGUAGE plpgsql
    SECURITY DEFINER
    SET search_path = public
    AS $$
    DECLARE
        result json;
    BEGIN
        EXECUTE 'SELECT json_agg(t) FROM (' || sql_query || ') t' INTO result;
        RETURN COALESCE(result, '[]'::json);
    END;
    $$;

    CREATE OR REPLACE FUNCTION run_exec(sql_query text)
    RETURNS void
    LANGUAGE plpgsql
    SECURITY DEFINER
    SET search_path = public
    AS $$
    BEGIN
        EXECUTE sql_query;
    END;
    $$;
    ```
    *Note: `SET search_path = public` is a security best practice for `SECURITY DEFINER` functions to prevent search_path hijacking.*

2. **Key Hardening**:
    - Update `Config` to explicitly expect a service role key if that's the decision.
    - Document the rationale in `PROJECT.md` or a new `SECURITY.md`.
3. **Permission Lockdown**:
    - `REVOKE ALL ON FUNCTION run_query(text) FROM public, anon;`
    - `GRANT EXECUTE ON FUNCTION run_query(text) TO service_role;`
    - (Same for `run_exec`)
4. **Validation**:
    - Add a test that attempts to call the RPC with the `anon` key and confirms it fails (403/401).
    - Confirm the app still works with the `service_role` key.

## Open Questions
- Do we want to keep arbitrary SQL at all?
    - *Decision*: For M1, yes, as it matches the existing architecture. Hardening the existing surface is the goal.
- Should we use a custom role instead of `service_role`?
    - *Decision*: `service_role` is standard for server-side trusted access in Supabase and simplifies setup.
