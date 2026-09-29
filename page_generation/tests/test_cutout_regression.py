"""Unit and integration tests for cutout regression comparison tool.

Tests scripts/compare_cutout_regression.py functions:
  - Rejection diagnosis (corner uniformity, component ratio, etc.)
  - Single-image cutout evaluation (erosion risk, background remnant)
  - Regression and improvement detection across comparison runs
  - Baseline snapshot consistency against ground truth labels
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

import compare_cutout_regression
from detail_page_ai.source_photos import SolidBackgroundCutoutExtractor

PILOT_DIR = PROJECT_ROOT / "generated/evaluation/full60-20260910-204433"
RUN_INDEX = PILOT_DIR / "run_index.json"
BASELINE_JSON = PROJECT_ROOT / "docs/phase4/evaluation/cutout-baseline-metrics.json"


def test_diagnose_rejection_corner_non_uniform() -> None:
    """Verify rejection diagnosis identifies corner non-uniformity."""
    extractor = SolidBackgroundCutoutExtractor()
    img_path = PROJECT_ROOT / "data/evaluation/cma_real_v1/images/cma-101636.jpg"
    assert img_path.is_file()

    reason, detail, max_dev = compare_cutout_regression.diagnose_rejection(
        img_path.read_bytes(), extractor
    )
    assert reason == "CORNER_NON_UNIFORM"
    assert max_dev > extractor.corner_uniformity_tolerance
    assert "모서리 최대 편차" in detail


def test_diagnose_rejection_component_ratio() -> None:
    """Verify rejection diagnosis identifies largest component ratio failure."""
    extractor = SolidBackgroundCutoutExtractor()
    img_path = PROJECT_ROOT / "data/evaluation/cma_real_v1/images/cma-124415.jpg"
    assert img_path.is_file()

    reason, detail, max_dev = compare_cutout_regression.diagnose_rejection(
        img_path.read_bytes(), extractor
    )
    assert reason == "LARGEST_COMPONENT_TOO_SMALL"
    assert max_dev <= extractor.corner_uniformity_tolerance
    assert "최대 연결 요소 비율" in detail


def test_evaluate_single_image_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify single image evaluation for a fallback case."""
    extractor = SolidBackgroundCutoutExtractor(corner_uniformity_tolerance=-1.0)
    monkeypatch.setattr(extractor, "extract", lambda *_: None)
    img_path = PROJECT_ROOT / "data/evaluation/cma_real_v1/images/cma-101636.jpg"

    res = compare_cutout_regression.evaluate_single_image(
        case_id="analysis-cma-101636",
        category="box",
        image_path=img_path,
        extractor=extractor,
    )
    assert res["status"] == "FALLBACK"
    assert res["rejection_reason"] == "CORNER_NON_UNIFORM"
    assert res["erosion_risk"] == "NONE"
    assert res["remnant_status"] == "EDGE"
    assert res["gt_match_a"] is True
    assert res["gt_match_b"] is True


def test_evaluate_single_image_composite_extraction() -> None:
    """Verify single image evaluation structure for a cutout extraction."""
    extractor = SolidBackgroundCutoutExtractor()
    img_path = PROJECT_ROOT / "data/evaluation/cma_real_v1/images/cma-165266.jpg"

    res = compare_cutout_regression.evaluate_single_image(
        case_id="analysis-cma-165266",
        category="textile",
        image_path=img_path,
        extractor=extractor,
    )
    assert res["case_id"] == "analysis-cma-165266"
    assert res["status"] in ("SUCCESS", "FALLBACK")
    assert res["erosion_risk"] in ("NONE", "LOW", "MEDIUM", "HIGH")
    assert res["remnant_status"] in ("NONE", "ENCLOSED", "EDGE")
    if res["status"] == "SUCCESS":
        assert res["foreground_pixels"] > 0
        assert res["rejection_reason"] is None


def test_evaluate_single_image_composite_enclosed_remnant() -> None:
    """Verify single image evaluation for a jewelry case with enclosed background."""
    extractor = SolidBackgroundCutoutExtractor()
    img_path = PROJECT_ROOT / "data/evaluation/cma_real_v1/images/cma-159023.jpg"

    res = compare_cutout_regression.evaluate_single_image(
        case_id="analysis-cma-159023",
        category="jewelry",
        image_path=img_path,
        extractor=extractor,
    )
    assert res["case_id"] == "analysis-cma-159023"
    assert res["status"] in ("SUCCESS", "FALLBACK")
    assert res["erosion_risk"] in ("NONE", "LOW", "MEDIUM", "HIGH")
    assert res["remnant_status"] in ("NONE", "ENCLOSED", "EDGE")
    if res["status"] == "SUCCESS":
        assert res["enclosed_bg_pixels"] >= 0


def test_evaluate_single_image_composite_clean() -> None:
    """Verify single image evaluation for a clean jewelry cutout."""
    extractor = SolidBackgroundCutoutExtractor()
    img_path = PROJECT_ROOT / "data/evaluation/cma_real_v1/images/cma-168479.jpg"

    res = compare_cutout_regression.evaluate_single_image(
        case_id="analysis-cma-168479",
        category="jewelry",
        image_path=img_path,
        extractor=extractor,
    )
    assert res["case_id"] == "analysis-cma-168479"
    assert res["status"] in ("SUCCESS", "FALLBACK")
    assert res["erosion_risk"] in ("NONE", "LOW", "MEDIUM", "HIGH")
    assert res["remnant_status"] in ("NONE", "ENCLOSED", "EDGE")
    assert res["gt_match_a"] is True
    assert res["gt_match_b"] is True


def test_compare_runs_regression_and_improvement_detection() -> None:
    """Verify comparison engine correctly classifies improved, regressed, and unchanged cases."""
    baseline = {
        "execution_summary": {"execution_rate_pct": 15.0},
        "records": [
            {
                "case_id": "case-improved",
                "category": "box",
                "status": "FALLBACK",
                "erosion_risk": "NONE",
                "remnant_status": "EDGE",
            },
            {
                "case_id": "case-regressed-fallback",
                "category": "jewelry",
                "status": "SUCCESS",
                "erosion_risk": "LOW",
                "remnant_status": "NONE",
            },
            {
                "case_id": "case-regressed-erosion",
                "category": "ceramic",
                "status": "SUCCESS",
                "erosion_risk": "LOW",
                "remnant_status": "NONE",
            },
            {
                "case_id": "case-regressed-remnant",
                "category": "metalware",
                "status": "SUCCESS",
                "erosion_risk": "LOW",
                "remnant_status": "NONE",
            },
            {
                "case_id": "case-regressed-bad-extraction",
                "category": "textile",
                "status": "FALLBACK",
                "erosion_risk": "NONE",
                "remnant_status": "EDGE",
            },
            {
                "case_id": "case-unchanged",
                "category": "furniture",
                "status": "FALLBACK",
                "erosion_risk": "NONE",
                "remnant_status": "EDGE",
            },
        ],
    }

    candidate = {
        "execution_summary": {"execution_rate_pct": 66.7},
        "records": [
            {
                "case_id": "case-improved",
                "category": "box",
                "status": "SUCCESS",
                "erosion_risk": "LOW",
                "remnant_status": "NONE",
            },
            {
                "case_id": "case-regressed-fallback",
                "category": "jewelry",
                "status": "FALLBACK",
                "erosion_risk": "NONE",
                "remnant_status": "EDGE",
                "erosion_risk_detail": "폴백",
                "remnant_detail": "폴백",
            },
            {
                "case_id": "case-regressed-erosion",
                "category": "ceramic",
                "status": "SUCCESS",
                "erosion_risk": "HIGH",
                "remnant_status": "NONE",
                "erosion_risk_detail": "제품 유약 소실 50,000px",
                "remnant_detail": "배경 완전 제거",
            },
            {
                "case_id": "case-regressed-remnant",
                "category": "metalware",
                "status": "SUCCESS",
                "erosion_risk": "LOW",
                "remnant_status": "EDGE",
                "erosion_risk_detail": "온전",
                "remnant_detail": "테두리 접촉 1200px",
            },
            {
                "case_id": "case-regressed-bad-extraction",
                "category": "textile",
                "status": "SUCCESS",
                "erosion_risk": "HIGH",
                "remnant_status": "NONE",
                "erosion_risk_detail": "크림색 평직 소실 150,000px",
                "remnant_detail": "배경 완전 제거",
            },
            {
                "case_id": "case-unchanged",
                "category": "furniture",
                "status": "FALLBACK",
                "erosion_risk": "NONE",
                "remnant_status": "EDGE",
            },
        ],
    }

    res = compare_cutout_regression.compare_runs(baseline, candidate)
    summary = res["summary"]

    assert summary["total_evaluated"] == 6
    assert summary["improved_count"] == 1
    assert summary["regressed_count"] == 4
    assert summary["unchanged_count"] == 1

    reg_ids = [r["case_id"] for r in res["regressed_cases"]]
    assert "case-regressed-fallback" in reg_ids
    assert "case-regressed-erosion" in reg_ids
    assert "case-regressed-remnant" in reg_ids
    assert "case-regressed-bad-extraction" in reg_ids

    imp_ids = [r["case_id"] for r in res["improved_cases"]]
    assert "case-improved" in imp_ids


def test_baseline_snapshot_metrics() -> None:
    """Verify saved baseline snapshot matches expected ground truth metrics."""
    assert BASELINE_JSON.is_file(), f"Baseline JSON missing: {BASELINE_JSON}"
    data = json.loads(BASELINE_JSON.read_text(encoding="utf-8"))

    assert data["total_cases"] == 60
    assert data["execution_summary"]["success_count"] == 9
    assert data["execution_summary"]["fallback_count"] == 51
    assert data["execution_summary"]["execution_rate_pct"] == 15.0

    # Rejection breakdown
    rej = data["rejection_reasons"]
    assert rej["CORNER_NON_UNIFORM"] == 50
    assert rej["LARGEST_COMPONENT_TOO_SMALL"] == 1

    # Corner deviation median ~ 101.3
    assert 100.0 <= data["corner_deviation_stats"]["median"] <= 102.0

    # Erosion: exactly 4 High risk cases
    assert data["erosion_risk_counts"]["HIGH"] == 4
    high_ids = [c["case_id"] for c in data["erosion_candidates"] if c["risk"] == "HIGH"]
    assert set(high_ids) == {
        "analysis-cma-165266",
        "analysis-cma-165267",
        "analysis-cma-165271",
        "analysis-cma-122443",
    }

    # Remnant: exactly 2 Enclosed cases
    assert data["remnant_status_counts"]["ENCLOSED"] == 2
    records_by_id = {r["case_id"]: r for r in data["records"]}
    assert records_by_id["analysis-cma-159023"]["remnant_status"] == "ENCLOSED"
    assert records_by_id["analysis-cma-131719"]["remnant_status"] == "ENCLOSED"


def test_cli_execution_with_snapshots(tmp_path: Path) -> None:
    """Verify CLI interface runs snapshot comparison and generates markdown."""
    out_md = tmp_path / "report.md"
    ret = compare_cutout_regression.main([
        "--baseline", str(BASELINE_JSON),
        "--candidate", str(BASELINE_JSON),
        "--markdown", str(out_md),
    ])
    assert ret == 0
    assert out_md.is_file()
    content = out_md.read_text(encoding="utf-8")
    assert "# 컷아웃 추출기 회귀 판정 보고서" in content
    assert "**변화 없음 (UNCHANGED)**: **60건**" in content
