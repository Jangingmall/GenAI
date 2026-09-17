#!/usr/bin/env python3
"""Build a human review CSV sheet from pilot evaluation outputs.

Reads run_index.json from the specified pilot directory and generates
review_sheet.csv encoded in UTF-8 with BOM (utf-8-sig) for seamless Excel editing.
All score fields are intentionally initialized to empty strings for independent human review.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

REVIEW_COLUMNS: list[str] = [
    "case_id",
    "category",
    "asset_id",
    "입력 이미지 경로",
    "산출물 경로",
    "실행 성공 여부",
    "에러 메시지",
    "검수자A_사실성",
    "검수자A_명료성",
    "검수자A_상품성",
    "검수자A_시각품질",
    "검수자A_코멘트",
    "검수자B_사실성",
    "검수자B_명료성",
    "검수자B_상품성",
    "검수자B_시각품질",
    "검수자B_코멘트",
    "합의_사실성",
    "합의_명료성",
    "합의_상품성",
    "합의_시각품질",
    "합의_메모",
]


def load_run_index(pilot_dir: Path) -> dict[str, Any]:
    """Load and parse run_index.json from pilot directory."""
    index_file = pilot_dir / "run_index.json"
    if not index_file.exists():
        raise FileNotFoundError(f"run_index.json not found in {pilot_dir}")

    try:
        data = json.loads(index_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise ValueError(f"Invalid JSON in {index_file}: {err}") from err

    return data


def build_review_rows(run_index: dict[str, Any]) -> list[dict[str, str]]:
    """Convert cases in run_index into review sheet rows.

    Note: All score columns are strictly left blank for reviewers.
    """
    cases = run_index.get("cases", [])
    rows: list[dict[str, str]] = []

    for case in cases:
        is_success = bool(case.get("success", False))
        status_label = "성공" if is_success else "실패"
        error_msg = "" if is_success else str(case.get("error") or "").strip()

        row: dict[str, str] = {
            "case_id": str(case.get("case_id", "")),
            "category": str(case.get("category", "")),
            "asset_id": str(case.get("asset_id", "")),
            "입력 이미지 경로": str(case.get("image_path", "")),
            "산출물 경로": str(case.get("output_dir", "")),
            "실행 성공 여부": status_label,
            "에러 메시지": error_msg,
            # Reviewer score columns MUST remain empty
            "검수자A_사실성": "",
            "검수자A_명료성": "",
            "검수자A_상품성": "",
            "검수자A_시각품질": "",
            "검수자A_코멘트": "",
            "검수자B_사실성": "",
            "검수자B_명료성": "",
            "검수자B_상품성": "",
            "검수자B_시각품질": "",
            "검수자B_코멘트": "",
            "합의_사실성": "",
            "합의_명료성": "",
            "합의_상품성": "",
            "합의_시각품질": "",
            "합의_메모": "",
        }
        rows.append(row)

    return rows


def build_review_sheet(pilot_dir: Path, output_path: Path | None = None) -> Path:
    """Build review_sheet.csv from run_index.json in pilot_dir."""
    pilot_dir = Path(pilot_dir).resolve()
    if not pilot_dir.is_dir():
        raise NotADirectoryError(f"Pilot directory does not exist or is not a directory: {pilot_dir}")

    run_index = load_run_index(pilot_dir)
    rows = build_review_rows(run_index)

    target_csv = (output_path or (pilot_dir / "review_sheet.csv")).resolve()
    target_csv.parent.mkdir(parents=True, exist_ok=True)

    with open(target_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    return target_csv


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate human review CSV sheet (review_sheet.csv) from pilot evaluation output."
    )
    parser.add_argument(
        "--pilot-dir",
        type=Path,
        dest="pilot_dir",
        default=None,
        help="Path to pilot run directory containing run_index.json.",
    )
    parser.add_argument(
        "pilot_dir_pos",
        nargs="?",
        type=Path,
        default=None,
        help="Positional path to pilot directory (fallback if --pilot-dir is omitted).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Optional explicit output path for review_sheet.csv (default: <pilot-dir>/review_sheet.csv).",
    )
    parsed = parser.parse_args(args)
    if parsed.pilot_dir is None:
        if parsed.pilot_dir_pos is not None:
            parsed.pilot_dir = parsed.pilot_dir_pos
        else:
            parser.error("The --pilot-dir argument is required.")
    return parsed


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        csv_path = build_review_sheet(args.pilot_dir, args.output)
        print(f"[SUCCESS] Review sheet created: {csv_path}")
        return 0
    except Exception as exc:
        print(f"[ERROR] Failed to build review sheet: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
