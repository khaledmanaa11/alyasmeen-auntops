# Phase 3 — Agent Eval: Measured Baseline (03-06, Task 3)

**This is a measurement, not a target.** Plan 03-07 derives regression thresholds from the
numbers below; nothing here was invented, and no number should be treated as "good enough" —
several failures below are genuine, notable agent weaknesses that a future phase may want to
fix. Re-running this eval after a prompt or tool change should be compared against this
document, not the other way around.

## Run details

| | |
|---|---|
| Command | `RUN_AGENT_EVAL=1 EVAL_SAMPLES=all PYTHONIOENCODING=utf-8 python -m pytest -m eval tests/eval -q -s` |
| Model | `claude-haiku-4-5-20251001` (`Config.CLAUDE_MODEL`, pinned in `.env`) |
| Date | 2026-08-28 (measured_at `2026-08-28T19:18:48Z`, per `tests/eval/.last_run.json`) |
| Sample size | 74 (all scored cases — the full dataset minus id 54, `opt_out_of_messages`, which is `UNSCORED` by design, see `tests/eval/expected_behavior.py`) |
| Seed | n/a for a full run (`EVAL_SAMPLES=all` bypasses sampling entirely — see `_select_case_ids`) |
| Wall-clock | 323.45s total (`1 passed in 323.45s (0:05:23)`), 4.6s average per AI-calling case |
| Estimated Anthropic calls | ~85 (67 of the 74 cases called Claude at least once; 7 cases — ids 23, 45, 47, 48, 57, 63, 67 — resolved through the deterministic keyword/media gates in `handle_message`/`process_event` before ever reaching `generate_reply()`, elapsed <0.01s each; 18 of the 67 AI-calling cases made a tool call and therefore cost 2 API calls, not 1) |
| Estimated cost | Well under $0.10 for this full run — ~85 Haiku calls at a ~2k-token system prompt (`_SYSTEM_PROMPT` + the 8-product `<catalog>` block) and a few-hundred-token completion each, consistent with `tests/data/eval_intent.py`'s own ~$0.80/M-input-token estimate |

**Note on `PYTHONIOENCODING=utf-8`:** required on this Windows sandbox — the default console
codepage here is `cp1255` (Hebrew), which cannot encode Arabic output and crashes any case
that logs/prints Arabic text under `pytest -s` (structlog's console renderer writes directly
to the real stdout when `-s` disables pytest's capture). This is an execution-environment
detail, not a code change; no source file needed a fix for it, and it will not affect a normal
CI/Linux environment. Command included above for reproducibility on this platform.

## Overall accuracy

| Tier | Pass / Total | Accuracy |
|---|---|---|
| **Overall** | 63 / 74 | **85.1%** |
| critical | 18 / 24 | 75.0% |
| handoff | 11 / 16 | 68.8% |
| informational | 34 / 34 | 100.0% |

(The informational-tier 100% partly reflects that most of those 34 cases are graded
`{"no_tool"}` and a plain conversational reply is easy to get right — not that FAQ answer
*quality* was graded; see the "Known limitations" section.)

## Per-case results

`expected` reflects `tests/eval/expected_behavior.py` **after** the one map correction made
below (id 20; ids 59/66 widened for consistency). `observed` is the real, unmodified output of
this run.

| id | intent | tier | expected | observed | result |
|----|--------|------|----------|----------|--------|
| 1 | greeting | informational | no_tool | no_tool | PASS |
| 2 | check_availability | informational | no_tool | no_tool | PASS |
| 3 | check_product_availability | informational | no_tool\|show_menu | no_tool | PASS |
| 4 | greeting | informational | no_tool | no_tool | PASS |
| 5 | greeting_and_check_availability | informational | no_tool | no_tool | PASS |
| 6 | greeting | informational | no_tool | no_tool | PASS |
| 7 | greeting | informational | no_tool | no_tool | PASS |
| 8 | greeting | informational | no_tool | no_tool | PASS |
| 9 | greeting | informational | no_tool | no_tool | PASS |
| 10 | greeting_and_check_product_availability | informational | no_tool\|show_menu | show_menu | PASS |
| 11 | create_order_and_check_ingredients | critical | add_to_cart\|show_menu | no_tool | **FAIL** |
| 12 | create_order_and_request_price | critical | add_to_cart | add_to_cart | PASS |
| 13 | create_order_and_check_fulfillment | critical | add_to_cart | add_to_cart | PASS |
| 14 | create_order_and_check_logistics | critical | add_to_cart | add_to_cart | PASS |
| 15 | modify_order_and_request_price | critical | add_to_cart\|no_tool | no_tool | PASS |
| 16 | request_product_recommendation | informational | no_tool\|show_menu | show_menu | PASS |
| 17 | create_order_with_gift_packaging_and_check_price | critical | add_to_cart | no_tool | **FAIL** |
| 18 | create_order_and_request_discount | critical | add_to_cart | add_to_cart | PASS |
| 19 | track_order_and_request_courier_contact | critical | get_order_status\|handoff | no_tool | **FAIL** |
| 20 | check_product_safety | informational | handoff\|no_tool | handoff | PASS (post-fix) |
| 21 | resume_abandoned_cart_and_checkout | critical | no_tool\|show_menu | no_tool | PASS |
| 22 | create_custom_bulk_order_and_check_price | handoff | handoff | handoff | PASS |
| 23 | report_damaged_item_and_request_resolution | handoff | handoff | handoff | PASS |
| 24 | check_delivery_zone | informational | no_tool | no_tool | PASS |
| 25 | modify_order_add_item_post_checkout | handoff | handoff | no_tool | **FAIL** |
| 26 | check_product_lifestyle_compliance | informational | no_tool | no_tool | PASS |
| 27 | submit_payment_proof | handoff | handoff | handoff | PASS |
| 28 | request_catalog_or_pricing | informational | no_tool\|show_menu | show_menu | PASS |
| 29 | duplicate_third_party_order | handoff | handoff | no_tool | **FAIL** |
| 30 | view_cart | critical | no_tool | no_tool | PASS |
| 31 | clear_cart | critical | no_tool | handoff | **FAIL** |
| 32 | set_fulfillment_pickup | critical | no_tool | no_tool | PASS |
| 33 | set_fulfillment_delivery_with_address | critical | no_tool\|save_address | handoff | **FAIL** |
| 34 | confirm_order | critical | no_tool | no_tool | PASS |
| 35 | track_order_with_complaint | handoff | handoff | get_order_status | **FAIL** |
| 36 | select_menu_item | critical | no_tool\|show_menu | no_tool | PASS |
| 37 | select_menu_item_with_quantity | critical | no_tool\|show_menu | no_tool | PASS |
| 38 | check_delivery_zone_and_product_availability | informational | no_tool\|show_menu | no_tool | PASS |
| 39 | create_order_and_request_price (Arabizi) | critical | add_to_cart | no_tool | **FAIL** |
| 40 | check_product_ingredients | informational | no_tool | no_tool | PASS |
| 41 | acknowledgment | informational | no_tool | no_tool | PASS |
| 42 | thanks_and_close_conversation | informational | no_tool | no_tool | PASS |
| 43 | cancel_order | handoff | handoff | handoff | PASS |
| 44 | price_objection | informational | no_tool | no_tool | PASS |
| 45 | request_human_handoff | handoff | handoff | handoff | PASS |
| 46 | request_store_info | informational | no_tool | no_tool | PASS |
| 47 | unsupported_media_voice_note | handoff | handoff | handoff | PASS |
| 48 | order_by_image_reference | handoff | handoff | handoff | PASS |
| 49 | check_product_availability_and_price (Hebrew) | informational | no_tool\|show_menu | no_tool | PASS |
| 50 | affirmation | critical | no_tool | no_tool | PASS |
| 51 | correct_menu_selection | critical | no_tool | no_tool | PASS |
| 52 | update_cart_quantity | critical | no_tool | no_tool | PASS |
| 53 | request_price_and_variants | informational | no_tool\|show_menu | no_tool | PASS |
| 55 | wrong_recipient | handoff | handoff | no_tool | **FAIL** |
| 56 | check_product_availability_and_ingredients | informational | no_tool\|show_menu | no_tool | PASS |
| 57 | track_order_with_refund_threat | handoff | handoff | handoff | PASS |
| 58 | create_order | critical | add_to_cart | add_to_cart | PASS |
| 59 | check_product_safety (child) | informational | handoff\|no_tool | no_tool | PASS |
| 60 | request_location_pin | informational | no_tool | no_tool | PASS |
| 61 | greeting_and_check_promotions | informational | no_tool | no_tool | PASS |
| 62 | request_deferred_payment | handoff | handoff | no_tool | **FAIL** |
| 63 | privacy_concern | handoff | handoff | handoff | PASS |
| 64 | create_order | critical | add_to_cart | add_to_cart | PASS |
| 65 | acknowledgment | informational | no_tool | no_tool | PASS |
| 66 | check_product_medical_suitability | informational | handoff\|no_tool | no_tool | PASS |
| 67 | unsupported_media_sticker | handoff | handoff | handoff | PASS |
| 68 | wholesale_inquiry | handoff | handoff | handoff | PASS |
| 69 | view_cart | critical | no_tool | no_tool | PASS |
| 70 | check_delivery_cost_and_time | informational | no_tool | no_tool | PASS |
| 71 | check_payment_methods | informational | no_tool | no_tool | PASS |
| 72 | positive_feedback | informational | no_tool | no_tool | PASS |
| 73 | check_restock_date | informational | no_tool | no_tool | PASS |
| 74 | modify_order_with_self_correction | critical | add_to_cart | add_to_cart | PASS |
| 75 | check_product_availability_and_price (Arabizi) | informational | no_tool\|show_menu | no_tool | PASS |

(id 54 — `opt_out_of_messages` — is `UNSCORED`, never run.)

## Failure diagnosis (11 real failures + 1 corrected map defect)

### (c) Map defect — corrected before recording

**id 20 — `check_product_safety` ("is this safe during pregnancy?")**
The original `expected_behavior.py` graded this `{"no_tool"}` only. The real run showed the
model calling `request_human_handoff` with reason "الزبونة حامل وبدها تتأكد من أمان الشامبو
وكريم الجسم للحمل". On inspection, `ai_service.py`'s own tool description for
`request_human_handoff` explicitly lists **"medical advice"** as an escalation trigger — the
model followed its own instructions correctly; the map was too narrow. **Fixed**: `EXPECTED[20]`
widened to `{"no_tool", "handoff"}`, and ids 59/66 (the two other product-safety-for-a-health-
condition cases) widened for the same reason, for consistency — even though those two did not
fail this run (both observed `no_tool`, still valid under the wider set). This correction was
applied by re-grading the **same real observed data** already captured in `tests/eval/.last_run.json**,
not by re-calling the API — the tool description already sanctions this exact outcome, so a
second real call would not add information, only cost. Corrected tally: **63/74 (85.1%)**
overall, informational tier **34/34 (100%)**. The raw, pre-fix run scored 62/74 (83.8%),
informational 33/34 (97.1%) — recorded here for transparency, not used as the final number.

### (a) Genuine agent weaknesses (10 cases) — not fixed, this is what the eval is for

**id 17 — hallucinated cart action (most notable finding of this run).** Customer asked for
gift-wrapped hair conditioner + body cream. The reply says *"خلصتِ! أضفت لك: مطري الشعر
الطبيعي... كريم الجسم بالخزامى..."* ("Done! I added for you: ...") — but `tool_calls` for this
case is **empty**. The model claimed a cart mutation that never happened. This is the exact
failure mode REQ-ai-no-hallucination exists to catch, and the system prompt's anti-hallucination
language (`<escalation_rules>`, "لا تدّعي أبداً أنك حوّلت المحادثة... إلا إذا استدعيتِ الأداة
فعلاً") only covers the handoff tool explicitly — it does not (yet) generalize to "never claim
add_to_cart succeeded without calling it." Worth a follow-up prompt tightening in a future phase.

**id 35 — hallucinated escalation, same pattern, on the handoff tool itself.** Customer
complains about a week-late order. The model calls `get_order_status` (finds nothing), then
its reply says *"بدي أحوّلك لحنان مباشرة"* ("I'm transferring you to Hanan directly") — but
`request_human_handoff` was never called. This one is more serious than id 17 because the
system prompt's `<escalation_rules>` explicitly forbid exactly this ("never claim you've
escalated unless you actually called the tool") and the model violated its own instruction.

**id 11 — buying-intent order not converted to a tool call.** "بدي اعمل هزمنا لشمع وكريمات...
بدي كمان مطري شعر" contains a clear buying verb ("بدي اعمل هزمنا") + named categories, which the
`<tool_rules>` decision tree says should call `add_to_cart`/`show_menu` immediately. The model
instead listed products conversationally and asked "بدك تضيفهم للسلة؟" (want me to add them?) —
not wrong exactly, but inconsistent with its own decision tree for a category-only, no-specific-
product-name order.

**id 19 — courier-contact request neither answered nor escalated.** Politely explains it has no
courier phone number and offers to connect the customer with Hanan, but calls neither
`get_order_status` nor `request_human_handoff` — ends on a question ("هل بدك أتواصلي معها؟")
instead of acting.

**id 25 — post-checkout order modification not escalated.** Correctly identifies it has no tool
to edit an existing order, but resolves it by asking the customer to place a *second* order and
merge them with Hanan later, rather than calling `request_human_handoff` — this is exactly the
success-criterion-4 boundary case (agent must hand off order changes past `to_do`, never
improvise), and the model handled it with prose instead of the tool.

**id 29 — third-party/duplicate order reference not escalated.** Correctly refuses to look up
another customer's order (privacy-safe instinct) but never calls `request_human_handoff`,
offering instead to re-add items if the customer restates them from memory.

**id 31 — over-escalation on a benign request.** "اشطبيلي كلشي من السلة" (clear my cart) has no
tool and needed no tool — a plain "I can't clear it myself, tell me what you'd like" would have
sufficed — but the model called `request_human_handoff` anyway. This is the opposite failure
mode from ids 19/25/29/35: unnecessary escalation adds noise to Hanan's queue for something
trivial.

**id 39 — Arabizi order genuinely ambiguous, model asked rather than guessed (defensible, still
a miss against the expected outcome).** "baddi 2 cream w shame3a wa7de" — `EVAL_CATALOG` has two
creams and two candles, so "cream"/"candle" alone is ambiguous; see the (b)-style fixture note
below.

**id 55 — wrong-recipient message not escalated.** As anticipated when authoring the map (see
`expected_behavior.py`'s comment on id 55): the `<escalation_rules>` block does not cover "this
message wasn't meant for you" scenarios, so no handoff fires — a polite clarifying reply is
given instead. Confirms this was a real, predictable gap rather than a surprise.

**id 62 — deferred-payment request answered directly instead of escalated.** Notably, "deferred
payment" is explicitly named in the `request_human_handoff` tool description alongside "custom/
bulk orders," "wholesale," and "medical advice" — and ids 22/68 (bulk/wholesale) both escalated
correctly this run, and id 20 (medical advice) did too. Only the deferred-payment branch of that
same tool-description list failed to fire — the model answered the policy question itself
("للأسف حالياً ما عندنا خيار دفع مؤجل") rather than deferring the decision to the owner as its
own tool description implies it should.

### (d) Infra/API flakiness — not a defect, the safety net worked

**id 33 — real empty-completion from Claude on the second (post-tool) call.** `save_address` was
called correctly with the right address. The *second* Anthropic call (forced final reply after
tool use) came back with no text content, which `ai_service.generate_reply()` correctly turns
into `AIUnavailableError("empty model response")` (03-03's contract) — `processor.py` then opens
an `ai_failure` handoff and sends the Arabic fallback, exactly as designed (03-05). Because the
harness's outcome-derivation gives `"handoff"` precedence over the tool name that was actually
called, this case is recorded as `handoff`, masking that `save_address` itself succeeded. This
is real, non-reproducible Claude-side noise (empty completions happen occasionally with any
model), not an agent judgment error and not a map defect — recorded honestly as a miss against
this case's narrow expectation, with the mechanism explained here rather than "fixed" by
loosening the map (loosening it to always accept `handoff` everywhere would make the eval
trivially easy to pass).

### (b) Harness/fixture artefact — not app/data/knowledge/ this time, but the same spirit

**id 39 (see above) revisited as a fixture note.** `EVAL_CATALOG` (`tests/eval/conftest.py`) was
authored with 2 near-identical creams and 2 near-identical candles for realism, but that makes a
generic "cream"/"candle" reference genuinely ambiguous in a way a real, larger, more
differentiated production catalog likely would not be. The model's clarifying question is a
reasonable response to a genuinely ambiguous synthetic catalog, not obviously an agent flaw —
flagged separately from the genuine-weakness list above because fixing it would mean changing
the eval fixture, not the agent.

**No case failed because of `app/data/knowledge/` being empty in this run** — none of the FAQ-
ish informational cases (ingredients, store hours, delivery cost, payment methods, restock date,
etc.) actually failed; the model answered all of them plausibly from the system prompt +
catalog alone, without needing the (currently empty) knowledge base. This is worth noting as a
positive result, distinct from the risk flagged in `expected_behavior.py`'s TIERS comment.

## Known limitations of this baseline

- **Accuracy of *content* is not graded**, only *which tool was called* (or none). A `no_tool`
  reply that is factually wrong about, say, delivery cost would still score PASS here — this
  eval catches tool-call/escalation regressions, not hallucinated FAQ facts.
- **74 cases is a small sample** for per-tier percentages — a single flipped case moves the
  handoff tier by 6.25 points. Treat these numbers as directional, not statistically precise.
- **Non-determinism**: `generate_reply()` runs at `temperature=0.3`; a re-run of the exact same
  74 cases would likely NOT reproduce this exact table case-for-case (id 33's empty-completion
  in particular is unlikely to repeat). Plan 03-07 should set thresholds with headroom for this,
  not treat 85.1%/75.0%/68.8%/100.0% as an exact bar.
- **`EVAL_CATALOG` is synthetic** (8 hand-written products), not the real production catalog —
  see id 39's diagnosis. Fuzzy-matching behavior against the real, eventual product catalog may
  differ.

---
*Phase: 03-agent-dependability-safety*
*Plan: 03-06*
*Recorded: 2026-08-28*
