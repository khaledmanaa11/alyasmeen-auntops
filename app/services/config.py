"""config.py — Central configuration for ALYASMEEN AuntOps. All environment variables and JSON config files are loaded here. Import Config everywhere — never read os.getenv() directly in other modules."""
import os

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

    # Database (Supabase — HTTPS via supabase-py)
    SUPABASE_URL = os.getenv("SUPABASE_URL", "https://ppwcfmuetgczclmnzvqr.supabase.co")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

    # WhatsApp (Meta Cloud API)
    WA_META_TOKEN       = os.getenv("WA_META_TOKEN")        # permanent access token
    WA_META_PHONE_ID    = os.getenv("WA_META_PHONE_ID")     # phone number ID
    WA_META_VERIFY_TOKEN = os.getenv("WA_META_VERIFY_TOKEN") # webhook verification
    WA_META_APP_SECRET  = os.getenv("WA_META_APP_SECRET")   # optional signature check

    # Claude AI (Anthropic)
    CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
    CLAUDE_MODEL   = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

    # Web Dashboard
    DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "admin123")
    SECRET_KEY         = os.getenv("SECRET_KEY", "change-me-in-production")

    # Aunt (monthly report + new-order notifications)
    AUNT_PHONE = os.getenv("AUNT_PHONE")  # e.g. 972591234567

    # AI knowledge base directory
    KNOWLEDGE_DIR: str = os.getenv(
        "KNOWLEDGE_DIR",
        os.path.join(os.path.dirname(__file__), "..", "data", "knowledge"),
    )

    # Broadcast message improvement — max tokens for the AI polish call
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

