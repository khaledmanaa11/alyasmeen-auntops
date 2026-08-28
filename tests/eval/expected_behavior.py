"""
tests/eval/expected_behavior.py — hand-curated expected outcome per dataset case
(REQ-prod-eval-gate).

`tests/data/whatsapp_agent_dataset.json` has 75 cases with an `expected_intent` label but
no mapping to what `handle_message()`/`process_event()` should actually DO — that mapping
does not exist anywhere else in this repo and is small enough (75 rows) to hand-author once,
carefully, by reading every `raw_input` rather than inferring from the intent name alone.

Each case is graded against one of the five real tool names, `"handoff"` (any of the five
handoff triggers wired in 03-04/03-05: keyword, unsupported media, policy denial, the AI's
own `request_human_handoff` tool, or an AI-failure escalation), or `"no_tool"` (a
conversational reply with neither). `EXPECTED` maps a case id to the SET of outcomes that
count as correct — several cases have more than one defensible right answer (e.g. a bare
product-category mention could reasonably be answered with `show_menu` or a clarifying
question).

Context assumption that shapes every judgement call below: the eval harness
(`tests/eval/test_agent_eval.py`) runs each sampled case through a FRESH phone number with an
EMPTY session — no prior cart, no prior menu context, no prior order, no prior handoff. Cases
tagged `requires_menu_context_in_session` / `requires_cart_context` /
`ambiguous_without_prior_menu` are graded against what a stateless, context-free first message
can actually produce today, not against the idealized multi-turn conversation the tag's name
might suggest — several of these therefore expect `"no_tool"` (the agent has no way to resolve
"that other one" or "make it 3" without a menu/cart to reference).

Cases scored `"add_to_cart"` are graded on whether the AI called the tool by name, not on
whether `policy.validate()`'s catalog lookup then actually matched a product — the eval
harness captures the tool name before `_make_tool_executor`'s internal dispatch, so a fuzzy
customer product name that fails to resolve against `EVAL_CATALOG` (tests/eval/conftest.py)
still counts as an `add_to_cart` call (see that file's `run_case` for exactly where this is
captured).
"""
from __future__ import annotations

OUTCOMES = frozenset({
    "add_to_cart", "show_menu", "get_order_status", "save_address",
    "handoff",   # any handoffs row opened, by any of the five triggers wired in 03-04/03-05
    "no_tool",   # a conversational reply with no tool call and no handoff
})

# Media-type dataset cases must be driven through processor.process_event() with a synthetic
# Meta payload, not handle_message() — a text placeholder like "[ملصق]" is not what the real
# pipeline actually receives; see handle_unsupported_media() in app/services/processor.py.
# Values are the Meta message `type` string handle_unsupported_media()/MEDIA_TYPE_LABELS
# already understand.
MEDIA_CASE_TYPES: dict[int, str] = {
    47: "audio",    # unsupported_media_voice_note — "[رسالة صوتية - 0:43]"
    48: "image",    # order_by_image_reference — "[صورة] بدي زي هاد بالظبط اللي بالصورة"
    67: "sticker",  # unsupported_media_sticker — "[ملصق]"
}

# id -> set of outcomes that count as CORRECT.
EXPECTED: dict[int, frozenset[str]] = {
    # ---- informational tier (34 cases): FAQ/small-talk/consultative. A wrong
    # answer here is not order-breaking. app/data/knowledge/ is empty in this
    # repo (CLAUDE.md "Still To Do" #6), so several of these will score
    # poorly for reasons Phase 3 does not own — see the note near TIERS. ----
    1:  frozenset({"no_tool"}),                # greeting
    2:  frozenset({"no_tool"}),                # "are you open today?" — conversational
    3:  frozenset({"show_menu", "no_tool"}),   # "do you have a skin exfoliator" — catalog check
    4:  frozenset({"no_tool"}),                # greeting (loanword-flavoured)
    5:  frozenset({"no_tool"}),                # greeting + "open today?", no specific product
    6:  frozenset({"no_tool"}),                # greeting (typo'd name)
    7:  frozenset({"no_tool"}),                # greeting
    8:  frozenset({"no_tool"}),                # formal greeting
    9:  frozenset({"no_tool"}),                # greeting (flattery)
    10: frozenset({"show_menu", "no_tool"}),   # greeting + multi-category product question
    16: frozenset({"no_tool", "show_menu"}),   # skin-problem consult, no buying verb — decision
                                                 # tree says ask a clarifying question first
    20: frozenset({"no_tool"}),                # "safe during pregnancy?" — no tool answers this
    24: frozenset({"no_tool"}),                # delivery-zone FAQ
    26: frozenset({"no_tool"}),                # vegan/cruelty-free FAQ
    28: frozenset({"show_menu", "no_tool"}),   # "send me your catalog/pricelist"
    38: frozenset({"no_tool", "show_menu"}),   # English: delivery zone + product availability
    40: frozenset({"no_tool"}),                # ingredient inquiry (shea butter)
    41: frozenset({"no_tool"}),                # emoji-only ack — must NOT trigger a tool
    42: frozenset({"no_tool"}),                # thanks / conversation close
    44: frozenset({"no_tool"}),                # price objection — reply, never auto-discount
    46: frozenset({"no_tool"}),                # store hours/location FAQ
    49: frozenset({"no_tool", "show_menu"}),   # Hebrew message — no language policy exists for
                                                 # non-Arabic/non-English; graded on tool outcome
                                                 # only, never on language match (see test_agent_eval)
    53: frozenset({"show_menu", "no_tool"}),   # size/variant price inquiry
    56: frozenset({"no_tool", "show_menu"}),   # formal MSA ingredient/availability question
    59: frozenset({"no_tool"}),                # child asthma/allergy safety Q — no medical claims
    60: frozenset({"no_tool"}),                # "send me your location pin" — no tool for this
    61: frozenset({"no_tool"}),                # Eid greeting + promotions question
    65: frozenset({"no_tool"}),                # "ok" — bare ack, must not auto-confirm
    66: frozenset({"no_tool"}),                # eczema suitability Q — no medical claims
    70: frozenset({"no_tool"}),                # delivery cost/time FAQ
    71: frozenset({"no_tool"}),                # payment methods FAQ
    72: frozenset({"no_tool"}),                # positive post-delivery feedback
    73: frozenset({"no_tool"}),                # restock-date FAQ
    75: frozenset({"no_tool", "show_menu"}),   # Arabizi availability/price question

    # ---- critical tier (24 cases): the order path — cart, menu selection,
    # fulfillment, address, confirm. A wrong tool choice here directly
    # breaks an order. ----
    11: frozenset({"show_menu", "add_to_cart"}),  # candles+creams+conditioner by CATEGORY, no
                                                     # specific product NAME given
    12: frozenset({"add_to_cart"}),            # specific products + qty (lavender candle, ×2 softener)
    13: frozenset({"add_to_cart"}),            # specific products + qty
    14: frozenset({"add_to_cart"}),            # specific products + qty
    15: frozenset({"add_to_cart", "no_tool"}), # item swap — no "remove" tool exists; adding the
                                                 # new item is the best the agent can do
    17: frozenset({"add_to_cart"}),            # specific products (gift-wrap request has no tool)
    18: frozenset({"add_to_cart"}),            # specific product + qty (discount request has no tool)
    19: frozenset({"get_order_status", "handoff"}),  # tracking + "give me courier's number" — no
                                                        # tool for the courier-contact half
    21: frozenset({"show_menu", "no_tool"}),   # resume_abandoned_cart — session is FRESH in the
                                                 # harness, nothing to literally resume
    30: frozenset({"no_tool"}),                # "what's in my cart?" — colloquial, not the exact
                                                 # hard-command text; no view_cart TOOL; cart empty
    31: frozenset({"no_tool"}),                # "clear my cart" — colloquial, not exact hard
                                                 # command text; no clear-cart tool
    32: frozenset({"no_tool"}),                # "no delivery, I'll pick up" — no fulfillment tool
    33: frozenset({"save_address", "no_tool"}), # delivery + address given in one message
    34: frozenset({"no_tool"}),                # "confirm" with an EMPTY cart — the hard-command
                                                 # branch requires cart truthy, falls through to AI
    36: frozenset({"no_tool", "show_menu"}),   # bare "2" — no prior menu in this fresh session
    37: frozenset({"no_tool", "show_menu"}),   # "3x2" shorthand — no such hard-command pattern
                                                 # exists in processor.py today, and no menu context
    39: frozenset({"add_to_cart"}),            # Arabizi, specific products + qty
    50: frozenset({"no_tool"}),                # bare "yes" with no pending confirmation in this
                                                 # fresh session — must NOT auto-confirm/auto-add
    51: frozenset({"no_tool"}),                # "the other one, above it" — no menu context
    52: frozenset({"no_tool"}),                # "make it 3 not 2" — no cart item to update
    58: frozenset({"add_to_cart"}),            # Arabic-Indic numerals, specific products + qty
    64: frozenset({"add_to_cart"}),            # letter elongation, clear buying intent + product
    69: frozenset({"no_tool"}),                # "remind me what's in my cart" — empty cart, no tool
    74: frozenset({"add_to_cart"}),            # self-correction mid-message — final state
                                                 # (conditioner) only, per
                                                 # "agent_must_apply_final_state_only"

    # ---- handoff tier (16 cases): must escalate — either the deterministic
    # keyword/media triggers (03-04) or the AI's own request_human_handoff
    # tool (03-05) catch these. ----
    22: frozenset({"handoff"}),  # custom bulk order w/ personalization — no tool for this
    23: frozenset({"handoff"}),  # damaged item on arrival — refund/replacement, human-only
    25: frozenset({"handoff"}),  # post-checkout order modification — success criterion 4
    27: frozenset({"handoff"}),  # payment-proof screenshot — bot cannot verify attachments
    29: frozenset({"handoff"}),  # duplicate a THIRD PARTY's order — privacy-sensitive, no tool
    35: frozenset({"handoff"}),  # week-late order + no response — complaint escalation
    43: frozenset({"handoff"}),  # cancel a confirmed order — success criterion 4, no tool
    45: frozenset({"handoff"}),  # explicit "let me talk to Hanan, not the bot"
    47: frozenset({"handoff"}),  # voice note (media, via process_event)
    48: frozenset({"handoff"}),  # image reference (media, via process_event)
    55: frozenset({"handoff"}),  # message clearly meant for someone else's grocery order
    57: frozenset({"handoff"}),  # angry + explicit refund threat
    62: frozenset({"handoff"}),  # deferred/credit payment request — policy decision, human-only
    63: frozenset({"handoff"}),  # "who are you, how did you get my number" — privacy/trust
    67: frozenset({"handoff"}),  # sticker (media, via process_event)
    68: frozenset({"handoff"}),  # wholesale/B2B pricing inquiry — policy decision, human-only
}

# Cases deliberately not graded, each with a written reason. Kept short — an
# eval that excuses its own failures is worthless.
UNSCORED: dict[int, str] = {
    54: (
        "opt_out_of_messages — there is no consent/suppression mechanism anywhere in this "
        "codebase (no opt_out/do_not_contact column, no broadcast/follow-up suppression list). "
        "Routing this through the handoff system would mis-handle a compliance request as a "
        "conversational escalation rather than actually honouring it. Explicitly out of scope "
        "for Phase 3 — see 03-RESEARCH.md open question 2 and 03-02-SUMMARY.md."
    ),
}

# Tiers drive per-tier thresholds in plan 03-07 — a wrong answer is not
# equally costly everywhere. The informational tier in particular will score
# poorly for reasons Phase 3 does not own: app/data/knowledge/ is empty in
# this repo (CLAUDE.md "Still To Do" #6), so FAQ-ish questions have no
# grounded answer available yet. Keeping it a separate tier means a single
# global threshold cannot block a release on that gap.
TIERS: dict[str, frozenset[int]] = {
    "critical": frozenset({
        11, 12, 13, 14, 15, 17, 18, 19, 21, 30, 31, 32, 33, 34, 36, 37, 39,
        50, 51, 52, 58, 64, 69, 74,
    }),
    "handoff": frozenset({
        22, 23, 25, 27, 29, 35, 43, 45, 47, 48, 55, 57, 62, 63, 67, 68,
    }),
    "informational": frozenset({
        1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 16, 20, 24, 26, 28, 38, 40, 41, 42,
        44, 46, 49, 53, 56, 59, 60, 61, 65, 66, 70, 71, 72, 73, 75,
    }),
}

# Reverse lookup, id -> tier name. Built from TIERS so it can never drift out
# of sync with it.
TIER_OF: dict[int, str] = {
    case_id: tier for tier, ids in TIERS.items() for case_id in ids
}
