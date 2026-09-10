from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.check_reference_label import (
    evaluate_case,
    evaluate_pilot,
    main,
)

PILOT_164008_DIR = Path("generated/evaluation/pilot-20260910-164008")
PILOT_161310_DIR = Path("generated/evaluation/pilot-20260910-161310")


def _make_sample_doc(*, lifestyle_has_label: bool = False, hero_has_label: bool = False) -> dict[str, Any]:
    lifestyle_figure_children: list[dict[str, Any]] = [
        {
            "id": "section-05-lifestyle-img",
            "type": "element",
            "tag": "img",
            "props": {
                "imageId": "lifestyle",
                "alt": "활용 장면",
            },
            "children": [],
        }
    ]
    if lifestyle_has_label:
        lifestyle_figure_children.append(
            {
                "id": "section-05-lifestyle-caption",
                "type": "element",
                "tag": "figcaption",
                "children": [
                    {
                        "id": "section-05-lifestyle-caption-text",
                        "type": "text",
                        "value": "AI 생성 활용 장면(참고용)",
                    }
                ],
            }
        )

    hero_figure_children: list[dict[str, Any]] = [
        {
            "id": "section-01-hero-img",
            "type": "element",
            "tag": "img",
            "props": {
                "imageId": "hero",
                "alt": "대표 이미지",
            },
            "children": [],
        }
    ]
    if hero_has_label:
        hero_figure_children.append(
            {
                "id": "section-01-hero-caption",
                "type": "element",
                "tag": "figcaption",
                "children": [
                    {
                        "id": "section-01-hero-caption-text",
                        "type": "text",
                        "value": "원본 보존(참고용)",
                    }
                ],
            }
        )

    return {
        "schemaVersion": "2.0",
        "canvasWidth": 774,
        "root": [
            {
                "id": "section-01",
                "type": "element",
                "tag": "section",
                "children": [
                    {
                        "id": "section-01-figure",
                        "type": "element",
                        "tag": "figure",
                        "children": hero_figure_children,
                    }
                ],
            },
            {
                "id": "section-05",
                "type": "element",
                "tag": "section",
                "children": [
                    {
                        "id": "section-05-figure",
                        "type": "element",
                        "tag": "figure",
                        "children": lifestyle_figure_children,
                    }
                ],
            },
        ],
    }


def _make_sample_summary(*, has_generated: bool = True) -> dict[str, Any]:
    photos: list[dict[str, Any]] = [
        {
            "photo_id": "hero",
            "label": "원본 보존 대표 이미지",
            "product_generated": False,
        },
        {
            "photo_id": "packshot",
            "label": "원본 보존 팩샷",
            "product_generated": False,
        },
    ]
    if has_generated:
        photos.append(
            {
                "photo_id": "lifestyle",
                "label": "AI 생성 활용 장면(참고용)",
                "product_generated": True,
            }
        )
        photos.append(
            {
                "photo_id": "detail-02",
                "label": "AI 생성 디테일(참고용)",
                "product_generated": True,
            }
        )
    return {
        "category": "craft_tableware",
        "detail_page": {
            "photos": photos,
        },
    }


def test_pilot_164008_produces_fail_and_exit_code_1():
    """Gate verification against pre-fix pilot run must report FAIL (exit code 1)."""
    assert PILOT_164008_DIR.is_dir(), "pilot-20260910-164008 directory must exist"

    results = evaluate_pilot(PILOT_164008_DIR)
    summary = results["summary"]

    assert summary["all_passed"] is False
    assert summary["total_cases"] == 6
    assert summary["fail_count"] == 6
    assert summary["pass_count"] == 0
    assert summary["missing_label_cases"] == 6
    assert summary["false_positive_cases"] == 0
    assert summary["html_unverifiable"] == 6

    # Verify each case has expected missing label
    for case in results["cases"]:
        assert case["judgment"] == "FAIL"
        assert len(case["missing_doc_targets"]) > 0
        assert case["false_positive_sources"] == []
        assert case["html_status"] == "확인 불가"

    exit_code = main(["--pilot-dir", str(PILOT_164008_DIR)])
    assert exit_code == 1


def test_pilot_161310_all_na_passes():
    """Gate verification against zero-generated-photo pilot must report PASS (exit code 0)."""
    if not PILOT_161310_DIR.is_dir():
        pytest.skip("pilot-20260910-161310 not found")

    results = evaluate_pilot(PILOT_161310_DIR)
    summary = results["summary"]

    assert summary["all_passed"] is True
    assert summary["fail_count"] == 0
    assert summary["na_count"] == 6

    exit_code = main(["--pilot-dir", str(PILOT_161310_DIR)])
    assert exit_code == 0


def test_synthetic_passing_case(tmp_path: Path):
    """Case passes when generated photo has reference label in react_document."""
    case_dir = tmp_path / "case_01"
    case_dir.mkdir()

    summary_data = _make_sample_summary(has_generated=True)
    doc_data = _make_sample_doc(lifestyle_has_label=True, hero_has_label=False)

    (case_dir / "result_summary.json").write_text(json.dumps(summary_data), encoding="utf-8")
    (case_dir / "react_document.json").write_text(json.dumps(doc_data), encoding="utf-8")

    case_result = evaluate_case(case_dir)

    assert case_result["judgment"] == "PASS"
    assert case_result["used_targets"] == ["lifestyle"]
    assert case_result["missing_doc_targets"] == []
    assert case_result["false_positive_sources"] == []
    assert case_result["html_status"] == "확인 불가"  # HTML absent does not cause failure


def test_synthetic_false_positive_failure_on_source_photo(tmp_path: Path):
    """Rule 4: Mislabeled source photo must trigger FAIL."""
    case_dir = tmp_path / "case_fp"
    case_dir.mkdir()

    summary_data = _make_sample_summary(has_generated=True)
    # Both lifestyle and hero have labels; hero is source photo -> FAIL
    doc_data = _make_sample_doc(lifestyle_has_label=True, hero_has_label=True)

    (case_dir / "result_summary.json").write_text(json.dumps(summary_data), encoding="utf-8")
    (case_dir / "react_document.json").write_text(json.dumps(doc_data), encoding="utf-8")

    case_result = evaluate_case(case_dir)

    assert case_result["judgment"] == "FAIL"
    assert "hero" in case_result["false_positive_sources"]
    assert "원본" in case_result["reason"]


def test_synthetic_missing_generated_label_failure(tmp_path: Path):
    """Rule 2: Generated photo without label triggers FAIL."""
    case_dir = tmp_path / "case_missing"
    case_dir.mkdir()

    summary_data = _make_sample_summary(has_generated=True)
    # Lifestyle lacks label
    doc_data = _make_sample_doc(lifestyle_has_label=False, hero_has_label=False)

    (case_dir / "result_summary.json").write_text(json.dumps(summary_data), encoding="utf-8")
    (case_dir / "react_document.json").write_text(json.dumps(doc_data), encoding="utf-8")

    case_result = evaluate_case(case_dir)

    assert case_result["judgment"] == "FAIL"
    assert "lifestyle" in case_result["missing_doc_targets"]
    assert "라벨 누락" in case_result["reason"]


def test_synthetic_zero_generated_photos_is_na(tmp_path: Path):
    """Rule 1: Case with 0 generated photos is N/A."""
    case_dir = tmp_path / "case_none"
    case_dir.mkdir()

    summary_data = _make_sample_summary(has_generated=False)
    doc_data = _make_sample_doc(lifestyle_has_label=False, hero_has_label=False)

    (case_dir / "result_summary.json").write_text(json.dumps(summary_data), encoding="utf-8")
    (case_dir / "react_document.json").write_text(json.dumps(doc_data), encoding="utf-8")

    case_result = evaluate_case(case_dir)

    assert case_result["judgment"] == "해당 없음"
    assert case_result["target_count"] == 0


def test_synthetic_html_verification(tmp_path: Path):
    """Rule 3: HTML render checks when HTML exists vs missing."""
    case_dir = tmp_path / "case_html"
    case_dir.mkdir()

    summary_data = _make_sample_summary(has_generated=True)
    doc_data = _make_sample_doc(lifestyle_has_label=True, hero_has_label=False)

    (case_dir / "result_summary.json").write_text(json.dumps(summary_data), encoding="utf-8")
    (case_dir / "react_document.json").write_text(json.dumps(doc_data), encoding="utf-8")

    # 1. HTML with label -> PASS & 확인 완료
    html_file = case_dir / "detail_page.html"
    html_file.write_text(
        "<html><body><figure><img src='lifestyle.png'><figcaption class='generated-photo-label'>AI 생성 활용 장면(참고용)</figcaption></figure></body></html>",
        encoding="utf-8",
    )
    result_with_html = evaluate_case(case_dir)
    assert result_with_html["judgment"] == "PASS"
    assert result_with_html["html_status"] == "확인 완료"

    # 2. HTML missing label -> FAIL
    html_file.write_text(
        "<html><body><figure><img src='lifestyle.png'></figure></body></html>",
        encoding="utf-8",
    )
    result_html_missing = evaluate_case(case_dir)
    assert result_html_missing["judgment"] == "FAIL"
    assert result_html_missing["html_status"] == "FAIL"

    # 3. HTML deleted -> 확인 불가, but React doc passes so judgment is PASS
    html_file.unlink()
    result_no_html = evaluate_case(case_dir)
    assert result_no_html["judgment"] == "PASS"
    assert result_no_html["html_status"] == "확인 불가"
