import pytest
from unittest.mock import patch, MagicMock
from app.db.database import validate_schema, REQUIRED_SCHEMA

def test_validate_schema_success():
    """Test that validate_schema passes when all tables and columns are present."""
    mock_rows = []
    for table, columns in REQUIRED_SCHEMA.items():
        for col in columns:
            mock_rows.append({"table_name": table, "column_name": col})
    
    # Add an extra table to ensure it doesn't cause failure
    mock_rows.append({"table_name": "extra_table", "column_name": "id"})

    with patch("app.db.database.query", return_value=mock_rows):
        # Should not raise any exception
        validate_schema()

def test_validate_schema_missing_table():
    """Test that validate_schema raises RuntimeError if a table is missing."""
    mock_rows = [{"table_name": "other_table", "column_name": "id"}] # No 'products' table
    
    with patch("app.db.database.query", return_value=mock_rows):
        with pytest.raises(RuntimeError) as excinfo:
            validate_schema()
        assert "Missing table 'products'" in str(excinfo.value)

def test_validate_schema_missing_column():
    """Test that validate_schema raises RuntimeError if a column is missing."""
    mock_rows = []
    for table, columns in REQUIRED_SCHEMA.items():
        for col in columns:
            # Skip one column in the products table
            if table == "products" and col == "active":
                continue
            mock_rows.append({"table_name": table, "column_name": col})
    
    with patch("app.db.database.query", return_value=mock_rows):
        with pytest.raises(RuntimeError) as excinfo:
            validate_schema()
        assert "Table 'products' missing columns" in str(excinfo.value)
        assert "active" in str(excinfo.value)
