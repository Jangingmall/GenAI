import argparse
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts import run_eval_pilot

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "data/evaluation/cma_real_v1/manifest.json"
ANALYSIS_PATH = PROJECT_ROOT / "data/evaluation/cma_real_v1/analysis_60.jsonl"


def test_select_pilot_cases_default_mode() -> None:
    """Default mode selects 1 case per category (6 total)."""
    selected = run_eval_pilot.select_pilot_cases(MANIFEST_PATH, ANALYSIS_PATH)
    assert len(selected) == 6
    categories = [c["category"] for c in selected]
    assert categories == run_eval_pilot.DEFAULT_CATEGORIES


def test_select_pilot_cases_all_mode() -> None:
    """--all mode selects all 60 cases from manifest across 6 categories."""
    selected = run_eval_pilot.select_pilot_cases(
        MANIFEST_PATH, ANALYSIS_PATH, all_cases=True
    )
    assert len(selected) == 60

    by_cat: dict[str, list[dict]] = {}
    for c in selected:
        by_cat.setdefault(c["category"], []).append(c)

    assert set(by_cat.keys()) == set(run_eval_pilot.DEFAULT_CATEGORIES)
    for cat, items in by_cat.items():
        assert len(items) == 10
        # Ensure asset_ids are sorted ascending within category
        asset_ids = [item["asset_id"] for item in items]
        assert asset_ids == sorted(asset_ids)


def test_select_pilot_cases_with_limit() -> None:
    """--limit caps the selected cases to N."""
    selected_3 = run_eval_pilot.select_pilot_cases(
        MANIFEST_PATH, ANALYSIS_PATH, all_cases=False, limit=3
    )
    assert len(selected_3) == 3

    selected_15 = run_eval_pilot.select_pilot_cases(
        MANIFEST_PATH, ANALYSIS_PATH, all_cases=True, limit=15
    )
    assert len(selected_15) == 15

    with pytest.raises(ValueError, match="limit must be non-negative"):
        run_eval_pilot.select_pilot_cases(
            MANIFEST_PATH, ANALYSIS_PATH, all_cases=True, limit=-1
        )


def test_dry_run_cli(capsys: pytest.CaptureFixture[str]) -> None:
    """--dry-run prints pilot cases and exits 0 without writing files."""
    args = argparse.Namespace(
        dry_run=True,
        all=False,
        all_cases=False,
        limit=None,
        resume=False,
        manifest=MANIFEST_PATH,
        analysis=ANALYSIS_PATH,
        output_dir=None,
        output_base=Path("/tmp/eval-test-nonexistent"),
    )
    code = run_eval_pilot.run_pilot(args)
    assert code == 0
    captured = capsys.readouterr()
    assert "[DRY-RUN] Selected 6 pilot cases" in captured.out
    assert "Dry-run complete. No models were invoked." in captured.out


def test_all_dry_run_cli(capsys: pytest.CaptureFixture[str]) -> None:
    """--all --dry-run prints 60 cases and exits 0."""
    args = argparse.Namespace(
        dry_run=True,
        all=True,
        all_cases=True,
        limit=None,
        resume=False,
        manifest=MANIFEST_PATH,
        analysis=ANALYSIS_PATH,
        output_dir=None,
        output_base=Path("/tmp/eval-test-nonexistent"),
    )
    code = run_eval_pilot.run_pilot(args)
    assert code == 0
    captured = capsys.readouterr()
    assert "[DRY-RUN] Selected 60 cases (all cases in manifest, asset_id asc):" in captured.out
    assert "[60] Category:   furniture" in captured.out
    assert "Dry-run complete. No models were invoked." in captured.out


def test_incremental_run_index_and_metadata(tmp_path: Path) -> None:
    """run_index.json is written incrementally and has clear metadata fields."""
    output_dir = tmp_path / "test-run"
    args = argparse.Namespace(
        text_model="test-text-model",
        image_model="mlx-community/flux2-klein-9b-4bit",
        image_provider="none",  # explicitly none
        text_url="http://127.0.0.1:11234",
        image_url="http://127.0.0.1:11234",
    )
    output_dir.mkdir(parents=True)
    records = [
        {
            "case_id": "case-1",
            "asset_id": "cma-1",
            "category": "textile",
            "image_model": "none",
            "success": True,
        }
    ]

    run_eval_pilot._write_run_index(
        output_dir=output_dir,
        pilot_id="test-run",
        started_at="2026-09-10T12:00:00Z",
        total_cases=6,
        case_records=records,
        args=args,
    )

    index_file = output_dir / "run_index.json"
    assert index_file.is_file()
    data = json.loads(index_file.read_text(encoding="utf-8"))

    assert data["total_cases"] == 6
    assert data["completed_cases"] == 1
    assert data["successful_cases"] == 1
    assert data["failed_cases"] == 0
    assert data["image_generated_cases"] == 0
    assert data["configured_image_model"] == "mlx-community/flux2-klein-9b-4bit"
    assert data["image_model"] == "none"
    assert data["image_provider"] == "none"


def test_resume_skips_completed_cases(tmp_path: Path) -> None:
    """--resume skips cases where result_summary.json exists and preserves records."""
    output_dir = tmp_path / "resume-run"
    output_dir.mkdir(parents=True)

    # Pre-populate case 1 as completed with result_summary.json
    case1_dir = output_dir / "analysis-cma-102980"
    case1_dir.mkdir(parents=True)
    (case1_dir / "result_summary.json").write_text("{}", encoding="utf-8")

    # Mock pipeline and save_pipeline_result
    mock_pipeline = MagicMock()
    mock_pipeline.run.return_value = MagicMock()

    with patch("scripts.run_eval_pilot.build_local_pipeline", return_value=mock_pipeline):
        with patch("scripts.run_eval_pilot.save_pipeline_result", return_value=case1_dir):
            args = argparse.Namespace(
                dry_run=False,
                all=False,
                all_cases=False,
                limit=2,  # test only first 2 cases
                resume=True,
                manifest=MANIFEST_PATH,
                analysis=ANALYSIS_PATH,
                output_dir=output_dir,
                output_base=tmp_path,
                text_url="http://fake",
                text_model="fake-text",
                text_timeout=10.0,
                text_provider="mlx",
                image_provider="none",
                image_url="http://fake",
                image_model="none",
                image_timeout=10.0,
                no_product_photos=True,
            )
            exit_code = run_eval_pilot.run_pilot(args)
            assert exit_code == 0

    # Pipeline run should have been called only ONCE (for case 2, since case 1 was skipped)
    assert mock_pipeline.run.call_count == 1

    # Check run_index.json
    index_file = output_dir / "run_index.json"
    assert index_file.is_file()
    index_data = json.loads(index_file.read_text(encoding="utf-8"))
    assert index_data["total_cases"] == 2
    assert index_data["completed_cases"] == 2
    assert index_data["successful_cases"] == 2
    assert len(index_data["cases"]) == 2
    assert index_data["cases"][0]["case_id"] == "analysis-cma-102980"
    assert index_data["cases"][0]["success"] is True
