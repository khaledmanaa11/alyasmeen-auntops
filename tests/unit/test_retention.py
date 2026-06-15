from unittest.mock import MagicMock, patch

import pytest

from app.services.retention import run_retention


@patch("app.services.retention.execute")
@patch("app.services.retention.Config")
def test_run_retention_calls(mock_config, mock_execute):
    """Test that run_retention calls execute with correct SQL."""
    mock_config.APP_CONFIG = {
        "retention": {
            "chat_history_days": 10,
            "retry_queue_days": 15
        }
    }
    
    run_retention()
    
    # Check that execute was called twice
    assert mock_execute.call_count == 2
    
    # Check first call (chat_history)
    args1 = mock_execute.call_args_list[0][0]
    assert "DELETE FROM chat_history" in args1[0]
    assert args1[1] == (10,)
    
    # Check second call (retry_queue)
    args2 = mock_execute.call_args_list[1][0]
    assert "DELETE FROM retry_queue" in args2[0]
    assert "resolved = TRUE" in args2[0]
    assert args2[1] == (15,)


@patch("app.services.retention.execute")
@patch("app.services.retention.Config")
def test_run_retention_defaults(mock_config, mock_execute):
    """Test that run_retention uses defaults when config is missing."""
    mock_config.APP_CONFIG = {}
    
    run_retention()
    
    # Check first call (chat_history default 30)
    args1 = mock_execute.call_args_list[0][0]
    assert args1[1] == (30,)
    
    # Check second call (retry_queue default 30)
    args2 = mock_execute.call_args_list[1][0]
    assert args2[1] == (30,)
