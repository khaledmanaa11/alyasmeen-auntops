"""
test_ai_service.py — Unit tests for app/services/ai_service.py

Tests prompt building, history trimming, language detection, and the
ai_available() guard. All Claude API calls are mocked.
"""


class TestAiAvailable:
    def test_returns_false_when_no_api_key(self, monkeypatch):
        import app.services.ai_service as ai

        monkeypatch.setattr(ai.Config, "CLAUDE_API_KEY", None)
        assert ai.ai_available() is False

    def test_returns_false_when_empty_api_key(self, monkeypatch):
        import app.services.ai_service as ai

        monkeypatch.setattr(ai.Config, "CLAUDE_API_KEY", "")
        assert ai.ai_available() is False

    def test_returns_true_when_key_set(self, monkeypatch):
        import app.services.ai_service as ai

        monkeypatch.setattr(ai.Config, "CLAUDE_API_KEY", "sk-test-key")
        assert ai.ai_available() is True


class TestBuildMessages:
    def test_appends_user_message(self):
        from app.services.ai_service import _build_messages

        msgs = _build_messages("مرحبا", None)
        assert msgs[-1]["role"] == "user"
        assert "مرحبا" in msgs[-1]["content"]

    def test_includes_previous_messages(self):
        from app.services.ai_service import _build_messages

        prev = [
            {"role": "user", "content": "first message"},
            {"role": "assistant", "content": "first reply"},
        ]
        msgs = _build_messages("new message", prev)
        assert len(msgs) == 3
        assert msgs[0]["content"] == "first message"
        assert msgs[1]["content"] == "first reply"
        assert msgs[2]["role"] == "user"

    def test_trims_history_to_last_6(self):
        from app.services.ai_service import _build_messages

        prev = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"}
            for i in range(20)
        ]
        msgs = _build_messages("latest", prev)
        # Should have at most 6 previous + 1 current = 7 total
        assert len(msgs) <= 7

    def test_skips_invalid_roles(self):
        from app.services.ai_service import _build_messages

        prev = [
            {"role": "system", "content": "should be skipped"},
            {"role": "user", "content": "valid"},
        ]
        msgs = _build_messages("new", prev)
        roles = [m["role"] for m in msgs]
        assert "system" not in roles

    def test_skips_empty_content(self):
        from app.services.ai_service import _build_messages

        prev = [
            {"role": "user", "content": ""},
            {"role": "assistant", "content": "valid reply"},
        ]
        msgs = _build_messages("new", prev)
        contents = [m["content"] for m in msgs]
        assert "" not in contents


class TestIsArabic:
    def test_arabic_text_returns_true(self):
        from app.services.ai_service import _is_arabic

        assert _is_arabic("مرحبا") is True

    def test_english_text_returns_false(self):
        from app.services.ai_service import _is_arabic

        assert _is_arabic("Hello world") is False

    def test_mixed_text_returns_true(self):
        from app.services.ai_service import _is_arabic

        assert _is_arabic("Hello مرحبا") is True

    def test_empty_string_returns_false(self):
        from app.services.ai_service import _is_arabic

        assert _is_arabic("") is False


class TestGenerateReply:
    def test_returns_fallback_when_no_api_key(self, monkeypatch):
        import app.services.ai_service as ai

        monkeypatch.setattr(ai.Config, "CLAUDE_API_KEY", None)
        reply = ai.generate_reply("مرحبا", None)
        assert isinstance(reply, str)
        assert len(reply) > 0

    def test_calls_claude_and_returns_text(self, monkeypatch):
        import app.services.ai_service as ai

        monkeypatch.setattr(ai.Config, "CLAUDE_API_KEY", "sk-test")
        monkeypatch.setattr(ai, "Anthropic", _make_mock_anthropic("AI reply text"))

        reply = ai.generate_reply("أريد كريما للبشرة", [])
        assert reply == "AI reply text"

    def test_uses_customer_name_in_system(self, monkeypatch):
        """When customer_name is provided the system prompt should include it."""
        import app.services.ai_service as ai

        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return _make_response("ok")

        fake_client = type("C", (), {
            "messages": type("M", (), {"create": staticmethod(fake_create)})()
        })()

        monkeypatch.setattr(ai.Config, "CLAUDE_API_KEY", "sk-test")
        monkeypatch.setattr(ai, "Anthropic", lambda **kw: fake_client)

        ai.generate_reply("hello", [], customer_name="فاطمة")
        assert "فاطمة" in captured.get("system", "")

    def test_includes_cart_context_when_items_present(self, monkeypatch):
        import app.services.ai_service as ai

        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return _make_response("ok")

        fake_client = type("C", (), {
            "messages": type("M", (), {"create": staticmethod(fake_create)})()
        })()

        monkeypatch.setattr(ai.Config, "CLAUDE_API_KEY", "sk-test")
        monkeypatch.setattr(ai, "Anthropic", lambda **kw: fake_client)

        cart = [{"name": "كريم", "qty": 1, "price": 25.0}]
        ai.generate_reply("confirm", [], cart=cart)
        assert "سلة" in captured.get("system", "")


def _make_mock_anthropic(reply_text: str):
    """Return a fake Anthropic class whose messages.create returns reply_text."""
    block = type("Block", (), {"text": reply_text})()
    response = type("R", (), {"content": [block]})()

    class FakeMessages:
        def create(self, **kwargs):
            return response

    class FakeClient:
        messages = FakeMessages()

    return lambda **kwargs: FakeClient()


def _make_response(text: str):
    block = type("Block", (), {"text": text})()
    return type("R", (), {"content": [block]})()
