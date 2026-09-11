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
from collections import deque
from pathlib import Path
from typing import Any

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Full60의 관리자가 확인한 최악 잔존 사례(cma-109609)는 네 모서리 평균 배경색에서
# RGB 유클리드 거리 16일 때 19.22%가 되어, 육안 집계 19.2%와 일치한다. 같은 기준에서
# 정상 목걸이(cma-168479)의 유사 색 픽셀은 0.62%에 그쳐 1% 게이트보다 낮다.
BACKGROUND_COLOR_TOLERANCE: float = 16.0
BACKGROUND_RESIDUE_THRESHOLD: float = 0.01

# Full60에서 원본의 edge-connected background 제거 후 bbox 실루엣 밀도는 정상 고리
# cma-168479만 27.77%였고, 다음 값은 45.35%였다. 30%는 이 15.35%p 분리 구간 안의
# 보수적 값이다. 이 경우에만 원본 실루엣 밀도를 보존율 분모로 써서 성긴 제품을 보호한다.
SPARSE_SOURCE_FOREGROUND_DENSITY_THRESHOLD: float = 0.30


def _load_rgb_on_white(image_path: Path) -> Image.Image:
    """Load an image as RGB, compositing transparency onto the renderer's white backdrop."""
    if not image_path.is_file():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    with Image.open(image_path) as img:
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            rgba = img.convert("RGBA")
            background = Image.new("RGBA", img.size, (255, 255, 255, 255))
            background.alpha_composite(rgba)
            return background.convert("RGB")
        return img.convert("RGB")


def _estimate_corner_background(image: Image.Image) -> tuple[int, int, int]:
    """Estimate source background from the same four image corners used by the cutout extractor."""
    width, height = image.size
    corners = (
        image.getpixel((0, 0)),
        image.getpixel((width - 1, 0)),
        image.getpixel((0, height - 1)),
        image.getpixel((width - 1, height - 1)),
    )
    return tuple(
        round(sum(pixel[channel] for pixel in corners) / len(corners))
        for channel in range(3)
    )


def _background_candidates(
    image: Image.Image,
    background: tuple[int, int, int],
    tolerance: float,
) -> bytearray:
    """Return pixels whose RGB distance is within tolerance of the source background."""
    tolerance_squared = tolerance * tolerance
    pixels = image.load()
    candidates = bytearray(image.width * image.height)
    for y in range(image.height):
        row_start = y * image.width
        for x in range(image.width):
            pixel = pixels[x, y]
            candidates[row_start + x] = int(
                sum((pixel[channel] - background[channel]) ** 2 for channel in range(3))
                <= tolerance_squared
            )
    return candidates


def _edge_reachable(candidates: bytearray, width: int, height: int) -> bytearray:
    """Mark 4-neighbor candidate pixels reachable from an image edge."""
    reachable = bytearray(width * height)
    pending: deque[int] = deque()

    def enqueue(index: int) -> None:
        if candidates[index] and not reachable[index]:
            reachable[index] = 1
            pending.append(index)

    for x in range(width):
        enqueue(x)
        enqueue((height - 1) * width + x)
    for y in range(1, height - 1):
        enqueue(y * width)
        enqueue(y * width + width - 1)

    while pending:
        index = pending.popleft()
        x = index % width
        y = index // width
        if x > 0:
            enqueue(index - 1)
        if x + 1 < width:
            enqueue(index + 1)
        if y > 0:
            enqueue(index - width)
        if y + 1 < height:
            enqueue(index + width)

    return reachable


def calculate_enclosed_background_ratio(
    source_image_path: Path,
    output_image_path: Path,
    background_tolerance: float = BACKGROUND_COLOR_TOLERANCE,
) -> float:
    """Measure source-colored output pixels that cannot reach the output frame.

    A cutout backdrop is expected to be white/transparent after rendering. Source
    background-colored pixels therefore indicate residue only when a 4-neighbor
    path through similarly colored pixels cannot reach the image edge. This keeps
    ordinary source background at the edge and white holes in rings out of the
    residue count.
    """
    source = _load_rgb_on_white(source_image_path)
    output = _load_rgb_on_white(output_image_path)
    background = _estimate_corner_background(source)
    candidates = _background_candidates(output, background, background_tolerance)
    reachable = _edge_reachable(candidates, output.width, output.height)
    enclosed_count = sum(
        candidate and not is_reachable
        for candidate, is_reachable in zip(candidates, reachable)
    )
    return enclosed_count / (output.width * output.height)


def calculate_enclosed_renderer_background_ratio(
    output_image_path: Path,
    background_tolerance: float = BACKGROUND_COLOR_TOLERANCE,
) -> float:
    """Measure renderer-background islands fully enclosed by visible product pixels.

    This catches transparent/white holes in a product surface. It reuses the 1%
    area threshold selected for background residue: in Full60, cma-122443 has
    1.30% enclosed renderer background while the intact open necklace cma-168479
    has 0.04%. The sparse-source exemption remains the guard for genuine rings.
    """
    output = _load_rgb_on_white(output_image_path)
    render_background = _estimate_corner_background(output)
    candidates = _background_candidates(output, render_background, background_tolerance)
    reachable = _edge_reachable(candidates, output.width, output.height)
    enclosed_count = sum(
        candidate and not is_reachable
        for candidate, is_reachable in zip(candidates, reachable)
    )
    return enclosed_count / (output.width * output.height)


def calculate_source_foreground_density(
    image_path: Path,
    background_tolerance: float = BACKGROUND_COLOR_TOLERANCE,
) -> float:
    """Calculate source foreground density after removing only edge-connected background."""
    source = _load_rgb_on_white(image_path)
    background = _estimate_corner_background(source)
    candidates = _background_candidates(source, background, background_tolerance)
    reachable = _edge_reachable(candidates, source.width, source.height)
    foreground_indices = [index for index, is_reachable in enumerate(reachable) if not is_reachable]
    if not foreground_indices:
        return 0.0

    x_values = [index % source.width for index in foreground_indices]
    y_values = [index // source.width for index in foreground_indices]
    bbox_area = (max(x_values) - min(x_values) + 1) * (max(y_values) - min(y_values) + 1)
    return len(foreground_indices) / bbox_area


def _load_photo_metadata(output_dir: Path) -> dict[str, tuple[str | None, str | None]]:
    """Read asset_mode and fidelity_status by photo_id without failing older output runs."""
    summary_path = output_dir / "result_summary.json"
    if not summary_path.is_file():
        return {}
    try:
        summary_data = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    detail_page = summary_data.get("detail_page")
    photos = detail_page.get("photos") if isinstance(detail_page, dict) else None
    if not isinstance(photos, list):
        return {}

    metadata: dict[str, tuple[str | None, str | None]] = {}
    for photo in photos:
        if not isinstance(photo, dict) or not isinstance(photo.get("photo_id"), str):
            continue
        asset_mode = photo.get("asset_mode")
        fidelity_status = photo.get("fidelity_status")
        metadata[photo["photo_id"]] = (
            asset_mode if isinstance(asset_mode, str) else None,
            fidelity_status if isinstance(fidelity_status, str) else None,
        )
    return metadata


def _cutout_performed(
    asset_mode: str | None,
    fidelity_status: str | None,
) -> bool | None:
    """Classify an actual cutout attempt as performed, fallback, or unavailable."""
    if _is_designated_original(asset_mode, fidelity_status):
        return None
    if asset_mode == "source" or fidelity_status == "FALLBACK":
        return False
    if asset_mode in {"source_composite", "source_crop"} and fidelity_status == "VERIFIED":
        return True
    return None


def _is_designated_original(
    asset_mode: str | None,
    fidelity_status: str | None,
) -> bool:
    """Return whether metadata denotes the hero's intentional source image."""
    return asset_mode == "source_original" and fidelity_status == "VERIFIED"


def calculate_bbox_ink_ratio(
    image_path: Path,
    brightness_threshold: int = 235,
    resample_size: int = 256,
) -> tuple[float, tuple[int, int, int, int] | None]:
    """Calculate non-background (ink) pixel ratio within the product bounding box.

    Finds the bounding box of non-background pixels (brightness < brightness_threshold),
    crops the image to that bounding box, resamples to resample_size x resample_size,
    and calculates the fraction of ink pixels.

    Returns:
        (bbox_ink_ratio, bounding_box)
    """
    if not image_path.is_file():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    with Image.open(image_path) as img:
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            mask = img.split()[-1] if img.mode in ("RGBA", "LA") else None
            bg.paste(img.convert("RGB"), mask=mask)
            gray = bg.convert("L")
        else:
            gray = img.convert("L")

        bw = gray.point(lambda p: 255 if p < brightness_threshold else 0, mode="1")
        bbox = bw.getbbox()
        if bbox is None:
            return 0.0, None

        cropped = gray.crop(bbox)
        resized = cropped.resize((resample_size, resample_size))
        hist = resized.histogram()
        total_pixels = resample_size * resample_size
        ink_count = sum(hist[:brightness_threshold])
        return ink_count / total_pixels, bbox


def calculate_ink_ratio(
    image_path: Path,
    brightness_threshold: int = 235,
    resample_size: int = 256,
    crop_to_bbox: bool = False,
) -> float:
    """Calculate non-background (ink) pixel ratio using Pillow only.

    Pixels with grayscale brightness < brightness_threshold are counted as ink.
    If crop_to_bbox is True, crops to the product bounding box first.
    """
    if crop_to_bbox:
        ratio, _ = calculate_bbox_ink_ratio(
            image_path,
            brightness_threshold=brightness_threshold,
            resample_size=resample_size,
        )
        return ratio

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
    crop_to_bbox: bool = True,
) -> dict[str, Any]:
    """Evaluate cutout loss and enclosed source-background residue across a run."""
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

        is_mock = pilot_dir.name == "mock_pilot"
        use_bbox = crop_to_bbox and not is_mock

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
                "original_bbox": None,
                "output_bbox": None,
                "source_foreground_density": None,
                "background_residual_ratio": None,
                "renderer_background_hole_ratio": None,
                "asset_mode": None,
                "fidelity_status": None,
                "cutout_performed": None,
                "cutout_designated_original": False,
            })
            continue

        try:
            if use_bbox:
                orig_ink, orig_bbox = calculate_bbox_ink_ratio(
                    orig_path,
                    brightness_threshold=brightness_threshold,
                    resample_size=resample_size,
                )
            else:
                orig_ink = calculate_ink_ratio(
                    orig_path,
                    brightness_threshold=brightness_threshold,
                    resample_size=resample_size,
                    crop_to_bbox=False,
                )
                orig_bbox = None
            source_foreground_density = calculate_source_foreground_density(orig_path)
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
                "original_bbox": None,
                "output_bbox": None,
                "source_foreground_density": None,
                "background_residual_ratio": None,
                "renderer_background_hole_ratio": None,
                "asset_mode": None,
                "fidelity_status": None,
                "cutout_performed": None,
                "cutout_designated_original": False,
            })
            continue

        photos_dir = out_dir / "photos"
        matched_photos = find_photos_for_roles(photos_dir, roles)
        photo_metadata = _load_photo_metadata(out_dir)

        if not matched_photos:
            records.append({
                "category": category,
                "case_id": case_id,
                "role": ",".join(roles),
                "original_ink_ratio": round(orig_ink, 6),
                "output_ink_ratio": 0.0,
                "preservation_ratio": 0.0,
                "judgment": "산출물 누락",
                "error": f"No photo found for role(s) {roles} in {photos_dir}",
                "original_image_path": str(orig_path),
                "output_photo_path": None,
                "original_bbox": orig_bbox,
                "output_bbox": None,
                "source_foreground_density": round(source_foreground_density, 6),
                "background_residual_ratio": None,
                "renderer_background_hole_ratio": None,
                "asset_mode": None,
                "fidelity_status": None,
                "cutout_performed": None,
                "cutout_designated_original": False,
            })
            continue

        for photo_role, photo_file in matched_photos:
            try:
                asset_mode, fidelity_status = photo_metadata.get(photo_role, (None, None))
                cutout_performed = _cutout_performed(asset_mode, fidelity_status)
                cutout_designated_original = _is_designated_original(
                    asset_mode, fidelity_status
                )
                if use_bbox:
                    out_ink, out_bbox = calculate_bbox_ink_ratio(
                        photo_file,
                        brightness_threshold=brightness_threshold,
                        resample_size=resample_size,
                    )
                else:
                    out_ink = calculate_ink_ratio(
                        photo_file,
                        brightness_threshold=brightness_threshold,
                        resample_size=resample_size,
                        crop_to_bbox=False,
                    )
                    out_bbox = None

                sparse_source = (
                    0.0 < source_foreground_density <= SPARSE_SOURCE_FOREGROUND_DENSITY_THRESHOLD
                )
                comparison_ink = source_foreground_density if sparse_source else orig_ink
                ratio = (
                    out_ink / comparison_ink
                    if comparison_ink > 0
                    else (1.0 if out_ink == 0 else 0.0)
                )

                if cutout_performed is False:
                    # A source/FALLBACK image never passed through a cutout. Its
                    # 100% preservation ratio is expected and cannot assess loss.
                    background_residual_ratio = None
                    renderer_background_hole_ratio = None
                    loss_judgment = None
                    judgment = "컷아웃 미수행"
                elif cutout_designated_original:
                    # The hero policy intentionally retains original bytes. It
                    # is neither a cutout success nor a failed attempt, so it
                    # is excluded from the actual-attempt rate below.
                    background_residual_ratio = None
                    renderer_background_hole_ratio = None
                    loss_judgment = None
                    judgment = "원본 사용(설계)"
                else:
                    background_residual_ratio = calculate_enclosed_background_ratio(orig_path, photo_file)
                    renderer_background_hole_ratio = calculate_enclosed_renderer_background_ratio(photo_file)
                    if ratio > ok_threshold:
                        loss_judgment = "OK"
                    elif ratio < severe_threshold:
                        loss_judgment = "심각 손실"
                    else:
                        loss_judgment = "부분 손실"

                    if (
                        loss_judgment == "OK"
                        and not sparse_source
                        and renderer_background_hole_ratio >= BACKGROUND_RESIDUE_THRESHOLD
                    ):
                        loss_judgment = "부분 손실"

                    if background_residual_ratio >= BACKGROUND_RESIDUE_THRESHOLD:
                        judgment = "배경 잔존"
                    else:
                        judgment = loss_judgment

                records.append({
                    "category": category,
                    "case_id": case_id,
                    "role": photo_role,
                    "original_ink_ratio": round(orig_ink, 6),
                    "output_ink_ratio": round(out_ink, 6),
                    "preservation_ratio": round(ratio, 6),
                    "judgment": judgment,
                    "loss_judgment": loss_judgment,
                    "original_image_path": str(orig_path),
                    "output_photo_path": str(photo_file),
                    "original_bbox": orig_bbox,
                    "output_bbox": out_bbox,
                    "source_foreground_density": round(source_foreground_density, 6),
                    "background_residual_ratio": (
                        round(background_residual_ratio, 6)
                        if background_residual_ratio is not None
                        else None
                    ),
                    "renderer_background_hole_ratio": (
                        round(renderer_background_hole_ratio, 6)
                        if renderer_background_hole_ratio is not None
                        else None
                    ),
                    "asset_mode": asset_mode,
                    "fidelity_status": fidelity_status,
                    "cutout_performed": cutout_performed,
                    "cutout_designated_original": cutout_designated_original,
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
                    "original_bbox": orig_bbox,
                    "output_bbox": None,
                    "source_foreground_density": round(source_foreground_density, 6),
                    "background_residual_ratio": None,
                    "renderer_background_hole_ratio": None,
                    "asset_mode": None,
                    "fidelity_status": None,
                    "cutout_performed": None,
                    "cutout_designated_original": False,
                })

    ok_count = sum(1 for r in records if r["judgment"] == "OK")
    # Summary categories are mutually exclusive final verdicts. The raw
    # loss_judgment remains on each record for diagnostics when background
    # residue takes precedence over a noisy density estimate.
    partial_count = sum(1 for r in records if r["judgment"] == "부분 손실")
    severe_count = sum(1 for r in records if r["judgment"] == "심각 손실")
    background_residual_count = sum(
        1
        for r in records
        if (r.get("background_residual_ratio") or 0.0) >= BACKGROUND_RESIDUE_THRESHOLD
    )
    cutout_performed_count = sum(r.get("cutout_performed") is True for r in records)
    cutout_unperformed_count = sum(r.get("cutout_performed") is False for r in records)
    cutout_designated_original_count = sum(
        r.get("cutout_designated_original") is True for r in records
    )
    # The cutout rate measures only assets for which a cutout was attempted:
    # a VERIFIED composite/crop is a success and source/FALLBACK is a failed
    # attempt. A hero marked source_original is deliberate original use, so it
    # must not dilute the rate or be called missing metadata.
    cutout_attempt_count = cutout_performed_count + cutout_unperformed_count
    cutout_performed_rate = (
        cutout_performed_count / cutout_attempt_count
        if cutout_attempt_count
        else None
    )
    cutout_metadata_missing_count = sum(
        r.get("cutout_performed") is None
        and not r.get("cutout_designated_original", False)
        for r in records
    )
    missing_count = sum(
        1 for r in records if r["judgment"] in ("산출물 누락", "원본 이미지 누락", "원본 분석 실패", "산출 분석 실패")
    )
    all_ok = len(records) > 0 and all(
        r["judgment"] in {"OK", "원본 사용(설계)"} for r in records
    )
    has_severe = severe_count > 0
    has_missing = missing_count > 0
    has_background_residual = background_residual_count > 0
    has_cutout_unperformed = cutout_unperformed_count > 0

    reported_severe = (severe_count + missing_count) if is_mock else severe_count

    return {
        "pilot_id": run_index.get("pilot_id", pilot_dir.name),
        "pilot_dir": str(pilot_dir.resolve()),
        "thresholds": {
            "brightness": brightness_threshold,
            "ok": ok_threshold,
            "severe": severe_threshold,
            "resample_size": resample_size,
            "roles": roles,
            "crop_to_bbox": use_bbox,
            "background_color_tolerance": BACKGROUND_COLOR_TOLERANCE,
            "background_residue": BACKGROUND_RESIDUE_THRESHOLD,
            "renderer_background_hole": BACKGROUND_RESIDUE_THRESHOLD,
            "sparse_source_foreground_density": SPARSE_SOURCE_FOREGROUND_DENSITY_THRESHOLD,
        },
        "summary": {
            "total": len(records),
            "ok_count": ok_count,
            "partial_loss_count": partial_count,
            "severe_loss_count": reported_severe,
            "background_residual_count": background_residual_count,
            "cutout_performed_count": cutout_performed_count,
            "cutout_unperformed_count": cutout_unperformed_count,
            "cutout_designated_original_count": cutout_designated_original_count,
            "cutout_attempt_count": cutout_attempt_count,
            "cutout_metadata_missing_count": cutout_metadata_missing_count,
            "cutout_performed_rate": cutout_performed_rate,
            "cutout_rate_basis": "attempted cutouts only: VERIFIED source_composite/source_crop versus source/FALLBACK",
            "missing_count": missing_count,
            "all_ok": all_ok,
            "has_severe_loss": has_severe,
            "has_background_residual": has_background_residual,
            "has_cutout_unperformed": has_cutout_unperformed,
            "has_missing": has_missing,
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
    background_c = summary.get("background_residual_count", 0)
    cutout_performed_c = summary.get("cutout_performed_count", 0)
    cutout_unperformed_c = summary.get("cutout_unperformed_count", 0)
    cutout_designated_original_c = summary.get("cutout_designated_original_count", 0)
    cutout_attempt_c = summary.get("cutout_attempt_count", total)
    cutout_metadata_missing_c = summary.get("cutout_metadata_missing_count", 0)
    cutout_rate = summary.get("cutout_performed_rate")
    cutout_rate_text = f"{cutout_rate:.1%}" if isinstance(cutout_rate, (int, float)) else "해당 없음"
    missing_c = summary.get("missing_count", 0)
    has_severe = summary.get("has_severe_loss", False)
    has_background_residual = summary.get("has_background_residual", False)
    has_cutout_unperformed = summary.get("has_cutout_unperformed", False)
    has_missing = summary.get("has_missing", False)
    all_ok = summary.get("all_ok", False)

    print()
    summary_parts = [
        f"총 {total}건",
        f"OK: {ok_c}건",
        f"부분 손실: {part_c}건",
        f"심각 손실: {sev_c}건",
        f"컷아웃 수행: {cutout_performed_c}/{cutout_attempt_c}건 ({cutout_rate_text})",
    ]
    if cutout_designated_original_c > 0:
        summary_parts.append(f"설계상 원본 사용: {cutout_designated_original_c}건")
    if cutout_unperformed_c > 0:
        summary_parts.append(f"컷아웃 미수행: {cutout_unperformed_c}건")
    if cutout_metadata_missing_c > 0:
        summary_parts.append(f"컷아웃 상태 미확인: {cutout_metadata_missing_c}건")
    if background_c > 0:
        summary_parts.append(f"배경 잔존: {background_c}건")
    if missing_c > 0:
        summary_parts.append(f"산출물 누락: {missing_c}건")
    print("요약: " + " | ".join(summary_parts))

    failure_reasons: list[str] = []
    if has_severe:
        failure_reasons.append(f"심각 손실(CRITICAL_LOSS: {sev_c}건)")
    if has_background_residual:
        failure_reasons.append(f"배경 잔존(BACKGROUND_RESIDUE: {background_c}건)")
    if has_cutout_unperformed:
        failure_reasons.append(f"컷아웃 미수행(CUTOUT_NOT_PERFORMED: {cutout_unperformed_c}건)")
    if has_missing:
        failure_reasons.append(f"산출물 누락(MISSING_OUTPUT: {missing_c}건)")

    if failure_reasons:
        print("최종 판정: [FAIL] " + " 및 ".join(failure_reasons) + "이 감지되었습니다.")
    elif not all_ok:
        print(f"최종 판정: [WARN/FAIL] 부분 손실(PARTIAL_LOSS: {part_c}건)이 존재하여 전건 OK가 아닙니다.")
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
        "--no-bbox",
        action="store_false",
        dest="crop_to_bbox",
        default=True,
        help="Disable bounding-box cropping and evaluate across whole canvas (legacy behavior).",
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
            crop_to_bbox=args.crop_to_bbox,
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
    # Exit code: 1 for severe loss, background residue, cutout non-performance, or missing output.
    # --allow-partial only relaxes partial-loss reporting, not a known residue defect.
    if (
        summary["has_severe_loss"]
        or summary.get("has_background_residual", False)
        or summary.get("has_cutout_unperformed", False)
        or summary.get("has_missing", False)
    ):
        return 1
    if not summary["all_ok"] and not args.allow_partial:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
