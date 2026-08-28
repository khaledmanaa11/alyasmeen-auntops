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
