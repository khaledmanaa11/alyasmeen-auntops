---
phase: 03-agent-dependability-safety
plan: 08
subsystem: testing
tags: [requirements-traceability, ast-guard, knowledge-vault, documentation, outbox, handoff]

# Dependency graph
requires:
  - phase: 03-agent-dependability-safety (03-04, wave 2)
    provides: "the paused gate + keyword-handoff gate inside handle_message"
  - phase: 03-agent-dependability-safety (03-05, wave 3)
    provides: "policy-gated tool executor, request_human_handoff tool, AI-failure escalation — the complete pipeline exercised by TestAgentCannotMutateOrders and TestAuntNotificationIsDurable"
  - phase: 03-agent-dependability-safety (03-06, wave 4)
    provides: "tests/eval/ + 03-EVAL-BASELINE.md, referenced (not restated) from ALYASMEEN/wiki/agent-safety.md"
provides:
  - "tests/unit/test_phase3_requirements.py — 12 executable tests proving REQ-bot-aunt-notification, REQ-sched-followup, REQ-sched-retry-queue (all satisfied structurally by Phase 4) and success criterion 4 (agent cannot mutate order status) cannot silently regress"
  - "ALYASMEEN/wiki/agent-safety.md — the durable knowledge-vault page Phase 3 shipped 8 plans without ever writing"
  - "CLAUDE.md brought back in line with the code: processor.py-is-the-brain architecture, the outbox-durable aunt notification, the 5-tool policy-gated AI loop, and the retired retry_queue"
affects: [phase-completion, future-phase-planning]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "AST-based source-boundary tests: ast.parse + a function-nesting NodeVisitor to attribute an RPC call to its enclosing function, rather than a plain string grep — avoids false positives on legitimate prose/comments (policy.py's own docstring discusses create_order_atomic without calling it) while still catching a real regression."
    - "Requirements-traceability test file as its own artifact, separate from the tests that shipped the behavior — makes 'satisfied structurally, not by new code' an asserted fact instead of a one-time August-2026 research claim."

key-files:
  created:
    - tests/unit/test_phase3_requirements.py
    - ALYASMEEN/wiki/agent-safety.md
  modified:
    - ALYASMEEN/wiki/index.md
    - ALYASMEEN/wiki/log.md
    - CLAUDE.md
    - .planning/STATE.md
    - .planning/ROADMAP.md

key-decisions:
  - "Deviated from the plan's literal task-2 wording, which listed 'the paused gate' as one of 'the five handoff triggers': the paused gate does not open a handoff, it silences the bot once one is already active. The wiki page documents the real five trigger reason codes (keyword_request/unsupported_media/ai_failure/ai_requested/policy_denied) plus the paused gate as a separate, complementary mechanism — verified against 03-05-SUMMARY.md's own more precise language and the code, not copied from the plan's task description."
  - "test_ai_tool_surface_has_no_order_mutating_tool checks tool NAMES against an exact forbidden-name set (not a bare substring match) because get_order_status legitimately contains the substring 'status' in its own name while being a read-only tool — mirrors the existing convention in tests/unit/test_ai_service.py::test_no_tool_can_mutate_order_status."
  - "The order-creation-boundary test does not touch app/routers/debug.py (which also legitimately calls create_order_atomic, for the /dev/test_order seed endpoint) — the plan's boundary is specifically 'not from ai_service.py, policy.py, or any other processor.py function', not a blanket ban on the whole app/ tree."

# Metrics
duration: ~30min
completed: 2026-08-28
---

# Phase 3 Plan 08: Requirement Verification Tests + Knowledge Vault Summary

**Converted three "verified once in research" Phase 3 requirements and success criterion 4 into 12 regression-tested assertions (including two AST-based source-boundary guards), wrote the agent-safety knowledge-vault page Phase 3 never had, and corrected CLAUDE.md's architecture description back to what the code actually does — closing out Phase 3 at 8/8 plans.**

## Performance

- **Duration:** ~30 min
- **Completed:** 2026-08-28
- **Tasks:** 3 completed
- **Files modified:** 6 (2 created, 4 modified)

## Accomplishments
- `tests/unit/test_phase3_requirements.py` (12 tests, 4 classes): `TestAuntNotificationIsDurable` proves the aunt's new-order alert is an `outbox_jobs` row that exists *before* any send is attempted, carries the order number and total, and survives even if the aunt's own `queue_text` call fails. `TestFollowupsAreDurable` proves `followup.send_followups()` enqueues through `queue_text` and never calls `send_text` directly, and that the `followup` job is actually registered in `app.worker.start_worker`. `TestRetryQueueIsRetired` proves `app.services.retry_queue`/`retry_actions` no longer import, `"retry"` is absent from `worker.py`, and the outbox poller (cross-referenced to `test_processor.py`'s deeper coverage, not duplicated) is the replacement mechanism. `TestAgentCannotMutateOrders` pins success criterion 4 at three independent layers: the AI tool surface (exact-name/exact-property checks, not a substring match that would false-positive on `get_order_status`'s own name), `policy.TOOL_SCOPES` covering every tool, and two AST-parsed source-boundary guards proving `UPDATE orders SET status` exists only in `ui_api.py` and `create_order_atomic` is called only from `processor._handle_confirm`.
- `ALYASMEEN/wiki/agent-safety.md` (new, ~210 lines): the vault page for `policy.py`, `handoff.py`, and the message-pipeline integration Phase 3 built across 8 plans without ever documenting. Every claim carries a `(source: file:line)` citation verified against the code this session. Explicitly flags `whatsapp-bot-brain.md`/`ai-service.md` as stale rather than silently propagating their pre-hardening claims. Linked from `index.md`; logged in `log.md`.
- `CLAUDE.md`: Project Structure tree, "How the Bot Works" diagram, the aunt-notification paragraph, Database Tables, and Key Rules all corrected to describe `processor.py`/`policy.py`/`handoff.py`/`audit.py`/`tests/eval/` instead of the pre-2026-08-25 `whatsapp.py`-is-the-brain architecture.

## Task Commits

Each task was committed atomically:

1. **Task 1: tests/unit/test_phase3_requirements.py** - `ab52c6c` (test)
2. **Task 2: Knowledge vault page + index + log** - `d23ebe9` (docs)
3. **Task 3: Bring CLAUDE.md in line with what the code actually does** - `ce8e743` (docs)

**Plan metadata:** _(this commit)_

## Files Created/Modified
- `tests/unit/test_phase3_requirements.py` — 12 new tests, 4 classes, requirements-traceability for REQ-bot-aunt-notification/REQ-sched-followup/REQ-sched-retry-queue + success criterion 4
- `ALYASMEEN/wiki/agent-safety.md` — new durable knowledge-vault page (policy gate, handoff triggers/lifecycle, order-mutation boundary, eval-gate pointer)
- `ALYASMEEN/wiki/index.md` — added `[[agent-safety]]` to the Concept pages list, bumped Last updated
- `ALYASMEEN/wiki/log.md` — appended the change entry, including the plan-task correction noted above
- `CLAUDE.md` — Project Structure, How the Bot Works, aunt notification, Database Tables, Scheduler, Key Rules, Still To Do, Tech Stack, Done list all corrected

## Decisions Made
See `key-decisions` in the frontmatter above — summarized: (1) documented the real five handoff *trigger* reason codes separately from the paused gate rather than propagating the plan task's looser phrasing; (2) used exact-match (not substring) checks for the "no order-mutating tool" test to avoid a false positive on `get_order_status`; (3) scoped the order-creation-boundary test to exactly what the plan specifies (`ai_service.py`/`policy.py`/other `processor.py` functions), not the whole `app/` tree, since `app/routers/debug.py`'s dev-only `/dev/test_order` seed also legitimately calls the same RPC.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Three more stale retry_queue/main.py-scheduler references found while editing CLAUDE.md**
- **Found during:** Task 3
- **Issue:** Beyond the Database Tables table the plan explicitly named, the "Done ✅" bullet, the "Tech Stack" line, and the entire "Scheduler (main.py)" section still described a live `retry_queue.process_retries` job and attributed the scheduler to `app/main.py` — both false since Phase 4 (the scheduler has lived in `app/worker.py`'s own Railway worker process since before this phase; `retry_queue` was retired in Phase 4). These directly contradicted the corrected sections Task 3 was already producing.
- **Fix:** Rewrote the "Scheduler" section to describe `app/worker.py`'s real 4 jobs (`followup`, `monthly_report`, `webhook_processor`, `outbox_processor`) and its own Railway `worker` process (verified against `Procfile`); corrected the two one-line references.
- **Files modified:** CLAUDE.md
- **Verification:** `grep -n "retry_queue" CLAUDE.md` shows only the retirement note in Database Tables and the "no retry_queue job" line in Scheduler; full suite still green.
- **Committed in:** ce8e743 (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 bug — stale documentation directly contradicting the sections being corrected in the same task). **Impact:** None on code; improves documentation accuracy consistent with Task 3's own stated goal. No scope creep — same file, same task, same root cause as the plan's own listed items.

## Issues Encountered
None. All three tasks' `<verify>` commands passed (one test assertion needed a fix mid-task 1: the initial literal-substring check for `create_order_atomic` in `policy.py` false-positived on the module's own docstring prose explaining why the RPC is *not* called there — switched to the same AST-based call-detection helper already used for the processor.py boundary, which correctly ignores comments/docstrings and only flags actual `rpc(...)` call nodes).

A sibling agent executed plan 03-07 concurrently in the same working directory (owning `tests/eval/test_agent_eval.py` and `docs/EVAL_GATE.md`) — coordinated via explicit git pathspecs on every commit; no file conflicts, no shared-index races. `.planning/STATE.md` and `.planning/ROADMAP.md` were re-read immediately before this plan's own edits to build on the sibling's already-committed 03-07 completion rather than overwrite it.

## User Setup Required
None — no external service configuration required.

## Next Phase Readiness
**Phase 3 (Agent Dependability & Safety) is now fully COMPLETE — 8/8 plans.** All four success criteria are met and test-covered: (1) policy gate runs before every tool dispatch (03-05, structurally + `test_policy.py`); (2) risky/uncertain messages trigger a durable handoff (03-01/03-04/03-05, five reason codes); (3) the eval gate measures against a real baseline and enforces regression thresholds (03-06/03-07); (4) the agent cannot mutate an order past `to_do` — now pinned at the tool, policy, and source-boundary layers by this plan.

Only Phase 5's `05-10` (human-gated live rollout checkpoint) remains project-wide before a milestone-level review. No blockers found during this plan's execution.

---
*Phase: 03-agent-dependability-safety*
*Completed: 2026-08-28*

## Self-Check: PASSED

- FOUND: tests/unit/test_phase3_requirements.py
- FOUND: ALYASMEEN/wiki/agent-safety.md
- FOUND: ALYASMEEN/wiki/index.md ([[agent-safety]] link present)
- FOUND: ALYASMEEN/wiki/log.md (entry present)
- FOUND: CLAUDE.md (policy.py/tests/eval/processor.py present; retry_queue described as retired)
- FOUND commit ab52c6c (Task 1: test(03-08))
- FOUND commit d23ebe9 (Task 2: docs(03-08))
- FOUND commit ce8e743 (Task 3: docs(03-08))
- Full suite: 483 passed, 3 skipped, 1 deselected
- `ALYASMEEN/graph/`/`ALYASMEEN/raw/` confirmed untouched (`git diff --stat` empty)
