"""
policy.py — Deterministic policy gate for REQ-prod-policy-gate.

Every AI-proposed tool call passes through `validate()` before it executes.
This module is pure (no DB, no AI, no network) — the caller supplies
everything it needs via the `context` argument. It is called from
`processor._make_tool_executor` (wired in plan 03-05).

Design constraint that shapes the whole module: this file performs no I/O.
It does not import `app.db.database`, `app.routers.whatsapp_helpers`,
`app.services.processor`, or `app.services.handoff`. The catalog and the
order status arrive through `context`, supplied by the caller that already
has them. Two reasons, both load-bearing: (a) it keeps the gate genuinely
deterministic and trivially unit-testable, and (b) this codebase binds DB
helpers at import time, so a `catalog` imported here would become yet
another seam every future test file has to remember to patch or else
silently hit the LIVE production database (see `tests/conftest.py`'s module
docstring; Pitfall 1 in `.planning/phases/03-agent-dependability-safety/03-RESEARCH.md`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Canonical clamp range for AI-supplied cart quantities. processor.py holds
# duplicate literals today (MIN_CART_QTY/MAX_CART_QTY, processor.py:39-40);
# plan 03-05 replaces those with an import from here so there is one source.
MIN_CART_QTY = 1
MAX_CART_QTY = 50

MIN_ADDRESS_CHARS = 10      # "رام الله" alone is not a deliverable address
MAX_ADDRESS_CHARS = 300
MAX_CATEGORY_CHARS = 60
MAX_REASON_CHARS = 200

# Every tool ai_service.py exposes, and what it is allowed to touch.
#   read      — no writes at all
#   cart      — mutates the in-session cart only
#   customer  — mutates the customer/session record
#   escalation— opens a handoff
#   order     — would mutate an existing order (NOTHING has this scope today)
#
# Why "order" has no members: order creation happens only through the
# hard-coded `confirm` path (processor.py:327-329 -> _handle_confirm ->
# create_order_atomic), and status progression happens only in the
# operator-authenticated app/routers/ui_api.py::api_update_status. The AI
# has never had a way to mutate an order. This dict + the order_not_mutable
# rule below turn that into an asserted, regression-tested rule instead of
# an accident — a future sixth tool is denied by default rather than
# allowed by omission.
TOOL_SCOPES = {
    "add_to_cart": "cart",
    "show_menu": "read",
    "get_order_status": "read",
    "save_address": "customer",
    "request_human_handoff": "escalation",
}

# Success criterion 4: the agent may only act on an order that is still
# being prepared. Once the aunt has moved it past to_do, agent mutation is
# refused.
AGENT_MUTABLE_ORDER_STATUSES = frozenset({"to_do"})


# ---------------------------------------------------------------------------
# Decision type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    code: str = "ok"          # machine reason: unknown_tool, session_paused,
    # product_not_in_catalog, address_too_short, order_not_mutable, ...
    message: str = ""         # Arabic text handed back to Claude as the tool_result
    args: dict = field(default_factory=dict)   # normalised args to execute with
    escalate: bool = False    # a denial that should also open a handoff


# ---------------------------------------------------------------------------
# Product grounding
# ---------------------------------------------------------------------------

def resolve_product(product_name: str, catalog: list[dict]) -> dict | None:
    """Exact case-insensitive name match first, then substring match.

    This is the same two-pass strategy `_tool_add_to_cart` uses at
    processor.py:419-430, extracted here so the grounding rule and the
    execution use one definition. `_tool_add_to_cart` keeps its own lookup
    (the numeric menu-pick path at processor.py:353-362 calls it directly,
    bypassing the AI and therefore this policy gate); passing the canonical
    name through means it hits the exact-match branch there.
    """
    if not product_name or not catalog:
        return None

    needle = product_name.lower()

    # 1. Exact match
    for p in catalog:
        if str(p.get("name", "")).lower() == needle:
            return p

    # 2. Partial match
    for p in catalog:
        if needle in str(p.get("name", "")).lower():
            return p

    return None


# ---------------------------------------------------------------------------
# Per-tool argument rules
# ---------------------------------------------------------------------------

def _validate_add_to_cart(args: dict, context: dict) -> PolicyDecision:
    catalog = context.get("catalog") or []
    product_name = str(args.get("product_name", "") or "")

    match = resolve_product(product_name, catalog)
    if match is None:
        return PolicyDecision(
            allowed=False,
            code="product_not_in_catalog",
            message=f"لم أجد منتجاً باسم '{product_name}' في القائمة.",
            escalate=False,
        )

    # Quantity: coerce with int(), fall back to 1 on TypeError/ValueError,
    # clamp to MIN_CART_QTY..MAX_CART_QTY.
    raw_qty = args.get("qty", 1)
    try:
        qty = int(raw_qty)
    except (TypeError, ValueError):
        qty = 1
    qty = max(MIN_CART_QTY, min(qty, MAX_CART_QTY))

    # Never take a price from args — there is no price field in the tool
    # schema (ai_service.py:225-244) and there must never be one. Even if a
    # future/hallucinated tool call includes one, it is dropped here: `args`
    # below is built explicitly, not by merging the caller's dict.
    return PolicyDecision(
        allowed=True,
        args={"product_name": match.get("name"), "qty": qty},
    )


def _validate_show_menu(args: dict, context: dict) -> PolicyDecision:
    category = str(args.get("category", "") or "").strip()[:MAX_CATEGORY_CHARS]
    return PolicyDecision(allowed=True, args={"category": category})


def _validate_get_order_status(args: dict, context: dict) -> PolicyDecision:
    return PolicyDecision(allowed=True, args={})


def _validate_save_address(args: dict, context: dict) -> PolicyDecision:
    address = str(args.get("address", "") or "").strip()
    if len(address) < MIN_ADDRESS_CHARS:
        return PolicyDecision(
            allowed=False,
            code="address_too_short",
            message="وين بالضبط؟ اكتبي المدينة والحي والشارع لو سمحتِ 🙏",
            escalate=False,
        )
    address = address[:MAX_ADDRESS_CHARS]
    return PolicyDecision(allowed=True, args={"address": address})


def _validate_request_human_handoff(args: dict, context: dict) -> PolicyDecision:
    # This tool is the escape hatch — it must never be the thing that gets
    # blocked (beyond the session_paused/unknown_tool rules above it).
    reason = str(args.get("reason", "") or "").strip()[:MAX_REASON_CHARS]
    if not reason:
        reason = "طلب الزبونة"
    return PolicyDecision(allowed=True, args={"reason": reason})


_ARG_VALIDATORS: dict[str, Callable[[dict, dict], PolicyDecision]] = {
    "add_to_cart": _validate_add_to_cart,
    "show_menu": _validate_show_menu,
    "get_order_status": _validate_get_order_status,
    "save_address": _validate_save_address,
    "request_human_handoff": _validate_request_human_handoff,
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def validate(tool_name: str, args: dict | None, context: dict) -> PolicyDecision:
    """Validate an AI-proposed tool call. No AI call, no database call.

    `context` keys (all optional except where noted, with safe defaults):
      - paused: bool
      - catalog: list[dict] — rows shaped {"name", "list_price", ...} exactly
        as whatsapp_helpers.catalog() returns them
      - order_status_provider: Callable[[], str | None] — called ONLY for
        order-scoped tools, so no DB read happens for the five tools that
        exist today
      - phone: str (for logging only)

    Rules, evaluated in this order (first denial wins).
    """
    args = args or {}

    # 1. session_paused — a human owns this conversation; the agent does not
    #    get to keep mutating state underneath her.
    if context.get("paused"):
        return PolicyDecision(
            allowed=False,
            code="session_paused",
            message="المحادثة محوّلة لحنان حالياً 🌿",
            escalate=False,
        )

    # 2. unknown_tool — default-deny is the point: an unrecognised tool name
    #    is either a model hallucination or a tool someone added without
    #    updating this policy.
    if tool_name not in TOOL_SCOPES:
        return PolicyDecision(
            allowed=False,
            code="unknown_tool",
            message="هذا الطلب بحاجة لمتابعة من حنان.",
            escalate=True,
        )

    # 3. order_not_mutable — unreachable with today's five tools (none has
    #    scope "order") — pinned by a test that registers a synthetic
    #    order-scoped tool.
    if TOOL_SCOPES[tool_name] == "order":
        provider = context.get("order_status_provider")
        status = provider() if provider else None
        if status not in AGENT_MUTABLE_ORDER_STATUSES:
            return PolicyDecision(
                allowed=False,
                code="order_not_mutable",
                message="طلبك تجاوز مرحلة التحضير، رح أحوّلك لحنان تتابع معك 🌿",
                escalate=True,
            )

    # 4. Per-tool argument rules.
    validator = _ARG_VALIDATORS[tool_name]
    return validator(args, context)


# ---------------------------------------------------------------------------
# Deterministic escalation detection (Arabic + English) — REQ-prod-handoff
# ---------------------------------------------------------------------------
#
# Plan 03-04 maps any non-None result of detect_handoff_keyword() to
# handoff.trigger(phone, "keyword_request", ...).
#
# Multi-word phrases are matched as substrings; single tokens are matched
# against whitespace/punctuation-delimited words ONLY. This split matters:
# a bare "بشر" is a substring of "بشرتي" ("my skin"), which is one of the
# most common things a customer says to a skincare bot
# (tests/unit/test_processor.py drives "بشرتي جافة كثير" through the
# pipeline) — a naive substring match on a short token would escalate a
# large fraction of normal conversations. "حنان" (the aunt's name) is the
# same story: it is only matched inside a phrase ("مع حنان", "احكي مع"),
# never as a bare word — "شكراً حنان" is a thank-you, not an escalation.
#
# Scope decision: opt_out_of_messages (dataset id 54) is deliberately OUT
# OF SCOPE for this phase — there is no consent/suppression mechanism
# anywhere in this codebase, and routing a do-not-contact request into the
# aunt's manual handoff queue would mis-handle a compliance request rather
# than honour it. Tracked as follow-up work outside Phase 3.

HANDOFF_PHRASES: dict[str, tuple[str, ...]] = {
    "explicit_human": (
        "احكي مع", "أحكي مع", "بدي حدا", "بدي أحكي", "بدي احكي",
        "مع حنان", "مش بوت", "مو بوت", "مش روبوت", "شخص حقيقي",
        "talk to a human", "talk to someone", "speak to a human",
        "real person", "customer service", "customer support",
    ),
    "complaint": (
        "بدي اشتكي", "بدي أشتكي",
    ),
    "refund": (
        "بدي مصاري", "رجعولي", "ردولي", "money back", "my money",
    ),
    "damaged": (),
    "privacy": (
        "من وين رقمي", "مين انتو", "مين أنتو", "how did you get my number",
    ),
}

HANDOFF_WORDS: dict[str, tuple[str, ...]] = {
    "explicit_human": (
        "موظف", "موظفة", "انسان", "إنسان", "human", "agent", "operator",
    ),
    "complaint": (
        "شكوى", "شكوي", "اشتكي", "complaint", "complain",
    ),
    "refund": (
        "استرجاع", "إسترجاع", "ارجاع", "إرجاع", "refund", "chargeback", "فلوسي",
    ),
    "damaged": (
        "مكسور", "مكسورة", "تالف", "تالفة", "broken", "damaged", "defective",
    ),
    "privacy": (
        "خصوصية", "privacy",
    ),
}

# Fixed iteration order so the return value is deterministic when a message
# matches two groups.
_GROUP_ORDER: tuple[str, ...] = ("explicit_human", "refund", "damaged", "complaint", "privacy")

# Whitespace + common punctuation (including the Arabic comma/question mark)
# used to build the whole-word token set for HANDOFF_WORDS matching.
_WORD_SPLIT_RE = re.compile(r"[\s،,.!؟?:;()\"'`]+")


def detect_handoff_keyword(text: str) -> str | None:
    """Return a handoff reason group name, or None. Pure string matching — no AI."""
    if not text:
        return None

    lowered = text.lower()
    words = {w for w in _WORD_SPLIT_RE.split(lowered) if w}

    for group in _GROUP_ORDER:
        for phrase in HANDOFF_PHRASES.get(group, ()):
            if phrase in lowered:
                return group
        if words & set(HANDOFF_WORDS.get(group, ())):
            return group

    return None
