"""
test_policy.py — Unit tests for app.services.policy, the deterministic
tool-call gate (REQ-prod-policy-gate) and escalation detector
(REQ-prod-handoff).

policy.py is pure — no DB, no AI, no network — so these tests need nothing
from conftest.py beyond the autouse `block_live_db`/`mock_db` guards (which
patch seams this module never touches; they are harmless no-ops here).
"""
from __future__ import annotations

import pytest

import app.services.ai_service as ai_service
import app.services.policy as policy
from app.services.policy import (
    MAX_ADDRESS_CHARS,
    MAX_CART_QTY,
    MIN_CART_QTY,
    TOOL_SCOPES,
    PolicyDecision,
    detect_handoff_keyword,
    validate,
)

FAKE_CATALOG = [
    {"id": 1, "name": "كريم اليدين", "list_price": 25.0, "description_sale": "كريم مرطب للأيدي"},
    {"id": 2, "name": "لوشن الجسم", "list_price": 40.0, "description_sale": "لوشن طبيعي"},
    {"id": 3, "name": "شمعة العود", "list_price": 35.0, "description_sale": "شمعة عطرية"},
]


# ---------------------------------------------------------------------------
# TestToolAllowlist
# ---------------------------------------------------------------------------

class TestToolAllowlist:
    def test_unknown_tool_denied_and_escalates(self):
        decision = validate("drop_table", {}, {})
        assert decision.allowed is False
        assert decision.code == "unknown_tool"
        assert decision.escalate is True

    def test_add_to_cart_allowed_with_valid_args(self):
        decision = validate(
            "add_to_cart",
            {"product_name": "كريم اليدين", "qty": 2},
            {"catalog": FAKE_CATALOG},
        )
        assert decision.allowed is True

    def test_show_menu_allowed(self):
        decision = validate("show_menu", {"category": "كريمات"}, {})
        assert decision.allowed is True

    def test_get_order_status_allowed(self):
        decision = validate("get_order_status", {}, {})
        assert decision.allowed is True

    def test_save_address_allowed_with_valid_args(self):
        decision = validate(
            "save_address",
            {"address": "رام الله - شارع الإرسال - بناية رقم 5"},
            {},
        )
        assert decision.allowed is True

    def test_request_human_handoff_allowed(self):
        decision = validate("request_human_handoff", {"reason": "زبونة غاضبة"}, {})
        assert decision.allowed is True

    def test_tool_scopes_match_ai_service_tools(self):
        """A sixth tool added to ai_service.py without a matching TOOL_SCOPES
        entry must fail this test — that is the guard's entire point.

        Known wave-1 interaction: 03-03 (same wave, parallel plan) is the one
        that adds the 5th tool (request_human_handoff) to ai_service._TOOLS.
        If this test is executed before 03-03's commit lands, it is expected
        to fail with TOOL_SCOPES having 5 entries vs. _TOOLS having 4 — that
        is correct and expected, not a bug in this module. Re-run after both
        wave-1 plans have landed rather than weakening this assertion.
        """
        tool_names = {t["name"] for t in ai_service._TOOLS}
        assert tool_names == set(TOOL_SCOPES)


# ---------------------------------------------------------------------------
# TestAddToCartGrounding (REQ-ai-no-hallucination)
# ---------------------------------------------------------------------------

class TestAddToCartGrounding:
    def test_exact_name_match_allowed_with_canonical_name(self):
        decision = validate(
            "add_to_cart",
            {"product_name": "كريم اليدين", "qty": 1},
            {"catalog": FAKE_CATALOG},
        )
        assert decision.allowed is True
        assert decision.args["product_name"] == "كريم اليدين"

    def test_partial_name_match_allowed_with_canonical_name(self):
        decision = validate(
            "add_to_cart",
            {"product_name": "كريم", "qty": 1},
            {"catalog": FAKE_CATALOG},
        )
        assert decision.allowed is True
        assert decision.args["product_name"] == "كريم اليدين"

    def test_product_absent_from_catalog_denied(self):
        decision = validate(
            "add_to_cart",
            {"product_name": "ذهب خالص", "qty": 1},
            {"catalog": FAKE_CATALOG},
        )
        assert decision.allowed is False
        assert decision.code == "product_not_in_catalog"
        assert "ذهب خالص" in decision.message

    def test_empty_catalog_denied(self):
        decision = validate(
            "add_to_cart",
            {"product_name": "كريم اليدين", "qty": 1},
            {"catalog": []},
        )
        assert decision.allowed is False
        assert decision.code == "product_not_in_catalog"

    def test_no_price_argument_is_ever_honoured(self):
        decision = validate(
            "add_to_cart",
            {"product_name": "كريم اليدين", "price": 1},
            {"catalog": FAKE_CATALOG},
        )
        assert decision.allowed is True
        assert "price" not in decision.args


# ---------------------------------------------------------------------------
# TestQuantityClamp
# ---------------------------------------------------------------------------

class TestQuantityClamp:
    @pytest.mark.parametrize(
        "raw_qty,expected",
        [
            (0, MIN_CART_QTY),
            (999, MAX_CART_QTY),
            ("3", 3),
            (None, 1),
            ("abc", 1),
            (2, 2),
        ],
    )
    def test_quantity_clamped(self, raw_qty, expected):
        decision = validate(
            "add_to_cart",
            {"product_name": "كريم اليدين", "qty": raw_qty},
            {"catalog": FAKE_CATALOG},
        )
        assert decision.allowed is True
        assert decision.args["qty"] == expected


# ---------------------------------------------------------------------------
# TestSaveAddressShape
# ---------------------------------------------------------------------------

class TestSaveAddressShape:
    def test_too_short_denied(self):
        decision = validate("save_address", {"address": "رام الله"}, {})
        assert decision.allowed is False
        assert decision.code == "address_too_short"

    def test_full_address_allowed_and_stripped(self):
        decision = validate(
            "save_address",
            {"address": "  رام الله - شارع الإرسال - بناية رقم 5  "},
            {},
        )
        assert decision.allowed is True
        assert decision.args["address"] == "رام الله - شارع الإرسال - بناية رقم 5"

    def test_long_address_truncated(self):
        long_address = "شارع طويل جداً " * 50
        decision = validate("save_address", {"address": long_address}, {})
        assert decision.allowed is True
        assert len(decision.args["address"]) == MAX_ADDRESS_CHARS


# ---------------------------------------------------------------------------
# TestPausedSession
# ---------------------------------------------------------------------------

class TestPausedSession:
    @pytest.mark.parametrize("tool_name", sorted(TOOL_SCOPES))
    def test_every_tool_denied_when_paused(self, tool_name):
        decision = validate(tool_name, {}, {"paused": True, "catalog": FAKE_CATALOG})
        assert decision.allowed is False
        assert decision.code == "session_paused"

    def test_request_human_handoff_denied_when_paused(self):
        # A paused conversation needs no second handoff.
        decision = validate("request_human_handoff", {"reason": "x"}, {"paused": True})
        assert decision.allowed is False
        assert decision.code == "session_paused"


# ---------------------------------------------------------------------------
# TestOrderMutationBoundary (success criterion 4)
# ---------------------------------------------------------------------------

class TestOrderMutationBoundary:
    def test_no_tool_today_has_order_scope(self):
        # Asserts the architectural fact that the agent cannot mutate orders:
        # order creation is confirm-only, status progression is
        # operator-only, and no AI tool has ever been given "order" scope.
        assert [t for t, s in TOOL_SCOPES.items() if s == "order"] == []

    def test_synthetic_order_tool_is_denied_past_to_do(self, monkeypatch):
        synthetic_scopes = dict(TOOL_SCOPES)
        synthetic_scopes["cancel_order"] = "order"
        monkeypatch.setattr(policy, "TOOL_SCOPES", synthetic_scopes)

        # cancel_order has no real arg validator (it doesn't exist as a real
        # tool) — register a trivial pass-through so the to_do-allowed case
        # below can reach a decision instead of raising KeyError.
        synthetic_validators = dict(policy._ARG_VALIDATORS)
        synthetic_validators["cancel_order"] = lambda args, context: PolicyDecision(allowed=True)
        monkeypatch.setattr(policy, "_ARG_VALIDATORS", synthetic_validators)

        for status in ("ready", "delivered", "done", None):
            decision = validate(
                "cancel_order",
                {},
                {"order_status_provider": lambda status=status: status},
            )
            assert decision.allowed is False, f"expected denial for status={status!r}"
            assert decision.code == "order_not_mutable"
            assert decision.escalate is True

        decision = validate(
            "cancel_order",
            {},
            {"order_status_provider": lambda: "to_do"},
        )
        assert decision.allowed is True
        assert decision.code != "order_not_mutable"

    def test_order_status_provider_not_called_for_non_order_tools(self):
        def _boom():
            raise AssertionError("order_status_provider must not be called for non-order tools")

        context = {"catalog": FAKE_CATALOG, "order_status_provider": _boom}
        validate("show_menu", {}, context)
        validate("add_to_cart", {"product_name": "كريم اليدين", "qty": 1}, context)


# ---------------------------------------------------------------------------
# TestDetectHandoffKeyword
# ---------------------------------------------------------------------------

class TestDetectHandoffKeyword:
    @pytest.mark.parametrize(
        "text,expected_group",
        [
            ("بدي احكي مع حنان مش مع البوت", "explicit_human"),
            ("I want to talk to a human", "explicit_human"),
            ("بدي اشتكي عليكم", "complaint"),
            ("عندي complaint عن الطلب", "complaint"),
            ("بدي فلوسي ترجع، تعبت من الوعود", "refund"),
            ("give me my money back", "refund"),
            ("الكريم اجا مكسور", "damaged"),
            ("the candle arrived broken", "damaged"),
            ("مين انتو اصلا؟ كيف وصلكم رقمي؟", "privacy"),
            ("this is a privacy concern", "privacy"),
        ],
    )
    def test_positive_matches(self, text, expected_group):
        assert detect_handoff_keyword(text) == expected_group

    @pytest.mark.parametrize(
        "text",
        [
            "بشرتي جافة كثير",
            "بدي كريم للبشرة الدهنية",
            "شكرا حنان",
        ],
    )
    def test_ordinary_skincare_message_does_not_trigger(self, text):
        assert detect_handoff_keyword(text) is None

    @pytest.mark.parametrize(
        "text",
        [
            "menu", "منتجات", "شو عندكم",
            "cart", "سلة", "طلبي",
            "clear", "فرغ", "افرغ السلة", "مسح",
            "confirm", "تأكيد", "اكد", "أكد", "تم",
            "pickup", "استلام",
            "delivery", "توصيل",
        ],
    )
    def test_hard_commands_do_not_trigger(self, text):
        # Plan 03-04 runs keyword detection BEFORE the hard commands, so a
        # collision here would silently break ordering.
        assert detect_handoff_keyword(text) is None

    def test_returns_stable_group_when_multiple_match(self):
        # Contains both an explicit_human phrase and a refund word — the
        # fixed group order (explicit_human before refund) must win.
        text = "بدي احكي مع حنان بخصوص استرجاع الفلوس"
        assert detect_handoff_keyword(text) == "explicit_human"
