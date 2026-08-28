---
phase: 03-agent-dependability-safety
plan: 02
subsystem: agent-safety
tags: [policy-gate, deterministic-validation, handoff-detection, arabic-nlp, whatsapp-bot]

# Dependency graph
requires:
  - phase: 03-agent-dependability-safety (plan 03-01, same wave)
    provides: "app/services/handoff.py::trigger() — the sink detect_handoff_keyword()'s result feeds into (wired by 03-04)"
  - phase: 03-agent-dependability-safety (plan 03-03, same wave)
    provides: "the 5th ai_service._TOOLS entry (request_human_handoff) that TOOL_SCOPES must mirror exactly"
provides:
  - "app/services/policy.py: PolicyDecision, validate(tool_name, args, context), TOOL_SCOPES, resolve_product(), detect_handoff_keyword()"
  - "A single deterministic chokepoint every AI tool call must pass through before execution (wired by 03-05)"
  - "A pure, unit-tested Arabic+English escalation-phrase detector (wired by 03-04)"
affects: [03-04-PLAN.md, 03-05-PLAN.md, 03-06-PLAN.md]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure-module policy gate: zero I/O, caller-supplied context dict (paused, catalog, order_status_provider, phone) — never imports app.db.database/processor/handoff/whatsapp_helpers"
    - "Default-deny tool allowlist (TOOL_SCOPES) keyed to scope categories (read/cart/customer/escalation/order) so a future 6th tool is denied by omission, not silently allowed"
    - "First-denial-wins rule ordering in validate(): paused > unknown_tool > order_not_mutable > per-tool arg rules"
    - "Two-tier keyword matching for false-positive safety: multi-word phrases via substring, single tokens via whitespace/punctuation-delimited whole-word set only"

key-files:
  created:
    - app/services/policy.py
    - tests/unit/test_policy.py
    - .planning/phases/03-agent-dependability-safety/deferred-items.md
  modified: []

key-decisions:
  - "policy.py stays 100% pure (no DB/AI/network imports) — verified by an import-set check and a grep for `from/import app` in both the plan's <verify> and this SUMMARY's own re-run"
  - "'order' scope has zero members by design (documented inline) — success criterion 4 is pinned via a monkeypatched synthetic order-scoped tool test, not by a real one, since no real tool has ever had this scope"
  - "opt_out_of_messages (dataset id 54) intentionally returns None from detect_handoff_keyword() — routing a compliance/consent request into the aunt's manual handoff queue would mis-handle it; documented in-module as explicitly out of scope for Phase 3"
  - "'حنان' (the aunt's name) and short tokens like 'بشر' are never bare-word-matched — only whole-word or multi-word-phrase matches trigger escalation, preventing false positives on ordinary skincare vocabulary ('بشرتي')"

patterns-established:
  - "Pattern: deterministic policy/detection modules in this codebase take zero I/O dependencies and receive all external state via an explicit context dict, keeping them synchronously unit-testable without conftest.py's DB-mocking machinery"

# Metrics
duration: ~20min
completed: 2026-08-28
---

# Phase 3 Plan 02: Deterministic Policy Gate + Escalation Detector Summary

**`app/services/policy.py` — a pure, zero-I/O `validate()` gate for all 5 AI tool calls (product grounding, quantity clamping, address shape, order-mutation boundary) plus a two-tier Arabic/English `detect_handoff_keyword()` detector, backed by 63 unit tests in `tests/unit/test_policy.py`.**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-08-28T18:31:18Z
- **Tasks:** 3
- **Files created:** 3 (`policy.py`, `test_policy.py`, `deferred-items.md`)

## Accomplishments
- `validate(tool_name, args, context) -> PolicyDecision`: single deterministic chokepoint for all 5 AI tools (`add_to_cart`, `show_menu`, `get_order_status`, `save_address`, `request_human_handoff`), evaluated in fixed rule order (session_paused → unknown_tool → order_not_mutable → per-tool arg rules), first denial wins.
- `resolve_product()` extracts the exact-then-substring catalog lookup `_tool_add_to_cart` already used (`processor.py:419-430`) into a single shared definition, so grounding-check and execution agree.
- `add_to_cart` never honours a `price` argument even if one is hallucinated into the tool call — explicit-construction of `args`, not a merge of the caller's dict, with a test (`test_no_price_argument_is_ever_honoured`) pinning it.
- `AGENT_MUTABLE_ORDER_STATUSES = {"to_do"}` + the `order_not_mutable` rule turn "the AI has no path to mutate an order past to_do" from an architectural accident into an asserted, regression-tested rule — pinned via a monkeypatched synthetic `cancel_order`/`"order"`-scope tool since no real tool has this scope today.
- `detect_handoff_keyword(text) -> str | None`: returns one of `explicit_human`, `complaint`, `refund`, `damaged`, `privacy`, or `None`, using dataset-grounded vocabulary (spot-checked against dataset ids 23, 45, 57, 63) with two hard false-positive guards: single tokens only whole-word match (prevents `"بشر"` colliding with `"بشرتي"`), and `"حنان"` only matches inside a phrase.

## Task Commits

Each task was committed atomically:

1. **Task 1: policy.py — PolicyDecision + validate()** - `2d23143` (feat)
2. **Task 2: detect_handoff_keyword()** - `15eb191` (feat)
3. **Task 3: tests/unit/test_policy.py** - `7f0609c` (test)

_Note: Task 2's diff was transiently swept into sibling plan 03-01's commit by a shared-git-index race (both agents run `git add`/`git commit` concurrently in the same working directory), then correctly separated out again when 03-01 amended its own commit — see "Deviations from Plan" below for the full account. The final state above is what actually landed on the branch._

## Files Created/Modified
- `app/services/policy.py` (336 lines) — `PolicyDecision`, `TOOL_SCOPES`, `AGENT_MUTABLE_ORDER_STATUSES`, `resolve_product()`, `validate()`, `HANDOFF_PHRASES`/`HANDOFF_WORDS`, `detect_handoff_keyword()`. Zero `app.*` imports beyond nothing at all (grep for `^(from|import) app` returns empty).
- `tests/unit/test_policy.py` (313 lines) — `TestToolAllowlist`, `TestAddToCartGrounding`, `TestQuantityClamp`, `TestSaveAddressShape`, `TestPausedSession`, `TestOrderMutationBoundary`, `TestDetectHandoffKeyword` (63 test cases total).
- `.planning/phases/03-agent-dependability-safety/deferred-items.md` (new) — logs 6 full-suite test failures verified to be pre-existing/unrelated to this plan (see below).

## Interface for downstream plans (03-04, 03-05)

```python
from app.services.policy import (
    validate, PolicyDecision, TOOL_SCOPES, AGENT_MUTABLE_ORDER_STATUSES,
    resolve_product, detect_handoff_keyword,
    MIN_CART_QTY, MAX_CART_QTY, MIN_ADDRESS_CHARS, MAX_ADDRESS_CHARS,
)

# validate() signature:
validate(tool_name: str, args: dict | None, context: dict) -> PolicyDecision

# context keys (all optional, safe defaults):
#   paused: bool
#   catalog: list[dict]                       # shaped like whatsapp_helpers.catalog() rows
#   order_status_provider: Callable[[], str | None]   # called ONLY for order-scoped tools
#   phone: str                                 # logging only, not read by policy.py

# PolicyDecision fields:
#   allowed: bool
#   code: str        # "ok" | "session_paused" | "unknown_tool" | "order_not_mutable"
#                     # | "product_not_in_catalog" | "address_too_short"
#   message: str      # Arabic text to hand back to Claude as the tool_result on denial
#   args: dict        # normalised args to execute with, on allow
#   escalate: bool     # True means the caller should also open a handoff

# detect_handoff_keyword() groups, in the fixed evaluation order:
#   "explicit_human", "refund", "damaged", "complaint", "privacy"  (or None)
```

03-04 maps any non-`None` `detect_handoff_keyword()` result to
`handoff.trigger(phone, "keyword_request", ...)`. 03-05 wires `validate()`
into `processor._make_tool_executor` and replaces `processor.py`'s duplicate
`MIN_CART_QTY`/`MAX_CART_QTY` literals with imports from `policy.py`.

## Decisions Made
- `"order"` scope intentionally has zero members — documented inline as an architectural fact (order creation is confirm-only, status progression is operator-only), asserted by `test_no_tool_today_has_order_scope`, and the boundary rule itself pinned via a monkeypatched synthetic tool rather than a real one.
- `opt_out_of_messages` (dataset id 54) deliberately does NOT trigger a handoff — no consent/suppression mechanism exists anywhere in this codebase yet, and routing it into the aunt's manual queue would mis-handle a compliance request. Verified: `detect_handoff_keyword("بكفي تبعتولي رسايل، بديش اشي شكرا")` returns `None`.
- Kept `resolve_product`'s two-pass (exact, then substring) matching identical to `_tool_add_to_cart`'s existing logic rather than improving it, per the plan's explicit instruction that `_tool_add_to_cart` keeps its own separate lookup for the numeric-menu-pick path that bypasses the AI/policy gate entirely.

## Deviations from Plan

### Auto-fixed Issues

None — no code deviations from the plan's specification. `validate()`, `PolicyDecision`, `TOOL_SCOPES`, `resolve_product()`, and `detect_handoff_keyword()` were implemented exactly as specified, including the exact Arabic message strings quoted in the plan (verified against `processor.py:433` and `ai_service.py:293` for wording parity).

### Process Anomaly (not a code deviation — documented for transparency)

**Shared-git-index race during concurrent multi-agent execution.**
- **What happened:** This plan (03-02) runs in the same working directory as sibling plans 03-01 and 03-03, executing concurrently. After committing Task 1 (`2d23143`), Task 2's edit to `policy.py` (the `detect_handoff_keyword()` addition, staged via `git add app/services/policy.py`) was still sitting in the shared index when sibling plan 03-01 ran its own `git add` + `git commit` for `handoff.trigger()`. A plain `git commit` (no pathspec) commits everything staged in the shared index, so 03-01's first commit (`81f251d`) unintentionally included my staged `policy.py` diff alongside their `handoff.py` changes. My own attempted `git commit -- app/services/policy.py` for Task 2 then found nothing new to commit (it was already captured).
- **Resolution:** No action was taken from this agent's side — per the executor's instructions, git history was never stashed, reset, or reverted. Sibling 03-01 independently amended its own commit shortly after (`c4790dc` replaces `81f251d`, stat confirms `app/services/handoff.py` only, no `policy.py`), which correctly un-bundled my `policy.py` changes back into the working tree as uncommitted. This agent then staged and committed them cleanly as `15eb191`, scoped to `app/services/policy.py` only (verified via `git diff --cached --stat` before committing).
- **Verification the final state is correct:** `git diff HEAD -- app/services/policy.py` is empty (working tree matches the committed file exactly); `pytest tests/unit/test_policy.py -q` passes 63/63 both before and after the git churn; the module purity check (`grep -nE "^(from|import) app" app/services/policy.py`) returns nothing at every checkpoint.
- **Files affected:** `app/services/policy.py` only — no other file was touched by this anomaly.
- **Impact:** None on the shipped code. The final commit `15eb191` contains exactly the intended Task 2 diff (88 insertions, matching the plan's specification line-for-line). Flagging this for the orchestrator/user as a known risk of running `type="execute"` plans concurrently in one working directory with a shared git index — a future improvement could have each concurrent agent commit with `git commit -- <own-files>` defensively from the start (this agent already does, per its own protocol) but that alone cannot prevent a sibling's plain `git commit` from sweeping up another agent's staged-but-uncommitted files.

---

**Total deviations:** 0 code deviations. 1 process anomaly (git-index race), self-resolved with no data loss, fully verified.
**Impact on plan:** None — final shipped code matches the plan specification exactly; only the intermediate commit history briefly (and harmlessly) misattributed 88 lines before self-correcting.

## Issues Encountered

**Known wave-1 interaction (anticipated by the plan): resolved favourably.** By the time Task 3 (`test_tool_scopes_match_ai_service_tools`) ran, sibling plan 03-03 had already committed the 5th tool (`request_human_handoff`) to `ai_service._TOOLS` (commit `f9685ac`, landed before this plan's Task 3). The guard test therefore passed on its first execution (`{t["name"] for t in _TOOLS} == set(TOOL_SCOPES)` — both sets have exactly 5 matching entries) — no red state was observed, and no re-run was needed. Documented here per the plan's explicit instruction to note this either way.

**Full-suite test failures — verified pre-existing, not caused by this plan.** A full `pytest -q` run (418 tests collected once `test_policy.py` and sibling wave-1 files existed) showed 6 failures: 5 in `tests/unit/test_database.py::TestQueryAndExecute::*` (`RuntimeError: Supabase circuit open`) and 1 in `tests/unit/test_audit.py::test_operator_actions_has_nineteen_entries`. Root-caused and confirmed unrelated to this plan by running `pytest -q --ignore=tests/unit/test_policy.py`, which reproduces the identical 6 failures with this plan's own files entirely absent from collection. The `test_database.py` failures come from module-level circuit-breaker globals (`app/db/database.py`) leaking across test files within one pytest session (no autouse reset fixture); `test_audit.py`'s count assertion is a moving target while wave-1 siblings are concurrently adding `OPERATOR_ACTIONS` entries. Logged to `.planning/phases/03-agent-dependability-safety/deferred-items.md` per the scope-boundary rule rather than fixed (neither file is in this plan's `files_modified`). `pytest tests/unit/test_policy.py -q` — the plan's actual required verification command — passes 63/63 cleanly both in isolation and as part of the full suite.

## User Setup Required

None — no external service configuration required. `policy.py` is pure Python with zero external dependencies beyond the standard library (`dataclasses`, `re`, `typing`).

## Next Phase Readiness

- `app/services/policy.py` is ready for 03-04 (wires `detect_handoff_keyword()` into `handle_message` before hard commands, and calls `handoff.trigger()` on any non-`None` result) and 03-05 (wires `validate()` into `processor._make_tool_executor`, replaces `processor.py`'s duplicate `MIN_CART_QTY`/`MAX_CART_QTY` with imports from here).
- No blockers. The interface (`validate()` signature, `context` keys, `PolicyDecision` fields, `detect_handoff_keyword()` group list) is fully documented above for those two plans to consume directly.
- Recommend whichever plan next owns `tests/conftest.py` or `app/db/database.py` add an autouse circuit-breaker-reset fixture per `deferred-items.md`'s recommendation, and re-run `test_audit.py::test_operator_actions_has_nineteen_entries` once all wave-1 `OPERATOR_ACTIONS` additions have landed.

---
*Phase: 03-agent-dependability-safety*
*Completed: 2026-08-28*

## Self-Check: PASSED

- FOUND: app/services/policy.py
- FOUND: tests/unit/test_policy.py
- FOUND: .planning/phases/03-agent-dependability-safety/deferred-items.md
- FOUND: .planning/phases/03-agent-dependability-safety/03-02-SUMMARY.md
- FOUND commit: 2d23143 (Task 1)
- FOUND commit: 15eb191 (Task 2)
- FOUND commit: 7f0609c (Task 3)
