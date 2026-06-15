import pytest
from app.db.database import validate_schema

def test_live_schema_is_sync():
    """Integration test: Verify that the live Supabase schema matches the codebase requirements.
    
    This test will fail if:
    1. SUPABASE_URL / SUPABASE_KEY are incorrect.
    2. The live database is missing tables or columns defined in database.REQUIRED_SCHEMA.
    """
    try:
        validate_schema()
    except RuntimeError as e:
        pytest.fail(f"Live schema drift detected: {e}")
    except Exception as e:
        pytest.fail(f"Failed to connect or query Supabase: {e}")
