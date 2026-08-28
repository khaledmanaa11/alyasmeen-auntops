"""
tests/eval/test_agent_eval.py — the pytest-based release-gate eval for REQ-prod-eval-gate.

Drives the REAL `app.services.processor.handle_message()` / `process_event()` pipeline (not a
side classification prompt like `tests/data/eval_intent.py`) over the labeled 75-case dataset
(`tests/data/whatsapp_agent_dataset.json`), scored against the hand-curated behaviour map in
`tests/eval/expected_behavior.py`. The database is faked (`tests/conftest.py`'s `mock_db` +
`block_live_db`) but Claude is real — `generate_reply()` is never patched here, so every
sampled case is a genuine Anthropic API call through `app.shared.gatekeeper`.

Opt-in, twice over (see tests/eval/conftest.py): excluded from every default/accidental pytest
invocation by the `eval` marker (pyproject.toml `addopts`), AND skipped even under an explicit
`pytest -m eval` unless `RUN_AGENT_EVAL=1` and `CLAUDE_API_KEY` are both set.

Usage
-----
    # Bounded, seeded sample (default 12 cases, stratified across all 3 tiers) — a cheap
    # pre-release smoke check, roughly 20 Claude calls (add_to_cart/request_human_handoff
    # cases cost 2 calls each due to the tool-use round trip; most cost 1).
    RUN_AGENT_EVAL=1 pytest -m eval tests/eval -q -s

    # Full dataset (all 74 scored cases; id 54 is deliberately UNSCORED, see
    # expected_behavior.py) — used to establish/refresh the measured baseline in
    # .planning/phases/03-agent-dependability-safety/03-EVAL-BASELINE.md.
    RUN_AGENT_EVAL=1 EVAL_SAMPLES=all pytest -m eval tests/eval -q -s

Cost estimate (Claude Haiku, ~2k-token system prompt incl. the eval catalog)
-----------------------------------------------------------------------------
  12 sampled cases  (default)  ~20 calls  <  $0.01
  74 cases (EVAL_SAMPLES=all)  ~100-120 calls  a few cents

This plan (03-06) asserts nothing beyond "the harness ran and produced a result for every
sampled case" — deliberately. Thresholds are plan 03-07's job: a gate asserting invented
numbers before a real baseline exists would either always pass or block the phase for no
reason. BASELINE_* below are filled in from the actual measured run recorded in
03-EVAL-BASELINE.md; 03-07 reads them from here, not from prose.
"""
from __future__ import annotations

import json
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services import processor
from app.services.ai_service import detect_language
from app.services.config import Config
from tests.conftest import last_handoff
from tests.eval.expected_behavior import EXPECTED, MEDIA_CASE_TYPES, TIER_OF, TIERS

# ---------------------------------------------------------------------------
# Measured baseline — filled in by Task 3 of 03-06-PLAN.md from a real run.
# See .planning/phases/03-agent-dependability-safety/03-EVAL-BASELINE.md for
# the full per-case table and failure diagnosis. Plan 03-07 derives release
# thresholds from these numbers; they are a MEASUREMENT, not a target.
# ---------------------------------------------------------------------------
BASELINE_MEASURED_AT: str | None = None
BASELINE_SAMPLE_SIZE: int | None = None
BASELINE_OVERALL: float | None = None
BASELINE_BY_TIER: dict[str, float] | None = None

DEFAULT_SAMPLES = "12"
DEFAULT_SEED = 20260828

_DATASET_PATH = Path(__file__).resolve().parents[1] / "data" / "whatsapp_agent_dataset.json"
DATASET: list[dict] = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
_CASES_BY_ID: dict[int, dict] = {c["id"]: c for c in DATASET}


# ---------------------------------------------------------------------------
# Sampling — deterministic, stratified across the three tiers so a small
# sample always covers critical and handoff cases, never N greetings.
# ---------------------------------------------------------------------------

def _select_case_ids(samples_spec: str, seed: int) -> list[int]:
    all_ids = sorted(EXPECTED.keys())

    spec = (samples_spec or "").strip().lower()
    if spec in ("0", "all", ""):
        return all_ids

    n = max(1, min(int(spec), len(all_ids)))

    tier_order = ("critical", "handoff", "informational")
    pools = {t: sorted(TIERS[t]) for t in tier_order}
    sizes = {t: len(pools[t]) for t in tier_order}
    total = len(all_ids)

    # Proportional floor allocation, at least 1 per tier once n allows it.
    quota = {t: (n * sizes[t]) // total for t in tier_order}
    if n >= len(tier_order):
        for t in tier_order:
            quota[t] = max(quota[t], 1)
    for t in tier_order:
        quota[t] = min(quota[t], sizes[t])

    # Reconcile rounding drift against n by nudging the largest tiers first.
    diff = n - sum(quota.values())
    order_by_size = sorted(tier_order, key=lambda t: sizes[t], reverse=True)
    i = 0
    while diff != 0 and i < 1000:
        t = order_by_size[i % len(order_by_size)]
        if diff > 0 and quota[t] < sizes[t]:
            quota[t] += 1
            diff -= 1
        elif diff < 0 and quota[t] > 0:
            quota[t] -= 1
            diff += 1
        i += 1

    rng = random.Random(seed)
    selected: list[int] = []
    for t in tier_order:
        selected.extend(rng.sample(pools[t], quota[t]))
    return sorted(selected)


# ---------------------------------------------------------------------------
# Language-match — a reporting metric only, never gating. detect_language()
# only distinguishes ar/en by Unicode range, so Hebrew and Arabizi (Arabic in
# Latin script) cases cannot be graded this way — recorded as None rather
# than forced into a wrong bucket.
# ---------------------------------------------------------------------------

def _language_match(language_profile: str, reply: str) -> bool | None:
    lp = language_profile.lower()
    if "hebrew" in lp or "arabizi" in lp:
        return None
    if "english" in lp:
        expected = "en"
    elif "arabic" in lp:
        expected = "ar"
    else:
        return None
    if not reply:
        return None
    return detect_language(reply) == expected


def _media_payload(media_type: str) -> dict:
    """Minimal Meta webhook payload — handle_unsupported_media() only reads msg_type."""
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "contacts": [{"profile": {"name": "زبونة"}}],
                    "messages": [{"type": media_type}],
                }
            }]
        }]
    }


def _last_reply(sent_messages: list[dict], phone: str) -> str:
    for entry in reversed(sent_messages):
        if entry.get("to") == phone:
            return entry.get("text") or ""
    return ""


# ---------------------------------------------------------------------------
# One case, one fresh phone, one real pipeline run.
# ---------------------------------------------------------------------------

def run_case(case: dict, fake_db, sent_messages: list, flush_outbox, monkeypatch) -> dict:
    case_id = case["id"]
    # Deterministic and unique per case within one run — no cross-case
    # session/handoff bleed, no dependency on the sampling RNG's state.
    phone = f"972599{case_id:06d}"

    calls: list[tuple[str, dict]] = []
    real_factory = processor._make_tool_executor

    def _capturing_factory(phone_arg, st, cart):
        executor = real_factory(phone_arg, st, cart)

        def _wrapped(name: str, args: dict) -> str:
            calls.append((name, dict(args)))
            return executor(name, args)

        return _wrapped

    monkeypatch.setattr(processor, "_make_tool_executor", _capturing_factory)

    media_type = MEDIA_CASE_TYPES.get(case_id)
    error: str | None = None
    start = time.monotonic()
    try:
        if media_type:
            processor.process_event(f"eval-case-{case_id}", phone, _media_payload(media_type))
        else:
            processor.handle_message(phone, case["raw_input"], "زبونة")
    except Exception as exc:  # noqa: BLE001 — one exploding case must not abort the run
        error = f"{type(exc).__name__}: {exc}"
    elapsed = time.monotonic() - start

    try:
        flush_outbox()
    except Exception as exc:  # noqa: BLE001
        error = error or f"flush_outbox failed: {type(exc).__name__}: {exc}"

    reply = _last_reply(sent_messages, phone)
    observed_handoff = last_handoff(fake_db, phone) is not None

    if observed_handoff:
        observed = "handoff"
    elif calls:
        observed = calls[-1][0]
    else:
        observed = "no_tool"

    expected = EXPECTED.get(case_id, frozenset())
    return {
        "id": case_id,
        "intent": case["expected_intent"],
        "tier": TIER_OF.get(case_id, "unscored"),
        "expected": sorted(expected),
        "observed": observed,
        "passed": (observed in expected) if expected else None,
        "reply_nonempty": bool(reply),
        "reply": reply,
        "language_match": _language_match(case["language_profile"], reply),
        "tool_calls": [{"name": n, "args": a} for n, a in calls],
        "elapsed_sec": round(elapsed, 3),
        "error": error,
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _print_report(results: list[dict]) -> None:
    total = len(results)
    total_pass = sum(1 for r in results if r["passed"])
    print("\n" + "=" * 78)
    print("  ALYASMEEN agent eval — real handle_message()/process_event() pipeline")
    print("=" * 78)
    if total:
        print(f"Overall: {total_pass}/{total} ({100 * total_pass / total:.1f}%)")
    else:
        print("Overall: n=0")

    by_tier: dict[str, list[dict]] = {}
    for r in results:
        by_tier.setdefault(r["tier"], []).append(r)
    for tier in ("critical", "handoff", "informational"):
        rows = by_tier.get(tier, [])
        if not rows:
            continue
        p = sum(1 for r in rows if r["passed"])
        print(f"  {tier:14s} {p:3d}/{len(rows):<3d} ({100 * p / len(rows):5.1f}%)")

    print("-" * 78)
    for r in sorted(results, key=lambda r: r["id"]):
        status = "OK " if r["passed"] else ("ERR" if r["error"] else "X  ")
        exp = "|".join(r["expected"]) or "-"
        print(
            f"  [{r['id']:2d}] {status} {r['tier']:14s} "
            f"exp={exp:<28s} got={r['observed']:<16s} {r['elapsed_sec']}s"
        )
    print("=" * 78 + "\n")


def _write_last_run(results: list[dict]) -> None:
    out_path = Path(__file__).parent / ".last_run.json"
    payload = {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "model": Config.CLAUDE_MODEL,
        "sample_size": len(results),
        "results": results,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# The test
# ---------------------------------------------------------------------------

@pytest.mark.eval
def test_agent_eval(fake_db, sent_messages, flush_outbox, monkeypatch):
    samples_spec = os.environ.get("EVAL_SAMPLES", DEFAULT_SAMPLES)
    seed = int(os.environ.get("EVAL_SEED", DEFAULT_SEED))
    case_ids = _select_case_ids(samples_spec, seed)

    results: list[dict] = []
    for cid in case_ids:
        case = _CASES_BY_ID[cid]
        try:
            result = run_case(case, fake_db, sent_messages, flush_outbox, monkeypatch)
        except Exception as exc:  # noqa: BLE001 — defence in depth around run_case itself
            result = {
                "id": cid, "intent": case["expected_intent"], "tier": TIER_OF.get(cid, "unscored"),
                "expected": sorted(EXPECTED.get(cid, [])), "observed": "error", "passed": False,
                "reply_nonempty": False, "reply": "", "language_match": None,
                "tool_calls": [], "elapsed_sec": None, "error": f"{type(exc).__name__}: {exc}",
            }
        results.append(result)

    _print_report(results)
    _write_last_run(results)

    # Deliberately NOT a quality gate yet (see module docstring) — thresholds
    # are plan 03-07's job, derived from a real measured baseline instead of
    # invented numbers. This only proves the harness ran end-to-end.
    assert len(results) == len(case_ids)
    assert all(r.get("observed") for r in results)
