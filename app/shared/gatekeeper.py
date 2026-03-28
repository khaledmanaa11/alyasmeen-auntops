"""
gatekeeper.py — Centralized external API call manager for ALYASMEEN AuntOps.

All outbound calls to Claude AI and WhatsApp Meta API must route through
this gatekeeper. It enforces rate limits loaded from config/rate_limits.json,
queues requests when limits are reached, retries on transient failures, and
logs every call with timestamp, service name, and success/failure outcome.

Why this exists: without a central gatekeeper, each service independently
retries and there is no visibility into total outbound API usage across the app.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "rate_limits.json"


def _load_rate_config(config_path: Path) -> dict:
    """Load rate limit configuration from a JSON file.

    Args:
        config_path: Absolute path to the rate_limits.json file.

    Returns:
        Parsed config dict, or empty dict if the file cannot be read.
    """
    try:
        with open(config_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        log.warning("gatekeeper: could not load rate config from %s: %s", config_path, exc)
        return {}


class _ServiceBucket:
    """Sliding-window rate limiter for one external service.

    Tracks the timestamps of recent requests in a deque and enforces
    both per-minute and per-hour limits using a sliding window approach.
    """

    def __init__(self, service_cfg: dict) -> None:
        """Initialise the bucket from a service config dict.

        Args:
            service_cfg: Dict with keys: requests_per_minute, requests_per_hour,
                         retry_after_seconds, max_retries.
        """
        self.rpm: int = service_cfg.get("requests_per_minute", 30)
        self.rph: int = service_cfg.get("requests_per_hour", 500)
        self.retry_after: int = service_cfg.get("retry_after_seconds", 30)
        self.max_retries: int = service_cfg.get("max_retries", 3)
        self._minute_window: deque[float] = deque()
        self._hour_window: deque[float] = deque()

    def _prune(self, now: float) -> None:
        """Remove timestamps older than the current window from both deques."""
        while self._minute_window and now - self._minute_window[0] > 60:
            self._minute_window.popleft()
        while self._hour_window and now - self._hour_window[0] > 3600:
            self._hour_window.popleft()

    def is_allowed(self) -> bool:
        """Return True if the next request is within rate limits."""
        now = time.monotonic()
        self._prune(now)
        return len(self._minute_window) < self.rpm and len(self._hour_window) < self.rph

    def record(self) -> None:
        """Record that a request was just made."""
        now = time.monotonic()
        self._minute_window.append(now)
        self._hour_window.append(now)

    @property
    def current_rpm(self) -> int:
        """Number of requests made in the last 60 seconds."""
        now = time.monotonic()
        self._prune(now)
        return len(self._minute_window)

    @property
    def current_rph(self) -> int:
        """Number of requests made in the last 3600 seconds."""
        now = time.monotonic()
        self._prune(now)
        return len(self._hour_window)


class ApiGatekeeper:
    """Centralized external API call manager.

    Enforces rate limits, handles retries with backoff, and logs all
    outbound API calls. Configuration is loaded from config/rate_limits.json
    — no limits are hardcoded in this class.

    Usage:
        gatekeeper = ApiGatekeeper()
        result = await gatekeeper.execute("claude_ai", my_async_fn, arg1, kwarg=val)

    The gatekeeper is safe to share as a module-level singleton.
    """

    def __init__(self, config_path: Path = _DEFAULT_CONFIG_PATH) -> None:
        """Load rate limit config and initialise per-service buckets.

        Args:
            config_path: Path to rate_limits.json. Defaults to config/rate_limits.json
                         relative to the project root.
        """
        raw = _load_rate_config(config_path)
        services: dict = raw.get("services", {})
        self._buckets: dict[str, _ServiceBucket] = {
            name: _ServiceBucket(cfg) for name, cfg in services.items()
        }
        log.info("gatekeeper: loaded rate limits for services: %s", list(self._buckets))

    def _bucket(self, service: str) -> _ServiceBucket:
        """Return the rate-limit bucket for a service, creating a default if unknown."""
        if service not in self._buckets:
            log.warning("gatekeeper: unknown service '%s' — using permissive defaults", service)
            self._buckets[service] = _ServiceBucket({})
        return self._buckets[service]

    async def execute(self, service: str, api_call: Callable, *args: Any, **kwargs: Any) -> Any:
        """Execute an API call through the gatekeeper.

        Checks the rate limit before execution, waits if the limit is reached,
        retries on transient failures (up to max_retries from config), and logs
        every call with timestamp, service name, and outcome.

        Args:
            service:  Service name key matching an entry in rate_limits.json
                      (e.g. "claude_ai" or "whatsapp").
            api_call: Async or sync callable to invoke.
            *args:    Positional arguments forwarded to api_call.
            **kwargs: Keyword arguments forwarded to api_call.

        Returns:
            The return value of api_call.

        Raises:
            The last exception raised by api_call after all retries are exhausted.
        """
        bucket = self._bucket(service)
        max_retries = bucket.max_retries
        retry_after = bucket.retry_after

        # Wait until within rate limit
        waited = 0.0
        while not bucket.is_allowed():
            log.warning(
                "gatekeeper: rate limit reached for %s (rpm=%d/%d) — waiting %ds",
                service, bucket.current_rpm, bucket.rpm, retry_after,
            )
            await asyncio.sleep(retry_after)
            waited += retry_after

        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                bucket.record()
                t0 = time.monotonic()
                if asyncio.iscoroutinefunction(api_call):
                    result = await api_call(*args, **kwargs)
                else:
                    result = api_call(*args, **kwargs)
                elapsed = time.monotonic() - t0
                log.info(
                    "gatekeeper: %s OK attempt=%d elapsed=%.2fs rpm=%d",
                    service, attempt + 1, elapsed, bucket.current_rpm,
                )
                return result

            except Exception as exc:
                last_exc = exc
                log.warning(
                    "gatekeeper: %s FAILED attempt=%d/%d error=%s",
                    service, attempt + 1, max_retries + 1, exc,
                )
                if attempt < max_retries:
                    backoff = retry_after * (2 ** attempt)
                    await asyncio.sleep(backoff)

        raise last_exc  # type: ignore[misc]

    def get_queue_status(self) -> dict:
        """Return current rate-limit stats per service.

        Useful for health-check endpoints and monitoring dashboards.

        Returns:
            Dict mapping service name → {current_rpm, rpm_limit, current_rph, rph_limit}.
        """
        return {
            name: {
                "current_rpm": bucket.current_rpm,
                "rpm_limit": bucket.rpm,
                "current_rph": bucket.current_rph,
                "rph_limit": bucket.rph,
            }
            for name, bucket in self._buckets.items()
        }


# Module-level singleton — import this everywhere instead of instantiating directly.
gatekeeper = ApiGatekeeper()
