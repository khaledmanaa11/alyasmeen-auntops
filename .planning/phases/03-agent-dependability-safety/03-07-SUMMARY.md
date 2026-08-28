---
phase: 03-agent-dependability-safety
plan: 07
subsystem: evaluation
tags: [eval-gate, regression-gate, pytest, release-process]

# Dependency graph
requires:
  - phase: 03-agent-dependability-safety (03-06)
    provides: "tests/eval/ real-pipeline eval harness + the measured baseline (85.1%/75.0%/68.8%/100.0%) this plan gates against"
provides:
  - "A pytest regression gate: tests/eval/test_agent_eval.py::test_agent_eval now fails when overall or per-tier accuracy drops below baseline-minus-tolerance, or when any sampled case gets no reply, or when any case raises an exception"
  - "tests/eval/test_agent_eval.py::test_gate_constants_are_consistent — default-suite, API-free, keeps TOLERANCE/BASELINE_BY_TIER from drifting apart silently"
  - "docs/EVAL_GATE.md — the documented pre-release procedure a human runs before shipping (command, tier meanings, failure playbook, re-baselining rule, known limitations)"
affects: [03-08]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Report-before-assert: the per-tier regression table is built and printed unconditionally (visible on PASS too, under -s), then reused verbatim as the pytest.fail() message on FAIL — no bare 'assert 0.71 >= 0.79'"
    - "Tier-level gating has a minimum-sample guard (MIN_SAMPLE_FOR_TIER_GATE=5): a tier sampled below that count is reported, never gated — a 12-case default run can draw 1-2 cases from a tier, which is noise not signal"
    - "One absolute (non-baseline-relative) invariant inside an otherwise relative gate: every sampled case must produce a non-empty customer reply, checked unconditionally regardless of TOLERANCE"

key-files:
  created:
    - docs/EVAL_GATE.md
  modified:
    - tests/eval/test_agent_eval.py
    - tests/eval/conftest.py

key-decisions:
  - "TOLERANCE values (critical 0.05, handoff 0.05, informational 0.15, overall 0.08) and MIN_SAMPLE_FOR_TIER_GATE=5 implemented exactly as specified in the plan's <action> block — not adjusted, even after real runs showed them producing a false-alarm-prone 12-case smoke gate (see Deviations); changing them would be inventing a threshold, which both the plan and the orchestrator's brief explicitly forbid"
  - "tests/eval/conftest.py's autouse _eval_guard fixture was skipping every test in the directory, not just eval-marked ones — scoped it to request.node.get_closest_marker('eval') so the plan's required default-suite, unmarked, API-free test_gate_constants_are_consistent actually runs under plain pytest -q instead of being silently skipped"
  - "No CI workflow invented (no .github/ exists) — docs/EVAL_GATE.md documents a human-run command only, per the plan's explicit scope boundary"

# Metrics
duration: ~30min
completed: 2026-08-28
---

# Phase 3 Plan 07: Eval Regression Gate + Release Procedure Summary

**`test_agent_eval` now exits non-zero on any tier/overall regression below the measured 03-06 baseline minus tolerance, on any customer left without a reply, or on any pipeline exception — with a printed per-tier table and per-case regression list as the failure message, not a bare assertion; `docs/EVAL_GATE.md` is the documented human pre-release command.**

## Performance

- **Duration:** ~30 min
- **Completed:** 2026-08-28T19:51:06Z
- **Tasks:** 2/2
- **Files modified:** 3 (2 modified, 1 created)

## Accomplishments
- `TOLERANCE` dict (critical/handoff 0.05, informational 0.15, overall 0.08) and
  `MIN_SAMPLE_FOR_TIER_GATE=5` added next to the `BASELINE_*` constants; `test_agent_eval` now
  asserts overall accuracy, per-tier accuracy (skipped below the min sample, reported not
  gated), a hard non-negotiable floor that every sampled case produced a non-empty reply, and
  that no case raised an exception.
- Failure reporting is the actual deliverable: `_build_regression_report()` constructs the
  per-tier baseline/measured/tolerance/floor/n/verdict table plus a regressed-case list
  (`id | intent | expected | observed | raw_input`) — built and printed *before* the assertion
  so it's visible on both PASS and FAIL, then reused verbatim as the `pytest.fail()` message.
- `test_gate_constants_are_consistent` (new, unmarked, no fixtures): checks
  `set(TOLERANCE) == set(BASELINE_BY_TIER) | {"overall"}`, every tolerance in `0..0.5`, and
  `BASELINE_MEASURED_AT` is set — runs in every default `pytest -q`.
- `docs/EVAL_GATE.md` (197 lines): what the gate checks (and an explicit contrast with
  `tests/data/eval_intent.py`, which is not the release gate), when to run it, the bash +
  PowerShell commands, how to read the per-tier table, a 4-branch failure playbook, the
  re-baselining procedure (update both `test_agent_eval.py` and `03-EVAL-BASELINE.md` in one
  commit, never quietly widen a tolerance), and known limitations. No CI workflow invented.

## Task Commits

1. **Task 1: Regression thresholds derived from the measured baseline** - `e1d1897` (test)
2. **Task 2: docs/EVAL_GATE.md — the documented pre-release procedure** - `a8c1463` (docs)

**Plan metadata:** (this commit, docs)

## Files Created/Modified
- `tests/eval/test_agent_eval.py` - `TOLERANCE`/`MIN_SAMPLE_FOR_TIER_GATE` constants, the regression assertion block, `_build_regression_report()`, `test_gate_constants_are_consistent`
- `tests/eval/conftest.py` - `_eval_guard` scoped to the `eval` marker instead of the whole directory
- `docs/EVAL_GATE.md` - new; the documented pre-release procedure

## Decisions Made
- Implemented the plan's literal `TOLERANCE`/`MIN_SAMPLE_FOR_TIER_GATE` values verbatim rather
  than tuning them after seeing real-run variance — see Deviations for what that variance
  looked like and why it was documented instead of "fixed."
- Scoped the directory's autouse skip-guard to the `eval` marker (see Deviations) rather than
  moving the new test to a different file — the plan explicitly named
  `tests/eval/test_agent_eval.py` as this task's file.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `tests/eval/conftest.py`'s autouse guard blocked the plan's own required default-suite test**
- **Found during:** Task 1, first `pytest -q` run after adding `test_gate_constants_are_consistent`
- **Issue:** `_eval_guard` (autouse, no marker check) unconditionally `pytest.skip()`s every test collected under `tests/eval/` unless `RUN_AGENT_EVAL=1` — including the new unmarked, API-free `test_gate_constants_are_consistent`, which the plan explicitly requires to run in the default suite ("This keeps the constants from rotting silently and costs nothing"). Without a fix, `pytest -q` would silently skip the very test meant to guard against silent drift.
- **Fix:** Added a `request` param and `if request.node.get_closest_marker("eval") is None: return` guard clause at the top of `_eval_guard`, so only tests actually carrying `@pytest.mark.eval` are gated by `RUN_AGENT_EVAL`/`CLAUDE_API_KEY`.
- **Files modified:** `tests/eval/conftest.py`
- **Verification:** `pytest -q` went from 470→471 passed with the new test actually executing (confirmed via `pytest -q -rs` showing it neither skipped nor deselected); `pytest -m eval` collection unaffected (still 1 deselected under default addopts).
- **Committed in:** `e1d1897` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking).
**Impact on plan:** Necessary for the plan's own explicit requirement (an unmarked, default-suite constants test) to actually function. No scope creep — `conftest.py` isn't owned by the concurrent sibling plan (03-08), confirmed against its `files_modified` list before editing.

## Issues Encountered

**Real-run finding, not a code defect — documented rather than fixed, per the "never invent
thresholds" constraint:** two consecutive real `RUN_AGENT_EVAL=1 EVAL_SAMPLES=12` runs against
an *unmodified* codebase both failed the overall regression gate (9/12 = 75.0%, then 8/12 =
66.7%, against a 77.1% floor). Root-caused, not a bug:

1. The default 12-case sample is deterministic (`_select_case_ids('12', DEFAULT_SEED)` always
   returns `[2, 9, 18, 20, 21, 24, 28, 31, 32, 55, 67, 72]`), and 2 of those 12 IDs (31 —
   `clear_cart`, 55 — `wrong_recipient`) are cases the original 74-case baseline *already*
   scored as failures (see `03-EVAL-BASELINE.md`'s per-case table). Any 12-sample smoke run
   structurally inherits those two misses.
2. On top of that, live-model non-determinism (`temperature=0.3`) added 1-2 additional misses
   per run (id 21 both times, id 18 once) that were NOT baseline failures — genuine sampling
   noise, exactly what `TOLERANCE`'s own docstring anticipates, just larger in practice than an
   8-point overall tolerance absorbs at n=12.

This was **not fixed** by adjusting `TOLERANCE`, `DEFAULT_SEED`, or `MIN_SAMPLE_FOR_TIER_GATE`
— doing so would be exactly the "invented threshold" / "quietly widen a tolerance to make a red
gate green" anti-pattern both the plan and `docs/EVAL_GATE.md` explicitly warn against. Instead
it's documented as a concrete, observed example in `docs/EVAL_GATE.md` section 5(d) ("noise on
a small sample — re-run with `EVAL_SAMPLES=all` before concluding anything"), so a future
Khaled seeing a red 12-case smoke run knows this is expected behavior requiring a full re-run
before concluding a real regression, not a bug to chase.

**Failure path exercised twice**, as the plan's `<verify>` requires:
1. **Organically** — the two real 12-case runs above both failed legitimately, printing the
   full per-tier table and regressed-case list.
2. **Synthetically** — `TOLERANCE["overall"]` was temporarily set to `-1.0` (inflating the
   floor above 1.0, guaranteeing failure), run with `EVAL_SAMPLES=3` (cheapest possible
   stratified sample) to minimize cost, confirmed `pytest.fail` fired with the regressed-case
   list printed, then reverted before committing. `git diff` before the Task 1 commit showed
   only the intended `TOLERANCE["overall"] = 0.08` value in the final state.

## User Setup Required
None. Running the gate is a documented command (`docs/EVAL_GATE.md`), not an env/dashboard
change — `CLAUDE_API_KEY` was already required and configured for 03-06.

## Next Phase Readiness
- Phase 3's eval-gate requirement (REQ-prod-eval-gate) is now fully delivered: a measured
  baseline (03-06) plus an actual regression gate + documented release procedure (03-07).
- `docs/EVAL_GATE.md` section 5(d)'s small-sample-noise note is a real operational finding —
  worth Khaled knowing before the first time he sees a red 12-case smoke run pre-release.
- 03-08 (parallel, disjoint files: `tests/unit/test_phase3_requirements.py`, `ALYASMEEN/wiki/*`,
  `CLAUDE.md`) is Phase 3's remaining plan; this plan did not touch any of its files.

---
*Phase: 03-agent-dependability-safety*
*Completed: 2026-08-28*

## Self-Check: PASSED

- FOUND: docs/EVAL_GATE.md
- FOUND: tests/eval/test_agent_eval.py
- FOUND: .planning/phases/03-agent-dependability-safety/03-07-SUMMARY.md
- FOUND: e1d1897 (Task 1 commit)
- FOUND: a8c1463 (Task 2 commit)
- Default suite: 483 passed, 3 skipped, 1 deselected, eval-free
