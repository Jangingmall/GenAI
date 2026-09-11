"""Unit and integration tests for cutout ground truth auditor.

Tests scripts/audit_cutout_truth.py against the 60 evaluation pilot cases,
verifying ground truth label consistency, manager judgements agreement,
hidden defect detection, and legacy gate error classification.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
SRC_DIR = PROJECT_ROOT / "src"

for p in [str(SCRIPTS_DIR), str(SRC_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import audit_cutout_truth

PILOT_DIR = PROJECT_ROOT / "generated/evaluation/full60-20260910-204433"


@pytest.fixture(scope="module")
def audit_results() -> dict:
    """Run full audit across 60 cases once for the test module."""
    assert PILOT_DIR.is_dir(), f"Pilot directory not found: {PILOT_DIR}"
    return audit_cutout_truth.audit_cutout_pilot(PILOT_DIR)


def test_full_60_cases_count_and_distribution(audit_results: dict) -> None:
    """Verify total case count and distribution across modes."""
    assert audit_results["total_cases"] == 60
    assert audit_results["mode_counts"]["source_composite"] == 9
    assert audit_results["mode_counts"]["source"] == 51


def test_axis_a_erosion_distribution(audit_results: dict) -> None:
    """Verify Axis A (product erosion) distribution on frozen artifacts."""
    a_counts = audit_results["axis_a_erosion_counts"]
    assert sum(a_counts.values()) == audit_results["total_cases"]
    assert a_counts["severe"] == 0
    assert a_counts["uncertain"] == 0
    assert a_counts["partial"] >= 4

    # Specifically verify the 4 partial erosion benchmark cases in the frozen dataset
    records_by_id = {r["case_id"]: r for r in audit_results["records"]}
    assert records_by_id["analysis-cma-165266"]["axis_a"] == "partial"
    assert records_by_id["analysis-cma-165267"]["axis_a"] == "partial"
    assert records_by_id["analysis-cma-165271"]["axis_a"] == "partial"
    assert records_by_id["analysis-cma-122443"]["axis_a"] == "partial"


def test_axis_b_remnant_distribution(audit_results: dict) -> None:
    """Verify Axis B (background remnant) distribution on frozen artifacts."""
    b_counts = audit_results["axis_b_remnant_counts"]
    assert sum(b_counts.values()) == audit_results["total_cases"]
    assert b_counts["uncertain"] == 0
    assert b_counts["enclosed"] >= 2
    assert b_counts["edge"] >= 50

    records_by_id = {r["case_id"]: r for r in audit_results["records"]}
    # Enclosed cases
    assert records_by_id["analysis-cma-159023"]["axis_b"] == "enclosed"
    assert records_by_id["analysis-cma-131719"]["axis_b"] == "enclosed"

    # Edge cases include pedestal remnant (122443)
    assert records_by_id["analysis-cma-122443"]["axis_b"] == "edge"


def test_manager_agreement(audit_results: dict) -> None:
    """Verify 100% agreement with manager's 5 visual judgements."""
    mgr = audit_results["manager_comparison"]
    assert mgr["evaluated_cases"] == 5
    assert mgr["agreement_count"] == 5
    assert mgr["agreement_rate"] == 1.0


def test_duplicate_case_identical_judgements(audit_results: dict) -> None:
    """Verify duplicate original pair (165266 and 165267) yield identical judgements."""
    records_by_id = {r["case_id"]: r for r in audit_results["records"]}
    r1 = records_by_id["analysis-cma-165266"]
    r2 = records_by_id["analysis-cma-165267"]

    assert r1["axis_a"] == r2["axis_a"] == "partial"
    assert r1["axis_b"] == r2["axis_b"] == "none"
    assert r1["metrics"]["eroded_pixels"] == r2["metrics"]["eroded_pixels"]


def test_hidden_defects_missed_by_legacy_gate(audit_results: dict) -> None:
    """Verify hidden defects in cases that legacy gate passed as OK."""
    records_by_id = {r["case_id"]: r for r in audit_results["records"]}

    # 1. 122443: ceramic vase glaze erosion + edge pedestal remnant passed as OK by legacy gate
    r_122443 = records_by_id["analysis-cma-122443"]
    assert r_122443["gate_judgment"] == "OK"
    assert r_122443["axis_a"] == "partial"
    assert r_122443["axis_b"] == "edge"
    assert r_122443["metrics"]["internal_holes"] > 10000
    assert r_122443["metrics"]["total_border_touch"] > 500

    # 2. 131719: jewelry necklace loop background remnant (82.6%) passed as OK by legacy gate
    r_131719 = records_by_id["analysis-cma-131719"]
    assert r_131719["gate_judgment"] == "OK"
    assert r_131719["axis_a"] == "none"
    assert r_131719["axis_b"] == "enclosed"
    assert r_131719["metrics"]["enclosed_bg_pixels"] > 200000


def test_legacy_gate_false_positives(audit_results: dict) -> None:
    """Verify legacy gate false positives on erosion."""
    records_by_id = {r["case_id"]: r for r in audit_results["records"]}

    # 168479: gold earrings cleanly cut out with 0% loss, legacy gate flagged 35.3% loss
    r_168479 = records_by_id["analysis-cma-168479"]
    assert r_168479["gate_judgment"] == "부분 손실"
    assert r_168479["axis_a"] == "none"
    assert r_168479["axis_b"] == "none"
    assert r_168479["gate_discrepancy"] == "FALSE_POSITIVE_EROSION"

    # 159023: legacy gate misidentified enclosed remnant as product erosion
    r_159023 = records_by_id["analysis-cma-159023"]
    assert r_159023["gate_judgment"] == "부분 손실"
    assert r_159023["axis_a"] == "none"
    assert r_159023["axis_b"] == "enclosed"


def test_fallback_cases_fidelity(audit_results: dict) -> None:
    """Verify all 51 fallback cases are byte-identical to source and exhibit edge remnant."""
    fallback_records = [r for r in audit_results["records"] if r["asset_mode"] == "source"]
    assert len(fallback_records) == 51

    for r in fallback_records:
        assert r["axis_a"] == "none"
        assert r["axis_b"] == "edge"
        assert r["metrics"]["byte_identical_to_source"] is True
        assert r["metrics"]["eroded_pixels"] == 0
        assert r["gate_discrepancy"] == "FALSE_NEGATIVE_REMNANT"


def test_markdown_and_json_export(tmp_path: Path, audit_results: dict) -> None:
    """Verify markdown report generation and json export."""
    md = audit_cutout_truth.format_markdown_table(audit_results)
    assert "# 컷아웃 품질 독립 감사 정답 집합" in md
    assert "analysis-cma-165266" in md
    assert "FALSE_NEGATIVE_BOTH" in md

    out_json = tmp_path / "truth.json"
    ret = audit_cutout_truth.main([
        "--pilot-dir", str(PILOT_DIR),
        "--json", str(out_json),
    ])
    assert ret == 0
    assert out_json.is_file()
    saved = json.loads(out_json.read_text(encoding="utf-8"))
    assert saved["total_cases"] == 60
