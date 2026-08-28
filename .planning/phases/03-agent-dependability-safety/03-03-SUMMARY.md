---
phase: 03-agent-dependability-safety
plan: 03
subsystem: ai
tags: [claude, anthropic, exception-contract, tool-use, escalation, handoff]

# Dependency graph
requires:
  - phase: 03-agent-dependability-safety (03-01)
    provides: app/services/handoff.py::trigger() — the AI-outage/tool-executor
      handoff path this plan's raise-on-failure contract now makes reachable
provides:
  - "AIUnavailableError(RuntimeError) in app.services.ai_service — raised (not
    swallowed) on missing CLAUDE_API_KEY, real Anthropic API failure (original
    exception chained via `from exc`), and empty model completion"
  - "5th Claude tool, request_human_handoff(reason: str, required) — defined
    in ai_service._TOOLS; execution/DB write is plan 03-05's job (per ADR-005
    / the one-AI-file rule — tool definitions live here, tool execution lives
    in processor.py)"
  - "<escalation_rules> system-prompt block: escalate on anger/refund
    demands/damaged-or-missing items/privacy concerns/explicit human
    requests; forbids claiming an escalation or an order change (cancel/
    refund/edit) without actually calling a tool"
  - "Removed the ai_service-side duplicate Arabic fallback string and the
    literal '(no reply)' sentinel — processor.AI_FALLBACK_REPLY is now the
    only AI fallback string in the codebase"
affects: [03-04, 03-05, 03-07]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Exception-chaining contract: generate_reply() now raises
      AIUnavailableError for every real failure (missing key, API error,
      empty completion) instead of returning a disguised fallback string;
      callers own the customer-facing text and any escalation decision"
    - "Tool definition vs. tool execution split: ai_service.py only ever
      defines new tools (schema + prompt rules); processor.py's
      _make_tool_executor is the only place a tool's side effects run"

key-files:
  created: []
  modified:
    - app/services/ai_service.py
    - tests/unit/test_ai_service.py

key-decisions:
  - "generate_reply() raises AIUnavailableError instead of swallowing every
    exception into a hard-coded Arabic string — this was the prerequisite
    the whole phase needed for AI-outage handoffs to ever be reachable in
    production (previously ai_service.py's own try/except made processor.py's
    except-block dead code)."
  - "The inner per-tool try/except (a single failing tool becomes a
    tool_result string) was deliberately left unchanged and commented — it
    is a different, still-correct behavior that must survive the new outer
    raise-on-failure contract."
  - "request_human_handoff's *definition* lives in ai_service.py; its
    *execution* (the actual handoff.trigger() call) is explicitly left for
    plan 03-05's tool executor, consistent with the one-AI-file rule and
    ADR-005 — ai_service.py has no phone/session context to call
    handoff.trigger() itself."
  - "Added a file-scoped autouse mock_catalog fixture to
    tests/unit/test_ai_service.py (test-only change, no production code)
    to fix a circuit-breaker test-pollution bug this plan's new tests
    otherwise triggered — see Deviations."

patterns-established:
  - "Tests calling generate_reply() with a valid API key must not let
    _full_catalog_context() reach the real (block_live_db-guarded)
    app.ai.retriever._catalog() — mock app.ai.retriever._catalog directly,
    the same way conftest.py mocks the DB seam for processor/whatsapp_helpers."

# Metrics
duration: ~20min
completed: 2026-08-28
---

# Phase 3 Plan 3: AI Failure Contract + Fifth Tool Summary

**`AIUnavailableError` replaces ai_service.py's silent-swallow-everything contract, and Claude gets a `request_human_handoff` tool it must actually call instead of merely claiming an escalation.**

## Performance

- **Duration:** ~20 min
- **Started:** ~2026-08-28T18:12:00Z (estimated — not captured at session start)
- **Completed:** 2026-08-28T18:32:18Z
- **Tasks:** 2
- **Files modified:** 2 (`app/services/ai_service.py`, `tests/unit/test_ai_service.py`)

## Accomplishments
- `generate_reply()` now raises `AIUnavailableError` on all three real-failure
  paths (missing/empty API key, a real Anthropic call failure with the
  original exception chained via `from exc`, and an empty model completion)
  instead of returning a hard-coded Arabic apology string that was
  indistinguishable from a normal reply.
- Claude has a fifth tool, `request_human_handoff` (`reason: str`, required),
  and a new `<escalation_rules>` system-prompt block that tells it to call
  the tool — not just say it did — on anger, refund demands, damaged/missing
  items, privacy concerns, or explicit human requests, and forbids promising
  a cancel/refund/order edit it has no tool to perform.
- A single failing *tool* (inside the agentic loop) still does not break the
  customer's reply — verified unchanged and covered by a new test.
- Found and fixed a real, reproducible test-pollution bug (see Deviations)
  that both sibling plans (03-01, 03-02) had already independently
  discovered and correctly deferred to this plan's ownership of
  `test_ai_service.py`.

## Task Commits

Each task was committed atomically:

1. **Task 1: AIUnavailableError — surface unrecoverable AI failures instead of swallowing them** - `f9685ac` (fix)
2. **Task 2: Fifth tool — request_human_handoff (definition + prompt rules)** - `934d08f` (feat)

**Plan metadata:** _(this commit)_

## Files Created/Modified
- `app/services/ai_service.py` — `AIUnavailableError(RuntimeError)` class;
  `generate_reply()` raises on missing key / API failure / empty completion;
  inner per-tool try/except left unchanged with an explanatory comment;
  fifth tool `request_human_handoff` added to `_TOOLS`; `<escalation_rules>`
  block + one worked example added to `_SYSTEM_PROMPT`.
- `tests/unit/test_ai_service.py` — rewrote `test_returns_fallback_when_no_api_key`
  as `test_raises_when_no_api_key`; added `test_raises_when_anthropic_call_fails`,
  `test_raises_when_response_has_no_text`, `test_failing_tool_does_not_break_the_reply`,
  and a new `TestRequestHumanHandoffTool` class (5 tests: tool-set membership,
  required `reason`, no tool exposes a `status`-mutating surface, prompt
  carries the escalation block + anti-fabrication rule, `tool_executor`
  receives the new tool's name/args through the existing 2-call loop); added
  an autouse `mock_catalog` fixture (see Deviations).

## Decisions Made
- Kept `AIUnavailableError` as a plain `RuntimeError` subclass (verified via
  `AIUnavailableError.__mro__[1].__name__ == "RuntimeError"`) so any existing
  broad `except Exception`/`except RuntimeError` handler (e.g.
  `processor.handle_message`'s current fallback path) keeps working
  unmodified until 03-05 gives it dedicated handling.
- `request_human_handoff`'s *definition* only lives here; the tool's
  *implementation* (opening a real `handoffs` row via `handoff.trigger()`)
  is explicitly out of scope for this plan and belongs to 03-05, consistent
  with the one-AI-file rule and ADR-005 — `ai_service.py` deliberately has
  no phone/session context to call `handoff.trigger()` itself.
- `processor.AI_FALLBACK_REPLY` is now the *only* AI fallback string in the
  codebase (the `ai_service.py`-side duplicate, `"عذرًا، صار خلل مؤقت. جرّب مرة ثانية 🙏"`,
  is gone — confirmed via `grep -rn "صار خلل مؤقت" app/` returning nothing).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1/3 - Bug/Blocking] Fixed a full-suite test-pollution bug this plan's own new tests triggered**
- **Found during:** Task 2, running the plan's own `<verification>` step
  (`pytest -q`, the full suite) after both tasks were otherwise complete.
- **Issue:** `generate_reply()`'s `_full_catalog_context()` does an unmocked
  `from app.ai.retriever import _catalog; get_catalog()` on every call.
  `app.ai.retriever` is not in `tests/conftest.py`'s `mock_db` patch list, so
  every `test_ai_service.py` test that calls `generate_reply()` with a valid
  API key hits the `block_live_db` guard, burns 3 real retry attempts (with
  backoff sleeps) inside `app/db/database.py`'s retry logic, and increments
  its **process-global** `_consecutive_failures` counter. This plan's
  pre-existing 4 such tests already sat at 4 of the circuit breaker's default
  `circuit_threshold` of 5; this plan's own new tests (`test_raises_when_anthropic_call_fails`,
  `test_raises_when_response_has_no_text`, `test_failing_tool_does_not_break_the_reply`,
  `test_tool_executor_receives_the_new_tool`) — all required by the plan's
  own `<action>` spec — pushed the count over the threshold, tripping the
  circuit open and failing all 5 tests in `tests/unit/test_database.py::TestQueryAndExecute`
  whenever they ran later in the same pytest process. Both sibling plans
  (03-01, 03-02) had already independently found and correctly deferred this
  exact bug in `.planning/phases/03-agent-dependability-safety/deferred-items.md`,
  since it lives in a file (`test_ai_service.py`) neither of them owns.
- **Fix:** Added a file-scoped `autouse` `mock_catalog` fixture to
  `tests/unit/test_ai_service.py` that monkeypatches `app.ai.retriever._catalog`
  to return `[]`, so `generate_reply()` never reaches the live-DB guard in
  this file's tests at all. No production code changed for this fix.
- **Files modified:** `tests/unit/test_ai_service.py` (test-only)
- **Verification:** `pytest tests/unit/test_ai_service.py tests/unit/test_database.py -q`
  and the full `pytest -q` are both green (431 passed, 3 skipped — up from
  the pre-fix full-suite run's 356 passed / 5 failed, all in
  `test_database.py`). `test_ai_service.py` itself also dropped from 8.75s
  to 1.24s, confirming the real-retry-sleep hypothesis.
- **Committed in:** `934d08f` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug/blocking, dual-classified since it
both broke correctness of the shared test session and blocked a clean full-
suite run).
**Impact on plan:** Test-only fix, no production code touched beyond what
the plan itself specified. Also updated the shared `deferred-items.md` to
record the resolution for the two sibling plans that had already logged this
same issue against files they don't own.

## Issues Encountered
None beyond the deviation above.

## User Setup Required
None — no external service configuration required.

## Next Phase Readiness
- `AIUnavailableError` is importable from `app.services.ai_service` and its
  three raise conditions are exercised by tests — plan 03-05 can now import
  it and give `processor.handle_message`'s existing `except` block dedicated
  handling (customer fallback text + opening a handoff) instead of the
  current catch-all `except Exception`.
- The `request_human_handoff` tool's exact schema (`name`, required
  `reason: string`) is fixed and tested — plan 03-05's tool executor can
  implement it by calling `handoff.trigger(phone, reason, ...)` (from 03-01)
  without any further changes to `ai_service.py`.
- No blockers for 03-04/03-05/03-07.

---
*Phase: 03-agent-dependability-safety*
*Completed: 2026-08-28*

## Self-Check: PASSED
- FOUND: app/services/ai_service.py
- FOUND: tests/unit/test_ai_service.py
- FOUND: .planning/phases/03-agent-dependability-safety/03-03-SUMMARY.md
- FOUND commit f9685ac (Task 1: fix(03-03))
- FOUND commit 934d08f (Task 2: feat(03-03))
