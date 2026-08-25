"""
test_main_debug_gate.py — Verifies the /dev/* debug router is only wired up
in dev/mock mode (Config.USE_MOCK_WHATSAPP), never in a production config.

Config.USE_MOCK_WHATSAPP and the debug-router registration in app/main.py
are both evaluated once at import time, so the only reliable way to test
both branches of the gate is a fresh interpreter per branch (a reload-in-
process approach would race with whichever value another test module
already imported Config with). Each subprocess sets the env vars app.main
needs (Config hard-fails outside pytest if DASHBOARD_PASSWORD/SECRET_KEY are
unset) and reports back whether app.main.debug_router ended up registered.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_CHECK_SCRIPT = (
    "import app.main as m\n"
    "print('DEBUG_ROUTER_REGISTERED' if m.debug_router is not None else 'DEBUG_ROUTER_NONE')\n"
    "paths = {r.path for r in m.app.routes}\n"
    "print('ROUTE_PRESENT' if '/dev/test_order' in paths else 'ROUTE_ABSENT')\n"
)

_BASE_ENV = {
    "DASHBOARD_PASSWORD": "test-password",
    "SECRET_KEY": "test-secret",
    "CLAUDE_MODEL": "claude-haiku-4-5-20251001",
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_KEY": "test-key",
}


def _run(extra_env: dict) -> str:
    import os

    env = dict(os.environ)
    env.update(_BASE_ENV)
    env.update(extra_env)
    # A subprocess has no PYTEST_CURRENT_TEST and no pytest import, so
    # Config's hard-fail-outside-pytest branch is exercised honestly.
    env.pop("PYTEST_CURRENT_TEST", None)
    result = subprocess.run(
        [sys.executable, "-c", _CHECK_SCRIPT],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    return result.stdout


def test_debug_router_registered_when_mock_whatsapp_on():
    out = _run({"USE_MOCK_WHATSAPP": "1"})
    assert "DEBUG_ROUTER_REGISTERED" in out
    assert "ROUTE_PRESENT" in out


def test_debug_router_not_registered_when_mock_whatsapp_off():
    out = _run({"USE_MOCK_WHATSAPP": "0"})
    assert "DEBUG_ROUTER_NONE" in out
    assert "ROUTE_ABSENT" in out
