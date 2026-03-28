"""
test_gatekeeper.py — Unit tests for app/shared/gatekeeper.py

Tests rate limiting (bucket logic), retry behaviour on transient failures,
and queue status reporting. All tests are synchronous — asyncio.run() is used
to call async methods without needing pytest-asyncio.
"""
import asyncio
import json
import tempfile
from pathlib import Path

import pytest


def run(coro):
    """Run an async coroutine synchronously in tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# _ServiceBucket tests
# ---------------------------------------------------------------------------

class TestServiceBucket:
    def _make_bucket(self, rpm=10, rph=100, retry_after=1, max_retries=2):
        from app.shared.gatekeeper import _ServiceBucket

        return _ServiceBucket({
            "requests_per_minute": rpm,
            "requests_per_hour": rph,
            "retry_after_seconds": retry_after,
            "max_retries": max_retries,
        })

    def test_bucket_initially_allows_requests(self):
        bucket = self._make_bucket(rpm=5)
        assert bucket.is_allowed() is True

    def test_bucket_blocks_at_rpm_limit(self):
        bucket = self._make_bucket(rpm=3)
        for _ in range(3):
            bucket.record()
        assert bucket.is_allowed() is False

    def test_current_rpm_counts_recent_requests(self):
        bucket = self._make_bucket(rpm=10)
        assert bucket.current_rpm == 0
        bucket.record()
        bucket.record()
        assert bucket.current_rpm == 2

    def test_current_rph_counts_recent_requests(self):
        bucket = self._make_bucket(rph=100)
        assert bucket.current_rph == 0
        for _ in range(5):
            bucket.record()
        assert bucket.current_rph == 5


# ---------------------------------------------------------------------------
# ApiGatekeeper tests
# ---------------------------------------------------------------------------

class TestApiGatekeeper:
    def _make_gatekeeper(self, rpm=50, rph=1000):
        """Create a gatekeeper with a temp config file."""
        from app.shared.gatekeeper import ApiGatekeeper

        cfg = {
            "services": {
                "test_service": {
                    "requests_per_minute": rpm,
                    "requests_per_hour": rph,
                    "retry_after_seconds": 1,
                    "max_retries": 2,
                }
            }
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as tmp:
            json.dump(cfg, tmp)
            tmp_name = tmp.name
        return ApiGatekeeper(config_path=Path(tmp_name))

    def test_execute_calls_sync_function(self):
        gk = self._make_gatekeeper()
        results = []

        def my_fn(x):
            results.append(x)
            return x * 2

        result = run(gk.execute("test_service", my_fn, 5))
        assert result == 10
        assert results == [5]

    def test_execute_calls_async_function(self):
        gk = self._make_gatekeeper()

        async def my_async_fn(x):
            return x + 1

        result = run(gk.execute("test_service", my_async_fn, 10))
        assert result == 11

    def test_execute_retries_on_failure(self):
        gk = self._make_gatekeeper()
        call_count = [0]

        def flaky_fn():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ConnectionError("transient error")
            return "ok"

        result = run(gk.execute("test_service", flaky_fn))
        assert result == "ok"
        assert call_count[0] == 3  # failed twice, succeeded on 3rd

    def test_execute_raises_after_max_retries_exhausted(self):
        gk = self._make_gatekeeper()

        def always_fail():
            raise RuntimeError("permanent failure")

        with pytest.raises(RuntimeError, match="permanent failure"):
            run(gk.execute("test_service", always_fail))

    def test_get_queue_status_returns_dict(self):
        gk = self._make_gatekeeper()
        status = gk.get_queue_status()
        assert isinstance(status, dict)
        assert "test_service" in status
        svc = status["test_service"]
        assert "current_rpm" in svc
        assert "rpm_limit" in svc
        assert "current_rph" in svc
        assert "rph_limit" in svc

    def test_unknown_service_uses_default_bucket(self):
        gk = self._make_gatekeeper()

        def fn():
            return "result"

        # Should not raise even for unknown service
        result = run(gk.execute("unknown_service", fn))
        assert result == "result"

    def test_load_missing_config_returns_empty_gatekeeper(self):
        from app.shared.gatekeeper import ApiGatekeeper

        gk = ApiGatekeeper(config_path=Path("/nonexistent/path/rate_limits.json"))
        # Should not raise; just has no configured services
        assert isinstance(gk.get_queue_status(), dict)
