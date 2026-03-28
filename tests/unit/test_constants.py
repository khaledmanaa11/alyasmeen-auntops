"""
test_constants.py — Unit tests for app/shared/constants.py

Verifies all constants exist, have correct types, and contain expected values.
"""


class TestOrderStatuses:
    def test_is_frozenset(self):
        from app.shared.constants import ORDER_STATUSES

        assert isinstance(ORDER_STATUSES, frozenset)

    def test_contains_all_statuses(self):
        from app.shared.constants import ORDER_STATUSES

        assert "to_do" in ORDER_STATUSES
        assert "ready" in ORDER_STATUSES
        assert "delivered" in ORDER_STATUSES
        assert "done" in ORDER_STATUSES

    def test_no_extra_statuses(self):
        from app.shared.constants import ORDER_STATUSES

        assert len(ORDER_STATUSES) == 4


class TestFulfillmentTypes:
    def test_is_frozenset(self):
        from app.shared.constants import FULFILLMENT_TYPES

        assert isinstance(FULFILLMENT_TYPES, frozenset)

    def test_contains_pickup_and_delivery(self):
        from app.shared.constants import FULFILLMENT_TYPES

        assert "pickup" in FULFILLMENT_TYPES
        assert "delivery" in FULFILLMENT_TYPES


class TestArabicStatusLabels:
    def test_is_dict(self):
        from app.shared.constants import ARABIC_STATUS_LABELS

        assert isinstance(ARABIC_STATUS_LABELS, dict)

    def test_all_statuses_have_labels(self):
        from app.shared.constants import ARABIC_STATUS_LABELS, ORDER_STATUSES

        for status in ORDER_STATUSES:
            assert status in ARABIC_STATUS_LABELS, f"Missing Arabic label for {status}"

    def test_labels_are_strings(self):
        from app.shared.constants import ARABIC_STATUS_LABELS

        for key, val in ARABIC_STATUS_LABELS.items():
            assert isinstance(val, str), f"Label for {key} is not a string"
            assert val  # not empty


class TestHardCommands:
    def test_is_frozenset(self):
        from app.shared.constants import HARD_COMMANDS

        assert isinstance(HARD_COMMANDS, frozenset)

    def test_contains_core_commands(self):
        from app.shared.constants import HARD_COMMANDS

        for cmd in ("cart", "clear", "pickup", "delivery", "confirm"):
            assert cmd in HARD_COMMANDS, f"Missing hard command: {cmd}"

    def test_all_items_are_strings(self):
        from app.shared.constants import HARD_COMMANDS

        for cmd in HARD_COMMANDS:
            assert isinstance(cmd, str)


class TestNumericConstants:
    def test_max_chat_history_turns_is_positive_int(self):
        from app.shared.constants import MAX_CHAT_HISTORY_TURNS

        assert isinstance(MAX_CHAT_HISTORY_TURNS, int)
        assert MAX_CHAT_HISTORY_TURNS > 0

    def test_max_ai_tokens_is_positive_int(self):
        from app.shared.constants import MAX_AI_TOKENS

        assert isinstance(MAX_AI_TOKENS, int)
        assert MAX_AI_TOKENS > 0

    def test_ai_temperature_is_float_in_range(self):
        from app.shared.constants import AI_TEMPERATURE

        assert isinstance(AI_TEMPERATURE, float)
        assert 0.0 <= AI_TEMPERATURE <= 1.0

    def test_whatsapp_menu_limit_is_positive(self):
        from app.shared.constants import WHATSAPP_MENU_LIMIT

        assert isinstance(WHATSAPP_MENU_LIMIT, int)
        assert WHATSAPP_MENU_LIMIT > 0

    def test_cookie_name_is_string(self):
        from app.shared.constants import COOKIE_NAME

        assert isinstance(COOKIE_NAME, str)
        assert COOKIE_NAME


class TestVersion:
    def test_version_format(self):
        from app.shared.version import __version__

        parts = __version__.split(".")
        assert len(parts) == 3
        for part in parts:
            assert part.isdigit()

    def test_author_and_project_are_strings(self):
        from app.shared.version import __author__, __project__

        assert isinstance(__author__, str) and __author__
        assert isinstance(__project__, str) and __project__
