-- Secure RPC Functions for Server-Side Database Access
-- This migration formalizes run_query and run_exec and restricts them to the service_role.

-- 1. Create run_query function
CREATE OR REPLACE FUNCTION run_query(sql text)
RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  result json;
BEGIN
  EXECUTE 'SELECT json_agg(t) FROM (' || sql || ') t' INTO result;
  RETURN result;
END;
$$;

-- 2. Create run_exec function
CREATE OR REPLACE FUNCTION run_exec(sql text)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  EXECUTE sql;
END;
$$;

-- 3. Revoke all permissions from public, anon, and authenticated roles
REVOKE ALL ON FUNCTION run_query(text) FROM public, anon, authenticated;
REVOKE ALL ON FUNCTION run_exec(text) FROM public, anon, authenticated;

-- 4. Grant execute permission only to the service_role
GRANT EXECUTE ON FUNCTION run_query(text) TO service_role;
GRANT EXECUTE ON FUNCTION run_exec(text) TO service_role;
