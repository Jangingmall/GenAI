#!/usr/bin/env python3
"""Cutout fidelity regression evaluation tool.

Evaluates how well product cutouts in generated pilot outputs preserve
the original product by comparing non-background (ink) pixel ratios.
Uses Pillow only (no numpy or external dependencies).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def calculate_ink_ratio(
    image_path: Path,
    brightness_threshold: int = 235,
    resample_size: int = 256,
) -> float:
    """Calculate non-background (ink) pixel ratio using Pillow only.

    Pixels with grayscale brightness < brightness_threshold are counted as ink.
    """
    if not image_path.is_file():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    with Image.open(image_path) as img:
        # Handle transparent RGBA / LA images by compositing onto white
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            mask = img.split()[-1] if img.mode in ("RGBA", "LA") else None
            bg.paste(img.convert("RGB"), mask=mask)
            gray = bg.convert("L")
        else:
            gray = img.convert("L")

        resized = gray.resize((resample_size, resample_size))
        hist = resized.histogram()
        total_pixels = resample_size * resample_size
        ink_count = sum(hist[:brightness_threshold])
        return ink_count / total_pixels


def find_photos_for_roles(photos_dir: Path, target_roles: list[str]) -> list[tuple[str, Path]]:
    """Find photo files in photos_dir matching target_roles."""
    if not photos_dir.is_dir():
        return []

    image_extensions = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
    all_files = sorted(
        [f for f in photos_dir.iterdir() if f.is_file() and f.suffix.lower() in image_extensions],
        key=lambda p: p.name,
    )

    matched: list[tuple[str, Path]] = []
    want_all = "all" in target_roles

    for f in all_files:
        stem = f.stem
        # Extract role/photo_id: e.g. '01-hero' -> 'hero', '05-detail-02' -> 'detail-02'
        if "-" in stem and stem.split("-", 1)[0].isdigit():
            role = stem.split("-", 1)[1]
        else:
            role = stem

        if want_all or role.lower() in target_roles:
            matched.append((role, f))

    return matched


def evaluate_cutout_fidelity(
    pilot_dir: Path,
    roles: list[str],
    brightness_threshold: int = 235,
    ok_threshold: float = 0.6,
    severe_threshold: float = 0.25,
    resample_size: int = 256,
) -> dict[str, Any]:
    """Evaluate cutout fidelity across all cases in run_index.json."""
    index_file = pilot_dir / "run_index.json"
    if not index_file.is_file():
        raise FileNotFoundError(f"run_index.json not found in {pilot_dir}")

    try:
        run_index = json.loads(index_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise ValueError(f"Invalid JSON in {index_file}: {err}") from err

    cases = run_index.get("cases", [])
    records: list[dict[str, Any]] = []

    for case in cases:
        case_id = case.get("case_id", "unknown")
        category = case.get("category", "unknown")
        raw_img_path = Path(case.get("image_path", ""))
        raw_out_dir = Path(case.get("output_dir", ""))

        # Resolve original image path
        orig_path = raw_img_path
        if not orig_path.is_absolute():
            for cand in [pilot_dir / orig_path, PROJECT_ROOT / orig_path]:
                if cand.exists():
                    orig_path = cand
                    break

        # Resolve output directory
        out_dir = raw_out_dir
        if not out_dir.is_absolute():
            for cand in [pilot_dir / out_dir, PROJECT_ROOT / out_dir]:
                if cand.exists():
                    out_dir = cand
                    break

        if not orig_path.is_file():
            records.append({
                "category": category,
                "case_id": case_id,
                "role": ",".join(roles),
                "original_ink_ratio": 0.0,
                "output_ink_ratio": 0.0,
                "preservation_ratio": 0.0,
                "judgment": "원본 이미지 누락",
                "error": f"Original image not found: {orig_path}",
                "original_image_path": str(orig_path),
                "output_photo_path": None,
            })
            continue

        try:
            orig_ink = calculate_ink_ratio(
                orig_path,
                brightness_threshold=brightness_threshold,
                resample_size=resample_size,
            )
        except Exception as exc:
            records.append({
                "category": category,
                "case_id": case_id,
                "role": ",".join(roles),
                "original_ink_ratio": 0.0,
                "output_ink_ratio": 0.0,
                "preservation_ratio": 0.0,
                "judgment": "원본 분석 실패",
                "error": f"Failed reading original image: {exc}",
                "original_image_path": str(orig_path),
                "output_photo_path": None,
            })
            continue

        photos_dir = out_dir / "photos"
        matched_photos = find_photos_for_roles(photos_dir, roles)

        if not matched_photos:
            records.append({
                "category": category,
                "case_id": case_id,
                "role": ",".join(roles),
                "original_ink_ratio": orig_ink,
                "output_ink_ratio": 0.0,
                "preservation_ratio": 0.0,
                "judgment": "산출물 누락",
                "error": f"No photo found for role(s) {roles} in {photos_dir}",
                "original_image_path": str(orig_path),
                "output_photo_path": None,
            })
            continue

        for photo_role, photo_file in matched_photos:
            try:
                out_ink = calculate_ink_ratio(
                    photo_file,
                    brightness_threshold=brightness_threshold,
                    resample_size=resample_size,
                )
                ratio = out_ink / orig_ink if orig_ink > 0 else (1.0 if out_ink == 0 else 0.0)

                if ratio > ok_threshold:
                    judgment = "OK"
                elif ratio < severe_threshold:
                    judgment = "심각 손실"
                else:
                    judgment = "부분 손실"

                records.append({
                    "category": category,
                    "case_id": case_id,
                    "role": photo_role,
                    "original_ink_ratio": round(orig_ink, 6),
                    "output_ink_ratio": round(out_ink, 6),
                    "preservation_ratio": round(ratio, 6),
                    "judgment": judgment,
                    "original_image_path": str(orig_path),
                    "output_photo_path": str(photo_file),
                })
            except Exception as exc:
                records.append({
                    "category": category,
                    "case_id": case_id,
                    "role": photo_role,
                    "original_ink_ratio": round(orig_ink, 6),
                    "output_ink_ratio": 0.0,
                    "preservation_ratio": 0.0,
                    "judgment": "산출 분석 실패",
                    "error": str(exc),
                    "original_image_path": str(orig_path),
                    "output_photo_path": str(photo_file),
                })

    ok_count = sum(1 for r in records if r["judgment"] == "OK")
    partial_count = sum(1 for r in records if r["judgment"] == "부분 손실")
    severe_count = sum(
        1 for r in records if r["judgment"] in ("심각 손실", "원본 이미지 누락", "산출물 누락", "원본 분석 실패", "산출 분석 실패")
    )
    all_ok = len(records) > 0 and ok_count == len(records)
    has_severe = severe_count > 0

    return {
        "pilot_id": run_index.get("pilot_id", pilot_dir.name),
        "pilot_dir": str(pilot_dir.resolve()),
        "thresholds": {
            "brightness": brightness_threshold,
            "ok": ok_threshold,
            "severe": severe_threshold,
            "resample_size": resample_size,
            "roles": roles,
        },
        "summary": {
            "total": len(records),
            "ok_count": ok_count,
            "partial_loss_count": partial_count,
            "severe_loss_count": severe_count,
            "all_ok": all_ok,
            "has_severe_loss": has_severe,
        },
        "records": records,
    }


def print_table(results: dict[str, Any]) -> None:
    """Print results formatted as a Markdown table and summary."""
    records = results.get("records", [])

    print("| 카테고리 | case_id | photo 역할 | 원본 잉크 비율 | 산출 잉크 비율 | 보존율 | 판정 |")
    print("|---|---|---|---|---|---|---|")

    for r in records:
        orig_str = f"{r['original_ink_ratio']:.4f} ({r['original_ink_ratio']*100:.1f}%)"
        out_str = f"{r['output_ink_ratio']:.4f} ({r['output_ink_ratio']*100:.1f}%)"
        ratio_str = f"{r['preservation_ratio']:.4f} ({r['preservation_ratio']*100:.1f}%)"
        print(f"| {r['category']} | {r['case_id']} | {r['role']} | {orig_str} | {out_str} | {ratio_str} | {r['judgment']} |")

    summary = results.get("summary", {})
    total = summary.get("total", 0)
    ok_c = summary.get("ok_count", 0)
    part_c = summary.get("partial_loss_count", 0)
    sev_c = summary.get("severe_loss_count", 0)

    print()
    print(f"요약: 총 {total}건 | OK: {ok_c}건 | 부분 손실: {part_c}건 | 심각 손실: {sev_c}건")
    if summary.get("has_severe_loss"):
        print("최종 판정: [FAIL] 심각 손실(CRITICAL_LOSS)이 감지되었습니다.")
    elif not summary.get("all_ok"):
        print("최종 판정: [WARN/FAIL] 부분 손실(PARTIAL_LOSS)이 존재하여 전건 OK가 아닙니다.")
    else:
        print("최종 판정: [PASS] 전건 정상 보존(ALL_OK)되었습니다.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check cutout fidelity between original image and generated photos."
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
        help="Positional fallback for pilot directory.",
    )
    parser.add_argument(
        "--role",
        default="hero",
        help="Photo role to evaluate (e.g. 'hero', 'packshot', 'all', default: 'hero').",
    )
    parser.add_argument(
        "--brightness-threshold",
        type=int,
        default=235,
        help="Grayscale threshold under which pixels are considered ink (default: 235).",
    )
    parser.add_argument(
        "--ok-threshold",
        type=float,
        default=0.6,
        help="Preservation ratio threshold strictly above which is OK (default: 0.6).",
    )
    parser.add_argument(
        "--severe-threshold",
        type=float,
        default=0.25,
        help="Preservation ratio threshold strictly below which is severe loss (default: 0.25).",
    )
    parser.add_argument(
        "--resample-size",
        type=int,
        default=256,
        help="Square resample dimension for comparison (default: 256).",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        dest="json_output",
        help="Optional path to save JSON results.",
    )
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Return exit code 0 when there are only partial losses and no severe losses.",
    )

    args = parser.parse_args(argv)
    if args.pilot_dir is None:
        if args.pilot_dir_pos is not None:
            args.pilot_dir = args.pilot_dir_pos
        else:
            parser.error("The --pilot-dir argument is required.")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    pilot_dir = args.pilot_dir.resolve()

    if not pilot_dir.is_dir():
        print(f"[ERROR] Directory does not exist: {pilot_dir}", file=sys.stderr)
        return 1

    roles = [r.strip().lower() for r in args.role.split(",") if r.strip()]

    try:
        results = evaluate_cutout_fidelity(
            pilot_dir=pilot_dir,
            roles=roles,
            brightness_threshold=args.brightness_threshold,
            ok_threshold=args.ok_threshold,
            severe_threshold=args.severe_threshold,
            resample_size=args.resample_size,
        )
    except Exception as exc:
        print(f"[ERROR] Failed evaluating cutout fidelity: {exc}", file=sys.stderr)
        return 1

    print_table(results)

    if args.json_output:
        out_json_path = args.json_output.resolve()
        out_json_path.parent.mkdir(parents=True, exist_ok=True)
        out_json_path.write_text(
            json.dumps(results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"JSON 결과 저장됨: {out_json_path}")

    summary = results["summary"]
    # Exit code: 1 if any severe loss, or not all_ok unless allow_partial is specified
    if summary["has_severe_loss"]:
        return 1
    if not summary["all_ok"] and not args.allow_partial:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
