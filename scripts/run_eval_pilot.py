#!/usr/bin/env python3
"""Pilot evaluation runner for CMA real v1 dataset (6 cases: 1 per category).

Selects 1 item per category deterministically (asset_id ascending), runs the
local detail-page pipeline sequentially, and saves all artifacts and a structured
run_index.json summary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from detail_page_ai.dto import GenerationOptions, UserHintsDto
from local_detail_page_ai.runner import build_local_pipeline, save_pipeline_result

DEFAULT_CATEGORIES = [
    "textile",
    "box",
    "metalware",
    "ceramic",
    "jewelry",
    "furniture",
]


def select_pilot_cases(
    manifest_path: Path,
    analysis_path: Path,
) -> list[dict[str, Any]]:
    """Select 1 item per category deterministically (asset_id ascending)."""
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest file not found: {manifest_path}")
    if not analysis_path.exists():
        raise FileNotFoundError(f"Analysis file not found: {analysis_path}")

    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assets = manifest_data.get("assets", [])

    # Load analysis cases by asset_id
    cases_by_asset: dict[str, dict[str, Any]] = {}
    with open(analysis_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            cases_by_asset[item["asset_id"]] = item

    # Group assets by category
    by_category: dict[str, list[dict[str, Any]]] = {}
    for asset in assets:
        cat = asset.get("category", "unknown")
        by_category.setdefault(cat, []).append(asset)

    # Determine category order (canonical order first, then any extra sorted)
    all_cats = list(by_category.keys())
    ordered_cats = [c for c in DEFAULT_CATEGORIES if c in all_cats] + sorted(
        [c for c in all_cats if c not in DEFAULT_CATEGORIES]
    )

    selected: list[dict[str, Any]] = []
    manifest_dir = manifest_path.parent

    for cat in ordered_cats:
        cat_assets = sorted(by_category[cat], key=lambda a: a["asset_id"])
        chosen_asset = cat_assets[0]
        asset_id = chosen_asset["asset_id"]
        case = cases_by_asset.get(asset_id, {})

        # Resolve image path
        raw_img_path = chosen_asset.get("image_path") or case.get("image_path")
        resolved_img_path = None
        for candidate in [
            manifest_dir / raw_img_path,
            PROJECT_ROOT / raw_img_path,
            Path(raw_img_path),
        ]:
            if candidate.exists():
                resolved_img_path = candidate
                break

        if resolved_img_path is None:
            resolved_img_path = manifest_dir / raw_img_path

        selected.append(
            {
                "category": cat,
                "asset_id": asset_id,
                "case_id": case.get("case_id", f"analysis-{asset_id}"),
                "image_path": str(resolved_img_path),
                "relative_image_path": raw_img_path,
                "sha256": chosen_asset.get("sha256", ""),
                "metadata": case.get("metadata", {}),
                "checks": case.get("checks", []),
                "reference_facts": chosen_asset.get("reference_facts", {}),
                "title": chosen_asset.get("title", ""),
            }
        )

    return selected


def print_dry_run(selected_cases: list[dict[str, Any]]) -> None:
    print("=" * 72)
    print(
        f"[DRY-RUN] Selected {len(selected_cases)} pilot cases (1 per category, asset_id asc):"
    )
    print("=" * 72)
    for idx, case in enumerate(selected_cases, start=1):
        meta = case.get("metadata", {})
        print(f"[{idx}] Category:   {case['category']}")
        print(f"    Case ID:    {case['case_id']}")
        print(f"    Asset ID:   {case['asset_id']}")
        print(f"    Title:      {case['title']}")
        print(f"    Image Path: {case['image_path']}")
        print(f"    SHA-256:    {case['sha256']}")
        print(f"    Product ID: {meta.get('product_id', case['asset_id'])}")
        print(f"    Options:    {meta.get('options', {})}")
        print(f"    User Hints: {meta.get('user_hints', {})}")
        print()
    print("=" * 72)
    print("Dry-run complete. No models were invoked.")


def run_pilot(args: argparse.Namespace) -> int:
    selected_cases = select_pilot_cases(args.manifest, args.analysis)

    if args.dry_run:
        print_dry_run(selected_cases)
        return 0

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if args.output_dir is not None:
        output_dir = Path(args.output_dir)
    else:
        output_dir = args.output_base / f"pilot-{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    pipeline = build_local_pipeline(
        text_url=args.text_url,
        text_model=args.text_model,
        text_timeout=args.text_timeout,
        generate_product_photos=not args.no_product_photos,
        text_provider=args.text_provider,
        image_provider=args.image_provider,
        image_url=args.image_url,
        image_model=args.image_model,
        image_timeout=args.image_timeout,
    )

    pilot_start_dt = datetime.now(timezone.utc).astimezone()
    case_records: list[dict[str, Any]] = []

    print(f"Starting pilot evaluation run: {len(selected_cases)} cases")
    print(f"Output directory: {output_dir}")
    print(f"Text model:  {args.text_model} ({args.text_url})")
    print(f"Image model: {args.image_model} ({args.image_url})")
    print("-" * 72)

    for idx, case in enumerate(selected_cases, start=1):
        case_id = case["case_id"]
        asset_id = case["asset_id"]
        category = case["category"]
        case_output_dir = output_dir / case_id

        print(
            f"[{idx}/{len(selected_cases)}] Running {case_id} (cat: {category}, asset: {asset_id})..."
        )
        case_start_dt = datetime.now(timezone.utc).astimezone()
        case_start_perf = time.perf_counter()

        record: dict[str, Any] = {
            "case_id": case_id,
            "asset_id": asset_id,
            "category": category,
            "image_path": str(case["image_path"]),
            "sha256": case["sha256"],
            "text_model": args.text_model,
            "image_model": args.image_model if args.image_provider == "mlx" else "none",
            "started_at": case_start_dt.isoformat(),
            "ended_at": None,
            "duration_seconds": None,
            "success": False,
            "error": None,
            "error_trace": None,
            "output_dir": str(case_output_dir),
        }

        try:
            img_path = Path(case["image_path"])
            if not img_path.exists():
                raise FileNotFoundError(f"Input image file not found: {img_path}")
            source_image = img_path.read_bytes()
            mime_type = mimetypes.guess_type(img_path.name)[0] or "image/jpeg"

            actual_hash = hashlib.sha256(source_image).hexdigest()
            if case["sha256"] and actual_hash != case["sha256"]:
                raise ValueError(
                    f"SHA256 mismatch for {asset_id}: expected {case['sha256']}, got {actual_hash}"
                )

            meta = case.get("metadata", {})
            user_hints_raw = meta.get("user_hints") or {}
            user_hints = UserHintsDto(
                product_name=user_hints_raw.get("product_name"),
                making_method=user_hints_raw.get("making_method"),
                care_guide=user_hints_raw.get("care_guide"),
            )
            raw_options = meta.get("options") or {}
            options = GenerationOptions(
                aspect_ratio=raw_options.get("aspect_ratio", "1:4"),
                image_size=raw_options.get("image_size", "2K"),
                output_mime_type=raw_options.get("output_mime_type", "image/png"),
            )

            result = pipeline.run(
                job_id=str(uuid.uuid4()),
                request_id=str(uuid.uuid4()),
                source_image=source_image,
                source_mime_type=mime_type,
                options=options,
                user_hints=user_hints,
                product_id=meta.get("product_id") or asset_id,
                source_asset_id=asset_id,
            )

            saved_path = save_pipeline_result(result, case_output_dir)
            record["idempotency_key"] = meta.get("idempotency_key")
            record["success"] = True
            record["output_dir"] = str(saved_path)
            print(f"  -> SUCCESS ({round(time.perf_counter() - case_start_perf, 2)}s)")
        except Exception as exc:
            record["success"] = False
            record["error"] = f"{type(exc).__name__}: {exc}"
            record["error_trace"] = traceback.format_exc()
            print(f"  -> FAILED: {record['error']}")
        finally:
            case_end_dt = datetime.now(timezone.utc).astimezone()
            record["ended_at"] = case_end_dt.isoformat()
            record["duration_seconds"] = round(
                time.perf_counter() - case_start_perf, 2
            )
            case_records.append(record)

            # Persist run_index incrementally after every case
            run_index = {
                "pilot_id": output_dir.name,
                "started_at": pilot_start_dt.isoformat(),
                "ended_at": datetime.now(timezone.utc).astimezone().isoformat(),
                "total_cases": len(selected_cases),
                "completed_cases": len(case_records),
                "successful_cases": sum(1 for r in case_records if r["success"]),
                "failed_cases": sum(1 for r in case_records if not r["success"]),
                "text_model": args.text_model,
                "image_model": args.image_model,
                "text_url": args.text_url,
                "image_url": args.image_url,
                "cases": case_records,
            }
            (output_dir / "run_index.json").write_text(
                json.dumps(run_index, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    print("-" * 72)
    successful = sum(1 for r in case_records if r["success"])
    failed = sum(1 for r in case_records if not r["success"])
    print(f"Pilot evaluation finished: {successful} succeeded, {failed} failed.")
    print(f"Summary written to: {output_dir / 'run_index.json'}")
    return 0 if failed == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run pilot evaluation: select 1 case per category (6 total) and run local pipeline."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Select and display the 6 pilot cases without invoking models or writing outputs.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=PROJECT_ROOT / "data/evaluation/cma_real_v1/manifest.json",
        help="Path to manifest.json (default: data/evaluation/cma_real_v1/manifest.json)",
    )
    parser.add_argument(
        "--analysis",
        type=Path,
        default=PROJECT_ROOT / "data/evaluation/cma_real_v1/analysis_60.jsonl",
        help="Path to analysis_60.jsonl (default: data/evaluation/cma_real_v1/analysis_60.jsonl)",
    )
    parser.add_argument(
        "--output-base",
        type=Path,
        default=PROJECT_ROOT / "generated/evaluation",
        help="Base directory for pilot output runs (default: generated/evaluation)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Explicit output directory. If omitted, generated/evaluation/pilot-<YYYYMMDD-HHMMSS> is used.",
    )
    parser.add_argument(
        "--text-url",
        default="http://127.0.0.1:11234",
        help="Text model server URL (default: http://127.0.0.1:11234)",
    )
    parser.add_argument(
        "--text-model",
        default="ddalcu/Qwen3.8-27B-MLX-Serve-4bit",
        help="Text model ID (default: ddalcu/Qwen3.8-27B-MLX-Serve-4bit)",
    )
    parser.add_argument(
        "--text-timeout",
        type=float,
        default=300.0,
        help="Text model timeout in seconds (default: 300.0)",
    )
    parser.add_argument(
        "--text-provider",
        choices=("ollama", "mlx"),
        default="mlx",
        help="Text model provider (default: mlx)",
    )
    parser.add_argument(
        "--image-provider",
        choices=("none", "mlx"),
        default="mlx",
        help="Image model provider (default: mlx)",
    )
    parser.add_argument(
        "--image-url",
        default="http://127.0.0.1:11234",
        help="Image model server URL (default: http://127.0.0.1:11234)",
    )
    parser.add_argument(
        "--image-model",
        default="mlx-community/flux2-klein-9b-4bit",
        help="Image model ID (default: mlx-community/flux2-klein-9b-4bit)",
    )
    parser.add_argument(
        "--image-timeout",
        type=float,
        default=300.0,
        help="Image model timeout in seconds (default: 300.0)",
    )
    parser.add_argument(
        "--no-product-photos",
        action="store_true",
        help="Use the primary source image without generating source-preserving role cuts.",
    )
    args = parser.parse_args()
    sys.exit(run_pilot(args))


if __name__ == "__main__":
    main()
