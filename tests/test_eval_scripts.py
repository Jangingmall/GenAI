"""Unit tests for evaluation scripts.

Tests run_eval_pilot, build_review_sheet, check_cutout_fidelity, and
check_scene_direction_coverage without invoking AI models or external servers.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
SRC_DIR = PROJECT_ROOT / "src"

for p in [str(SCRIPTS_DIR), str(SRC_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import build_review_sheet
import check_cutout_fidelity
import check_scene_direction_coverage
import run_eval_pilot


# ==============================================================================
# 1. run_eval_pilot tests
# ==============================================================================

def test_select_pilot_cases_real_dataset() -> None:
    """Verify pilot selection on real dataset chooses 6 distinct categories deterministically."""
    manifest_path = PROJECT_ROOT / "data/evaluation/cma_real_v1/manifest.json"
    analysis_path = PROJECT_ROOT / "data/evaluation/cma_real_v1/analysis_60.jsonl"

    assert manifest_path.exists(), f"Manifest file missing: {manifest_path}"
    assert analysis_path.exists(), f"Analysis file missing: {analysis_path}"

    cases_run1 = run_eval_pilot.select_pilot_cases(manifest_path, analysis_path)
    cases_run2 = run_eval_pilot.select_pilot_cases(manifest_path, analysis_path)

    # 1. Must select exactly 6 cases
    assert len(cases_run1) == 6

    # 2. All 6 categories must be distinct and match default categories
    selected_categories = [c["category"] for c in cases_run1]
    assert len(set(selected_categories)) == 6
    assert set(selected_categories) == set(run_eval_pilot.DEFAULT_CATEGORIES)

    # 3. Deterministic: two calls must return identical output
    assert cases_run1 == cases_run2

    # 4. Check essential fields
    for case in cases_run1:
        assert case["category"]
        assert case["asset_id"]
        assert case["case_id"]
        assert case["image_path"]
        assert Path(case["image_path"]).exists()


def test_select_pilot_cases_deterministic_lowest_asset_id(tmp_path: Path) -> None:
    """Verify select_pilot_cases deterministically picks asset with lowest asset_id per category."""
    manifest_data = {
        "assets": [
            {"asset_id": "cma-300", "category": "textile", "image_path": "img3.jpg", "title": "C"},
            {"asset_id": "cma-100", "category": "textile", "image_path": "img1.jpg", "title": "A"},
            {"asset_id": "cma-200", "category": "textile", "image_path": "img2.jpg", "title": "B"},
            {"asset_id": "cma-999", "category": "box", "image_path": "box2.jpg", "title": "Box 2"},
            {"asset_id": "cma-888", "category": "box", "image_path": "box1.jpg", "title": "Box 1"},
        ]
    }
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")

    analysis_lines = [
        json.dumps({"asset_id": "cma-100", "case_id": "case-100", "metadata": {}}),
        json.dumps({"asset_id": "cma-200", "case_id": "case-200", "metadata": {}}),
        json.dumps({"asset_id": "cma-300", "case_id": "case-300", "metadata": {}}),
        json.dumps({"asset_id": "cma-888", "case_id": "case-888", "metadata": {}}),
        json.dumps({"asset_id": "cma-999", "case_id": "case-999", "metadata": {}}),
    ]
    analysis_file = tmp_path / "analysis.jsonl"
    analysis_file.write_text("\n".join(analysis_lines), encoding="utf-8")

    selected = run_eval_pilot.select_pilot_cases(manifest_file, analysis_file)
    assert len(selected) == 2

    # textile lowest is cma-100; box lowest is cma-888
    selected_by_cat = {c["category"]: c["asset_id"] for c in selected}
    assert selected_by_cat["textile"] == "cma-100"
    assert selected_by_cat["box"] == "cma-888"


def test_select_pilot_cases_missing_files_raises(tmp_path: Path) -> None:
    """Verify select_pilot_cases raises FileNotFoundError if files are missing."""
    non_existent = tmp_path / "non_existent.json"
    existing = tmp_path / "existing.json"
    existing.write_text("{}", encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        run_eval_pilot.select_pilot_cases(non_existent, existing)

    with pytest.raises(FileNotFoundError):
        run_eval_pilot.select_pilot_cases(existing, non_existent)


# ==============================================================================
# 2. build_review_sheet tests
# ==============================================================================

def test_build_review_sheet_columns() -> None:
    """Verify REVIEW_COLUMNS contains 4 evaluation axes x 2 reviewers + consensus columns."""
    columns = build_review_sheet.REVIEW_COLUMNS

    expected_axes = ["사실성", "명료성", "상품성", "시각품질"]
    for axis in expected_axes:
        assert f"검수자A_{axis}" in columns
        assert f"검수자B_{axis}" in columns
        assert f"합의_{axis}" in columns

    assert "검수자A_코멘트" in columns
    assert "검수자B_코멘트" in columns
    assert "합의_메모" in columns
    assert "실행 성공 여부" in columns
    assert "에러 메시지" in columns


def test_build_review_rows_empty_scores_and_includes_failures() -> None:
    """Verify score columns are blank and failed cases are preserved with error messages."""
    mock_run_index = {
        "cases": [
            {
                "case_id": "analysis-success",
                "category": "ceramic",
                "asset_id": "cma-123",
                "image_path": "input/cma-123.jpg",
                "output_dir": "output/analysis-success",
                "success": True,
                "error": None,
            },
            {
                "case_id": "analysis-failed",
                "category": "metalware",
                "asset_id": "cma-456",
                "image_path": "input/cma-456.jpg",
                "output_dir": "output/analysis-failed",
                "success": False,
                "error": "Pipeline execution timed out after 300s",
            },
        ]
    }

    rows = build_review_sheet.build_review_rows(mock_run_index)
    assert len(rows) == 2

    # 1. Success case row
    assert rows[0]["case_id"] == "analysis-success"
    assert rows[0]["실행 성공 여부"] == "성공"
    assert rows[0]["에러 메시지"] == ""

    # 2. Failed case row preserved
    assert rows[1]["case_id"] == "analysis-failed"
    assert rows[1]["실행 성공 여부"] == "실패"
    assert "timed out" in rows[1]["에러 메시지"]

    # 3. All score columns must be empty strings for independent human review
    score_columns = [
        "검수자A_사실성", "검수자A_명료성", "검수자A_상품성", "검수자A_시각품질",
        "검수자B_사실성", "검수자B_명료성", "검수자B_상품성", "검수자B_시각품질",
        "합의_사실성", "합의_명료성", "합의_상품성", "합의_시각품질",
    ]
    for row in rows:
        for col in score_columns:
            assert row[col] == "", f"Score column {col} should be empty, got {row[col]!r}"


def test_build_review_sheet_file_creation(tmp_path: Path) -> None:
    """Verify build_review_sheet writes valid utf-8-sig CSV matching REVIEW_COLUMNS."""
    pilot_dir = tmp_path / "mock-pilot"
    pilot_dir.mkdir()
    index_file = pilot_dir / "run_index.json"
    index_file.write_text(
        json.dumps({
            "cases": [
                {"case_id": "c1", "category": "box", "asset_id": "a1", "success": True},
            ]
        }),
        encoding="utf-8",
    )

    out_csv = tmp_path / "test_sheet.csv"
    generated_path = build_review_sheet.build_review_sheet(pilot_dir, out_csv)
    assert generated_path.is_file()

    with open(generated_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == build_review_sheet.REVIEW_COLUMNS
        row_list = list(reader)
        assert len(row_list) == 1
        assert row_list[0]["case_id"] == "c1"


# ==============================================================================
# 3. check_cutout_fidelity tests
# ==============================================================================

def test_calculate_ink_ratio_known_inputs(tmp_path: Path) -> None:
    """Verify ink ratio calculation on known monochrome and geometric patterns."""
    # 1. Pure white: no pixels < 235 brightness -> ink ratio must be 0.0
    white_img = tmp_path / "white.png"
    Image.new("RGB", (100, 100), (255, 255, 255)).save(white_img)
    assert check_cutout_fidelity.calculate_ink_ratio(white_img) == 0.0

    # 2. Pure black: all pixels < 235 brightness -> ink ratio must be 1.0
    black_img = tmp_path / "black.png"
    Image.new("RGB", (100, 100), (0, 0, 0)).save(black_img)
    assert check_cutout_fidelity.calculate_ink_ratio(black_img) == 1.0

    # 3. Exactly half black (left) and half white (right) -> ink ratio ~ 0.5
    half_img = tmp_path / "half.png"
    img = Image.new("RGB", (200, 200), (255, 255, 255))
    for x in range(100):
        for y in range(200):
            img.putpixel((x, y), (0, 0, 0))
    img.save(half_img)
    ratio = check_cutout_fidelity.calculate_ink_ratio(half_img)
    assert abs(ratio - 0.5) < 0.02

    # 4. RGBA image with transparent background and black quarter square
    rgba_img = tmp_path / "rgba.png"
    rgba = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    for x in range(100):
        for y in range(100):
            rgba.putpixel((x, y), (0, 0, 0, 255))
    rgba.save(rgba_img)
    rgba_ratio = check_cutout_fidelity.calculate_ink_ratio(rgba_img)
    assert abs(rgba_ratio - 0.25) < 0.02


def test_check_cutout_fidelity_threshold_boundaries(tmp_path: Path) -> None:
    """Verify cutout fidelity threshold boundaries (OK / 부분 손실 / 심각 손실 / 산출물 누락)."""
    pilot_dir = tmp_path / "mock_pilot"
    pilot_dir.mkdir()

    # Create base original image (all black, ink_ratio = 1.0)
    orig_img = tmp_path / "orig.png"
    Image.new("RGB", (100, 100), (0, 0, 0)).save(orig_img)

    # Setup case directories and outputs with varied ink retention:
    # Case 1: output ~0.8 ink -> ratio 0.8 > ok_threshold(0.6) => OK
    case1_dir = pilot_dir / "case-ok"
    photos1 = case1_dir / "photos"
    photos1.mkdir(parents=True)
    c1_img = Image.new("RGB", (100, 100), (255, 255, 255))
    for x in range(80):
        for y in range(100):
            c1_img.putpixel((x, y), (0, 0, 0))
    c1_img.save(photos1 / "01-hero.png")

    # Case 2: output ~0.4 ink -> 0.25 <= ratio 0.4 <= 0.6 => 부분 손실
    case2_dir = pilot_dir / "case-partial"
    photos2 = case2_dir / "photos"
    photos2.mkdir(parents=True)
    c2_img = Image.new("RGB", (100, 100), (255, 255, 255))
    for x in range(40):
        for y in range(100):
            c2_img.putpixel((x, y), (0, 0, 0))
    c2_img.save(photos2 / "01-hero.png")

    # Case 3: output ~0.1 ink -> ratio 0.1 < severe_threshold(0.25) => 심각 손실
    case3_dir = pilot_dir / "case-severe"
    photos3 = case3_dir / "photos"
    photos3.mkdir(parents=True)
    c3_img = Image.new("RGB", (100, 100), (255, 255, 255))
    for x in range(10):
        for y in range(100):
            c3_img.putpixel((x, y), (0, 0, 0))
    c3_img.save(photos3 / "01-hero.png")

    # Case 4: empty photos dir => 산출물 누락
    case4_dir = pilot_dir / "case-missing"
    photos4 = case4_dir / "photos"
    photos4.mkdir(parents=True)

    run_index = {
        "cases": [
            {"case_id": "case-ok", "category": "box", "image_path": str(orig_img), "output_dir": str(case1_dir)},
            {"case_id": "case-partial", "category": "ceramic", "image_path": str(orig_img), "output_dir": str(case2_dir)},
            {"case_id": "case-severe", "category": "metalware", "image_path": str(orig_img), "output_dir": str(case3_dir)},
            {"case_id": "case-missing", "category": "textile", "image_path": str(orig_img), "output_dir": str(case4_dir)},
        ]
    }
    (pilot_dir / "run_index.json").write_text(json.dumps(run_index), encoding="utf-8")

    result = check_cutout_fidelity.evaluate_cutout_fidelity(
        pilot_dir=pilot_dir,
        roles=["hero"],
        ok_threshold=0.6,
        severe_threshold=0.25,
    )

    judgments = {r["case_id"]: r["judgment"] for r in result["records"]}
    assert judgments["case-ok"] == "OK"
    assert judgments["case-partial"] == "부분 손실"
    assert judgments["case-severe"] == "심각 손실"
    assert judgments["case-missing"] == "산출물 누락"

    summary = result["summary"]
    assert summary["ok_count"] == 1
    assert summary["partial_loss_count"] == 1
    assert summary["severe_loss_count"] == 2  # severe + missing


def test_cutout_fidelity_detects_enclosed_background_and_preserves_sparse_product(
    tmp_path: Path,
) -> None:
    """Catch source-colored closed residue without calling a sparse open product lost."""
    pilot_dir = tmp_path / "pilot"
    pilot_dir.mkdir()

    residue_source = tmp_path / "residue-source.png"
    Image.new("RGB", (100, 100), (140, 140, 140)).save(residue_source)
    residue_photo_dir = pilot_dir / "residue" / "photos"
    residue_photo_dir.mkdir(parents=True)
    residue_output = Image.new("RGB", (100, 100), (255, 255, 255))
    residue_draw = ImageDraw.Draw(residue_output)
    residue_draw.rectangle((20, 20, 80, 80), outline=(30, 30, 30), width=6)
    residue_draw.rectangle((28, 28, 72, 72), fill=(140, 140, 140))
    residue_output.save(residue_photo_dir / "01-hero.png")

    sparse_source = tmp_path / "sparse-source.png"
    sparse_original = Image.new("RGB", (100, 100), (220, 220, 220))
    sparse_draw = ImageDraw.Draw(sparse_original)
    sparse_draw.line(((20, 20), (20, 80), (80, 80), (80, 20)), fill=(20, 20, 20), width=5)
    sparse_original.save(sparse_source)
    sparse_photo_dir = pilot_dir / "sparse" / "photos"
    sparse_photo_dir.mkdir(parents=True)
    sparse_output = Image.new("RGB", (100, 100), (255, 255, 255))
    ImageDraw.Draw(sparse_output).line(
        ((20, 20), (20, 80), (80, 80), (80, 20)), fill=(20, 20, 20), width=5
    )
    sparse_output.save(sparse_photo_dir / "01-hero.png")

    (pilot_dir / "run_index.json").write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "residue",
                        "category": "jewelry",
                        "image_path": str(residue_source),
                        "output_dir": str(pilot_dir / "residue"),
                    },
                    {
                        "case_id": "sparse",
                        "category": "jewelry",
                        "image_path": str(sparse_source),
                        "output_dir": str(pilot_dir / "sparse"),
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    residue_ratio = check_cutout_fidelity.calculate_enclosed_background_ratio(
        residue_source, residue_photo_dir / "01-hero.png"
    )
    assert residue_ratio > 0.10

    result = check_cutout_fidelity.evaluate_cutout_fidelity(pilot_dir=pilot_dir, roles=["hero"])
    records = {record["case_id"]: record for record in result["records"]}

    assert records["residue"]["judgment"] == "배경 잔존"
    assert records["residue"]["background_residual_ratio"] > 0.10
    assert records["sparse"]["judgment"] == "OK"
    assert records["sparse"]["source_foreground_density"] <= 0.30
    assert records["sparse"]["preservation_ratio"] > 0.60
    assert result["summary"]["background_residual_count"] == 1
    assert result["summary"]["has_background_residual"] is True


def test_cutout_fidelity_reports_source_fallback_as_not_performed(tmp_path: Path) -> None:
    """A byte-identical source fallback is not evidence that a cutout succeeded."""
    pilot_dir = tmp_path / "pilot"
    pilot_dir.mkdir()
    original = tmp_path / "source.png"
    Image.new("RGB", (100, 100), (30, 30, 30)).save(original)

    case_dir = pilot_dir / "fallback"
    photos_dir = case_dir / "photos"
    photos_dir.mkdir(parents=True)
    Image.new("RGB", (100, 100), (30, 30, 30)).save(photos_dir / "01-hero.png")
    (case_dir / "result_summary.json").write_text(
        json.dumps(
            {
                "detail_page": {
                    "photos": [
                        {
                            "photo_id": "hero",
                            "asset_mode": "source",
                            "fidelity_status": "FALLBACK",
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    (pilot_dir / "run_index.json").write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "fallback",
                        "category": "textile",
                        "image_path": str(original),
                        "output_dir": str(case_dir),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = check_cutout_fidelity.evaluate_cutout_fidelity(pilot_dir=pilot_dir, roles=["hero"])
    record = result["records"][0]

    assert record["preservation_ratio"] == 1.0
    assert record["judgment"] == "컷아웃 미수행"
    assert record["asset_mode"] == "source"
    assert record["fidelity_status"] == "FALLBACK"
    assert record["cutout_performed"] is False
    assert record["loss_judgment"] is None
    assert record["background_residual_ratio"] is None
    assert record["renderer_background_hole_ratio"] is None
    assert result["summary"]["cutout_performed_count"] == 0
    assert result["summary"]["cutout_unperformed_count"] == 1
    assert result["summary"]["cutout_performed_rate"] == 0.0
    assert result["summary"]["has_cutout_unperformed"] is True


def test_cutout_fidelity_flags_enclosed_renderer_background_as_product_loss(
    tmp_path: Path,
) -> None:
    """A white hole enclosed by product pixels is cutout erosion, not an open ring void."""
    pilot_dir = tmp_path / "pilot"
    pilot_dir.mkdir()
    original = tmp_path / "source.png"
    Image.new("RGB", (100, 100), (100, 100, 100)).save(original)

    case_dir = pilot_dir / "glaze-hole"
    photos_dir = case_dir / "photos"
    photos_dir.mkdir(parents=True)
    output = Image.new("RGB", (100, 100), (255, 255, 255))
    draw = ImageDraw.Draw(output)
    draw.rectangle((20, 20, 80, 80), fill=(30, 30, 30))
    draw.rectangle((40, 40, 60, 60), fill=(255, 255, 255))
    output.save(photos_dir / "01-hero.png")
    (pilot_dir / "run_index.json").write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "glaze-hole",
                        "category": "ceramic",
                        "image_path": str(original),
                        "output_dir": str(case_dir),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    hole_ratio = check_cutout_fidelity.calculate_enclosed_renderer_background_ratio(
        photos_dir / "01-hero.png"
    )
    assert hole_ratio > 0.01

    result = check_cutout_fidelity.evaluate_cutout_fidelity(pilot_dir=pilot_dir, roles=["hero"])
    record = result["records"][0]
    assert record["renderer_background_hole_ratio"] > 0.01
    assert record["loss_judgment"] == "부분 손실"
    assert record["judgment"] == "부분 손실"


# ==============================================================================
# 4. check_scene_direction_coverage tests
# ==============================================================================

def test_check_scene_direction_coverage_expected_table() -> None:
    """Verify expected branch mapping covers all 6 evaluation categories."""
    expected = check_scene_direction_coverage.CATEGORY_EXPECTED_BRANCH
    required_cats = {"textile", "box", "ceramic", "metalware", "furniture", "jewelry"}

    assert set(expected.keys()) == required_cats
    assert expected["textile"] == "textile"
    assert expected["box"] == "box"
    assert expected["ceramic"] == "ceramic"
    assert expected["metalware"] == "metal"
    assert expected["furniture"] == "wood"
    assert expected["jewelry"] == "jewelry"


def test_compute_summary_and_verdict_logic() -> None:
    """Verify compute_summary accurately tracks matches, misclassifications, and defaults."""
    # 1. All match scenario
    records_all_match = [
        {"category": "textile", "branch": "textile", "match_status": "match"},
        {"category": "box", "branch": "box", "match_status": "match"},
    ]
    summary1 = check_scene_direction_coverage.compute_summary(records_all_match)
    assert summary1["total_count"] == 2
    assert summary1["match_count"] == 2
    assert summary1["misclassified_count"] == 0
    assert summary1["default_count"] == 0

    # 2. Misclassification scenario
    records_misclassified = [
        {"category": "jewelry", "branch": "metal", "match_status": "misclassified"},
        {"category": "box", "branch": "box", "match_status": "match"},
    ]
    summary2 = check_scene_direction_coverage.compute_summary(records_misclassified)
    assert summary2["total_count"] == 2
    assert summary2["match_count"] == 1
    assert summary2["misclassified_count"] == 1
    assert summary2["default_count"] == 0

    # 3. Default (unsupported) scenario
    records_default = [
        {"category": "furniture", "branch": "default", "match_status": "default"},
    ]
    summary3 = check_scene_direction_coverage.compute_summary(records_default)
    assert summary3["default_count"] == 1


def test_check_scene_direction_coverage_fails_on_misclassification(tmp_path: Path) -> None:
    """Verify check_scene_direction_coverage returns exit code 1 when misclassifications occur."""
    mock_pilot = tmp_path / "mock_pilot"
    mock_pilot.mkdir()

    # Case where category is jewelry, but product metadata matches metal keywords instead of jewelry keywords
    case_dir = mock_pilot / "analysis-mismatch"
    case_dir.mkdir()

    summary_data = {
        "product": {
            "product_type": "금속 주물",
            "display_name": "청동 주물 장식",
            "summary": "황동과 청동으로 주조된 금속 장식품입니다.",
            "keywords": ["metal", "금속"],
        }
    }
    (case_dir / "result_summary.json").write_text(json.dumps(summary_data), encoding="utf-8")

    run_index = {
        "cases": [
            {
                "case_id": "analysis-mismatch",
                "asset_id": "cma-test-01",
                "category": "jewelry",  # expected jewelry, but product gets metal
                "output_dir": str(case_dir),
            }
        ]
    }
    (mock_pilot / "run_index.json").write_text(json.dumps(run_index), encoding="utf-8")

    # Strict mode: must return exit code 1 due to misclassification
    exit_code_strict = check_scene_direction_coverage.main(["--pilot-dir", str(mock_pilot)])
    assert exit_code_strict == 1

    # Lenient mode (--strict-off): misclassifications allowed, only default fails -> returns 0
    exit_code_lenient = check_scene_direction_coverage.main(["--pilot-dir", str(mock_pilot), "--strict-off"])
    assert exit_code_lenient == 0
