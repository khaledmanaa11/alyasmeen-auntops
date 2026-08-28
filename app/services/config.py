"""config.py ג€” Central configuration for ALYASMEEN AuntOps. All environment variables and JSON config files are loaded here. Import Config everywhere ג€” never read os.getenv() directly in other modules."""
import os
import sys

from dotenv import load_dotenv

load_dotenv()


def _bool(x: str | None) -> bool:
    """Convert an environment variable string to a boolean.

    Returns True for the strings "1", "true", "yes", or "y" (case-insensitive).
    Returns False for everything else, including None and empty strings.
    """
    return str(x or "").strip().lower() in ("1", "true", "yes", "y")


class Config:
    # Mode
    USE_MOCK_WHATSAPP = _bool(os.getenv("USE_MOCK_WHATSAPP", "1"))

    # Database (Supabase ג€” HTTPS via supabase-py)
    SUPABASE_URL = os.getenv("SUPABASE_URL", "https://ppwcfmuetgczclmnzvqr.supabase.co")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
    # anon/public key ג€” used ONLY by app/services/auth.py for the non-admin Supabase Auth
    # surface (sign_in_with_password, mfa.*, reset_password_for_email). SUPABASE_KEY above
    # stays the service_role key, reserved for auth.admin.* and all database.py traffic.
    # Keep them separate even though the app is server-only ג€” mixing them is how a
    # service_role key eventually leaks into a code path that faces a browser.
    SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
    # Postgres connection string (required for APScheduler JobStore)
    DATABASE_URL = os.getenv("DATABASE_URL", "")

    # WhatsApp (Meta Cloud API)
    WA_META_TOKEN       = os.getenv("WA_META_TOKEN")        # permanent access token
    WA_META_PHONE_ID    = os.getenv("WA_META_PHONE_ID")     # phone number ID
    WA_META_VERIFY_TOKEN = os.getenv("WA_META_VERIFY_TOKEN") # webhook verification
    WA_META_APP_SECRET  = os.getenv("WA_META_APP_SECRET")   # optional signature check

    # Claude AI (Anthropic)
    CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
    CLAUDE_MODEL   = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

    # Web Dashboard
    DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD")
    SECRET_KEY         = os.getenv("SECRET_KEY")

    # Aunt (monthly report + new-order notifications)
    AUNT_PHONE = os.getenv("AUNT_PHONE")  # e.g. 972591234567
    # Admin (Khaled) ג€” receives new-device login alerts and every permanent-failure alert.
    # The aunt is not bothered by device alerts; Khaled gets everything.
    ADMIN_PHONE = os.getenv("ADMIN_PHONE")
    # Base URL used as the redirect_to target for Supabase Auth password-reset links.
    DASHBOARD_BASE_URL = os.getenv("DASHBOARD_BASE_URL", "http://localhost:8000")

    # AI knowledge base directory
    KNOWLEDGE_DIR: str = os.getenv(
        "KNOWLEDGE_DIR",
        os.path.join(os.path.dirname(__file__), "..", "data", "knowledge"),
    )

    # Broadcast message improvement ג€” max tokens for the AI polish call
    BROADCAST_IMPROVEMENT_MAX_TOKENS: int = 300

    # JSON config (loaded from config/ directory)
    RATE_LIMITS: dict = {}
    APP_CONFIG: dict = {}


def _load_json_config(filename: str) -> dict:
    """Load a JSON config file relative to the project root. Returns {} on error."""
    import json
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[2]
    config_path = project_root / filename
    try:
        with open(config_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


Config.RATE_LIMITS = _load_json_config("config/rate_limits.json")
Config.APP_CONFIG = _load_json_config("config/setup.json")

# --- Validation ---
if not Config.CLAUDE_MODEL:
    raise ValueError("CLAUDE_MODEL is required")

# DASHBOARD_PASSWORD / SECRET_KEY must never fall back to a hardcoded value —
# skip the hard-fail under pytest so the test suite doesn't need real secrets.
_RUNNING_UNDER_PYTEST = "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules
if not _RUNNING_UNDER_PYTEST:
    if not Config.DASHBOARD_PASSWORD:
        raise ValueError("DASHBOARD_PASSWORD is required — set it in your environment/.env")
    if not Config.SECRET_KEY:
        raise ValueError("SECRET_KEY is required — set it in your environment/.env")
