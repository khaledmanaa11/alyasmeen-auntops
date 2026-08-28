---
phase: 03-agent-dependability-safety
plan: 01
subsystem: agent-safety
tags: [handoff, outbox, audit, whatsapp, supabase]

# Dependency graph
requires:
  - phase: 05-operator-security-ux
    provides: "handoff.py's resolve()/active_count()/bot_recently_active(), audit.py's log_action()/OPERATOR_ACTIONS allowlist, the /audit page and _nav.html badge, processor.py's queue_text() durable outbox and notify_permanent_failure() loop-guard pattern"
provides:
  - "handoff.trigger(phone, reason, metadata=None, assigned_to='aunt', notify=True) -> str — the producer half of the handoff system; every future handoff call site (03-04 media/keyword, 03-05 AI-failure/tool-escalation) calls this one function"
  - "REASON_LABELS — the 6 caller reason codes (keyword_request, unsupported_media, ai_failure, ai_requested, policy_denied, operator_takeover) mapped to plain-Arabic sentences"
  - "handoff_triggered in audit.OPERATOR_ACTIONS + a readable /audit page sentence"
affects: [03-04-media-and-keyword-handoff, 03-05-ai-failure-and-escalation-tool]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Idempotent producer function: SELECT-before-INSERT on (phone, status='active'), self-healing the session pause on repeat calls instead of opening a second row"
    - "UPSERT (INSERT ... ON CONFLICT DO UPDATE) instead of bare UPDATE when the target row's existence cannot be guaranteed by call order"
    - "Two-tier error contract inside one function: durable state (INSERT/UPSERT) is allowed to raise; audit + notification are wrapped in try/except and log a warning instead"

key-files:
  created:
    - tests/unit/test_handoff_trigger.py
  modified:
    - app/services/handoff.py
    - app/services/audit.py
    - app/templates/audit.html
    - tests/unit/test_audit.py

key-decisions:
  - "trigger()'s idempotent-repeat path re-asserts the session pause (self-heal) but issues no second INSERT, no second audit.log_action call, and no second notification — only a structlog log.info('handoff_already_active', ...), so the audit trail shows exactly one handoff_triggered row per real escalation."
  - "_pause_session() upserts sessions.paused=TRUE (INSERT ... ON CONFLICT DO UPDATE) rather than reusing resolve()'s bare UPDATE, because trigger() can be reached (via a future unsupported-media handoff) before save_session() has ever written a sessions row for a brand-new customer."
  - "_notify_aunt() is a private module function, not part of the public trigger() contract, modeled 1:1 on processor.notify_permanent_failure(): same loop guard (never alert AUNT_PHONE/ADMIN_PHONE about themselves), same queue_text()-only send path, same try/except-everything shape."

patterns-established:
  - "Any module adding a new kind of audit row must add the action string to audit.OPERATOR_ACTIONS (app/services/audit.py) AND a case in audit.html's describe() switch, or the /audit page silently omits/mis-renders it — reconfirmed load-bearing here exactly as STATE.md already flagged."

# Metrics
duration: 30min
completed: 2026-08-28
---

# Phase 3 Plan 01: Handoff Trigger Summary

**`handoff.trigger()` — the missing producer half of the Phase-5 handoff system — now durably opens an idempotent handoff, upserts `sessions.paused`, and WhatsApps the aunt through the outbox, all wired into the existing `/audit` trail.**

## Performance

- **Duration:** ~30 min
- **Completed:** 2026-08-28T18:33:39Z
- **Tasks:** 3 completed
- **Files modified:** 4 (1 created, 3 modified)

## Accomplishments
- `app/services/handoff.py` gained `trigger(phone, reason, metadata=None, assigned_to="aunt", notify=True) -> str` — the entry point the module's own docstring had explicitly refused to implement since Phase 5, now built exactly on `resolve()`'s established query/execute/audit pattern.
- Idempotency: a second `trigger()` call for a phone with an already-active handoff self-heals the session pause but opens no second row, writes no second audit entry, and sends no second WhatsApp alert — the only thing standing between a customer's five angry messages and an alert storm in the aunt's inbox.
- `sessions.paused` is set via an UPSERT (`INSERT ... ON CONFLICT (phone) DO UPDATE`), not a bare `UPDATE` — correct even for a brand-new customer whose very first message is unsupported media and who has no `sessions` row yet.
- The aunt is notified through the durable outbox (`processor.queue_text`, never a direct send), loop-guarded against `AUNT_PHONE`/`ADMIN_PHONE`, modeled directly on `processor.notify_permanent_failure()`.
- `handoff_triggered` added to `audit.OPERATOR_ACTIONS` and rendered as a plain-Arabic sentence on the existing `/audit` page — without this the write would have silently vanished from the operator trail (the exact trap STATE.md already flagged).

## Task Commits

Each task was committed atomically:

1. **Task 1: handoff.trigger() — durable handoff creation + session pause** - `c4790dc` (feat)
2. **Task 2: Aunt notification through the outbox + handoff_triggered in the audit trail** - `aa67faa` (feat)
3. **Task 3: Unit tests for trigger()** - `3cf7696` (test) + `d782978` (docs — deferred-items note)

_Note: Task 1's first commit attempt (`81f251d`) accidentally swept a concurrent sibling plan's unstaged `policy.py` changes into the same commit due to a staging race (both agents share this working directory); it was immediately undone with `git reset --soft HEAD~1` + selective unstage and recommitted as `c4790dc` containing only `app/services/handoff.py`. No sibling work was lost — see Deviations below._

## Files Created/Modified
- `app/services/handoff.py` — added `trigger()`, `_pause_session()`, `_notify_aunt()`, `REASON_LABELS`; rewrote the module docstring (trigger() is no longer a Phase-3 stub); import line now also brings in `execute_returning` and `Config`
- `app/services/audit.py` — added `"handoff_triggered"` to `OPERATOR_ACTIONS`
- `app/templates/audit.html` — added a `handoff_triggered` case to the `describe(entry)` switch
- `tests/unit/test_handoff_trigger.py` — new, 7 tests, local `FakeHandoffDB` + `queued`/`fake_handoff_db` fixtures
- `tests/unit/test_audit.py` — `OPERATOR_ACTIONS` exact-count assertion updated 19 → 20 and renamed (mechanical consequence of Task 2, in-scope since `audit.py` belongs to this plan)

## Interface for downstream plans (03-04, 03-05 — verbatim)

```python
def trigger(phone: str, reason: str, metadata: dict | None = None,
            assigned_to: str = "aunt", notify: bool = True) -> str:
    """Returns the handoff id (existing or newly created)."""
```

`REASON_LABELS` keys (the only valid `reason` values — anything else is
rendered raw via `.get(reason, reason)` rather than rejected):
`keyword_request`, `unsupported_media`, `ai_failure`, `ai_requested`,
`policy_denied`, `operator_takeover`.

**Error contract (verbatim, load-bearing for 03-04/03-05):**
- Steps 1-3 (idempotency SELECT, the `handoffs` INSERT, the `sessions.paused`
  UPSERT) are **allowed to raise**. `app/db/database.py` already
  retries/circuit-breaks these calls; callers in the message pipeline must
  wrap `trigger()` itself so the customer still gets a reply if the durable
  write fails.
- Steps 4-5 (the `audit.log_action` call, `_notify_aunt`) are **best-effort**
  and never raise past `trigger()` — a failing notification or audit write
  never undoes an already-successful handoff.

`handoffs.phone` has a live FK to `customers(phone)` — every caller must
have already called `upsert_customer()` (or equivalent) before calling
`trigger()`.

## Decisions Made
- Idempotent-repeat path logs `handoff_already_active` via `structlog`
  (`log.info`), not a second `audit.log_action` call — the plan's "no second
  audit entry" instruction was read as governing the durable audit trail
  specifically, not internal diagnostic logging. Verified by
  `test_writes_handoff_triggered_audit_action` asserting exactly one
  `log_action` call for two `trigger()` invocations in
  `test_second_trigger_for_same_phone_reuses_active_handoff`.
- `_notify_aunt`'s message format is `f"🙋 {reason_label} — {name_label}\n..."`
  (reason first, customer name second) — matches the plan's literal
  `{label} — {label_name}` template where `label` = `REASON_LABELS.get(reason, reason)`
  and `label_name` = customer name or phone fallback.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed a staging race that swept a sibling plan's unstaged changes into Task 1's first commit**
- **Found during:** Task 1 commit
- **Issue:** `git commit -m "..."` with no pathspec commits everything currently staged, not just what this agent explicitly `git add`ed. A concurrent sibling agent (03-02) staged its own `app/services/policy.py` changes between this agent's `git add app/services/handoff.py` and `git commit` calls, in the same shared working directory — the resulting commit (`81f251d`) contained both files.
- **Fix:** `git reset --soft HEAD~1` (undo the commit, keep everything staged) → `git reset HEAD -- app/services/policy.py` (unstage only the sibling's file, restoring its pre-race unstaged working-tree state) → recommit with an explicit `-- app/services/handoff.py` pathspec. All subsequent commits in this plan used explicit pathspecs to prevent recurrence.
- **Files modified:** none beyond the intended `app/services/handoff.py` — `policy.py`'s content was never altered, only its staged/unstaged git state was restored.
- **Verification:** `git show --stat HEAD` after the fix shows only `app/services/handoff.py`; sibling's `policy.py` changes were later committed intact by 03-02 itself (`15eb191`, `7f0609c`).
- **Committed in:** `c4790dc` (the corrected Task 1 commit)

**2. [Rule 1 - Bug] Updated a stale exact-count assertion in test_audit.py**
- **Found during:** Task 3 verification (`pytest tests/unit/test_handoff_trigger.py tests/unit/test_handoff_resolve.py tests/unit/test_audit.py -q`)
- **Issue:** `test_operator_actions_has_nineteen_entries` hardcoded `len(audit.OPERATOR_ACTIONS) == 19` — a direct, mechanical consequence of Task 2 adding `"handoff_triggered"` to that same tuple in `audit.py`, a file this plan owns.
- **Fix:** Renamed to `test_operator_actions_has_twenty_entries`, updated the assertion to 20, updated the inline comment.
- **Files modified:** `tests/unit/test_audit.py`
- **Verification:** `pytest tests/unit/test_audit.py -q` passes; full suite green.
- **Committed in:** `3cf7696`

---

**Total deviations:** 2 auto-fixed (1 blocking/git-hygiene, 1 bug/stale test assertion)
**Impact on plan:** Both fixes were mechanical consequences of the plan's own intended changes (a shared-workspace commit hygiene issue and a hardcoded count in a file this plan owns). No scope creep — neither touched a sibling-owned file's content.

## Issues Encountered
- **Full-suite pollution, not caused by this plan, discovered during Task 3 verification:** a first `pytest -q` run showed 5 failures in `tests/unit/test_database.py::TestQueryAndExecute::*` (`RuntimeError: Supabase circuit open`). Isolated via `pytest -q --ignore=tests/unit/test_ai_service.py` (406 passed, 3 skipped — fully green) that the cause was sibling plan 03-03's then-in-progress, uncommitted `test_ai_service.py` tripping `app/db/database.py`'s module-global circuit breaker, which leaked into whichever file ran next in the same pytest process — the identical class of issue 03-02 had already logged in `deferred-items.md` for a different sibling file. Logged an update to `deferred-items.md` (commit `d782978`) documenting the isolation rather than fixing `test_ai_service.py` (out of this plan's `files_modified`). **Resolved independently by 03-03 later in the same session** (root-caused to an unmocked `app.ai.retriever` catalog call in `test_ai_service.py`, fixed with a file-scoped autouse fixture — see `deferred-items.md`'s "Resolved by 03-03" entry and `03-03-SUMMARY.md`). Final full-suite run after all sibling plans landed: **431 passed, 3 skipped** — fully green, no reduction from the plan's declared 353-passed baseline (which predates 03-02/03-03's own new tests).

## User Setup Required
None — no external service configuration required.

## Next Phase Readiness
- `handoff.trigger()` is ready for 03-04 (media/keyword handoff call sites) and 03-05 (AI-failure/tool-escalation call sites) to call verbatim per the interface recorded above.
- `REASON_LABELS` already includes `policy_denied` and `ai_requested`, anticipating 03-02's `detect_handoff_keyword()` (already landed, `15eb191`) and 03-03's new `request_human_handoff` tool (already landed, `934d08f`) as callers — neither has been wired to call `trigger()` yet as of this plan; that wiring is 03-04/03-05's job, not this plan's.
- No blockers. The one open cross-cutting item (no autouse circuit-breaker reset fixture in `tests/conftest.py`) is tracked in `deferred-items.md`, not blocking, and outside this plan's file ownership.

---
*Phase: 03-agent-dependability-safety*
*Completed: 2026-08-28*

## Self-Check: PASSED

All key files found on disk (`app/services/handoff.py`, `app/services/audit.py`,
`app/templates/audit.html`, `tests/unit/test_handoff_trigger.py`, this
SUMMARY.md). All 4 commits (`c4790dc`, `aa67faa`, `3cf7696`, `d782978`) found
in `git log`.
