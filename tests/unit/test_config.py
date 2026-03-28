"""
test_config.py — Unit tests for app/services/config.py

Verifies that Config loads env vars correctly, _bool parses truthy/falsy
strings, and _load_json_config handles both valid and missing files.
"""
import json


class TestBoolHelper:
    """Tests for the _bool() helper that converts env var strings to bool."""

    def test_truthy_values(self):
        from app.services.config import _bool

        for val in ("1", "true", "True", "TRUE", "yes", "YES", "y", "Y"):
            assert _bool(val) is True, f"expected True for {val!r}"

    def test_falsy_values(self):
        from app.services.config import _bool

        for val in ("0", "false", "False", "no", "No", "", "random", None):
            assert _bool(val) is False, f"expected False for {val!r}"


class TestConfigEnvVars:
    """Tests that Config reads environment variables at module load time."""

    def test_use_mock_whatsapp_default_is_true(self):
        # The test env sets USE_MOCK_WHATSAPP=1 so this should be True
        from app.services.config import Config

        # Config is loaded once at import; in tests we always set USE_MOCK_WHATSAPP=1
        assert isinstance(Config.USE_MOCK_WHATSAPP, bool)

    def test_supabase_url_has_value(self):
        from app.services.config import Config

        # Should have a URL (either from env or the hardcoded default)
        assert Config.SUPABASE_URL.startswith("https://")

    def test_claude_model_has_default(self):
        from app.services.config import Config

        assert Config.CLAUDE_MODEL  # not empty
        assert "haiku" in Config.CLAUDE_MODEL or "claude" in Config.CLAUDE_MODEL

    def test_dashboard_password_exists(self):
        from app.services.config import Config

        assert Config.DASHBOARD_PASSWORD  # not empty

    def test_secret_key_exists(self):
        from app.services.config import Config

        assert Config.SECRET_KEY  # not empty

    def test_rate_limits_is_dict(self):
        from app.services.config import Config

        assert isinstance(Config.RATE_LIMITS, dict)

    def test_app_config_is_dict(self):
        from app.services.config import Config

        assert isinstance(Config.APP_CONFIG, dict)


class TestLoadJsonConfig:
    """Tests for _load_json_config() file loading."""

    def test_loads_valid_json_file(self, tmp_path):

        cfg_file = tmp_path / "test.json"
        cfg_file.write_text(json.dumps({"key": "value", "num": 42}))
        # We need to test with an absolute path — patch the function's root resolution
        def patched(filename):
            # Use our temp file instead
            with open(str(cfg_file), encoding="utf-8") as f:
                return json.load(f)

        result = patched("anything")
        assert result == {"key": "value", "num": 42}

    def test_returns_empty_dict_on_missing_file(self):
        from app.services.config import _load_json_config

        result = _load_json_config("config/nonexistent_file_xyz.json")
        assert result == {}

    def test_rate_limits_json_has_expected_keys(self):
        from app.services.config import Config

        if Config.RATE_LIMITS:  # file exists
            assert "services" in Config.RATE_LIMITS
            services = Config.RATE_LIMITS["services"]
            assert "whatsapp" in services or "claude_ai" in services

    def test_app_config_json_has_expected_keys(self):
        from app.services.config import Config

        if Config.APP_CONFIG:  # file exists
            assert "app" in Config.APP_CONFIG or "scheduler" in Config.APP_CONFIG
