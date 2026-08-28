---
phase: 03-agent-dependability-safety
plan: 05
subsystem: agent-safety
tags: [policy-gate, tool-executor, handoff, ai-failure, whatsapp-bot]

# Dependency graph
requires:
  - phase: 03-agent-dependability-safety (03-02, wave 1)
    provides: "app/services/policy.py::validate(tool_name, args, context) -> PolicyDecision"
  - phase: 03-agent-dependability-safety (03-03, wave 1)
    provides: "app/services/ai_service.py::AIUnavailableError, the request_human_handoff tool definition"
  - phase: 03-agent-dependability-safety (03-04, wave 2)
    provides: "processor._open_handoff(), HANDOFF_ACK_REPLY, the paused/keyword-handoff gate ordering inside handle_message"
provides:
  - "Every AI-proposed tool call passes through policy.validate() before its implementation runs — the deterministic gate is now live at the single chokepoint (_make_tool_executor's closure)"
  - "request_human_handoff is a working tool: opens a real handoffs row, pauses the session, and the customer gets exactly one deterministic Arabic acknowledgement (HANDOFF_ACK_REPLY) — never the model's own phrasing"
  - "AIUnavailableError (and any other generate_reply exception) now triggers an ai_failure handoff in addition to the existing Arabic fallback reply — an AI outage produces a human follow-up, not a silent apology"
  - "handoff.trigger()'s per-phone idempotency + the paused gate (03-04) together prevent an alert storm: repeated failures/messages during one outage or handoff open exactly one handoff and one aunt notification per customer"
affects: [03-06, 03-07, 03-08]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Executor-closure gate: policy.validate() runs first inside _make_tool_executor's inner function, before any if name == '...' dispatch branch — every one of the 5 AI tools (including request_human_handoff itself) passes through it, and a denial short-circuits before any _tool_* implementation runs."
    - "handoff_pending is a transient, non-persisted session flag (set only on a SUCCESSFUL _open_handoff call, consumed via st.pop() right before the final queue_text in handle_message's AI-fallback branch) — this is what guarantees the customer gets exactly one deterministically-worded message instead of the model's own reply plus an ack."
    - "AI-failure handoffs (ai_failure) do NOT go through handoff_pending — _open_handoff() is called directly in the except blocks and its result is discarded; the reply is unconditionally AI_FALLBACK_REPLY on this path, never HANDOFF_ACK_REPLY, matching success criterion 3's exact wording."

key-files:
  created:
    - tests/unit/test_processor_policy.py
  modified:
    - app/services/processor.py

key-decisions:
  - "Task 1's dispatch intentionally does NOT wire request_human_handoff yet — that branch (and the _tool_request_human_handoff implementation itself) is added in Task 2's commit, so a made-up/premature tool name during the brief Task-1-only window would have hit the 'Tool {name} not found' dead-code fallthrough rather than crash. This only matters for the atomic-commit history; by the end of Task 2 all 5 tools dispatch correctly."
  - "order_status_provider is passed into policy.validate()'s context as a lambda, never called eagerly — verified by test_no_extra_database_read_for_non_order_tools, which monkeypatches get_latest_order to raise and confirms show_menu/add_to_cart never trigger it."
  - "The plan's own Task 2 <verify> script (hm.index('handoff_pending') < hm.index('queue_text(phone, reply)')) collides with 03-04's earlier keyword-handoff gate, which already contains the literal string 'queue_text(phone, reply)' at an earlier point in handle_message's source. Re-verified the actual intent (handoff_pending precedes the AI-fallback section's queue_text call) using hm.rindex() instead of hm.index() for both sides — this is a verification-script artifact only, not a code deviation; the code itself matches the plan's specification exactly."

patterns-established:
  - "Any future tool executor change must keep policy.validate() as literally the first statement inside the closure, before catalog/order lookups are used for dispatch — this is what the phase's success criterion 1 (no un-gated tool call) depends on structurally, not just by convention."

# Metrics
duration: ~13min
completed: 2026-08-28
---

# Phase 3 Plan 05: Policy-Gated Tool Executor + Working Escalation Summary

**Every one of Claude's 5 tool calls now passes through `policy.validate()` before it can touch the cart/session/customer record, `request_human_handoff` opens a real database row instead of just a promise, and an AI outage produces a durable handoff on top of the existing Arabic fallback reply.**

## Performance

- **Duration:** ~13 min (876ea70 at 21:50:09 to 044e07f at 21:54:33, local time; UTC completion ~18:54)
- **Started:** 2026-08-28T18:50:09Z (estimated from first commit)
- **Completed:** 2026-08-28T18:54:53Z
- **Tasks:** 3 completed
- **Files modified:** 2 (1 created, 1 modified)

## Accomplishments
- `_make_tool_executor(phone, st, cart)`'s inner `executor()` closure now calls `policy.validate(name, args, context)` as its first action, before any dispatch branch — `context` carries `phone`, `paused`, `cart`, `catalog()` (already-imported and already-patched-by-every-test), and a **lazy** `order_status_provider` lambda that costs zero extra DB reads for today's five tools (none is order-scoped). A denial returns `decision.message` as the tool result — Claude phrases a natural Arabic sentence around it — and opens a `policy_denied` handoff when `decision.escalate` is set.
- `processor.py`'s local `MIN_CART_QTY`/`MAX_CART_QTY` literals are gone — both now come from `app.services.policy` via `from app.services.policy import MAX_CART_QTY, MIN_CART_QTY`. `processor.MIN_CART_QTY`/`processor.MAX_CART_QTY` still resolve correctly (verified: prints `1 50`), and `_tool_add_to_cart`'s own clamp is deliberately left in place — the numeric menu-pick path bypasses the AI (and therefore the gate) entirely, so both layers need it.
- `_tool_request_human_handoff(phone, st, reason)` opens a real handoff via `_open_handoff()` and only sets `st["handoff_pending"] = True` on success — a failed durable write returns an apology string instead, and the customer never gets told an escalation happened that didn't.
- `handle_message()` consumes `handoff_pending` (via `st.pop()`) immediately after `generate_reply()` returns, replacing the model's own reply with `HANDOFF_ACK_REPLY` — the customer gets **exactly one** message per handoff event, worded deterministically by us, never by the model (which is free to over-promise, e.g. "حنان رح تتصل فيكِ خلال ساعة", if left to phrase it itself).
- `generate_reply()`'s call site now has two except branches: `AIUnavailableError` (03-03's dedicated exception for missing key / API failure / empty completion) and a defence-in-depth generic `Exception` catch — both send `AI_FALLBACK_REPLY` **and** open an `ai_failure` handoff via `_open_handoff()` (its return value discarded; this path never sets `handoff_pending`, so the reply is always the fallback string, never the ack — matching the plan's success criterion 3 exactly).
- `handoff.trigger()`'s per-phone idempotency, combined with 03-04's paused gate short-circuiting every subsequent message once a handoff is open, together guarantee at most one handoff row and one aunt WhatsApp notification per customer per outage/escalation event — verified directly with a two-message test.
- 13 new tests in `tests/unit/test_processor_policy.py` (276 lines) driving the real `handle_message()` end-to-end with `generate_reply` stubbed to invoke the genuine `tool_executor` closure — no mocking of `policy.validate()` itself anywhere.

## Task Commits

Each task was committed atomically:

1. **Task 1: Policy-gate the tool executor** - `876ea70` (feat)
2. **Task 2: _tool_request_human_handoff + the single deterministic acknowledgement** - `2f98133` (feat)
3. **Task 3: AI-failure escalation + tests for the whole gated path** - `044e07f` (feat)

**Plan metadata:** _(this commit)_

## Files Created/Modified
- `app/services/processor.py` — imports `MAX_CART_QTY`/`MIN_CART_QTY` from `policy` (module-level names unchanged); `_make_tool_executor`'s closure runs `policy.validate()` before dispatch and handles denial (return message, conditionally escalate); `_tool_request_human_handoff()` (new); `request_human_handoff` dispatch branch; `handle_message()` consumes `handoff_pending` before the final `queue_text` in the AI-fallback branch; `generate_reply` import now also pulls `AIUnavailableError`; the AI-fallback `try/except` has dedicated `AIUnavailableError` and generic `Exception` branches, both opening an `ai_failure` handoff.
- `tests/unit/test_processor_policy.py` (new, 276 lines, 13 tests) — `TestPolicyGateBlocksBadToolCalls` (6), `TestRequestHumanHandoffTool` (3), `TestAIFailureEscalation` (3), `TestPausedSessionBlocksTools` (1).

## Interface for downstream plans (03-06 — verbatim)

```python
# The executor's context dict passed to policy.validate(), for reference:
{
    "phone": phone,
    "paused": bool(st.get("paused")),
    "cart": cart,
    "catalog": catalog(),
    "order_status_provider": lambda: (get_latest_order(phone) or {}).get("status"),
}

# A denial returns decision.message as the tool result string (Arabic,
# handed to Claude as a tool_result — the customer never sees it raw).

# handoff_pending: a transient dict key on `st`, set to True only by
# _tool_request_human_handoff() (on success) or the policy-denial escalate
# branch inside the executor closure. Consumed once via st.pop() in
# handle_message(), right before the AI-fallback section's final
# queue_text(phone, reply) call — never persisted by save_session().
```

**Live handoff reason codes after this plan** (all flow through `_open_handoff(phone, reason, metadata)` -> `handoff.trigger()`, whose `REASON_LABELS` dict — `app/services/handoff.py` — is the single source of the Arabic label the aunt sees):
- `keyword_request` — 03-04, Arabic/English "talk to a human" phrase match
- `unsupported_media` — 03-04, voice note/image/sticker/document/video/location/contacts
- `policy_denied` — 03-05, an unknown/hallucinated tool call the gate rejected with `escalate=True` (today only `unknown_tool` sets `escalate=True`; per-tool argument denials like `product_not_in_catalog`/`address_too_short` do NOT escalate — those are treated as ordinary conversational corrections, not handoff-worthy)
- `ai_requested` — 03-05, Claude called `request_human_handoff` itself
- `ai_failure` — 03-05, `generate_reply()` raised (`AIUnavailableError` or any other exception)
- `operator_takeover` — 05-06, an operator forced a status change while the bot was still active on that conversation (pre-existing, unrelated to this phase's message pipeline)

All five handoff triggers this phase owed are now live and tested: keyword (03-04), unsupported media (03-04), AI failure (here), the AI's own tool (here), and policy denial (here) — plus the paused gate (03-04) that makes every one of them stick.

## Decisions Made
- Kept Task 1's dispatch without the `request_human_handoff` branch (added in Task 2) to match the plan's task-by-task structure exactly — verified no regression since Task 1's own `<verify>` block never exercises that tool.
- `order_status_provider` stays a lambda, never evaluated for today's five tools — pinned by a dedicated test (`test_no_extra_database_read_for_non_order_tools`) that makes `get_latest_order` raise `AssertionError` if called.
- AI-failure handoffs never set `handoff_pending` / never produce `HANDOFF_ACK_REPLY` — the reply on that path is unconditionally `AI_FALLBACK_REPLY`, matching the plan's exact wording for success criterion 3 ("AIUnavailableError produces the Arabic fallback AND a handoff") rather than reusing the ack-message mechanism built for `request_human_handoff`.

## Deviations from Plan

### Verification-script artifact (not a code deviation)

**1. Task 2's `<verify>` index-ordering check collided with 03-04's pre-existing code**
- **Found during:** Task 2, running the plan's own `<verify>` command after the edit.
- **Issue:** The plan's verify script asserts `hm.index('handoff_pending') < hm.index('queue_text(phone, reply)')`. `handle_message()` already contained a second, earlier literal occurrence of `queue_text(phone, reply)` inside 03-04's keyword-handoff gate (section 2b) — `hm.index()` finds that occurrence first, which sits before this plan's new code, so the assertion failed even though the actual ordering this task cares about (inside the AI-fallback section) was correct.
- **Fix:** Re-ran the check with `hm.rindex()` on both sides (last occurrence of each string), which correctly targets section 6's `queue_text` call — the one this plan's `handoff_pending` logic actually gates. No production code changed; this is a test-script correction only, and was not committed as a file (ad hoc verification, not part of the test suite).
- **Verification:** `pytest tests/unit/test_processor.py tests/unit/test_processor_safety.py -q` (34 + 20 = 54 tests) passed, confirming the actual behavior is correct regardless of the verify-script wording.
- **Impact:** None on shipped code — purely a plan-authoring artifact from writing the verify script before accounting for 03-04's prior edit to the same function.

---

**Total deviations:** 0 code deviations. 1 verification-script artifact, self-resolved with no impact on shipped code.
**Impact on plan:** None — the plan's specification was implemented exactly as written; only the plan's own ad hoc verify command needed a `rindex()` correction to account for code 03-04 had already added to the same function.

## Issues Encountered
None. All three tasks' `<verify>` commands (after the one script correction above) passed on the first attempt; the full suite went from the 451-passed/3-skipped baseline to 464 passed/3 skipped (451 + 13 new tests, zero regressions) after every task and again at the end. `app/routers/whatsapp.py` confirmed untouched via `git diff --stat` against the pre-plan commit (`eaf5cc1`).

## User Setup Required
None — no external service configuration required.

## Next Phase Readiness
- The policy gate, `request_human_handoff`, and AI-failure escalation are all live, tested, and documented above for 03-06 (and later plans) to build on — the full context dict shape, `handoff_pending` mechanism, and the complete list of live handoff reason codes are recorded verbatim in this SUMMARY's "Interface for downstream plans" section.
- No blockers. Success criteria 1-4 are all met and independently test-covered: (1) `policy.validate()` runs before every dispatch — proved structurally by the code and by every denial test never mutating state; (2) `request_human_handoff` writes a real handoff and sends exactly one deterministic ack — `test_customer_receives_exactly_one_message_and_it_is_the_ack`; (3) `AIUnavailableError` produces the fallback AND a handoff, customer always gets a reply — `test_ai_unavailable_sends_fallback_and_opens_handoff`; (4) repeated failures produce one handoff per customer, not a storm — `test_second_message_during_ai_outage_does_not_open_a_second_handoff`.

---
*Phase: 03-agent-dependability-safety*
*Completed: 2026-08-28*

## Self-Check: PASSED

- FOUND: app/services/processor.py
- FOUND: tests/unit/test_processor_policy.py
- FOUND: .planning/phases/03-agent-dependability-safety/03-05-SUMMARY.md
- FOUND commit 876ea70 (Task 1: feat(03-05))
- FOUND commit 2f98133 (Task 2: feat(03-05))
- FOUND commit 044e07f (Task 3: feat(03-05))
