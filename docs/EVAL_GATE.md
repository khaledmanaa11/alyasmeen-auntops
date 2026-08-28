# Agent Eval — Release Gate

**Date:** 2026-08-28
**Status:** Live. `RUN_AGENT_EVAL=1 pytest -m eval tests/eval` is a documented human step run
before a release — there is no CI in this repo (no `.github/` at all) and this plan
deliberately did not invent one just to host this gate.

This is the same practical register as `docs/BACKUP_DRILL.md` — written for Khaled to run
before shipping a change, not for a pipeline to run automatically.

---

## 1. What this gate checks

`tests/eval/test_agent_eval.py::test_agent_eval` drives the **real** `handle_message()` /
`process_event()` pipeline in `app/services/processor.py` — the exact code path a customer's
WhatsApp message goes through in production — over the 75-case labeled Arabic/English/Hebrew/
Arabizi dataset (`tests/data/whatsapp_agent_dataset.json`). For each case it records:

- which of the 5 AI tools fired (`add_to_cart`, `show_menu`, `get_order_status`,
  `save_address`, `request_human_handoff`), or none
- whether a `handoffs` row was opened (any of the 5 triggers: keyword, unsupported media,
  policy denial, the AI's own tool, or an AI-failure escalation)
- whether the customer got a non-empty reply at all

...and scores it against the hand-curated expected outcome in `tests/eval/expected_behavior.py`.
The database is faked (`tests/conftest.py`'s `mock_db` + `block_live_db` — zero live-DB
exposure) but Claude is real: `generate_reply()` is never patched, so every sampled case is a
genuine Anthropic API call through `app.shared.gatekeeper`.

**This is NOT `tests/data/eval_intent.py`.** That script is a different tool measuring a
different thing: it asks Claude to *classify intent* from noise-corrupted message text as a
standalone side-channel prompt, disconnected from the actual bot pipeline — no tools, no
handoffs, no cart, no real code path. It is useful for a different question ("how robust is
intent classification to typos/noise") but it is **not** a release gate and running it proves
nothing about whether `handle_message()` itself still behaves correctly. If you're looking for
"does the bot still work before I ship this," this file — not `eval_intent.py` — is the answer.

---

## 2. When to run it

Run before any release that touches:

- `app/services/ai_service.py` (system prompt, tool definitions, `generate_reply()`)
- `app/services/processor.py` (`handle_message`, `process_event`, the tool executor)
- `app/services/policy.py` (the tool-call gate)
- `app/services/handoff.py` (escalation triggers)
- `Config.CLAUDE_MODEL` (a model bump)

**Not needed** for template/CSS/dashboard-only changes, migrations, or anything that doesn't
touch the WhatsApp conversation path.

---

## 3. The command

Costs real money — a routine sampled run is pennies, a full run is well under $0.10. Guarded
by both a pytest marker (`eval`, excluded from `pyproject.toml`'s default `addopts`) and an
env var (`RUN_AGENT_EVAL=1`) so `pytest -q` never runs it and nobody spends API money by typing
the wrong flag.

**Bash / Git Bash:**
```bash
# Routine pre-release smoke check — 12-case stratified sample, ~20 Claude calls, ~$0.01-0.02
RUN_AGENT_EVAL=1 pytest -m eval tests/eval -q -s

# Full 74-case run — before a big release, or to establish/refresh the baseline
RUN_AGENT_EVAL=1 EVAL_SAMPLES=all pytest -m eval tests/eval -q -s
```

**PowerShell** (this project is developed on Windows):
```powershell
$env:RUN_AGENT_EVAL=1; pytest -m eval tests/eval -q -s
$env:RUN_AGENT_EVAL=1; $env:EVAL_SAMPLES="all"; pytest -m eval tests/eval -q -s
```

**Windows console note:** if you see a `UnicodeEncodeError` under `-s` (pytest's capture is
disabled so structlog writes Arabic straight to the real console), set
`PYTHONIOENCODING=utf-8` (bash) / `$env:PYTHONIOENCODING="utf-8"` (PowerShell) first. This is a
Windows console-codepage quirk (cp1255 on this sandbox), not a code issue, and won't affect a
normal CI/Linux environment.

---

## 4. Reading the output

Every run prints two blocks under `-s`, win or lose:

1. **Per-case results** — one line per sampled case: id, tier, PASS/FAIL/ERR, expected vs
   observed outcome, elapsed seconds.
2. **The regression gate table** — baseline / measured / tolerance / floor / n / verdict, one
   row for `overall` and one per tier, plus (on any failure) the list of regressed cases with
   their raw customer message, and separately any hard-floor violations (no reply sent) or
   pipeline exceptions.

The three tiers, and why they're graded differently:

| Tier | What it covers | Tolerance | Why |
|---|---|---|---|
| `critical` | The order path: cart, menu selection, fulfillment, address, confirm | 5 pts | A wrong tool choice here directly breaks an order |
| `handoff` | Must-escalate cases: complaints, refunds, damaged items, privacy, wholesale, etc. | 5 pts | A missed escalation means an angry customer talks to a bot instead of Hanan |
| `informational` | FAQ/small-talk/consultative | 15 pts (loosest) | `app/data/knowledge/` is empty in this repo (see main `CLAUDE.md`'s "Still To Do"), so FAQ-ish answers have no grounded source yet — that gap is not this gate's job to enforce |

A tier's row shows `SKIPPED (n=N < 5)` instead of PASS/FAIL when a run sampled fewer than
`MIN_SAMPLE_FOR_TIER_GATE` (5) cases from it — a 12-case default run can draw as few as 1-2
cases from a tier, and a percentage over 1-2 cases is noise, not a signal. It's reported, never
gated.

**One check is absolute, not baseline-relative:** every sampled case must produce a non-empty
reply to the customer. "The customer always gets a reply" is a phase invariant (Phase 3 locked
decision), not something allowed to regress by a tolerance — if this trips, it's always
real, and it fails the run regardless of everything else.

---

## 5. What to do when it fails

Work through this list in order — don't jump straight to re-baselining:

**(a) A real behaviour regression.** The model (or a code change to `processor.py`/
`policy.py`/`handoff.py`) genuinely got worse at something it used to do correctly. **Fix the
code. Do not touch the baseline or the thresholds.** This is the gate doing its job.

**(b) A bad expectation in `tests/eval/expected_behavior.py`.** The map itself was wrong for
this case — re-read the `raw_input` and the tool's own description in `ai_service.py`'s
`_TOOLS`. If the model's behaviour is actually correct/defensible and the map was too narrow
(exactly what happened with case id 20 — "safe during pregnancy?" — during the original 03-06
baseline measurement, see `.planning/phases/03-agent-dependability-safety/03-EVAL-BASELINE.md`'s
"Failure diagnosis" section), fix the map with a written reason in the same commit, and re-run.

**(c) Genuine model drift after a `CLAUDE_MODEL` bump.** If you deliberately changed
`Config.CLAUDE_MODEL` and the new model's baseline behaviour is legitimately different (not
worse, just different), that's a re-baselining case — see section 6.

**(d) Noise on a small sample.** `generate_reply()` runs at `temperature=0.3`, so the exact
same 12 cases can score differently between two runs — this is expected, not a bug. **Before
concluding anything from a 12-case FAIL, re-run with `EVAL_SAMPLES=all`.** This is not
theoretical: during this plan's own verification, two consecutive real
`RUN_AGENT_EVAL=1 EVAL_SAMPLES=12` runs against an unmodified codebase both failed the overall
gate (75.0% and 66.7%, against a 77.1% floor) purely from small-sample variance — the fixed
seed (`DEFAULT_SEED`) happens to always draw 2 of the dataset's known baseline-failing cases
(ids 31, 55 — see the baseline doc) into every 12-case sample, on top of ordinary model
variance on 1-2 other cases per run. **A red 12-case smoke run is a prompt to re-run the full
74, not an automatic release blocker on its own.**

---

## 6. Re-baselining

Do this **only** after ruling out (a) and (b) above — re-baselining downward must be a
deliberate, reviewable decision, never a reflex to make a red gate green.

1. Run the full dataset: `RUN_AGENT_EVAL=1 EVAL_SAMPLES=all pytest -m eval tests/eval -q -s`
   (needs `PYTHONIOENCODING=utf-8` on Windows, see section 3).
2. Update `BASELINE_MEASURED_AT` / `BASELINE_SAMPLE_SIZE` / `BASELINE_OVERALL` /
   `BASELINE_BY_TIER` in `tests/eval/test_agent_eval.py` from the new run's output.
3. Update the numbers and the per-case table in
   `.planning/phases/03-agent-dependability-safety/03-EVAL-BASELINE.md` to match.
4. Commit both files together, in one commit, with a message stating **why** the baseline
   changed (which cases moved and the actual cause — model bump, legitimate behaviour change,
   etc.).

**Never quietly widen a `TOLERANCE` entry to make a red gate green.** Lowering a baseline, or
loosening a tolerance, is a decision that must be visible in the diff and explained in the
commit message — not a silent workaround. `tests/eval/test_agent_eval.py::
test_gate_constants_are_consistent` (in the default, always-on suite) only checks the
constants are internally consistent — it does not, and cannot, stop someone from widening a
tolerance on purpose. That responsibility is on whoever reviews the diff.

---

## 7. Known limitations

- **Small dataset.** 75 cases (74 scored; id 54, `opt_out_of_messages`, is deliberately
  `UNSCORED` — there is no consent/suppression mechanism in this codebase to score it against).
  A single flipped case moves the `handoff` tier by ~6 points.
- **No CI.** This repo has no `.github/` directory at all — inventing a pipeline solely to host
  this gate would be a larger change than Phase 3 asked for. The gate is a human pre-release
  step; automating it would belong to a later phase (e.g. go-live/deploy hardening), if ever.
- **The database is faked.** The eval validates agent *behaviour* (tool choice, escalation,
  reply presence), not real Supabase integration — a passing eval says nothing about whether
  `database.py`'s retry/circuit-breaker plumbing, RLS, or live schema are healthy.
- **`informational` scores are capped by an empty `app/data/knowledge/`.** The tier's loose
  15-point tolerance exists because of this pre-existing gap (main `CLAUDE.md`'s "Still To Do"
  list), not because informational mistakes don't matter.
- **Content correctness is not graded**, only *which tool was called* (or none). A `no_tool`
  reply that states a wrong delivery price would still score PASS — this gate catches tool-call
  and escalation regressions, not hallucinated facts.
- **`EVAL_CATALOG` (`tests/eval/conftest.py`) is synthetic** — 8 hand-written products, not the
  real production catalog. Fuzzy product-name matching may behave differently against the real
  catalog once it's populated (see main `CLAUDE.md`'s "Add real products" TODO).

---

*Phase: 03-agent-dependability-safety*
*Plan: 03-07*
