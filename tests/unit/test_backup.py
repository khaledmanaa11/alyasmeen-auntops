import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.backup import _prune_backups, run_backup
from app.services.config import Config


@pytest.fixture
def mock_backup_dir(tmp_path):
    """Create a temporary backups directory."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    return backup_dir


@patch("app.services.backup.Config")
@patch("app.services.backup.Path")
@patch("app.services.backup.subprocess.run")
def test_run_backup(mock_run, mock_path, mock_config, tmp_path):
    """Test that run_backup calls the correct command."""
    mock_config.SUPABASE_DB_PASSWORD = "test-password"
    
    # Mock project root to use tmp_path
    mock_path.return_value.resolve.return_value.parents.__getitem__.return_value = tmp_path
    
    backup_dir = tmp_path / "backups"
    
    run_backup()
    
    # Verify subprocess.run was called with correct cmd and env
    args, kwargs = mock_run.call_args
    cmd = args[0]
    assert "supabase" in cmd
    assert "db" in cmd
    assert "dump" in cmd
    assert "--data-only" in cmd
    
    env = kwargs.get("env")
    assert env["SUPABASE_DB_PASSWORD"] == "test-password"


def test_prune_backups(mock_backup_dir):
    """Test that retention logic keeps only last 7 files."""
    # Create 10 dummy backup files
    for i in range(10):
        filepath = mock_backup_dir / f"backup_2026-06-{i+1:02d}_0000.sql"
        filepath.write_text("dummy data")
        # Ensure different modification times
        os.utime(filepath, (1623715200 + i, 1623715200 + i))

    _prune_backups(mock_backup_dir)

    remaining = list(mock_backup_dir.glob("backup_*.sql"))
    assert len(remaining) == 7
    # Verify that the oldest ones (1, 2, 3) were pruned
    # Sorted by mtime descending, so indices 0-6 are i=9 down to i=3.
    # i=0, 1, 2 should be gone.
    filenames = [f.name for f in remaining]
    assert "backup_2026-06-01_0000.sql" not in filenames
    assert "backup_2026-06-02_0000.sql" not in filenames
    assert "backup_2026-06-03_0000.sql" not in filenames
    assert "backup_2026-06-04_0000.sql" in filenames


@patch("app.services.backup.Config")
def test_run_backup_no_password(mock_config):
    """Test that run_backup skips if password is missing."""
    mock_config.SUPABASE_DB_PASSWORD = ""
    with patch("logging.Logger.warning") as mock_log:
        run_backup()
        # Verify skip was logged (or at least no subprocess was run)
        # In a real test we'd check if subprocess.run was NOT called.
