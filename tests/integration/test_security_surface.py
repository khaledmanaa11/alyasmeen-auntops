"""
test_security_surface.py — Empirically validates that custom RPC functions 
are locked down to the service_role key.
"""
import os
import pytest
from supabase import create_client
from app.services.config import Config

# This test requires a live Supabase project configured in .env
# to truly validate the "empirical" part of the plan.
# If SUPABASE_URL/KEY are not set, it will be skipped.

URL = Config.SUPABASE_URL
KEY = Config.SUPABASE_KEY

@pytest.mark.skipif(not URL or "your-project" in URL, reason="Supabase not configured")
class TestSecuritySurface:
    
    def test_anon_key_cannot_call_rpc(self, monkeypatch):
        """
        GIVEN an 'anon' key (simulated here if we don't have a real one, 
        but ideally the user provides a real restricted one).
        WHEN attempting to call run_query.
        THEN it should fail with a 403 or similar permission error.
        """
        # Note: If Config.SUPABASE_KEY is already the service_role key,
        # we'd need a real 'anon' key to test this properly.
        # For this test, we assume the user might have an 'anon' key 
        # we can test against, or we just prove the concept.
        
        # If we have a real SUPABASE_ANON_KEY in env, use it.
        anon_key = os.getenv("SUPABASE_ANON_KEY")
        if not anon_key:
            pytest.skip("SUPABASE_ANON_KEY not set in environment")
            
        client = create_client(URL, anon_key)
        
        with pytest.raises(Exception) as excinfo:
            client.rpc("run_query", {"sql": "SELECT 1"}).execute()
        
        # Supabase-py raises postgrest.exceptions.APIError
        # The error message should indicate a permission issue
        assert "403" in str(excinfo.value) or "permission denied" in str(excinfo.value).lower()

    def test_service_role_key_can_call_rpc(self):
        """
        GIVEN the service_role key.
        WHEN attempting to call run_query.
        THEN it should succeed.
        """
        if not KEY or "your-service-role-key" in KEY:
            pytest.skip("SUPABASE_KEY (service_role) not set")
            
        client = create_client(URL, KEY)
        res = client.rpc("run_query", {"sql": "SELECT 1"}).execute()
        assert res.data is not None
        assert len(res.data) == 1
        assert res.data[0] == {"?column?": 1}
