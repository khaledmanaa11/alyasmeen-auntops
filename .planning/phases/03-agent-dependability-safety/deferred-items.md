# Deferred Items — Phase 03 (Agent Dependability & Safety)

Out-of-scope discoveries found during plan execution, logged rather than fixed
(per the executor's scope-boundary rule: only fix issues directly caused by
the current task's own changes).

## From 03-02 (policy.py + test_policy.py)

**Full-suite test pollution — global Supabase circuit-breaker state leaks
across test files within one pytest session.**

- Found during: Task 3 (`pytest tests/unit/test_policy.py -q` passed; a
  follow-up full-suite `pytest -q` run showed 6 unrelated failures).
- Symptom: `tests/unit/test_database.py::TestQueryAndExecute::*` (5 tests)
  fail with `RuntimeError: Supabase circuit open — failing fast for N.Ns
  after repeated errors` only when run as part of the full suite; all 27
  tests in that file pass in isolation (`pytest tests/unit/test_database.py -q`).
  `app/db/database.py`'s `_consecutive_failures`/`_circuit_open_until` are
  module-level globals with no autouse reset fixture, so some other test
  file's failure-path exercise (likely a wave-1 sibling plan's new
  failure-simulation tests) trips the breaker and a later, unrelated test
  file inherits the open-circuit cooldown.
- Also failing in the full suite: `tests/unit/test_audit.py::test_operator_actions_has_nineteen_entries`
  (an exact-count assertion on `audit.OPERATOR_ACTIONS` — a concurrent
  sibling plan is adding entries to that allowlist mid-session, so the
  count is a moving target during parallel wave-1 execution, not a policy.py
  regression).
- Verified NOT caused by this plan's changes: `pytest -q --ignore=tests/unit/test_policy.py`
  reproduces the identical 6 failures with `policy.py`/`test_policy.py`
  entirely absent from the collection.
- Not fixed here: `policy.py` is pure (no DB import at all — see the
  module's own verification command), and `test_policy.py` doesn't touch
  `app.db.database` or `app.services.audit`. Neither belongs to this plan's
  `files_modified`.
- Recommendation for whichever plan/session next has ownership of
  `tests/conftest.py` or `app/db/database.py`: add an autouse fixture that
  resets `_consecutive_failures = 0` / `_circuit_open_until = 0.0` between
  tests, and re-run `test_audit.py::test_operator_actions_has_nineteen_entries`
  once all wave-1 `OPERATOR_ACTIONS` additions have landed.

## From 03-01 (handoff.py + audit.py + audit.html + test_handoff_trigger.py)

**Update on the above: `test_audit.py`'s count assertion is fixed; the
circuit-breaker leak is still open and now isolated to `test_ai_service.py`.**

- `audit.py` belongs to this plan (03-01 owns Task 2's `OPERATOR_ACTIONS`
  addition), so the exact-count test was in scope: added `"handoff_triggered"`,
  renamed the test to `test_operator_actions_has_twenty_entries`, asserts 20.
  Confirmed via `pytest tests/unit/test_handoff_trigger.py
  tests/unit/test_handoff_resolve.py tests/unit/test_audit.py -q` — 20/20 pass.
- The circuit-breaker leak (still present, not fixed here — belongs to
  whoever owns `tests/conftest.py`/`app/db/database.py`, per 03-02's note
  above) is, as of this session, reproducible via
  `pytest tests/unit/test_ai_service.py tests/unit/test_database.py -q`
  alone — 03-03's in-progress (uncommitted at the time of this run)
  `test_ai_service.py` changes trip the breaker and leak into
  `test_database.py::TestQueryAndExecute::*` (5 tests). Confirmed NOT caused
  by 03-01's own files: `pytest -q --ignore=tests/unit/test_ai_service.py`
  is fully green — 406 passed, 3 skipped, with `test_handoff_trigger.py` and
  the updated `test_audit.py` both included. Neither `test_ai_service.py`
  nor `ai_service.py` is in this plan's `files_modified`.

## Resolved by 03-03 (ai_service.py + test_ai_service.py)

**The circuit-breaker leak flagged by both 03-01 and 03-02 above is fixed —
root cause was in `test_ai_service.py`, which this plan owns.**

- Root cause: `generate_reply()`'s `_full_catalog_context()` does an
  unmocked `from app.ai.retriever import _catalog; get_catalog()` on every
  call. `app.ai.retriever` is not in conftest's `mock_db` patch list, so in
  every `test_ai_service.py` test that calls `generate_reply()` with a valid
  API key, this hits `block_live_db`'s guard, burns 3 real retry attempts
  (with sleeps) against `app/db/database.py`'s retry logic, and increments
  its process-global `_consecutive_failures`. The plan's own pre-existing 4
  tests already sat at 4/5 of the circuit's default `circuit_threshold`; this
  plan's new tests (which legitimately call `generate_reply()` per its own
  `<action>` spec) pushed the count over the threshold, tripping the circuit
  open for `circuit_cooldown_seconds` and failing whichever unrelated test
  file happened to run next in the same pytest process.
- Fix (Rule 1/3, scoped to `tests/unit/test_ai_service.py` only — no
  production code changed for this): added a file-scoped autouse
  `mock_catalog` fixture that monkeypatches `app.ai.retriever._catalog` to
  return `[]`, so `generate_reply()` never reaches the live-DB guard at all
  in this file's tests.
- Verified: `pytest tests/unit/test_ai_service.py tests/unit/test_database.py -q`
  and the full `pytest -q` are both green (431 passed, 3 skipped) — see
  `03-03-SUMMARY.md`.
- Not touched: `tests/conftest.py` / `app/db/database.py` themselves still
  have no autouse circuit-breaker reset, and any *other* file that calls
  `generate_reply()` (or otherwise reaches an unmocked DB seam) enough times
  in one session could still trip the same shared global. A durable fix
  (reset the breaker in an autouse fixture, or add `app.ai.retriever` to
  conftest's `mock_db` patch list) is still open for whoever next owns
  `tests/conftest.py`.
