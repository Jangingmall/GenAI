"""Unit tests for check_plan_diversity script.

Tests calculation functions, diversity metrics, positional analysis,
quality gate evaluations, and CLI execution using in-memory and synthetic data.
Does not depend on actual model outputs or external servers.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import check_plan_diversity as cpd


# ==============================================================================
# 1. Metric Calculation Unit Tests
# ==============================================================================

def test_compute_common_blocks_identical() -> None:
    plans = [
        ["hero", "statement", "gallery", "closing"],
        ["hero", "statement", "gallery", "closing"],
        ["hero", "statement", "gallery", "closing"],
    ]
    common = cpd.compute_common_blocks(plans)
    assert common == ["closing", "gallery", "hero", "statement"]


def test_compute_common_blocks_disjoint() -> None:
    plans = [
        ["hero", "statement"],
        ["gallery", "detail"],
        ["palette", "closing"],
    ]
    common = cpd.compute_common_blocks(plans)
    assert common == []


def test_compute_common_blocks_partial() -> None:
    plans = [
        ["hero", "statement", "gallery", "closing"],
        ["hero", "feature_grid", "gallery", "closing"],
        ["hero", "detail_split", "gallery", "notice", "closing"],
    ]
    common = cpd.compute_common_blocks(plans)
    assert common == ["closing", "gallery", "hero"]


def test_compute_effective_common_blocks() -> None:
    plans = [
        ["hero", "statement", "gallery", "closing"],
        ["hero", "feature_grid", "gallery", "closing"],
        ["hero", "detail_split", "gallery", "notice", "closing"],
    ]
    # All common: hero, gallery, closing
    # Effective common: gallery (hero and closing excluded)
    effective = cpd.compute_effective_common_blocks(plans)
    assert effective == ["gallery"]


def test_compute_catalog_baseline_deterministic() -> None:
    base1 = cpd.compute_catalog_baseline(sample_size=6, iterations=100, seed=42)
    base2 = cpd.compute_catalog_baseline(sample_size=6, iterations=100, seed=42)
    assert base1 == base2
    assert 0.50 <= base1["mean_jaccard"] <= 0.80
    assert base1["sample_size"] == 6
    assert base1["iterations"] == 100


def test_compute_catalog_baseline_fallback(tmp_path: Path) -> None:
    non_existent = tmp_path / "does_not_exist.json"
    fallback = cpd.compute_catalog_baseline(catalog_path=non_existent, sample_size=6)
    assert fallback["source"] == "fallback_default"
    assert fallback["mean_jaccard"] == 0.640


def test_compute_common_blocks_empty() -> None:
    assert cpd.compute_common_blocks([]) == []


def test_compute_jaccard_similarity() -> None:
    # Identical sets
    assert cpd.compute_jaccard_similarity({"a", "b"}, {"a", "b"}) == 1.0

    # Completely disjoint
    assert cpd.compute_jaccard_similarity({"a", "b"}, {"c", "d"}) == 0.0

    # 50% overlap: intersection 2, union 4 -> 0.5
    assert cpd.compute_jaccard_similarity({"a", "b", "c"}, {"b", "c", "d"}) == 0.5

    # Both empty
    assert cpd.compute_jaccard_similarity(set(), set()) == 1.0

    # One empty
    assert cpd.compute_jaccard_similarity({"a"}, set()) == 0.0


def test_compute_pairwise_similarities_all_identical() -> None:
    case_ids = ["c1", "c2", "c3"]
    plans = [
        ["hero", "gallery", "closing"],
        ["hero", "gallery", "closing"],
        ["hero", "gallery", "closing"],
    ]
    avg_j, pairs, identical = cpd.compute_pairwise_similarities(case_ids, plans)

    assert avg_j == 1.0
    assert len(pairs) == 3  # 3 * 2 / 2
    assert len(identical) == 3
    assert set(identical) == {("c1", "c2"), ("c1", "c3"), ("c2", "c3")}
    for p in pairs:
        assert p["is_identical"] is True
        assert p["jaccard"] == 1.0


def test_compute_pairwise_similarities_all_disjoint() -> None:
    case_ids = ["c1", "c2", "c3"]
    plans = [
        ["a", "b"],
        ["c", "d"],
        ["e", "f"],
    ]
    avg_j, pairs, identical = cpd.compute_pairwise_similarities(case_ids, plans)

    assert avg_j == 0.0
    assert len(pairs) == 3
    assert len(identical) == 0
    for p in pairs:
        assert p["is_identical"] is False
        assert p["jaccard"] == 0.0


def test_compute_pairwise_similarities_known_mixed() -> None:
    case_ids = ["c1", "c2", "c3"]
    plans = [
        ["a", "b", "c"],  # c1
        ["a", "b", "c"],  # c2: identical to c1 -> J(c1, c2) = 1.0
        ["a", "b", "d"],  # c3: 2 in common with c1/c2, union 4 -> J(c1, c3) = 0.5, J(c2, c3) = 0.5
    ]
    avg_j, pairs, identical = cpd.compute_pairwise_similarities(case_ids, plans)

    # Expected avg = (1.0 + 0.5 + 0.5) / 3 = 2.0 / 3 = 0.6667
    assert pytest.approx(avg_j, rel=1e-4) == 2.0 / 3.0
    assert len(identical) == 1
    assert identical == [("c1", "c2")]


def test_compute_length_distribution() -> None:
    plans = [
        ["a", "b", "c"],
        ["a", "b"],
        ["a", "b", "c"],
        ["a", "b", "c", "d"],
    ]
    dist = cpd.compute_length_distribution(plans)
    assert dist == {2: 1, 3: 2, 4: 1}


def test_compute_positional_fixedness() -> None:
    plans = [
        ["hero", "statement", "gallery", "closing"],
        ["hero", "statement", "detail", "closing"],
        ["hero", "feature", "gallery", "closing"],
    ]
    pos_stats = cpd.compute_positional_fixedness(plans)

    assert len(pos_stats) == 4

    # Pos 1: hero (3/3, 100%)
    assert pos_stats[0]["position"] == 1
    assert pos_stats[0]["most_frequent_block"] == "hero"
    assert pos_stats[0]["most_frequent_count"] == 3
    assert pos_stats[0]["fixedness_ratio"] == 1.0

    # Pos 2: statement (2/3, 66.7%)
    assert pos_stats[1]["position"] == 2
    assert pos_stats[1]["most_frequent_block"] == "statement"
    assert pos_stats[1]["most_frequent_count"] == 2
    assert pytest.approx(pos_stats[1]["fixedness_ratio"], rel=1e-3) == 2 / 3

    # Pos 3: gallery (2/3)
    assert pos_stats[2]["position"] == 3
    assert pos_stats[2]["most_frequent_block"] == "gallery"
    assert pos_stats[2]["most_frequent_count"] == 2


def test_compute_sequence_diversity() -> None:
    plans = [
        ["hero", "statement", "closing"],
        ["hero", "statement", "closing"],
        ["hero", "feature", "closing"],
        ["hero", "gallery", "closing"],
    ]
    seq_div = cpd.compute_sequence_diversity(plans)

    assert seq_div["unique_sequence_count"] == 3
    assert seq_div["max_frequency"] == 2
    assert seq_div["total_cases"] == 4
    assert seq_div["sequences"][0]["sequence"] == ["hero", "statement", "closing"]
    assert seq_div["sequences"][0]["count"] == 2


# ==============================================================================
# 2. Quality Gate Evaluation Tests
# ==============================================================================

def test_evaluate_plan_diversity_passes_when_diverse() -> None:
    """A diverse set of 6 plans should pass all gates."""
    records = [
        {"case_id": "c1", "blocks": ["hero", "block_a", "closing"]},
        {"case_id": "c2", "blocks": ["hero", "block_b", "closing"]},
        {"case_id": "c3", "blocks": ["hero", "block_c", "closing"]},
        {"case_id": "c4", "blocks": ["hero", "block_d", "closing"]},
        {"case_id": "c5", "blocks": ["hero", "block_e", "closing"]},
        {"case_id": "c6", "blocks": ["hero", "block_f", "closing"]},
    ]
    # Common blocks: ['closing', 'hero'] (2 blocks <= 4)
    # Each pair shares {hero, closing} (2), union is {hero, closing, a, b} (4) -> Jaccard = 2/4 = 0.50 (50% <= 60%)
    # Identical pairs: 0 (<= 0)
    result = cpd.evaluate_plan_diversity(records, max_avg_jaccard=0.60, max_common_blocks=4, max_identical_pairs=0)

    assert result["pass"] is True
    assert result["failures"] == []
    assert result["gates"]["avg_jaccard"]["pass"] is True
    assert result["gates"]["common_blocks"]["pass"] is True
    assert result["gates"]["identical_pairs"]["pass"] is True
    assert result["metrics"]["common_block_count"] == 2
    assert result["metrics"]["identical_pairs_count"] == 0
    assert result["metrics"]["avg_jaccard_pct"] == 50.0


def test_evaluate_plan_diversity_fails_on_high_jaccard() -> None:
    records = [
        {"case_id": "c1", "blocks": ["hero", "a", "b", "c", "d", "e", "closing"]},
        {"case_id": "c2", "blocks": ["hero", "a", "b", "c", "d", "f", "closing"]},
    ]
    # Intersect: {hero, a, b, c, d, closing} = 6, Union = 8 -> Jaccard = 6/8 = 0.75 (75% > 60%)
    result = cpd.evaluate_plan_diversity(records, max_avg_jaccard=0.60, max_common_blocks=10, max_identical_pairs=0)

    assert result["pass"] is False
    assert any("평균 집합 일치도 초과" in f for f in result["failures"])
    assert result["gates"]["avg_jaccard"]["pass"] is False


def test_evaluate_plan_diversity_fails_on_common_blocks() -> None:
    records = [
        {"case_id": "c1", "blocks": ["b1", "b2", "b3", "b4", "b5", "unique1"]},
        {"case_id": "c2", "blocks": ["b1", "b2", "b3", "b4", "b5", "unique2"]},
    ]
    # Common blocks = 5 (threshold: <= 4)
    result = cpd.evaluate_plan_diversity(records, max_avg_jaccard=0.90, max_common_blocks=4, max_identical_pairs=0)

    assert result["pass"] is False
    assert any("공통 블록 종수 초과" in f for f in result["failures"])
    assert result["gates"]["common_blocks"]["pass"] is False


def test_evaluate_plan_diversity_fails_on_identical_pairs() -> None:
    records = [
        {"case_id": "c1", "blocks": ["hero", "a", "closing"]},
        {"case_id": "c2", "blocks": ["hero", "a", "closing"]},  # identical to c1
        {"case_id": "c3", "blocks": ["hero", "b", "closing"]},
    ]
    result = cpd.evaluate_plan_diversity(records, max_avg_jaccard=0.90, max_common_blocks=10, max_identical_pairs=0)

    assert result["pass"] is False
    assert any("완전 일치 쌍" in f for f in result["failures"])
    assert result["gates"]["identical_pairs"]["pass"] is False
    assert result["metrics"]["identical_pairs_count"] == 1


def test_evaluate_plan_diversity_default_allows_one_identical_pair() -> None:
    records = [
        {"case_id": "c1", "blocks": ["hero", "a", "b", "closing"]},
        {"case_id": "c2", "blocks": ["hero", "a", "b", "closing"]},  # 1 identical pair (c1, c2)
        {"case_id": "c3", "blocks": ["hero", "c", "d", "closing"]},
        {"case_id": "c4", "blocks": ["hero", "e", "f", "closing"]},
    ]
    result = cpd.evaluate_plan_diversity(records, max_avg_jaccard=0.90, max_effective_common=4)
    # Under default max_identical_pairs=1, this single pair is permitted
    assert result["gates"]["identical_pairs"]["pass"] is True
    assert result["metrics"]["identical_pairs_count"] == 1


def test_evaluate_plan_diversity_uses_catalog_baseline() -> None:
    records = [
        {"case_id": "c1", "blocks": ["hero", "a", "closing"]},
        {"case_id": "c2", "blocks": ["hero", "b", "closing"]},
    ]
    result = cpd.evaluate_plan_diversity(records, max_jaccard_delta=0.10)
    baseline_mean = result["catalog_baseline"]["mean_jaccard"]
    expected_threshold = round(baseline_mean + 0.10, 4)
    assert result["thresholds"]["max_avg_jaccard"] == expected_threshold
    assert result["gates"]["avg_jaccard"]["threshold"] == expected_threshold


# ==============================================================================
# 3. CLI and File Loading Integration Tests
# ==============================================================================

def test_load_pilot_plans_from_mock_dir(tmp_path: Path) -> None:
    """Verify loading from mock pilot dir with run_index.json."""
    case1_dir = tmp_path / "analysis-case-1"
    case2_dir = tmp_path / "analysis-case-2"
    case1_dir.mkdir()
    case2_dir.mkdir()

    (case1_dir / "result_summary.json").write_text(
        json.dumps({
            "product": {
                "page_plan": [
                    {"section_id": "s1", "block_type": "hero"},
                    {"section_id": "s2", "block_type": "gallery"},
                ]
            }
        }),
        encoding="utf-8",
    )
    (case2_dir / "result_summary.json").write_text(
        json.dumps({
            "product": {
                "page_plan": [
                    {"section_id": "s1", "block_type": "hero"},
                    {"section_id": "s2", "block_type": "detail_split"},
                ]
            }
        }),
        encoding="utf-8",
    )

    run_index = {
        "pilot_id": "test-pilot",
        "cases": [
            {"case_id": "analysis-case-1", "category": "cat1", "output_dir": str(case1_dir)},
            {"case_id": "analysis-case-2", "category": "cat2", "output_dir": str(case2_dir)},
        ],
    }
    (tmp_path / "run_index.json").write_text(json.dumps(run_index), encoding="utf-8")

    records = cpd.load_pilot_plans(tmp_path)
    assert len(records) == 2
    assert records[0]["case_id"] == "analysis-case-1"
    assert records[0]["blocks"] == ["hero", "gallery"]
    assert records[1]["case_id"] == "analysis-case-2"
    assert records[1]["blocks"] == ["hero", "detail_split"]


def test_main_cli_returns_zero_on_pass(tmp_path: Path) -> None:
    """CLI should return 0 when mock pilot satisfies diversity thresholds."""
    # 3 diverse cases
    for idx, blk in enumerate(["b_alpha", "b_beta", "b_gamma"], start=1):
        c_dir = tmp_path / f"analysis-c{idx}"
        c_dir.mkdir()
        (c_dir / "result_summary.json").write_text(
            json.dumps({"product": {"page_plan": [{"block_type": "hero"}, {"block_type": blk}]}}),
            encoding="utf-8",
        )

    exit_code = cpd.main([str(tmp_path), "--max-avg-jaccard", "0.60", "--max-common-blocks", "4"])
    assert exit_code == 0


def test_main_cli_returns_one_on_fail_and_writes_json(tmp_path: Path) -> None:
    """CLI should return 1 when repetitive, and write valid JSON report."""
    # 3 identical cases -> 3 identical pairs > max_identical_pairs (default 1)
    for idx in [1, 2, 3]:
        c_dir = tmp_path / f"analysis-c{idx}"
        c_dir.mkdir()
        (c_dir / "result_summary.json").write_text(
            json.dumps({"product": {"page_plan": [{"block_type": "hero"}, {"block_type": "statement"}]}}),
            encoding="utf-8",
        )

    json_out = tmp_path / "diversity_report.json"
    exit_code = cpd.main([str(tmp_path), "--json", str(json_out)])
    assert exit_code == 1
    assert json_out.exists()

    payload = json.loads(json_out.read_text(encoding="utf-8"))
    assert payload["pass"] is False
    assert payload["metrics"]["identical_pairs_count"] == 3
    assert payload["gates"]["identical_pairs"]["pass"] is False
