"""
tests/unit/test_eval_dataset.py — keeps tests/eval/expected_behavior.py in sync with
tests/data/whatsapp_agent_dataset.json.

Fast and API-free, runs in the DEFAULT suite (no `eval`/`integration` marker) — this is the
cheap guard that catches drift the moment the dataset changes, without costing anything.
"""
from __future__ import annotations

import json
from pathlib import Path

from tests.eval.expected_behavior import EXPECTED, OUTCOMES, TIER_OF, TIERS, UNSCORED

DATASET_PATH = Path(__file__).resolve().parents[1] / "data" / "whatsapp_agent_dataset.json"


def _load_dataset() -> list[dict]:
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))


def test_dataset_file_still_has_75_entries_with_expected_keys():
    dataset = _load_dataset()
    assert len(dataset) == 75
    required_keys = {
        "id", "raw_input", "expected_intent", "language_profile", "entities", "edge_case_tags",
    }
    for case in dataset:
        assert required_keys <= set(case.keys()), case


def test_every_dataset_id_is_scored_or_explicitly_unscored():
    dataset_ids = {c["id"] for c in _load_dataset()}
    scored_ids = set(EXPECTED)
    unscored_ids = set(UNSCORED)

    # No id counted twice, no id missing.
    assert not (scored_ids & unscored_ids), scored_ids & unscored_ids
    assert dataset_ids == scored_ids | unscored_ids, dataset_ids ^ (scored_ids | unscored_ids)


def test_every_expected_value_is_a_nonempty_subset_of_outcomes():
    for case_id, outcomes in EXPECTED.items():
        assert outcomes, f"case {case_id} has an empty outcome set"
        assert outcomes <= OUTCOMES, f"case {case_id} has unknown outcome(s): {outcomes - OUTCOMES}"


def test_tiers_partition_the_scored_ids_with_no_overlap_and_no_orphans():
    scored_ids = set(EXPECTED)
    tiered_ids: set[int] = set()
    for tier_name, ids in TIERS.items():
        overlap = tiered_ids & ids
        assert not overlap, f"tier {tier_name!r} overlaps another tier on ids: {overlap}"
        tiered_ids |= ids
    assert tiered_ids == scored_ids, tiered_ids ^ scored_ids


def test_tier_of_matches_tiers():
    for tier_name, ids in TIERS.items():
        for case_id in ids:
            assert TIER_OF[case_id] == tier_name
    assert set(TIER_OF) == set(EXPECTED)


def test_unscored_entries_are_justified_and_short():
    # Keep this small — an eval that excuses its own failures is worthless.
    assert 0 < len(UNSCORED) <= 5
    for case_id, reason in UNSCORED.items():
        assert isinstance(reason, str) and len(reason) >= 20, case_id
