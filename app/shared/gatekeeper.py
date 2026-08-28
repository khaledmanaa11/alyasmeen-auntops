"""
gatekeeper.py — Centralized external API call manager for ALYASMEEN AuntOps.

All outbound calls to Claude AI and WhatsApp Meta API must route through
this gatekeeper. It enforces rate limits loaded from config/rate_limits.json
and logs every call with timestamp, service name, and success/failure outcome.

Why this is synchronous (no coroutines, no event loop): the worker
(`app/worker.py`) runs an APScheduler `BlockingScheduler` with interval jobs
on a 2-3s cadence (`process_webhook_events` every 3s, `process_outbox_jobs`
every 2s) and APScheduler's default `max_instances=1` per job means a job
instance that blocks past its next scheduled fire is *skipped*, not queued.
The previous coroutine-based `execute()` design awaited a sleep call
(`retry_after` seconds) inside an *unbounded* loop
(`while not bucket.is_allowed(): ...`) — sleeping even one full
`retry_after_seconds` (10s for claude_ai, 30s for whatsapp, both calibrated
for a different, concurrent design) already blows past several poll
intervals and stalls the single worker thread. This rewrite makes
`execute()` a plain synchronous call with a small, bounded admission-control
wait (`_MAX_WAIT_SECONDS`) that is independent of `retry_after_seconds` in
the config — if a service is still rate-limited after the bounded wait,
`RateLimitExceeded` is raised immediately instead of sleeping further. There
is also no internal retry-on-failure loop: retry/defer is already handled
one layer up, by the outbox's `attempts`/`max_attempts` (re-polled every 2s)
and by `ai_service`'s existing fallback-on-exception path — a second nested
retry loop here would only make latency less predictable.
"""
from __future__ import annotations

import json
import logging
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "rate_limits.json"

# Bounded admission-control wait for execute(). Deliberately small and
# independent of config/rate_limits.json's retry_after_seconds (10s/30s) —
# those values stay in the config file as documentation of target rate
# limits for a human tuning them, but must NOT drive a sleep duration inside
# a 2-3s-interval worker loop (see module docstring / 04-RESEARCH.md
# "Pitfall 1").
_MAX_WAIT_SECONDS = 1.5
_POLL_INTERVAL_SECONDS = 0.2


class RateLimitExceeded(RuntimeError):
    """Raised when a service is still rate-limited after the bounded wait."""


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
            service_cfg: Dict with keys: requests_per_minute, requests_per_hour.
        """
        self.rpm: int = service_cfg.get("requests_per_minute", 30)
        self.rph: int = service_cfg.get("requests_per_hour", 500)
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

    Enforces rate limits and logs all outbound API calls. Configuration is
    loaded from config/rate_limits.json — no limits are hardcoded in this
    class. Fully synchronous — safe to call from the worker's blocking,
    2-3s-interval APScheduler jobs.

    Usage:
        gatekeeper = ApiGatekeeper()
        result = gatekeeper.execute("claude_ai", my_sync_fn, arg1, kwarg=val)

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

    def execute(
        self,
        service: str,
        api_call: Callable,
        *args: Any,
        max_wait: float = _MAX_WAIT_SECONDS,
        poll_interval: float = _POLL_INTERVAL_SECONDS,
        **kwargs: Any,
    ) -> Any:
        """Execute an API call through the gatekeeper.

        Checks the rate limit before execution. If the service is currently
        rate-limited, polls briefly (up to `max_wait` seconds total) for a
        slot to open. If still rate-limited after that bounded wait, raises
        `RateLimitExceeded` instead of blocking further. No internal retry
        on failure — `api_call`'s exceptions propagate directly to the
        caller, which already has its own retry/fallback handling.

        Args:
            service:       Service name key matching an entry in rate_limits.json
                           (e.g. "claude_ai" or "whatsapp").
            api_call:      Sync callable to invoke.
            *args:         Positional arguments forwarded to api_call.
            max_wait:      Maximum total seconds to wait for a rate-limit slot
                           before raising RateLimitExceeded.
            poll_interval: Seconds to sleep between rate-limit checks while waiting.
            **kwargs:      Keyword arguments forwarded to api_call.

        Returns:
            The return value of api_call.

        Raises:
            RateLimitExceeded: if the service is still rate-limited after the
                bounded wait.
            Exception: whatever api_call itself raises, propagated unmodified.
        """
        bucket = self._bucket(service)
        waited = 0.0
        while not bucket.is_allowed() and waited < max_wait:
            time.sleep(poll_interval)
            waited += poll_interval

        if not bucket.is_allowed():
            log.warning(
                "gatekeeper: %s still rate-limited after %.2fs wait (rpm=%d/%d) — failing fast",
                service, waited, bucket.current_rpm, bucket.rpm,
            )
            raise RateLimitExceeded(f"{service} rate limit exceeded after {waited:.2f}s wait")

        bucket.record()
        t0 = time.monotonic()
        result = api_call(*args, **kwargs)
        log.info(
            "gatekeeper: %s OK elapsed=%.2fs rpm=%d/%d",
            service, time.monotonic() - t0, bucket.current_rpm, bucket.rpm,
        )
        return result

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
