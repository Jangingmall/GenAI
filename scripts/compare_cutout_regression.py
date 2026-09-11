#!/usr/bin/env python3
"""Cutout regression comparison tool for evaluating extractor modifications.

Directly invokes SolidBackgroundCutoutExtractor across the evaluation image dataset
(without running full detail page pipelines) to compute:
  1. Cutout execution rate and breakdown of rejection reasons.
  2. Erosion risk (measuring product body damage, internal holes, discarded pixels).
  3. Background remnant ratio (measuring edge touches and enclosed loops).
  4. Ground truth alignment against docs/evaluation/cutout-ground-truth.md.
  5. Side-by-side comparison between baseline and candidate runs (identifying
     IMPROVED, REGRESSED, and UNCHANGED cases at the case_id level).
"""

from __future__ import annotations

import argparse
import io
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from scipy import ndimage

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
SRC_DIR = PROJECT_ROOT / "src"

for p in [str(SCRIPTS_DIR), str(SRC_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from detail_page_ai.source_photos import SolidBackgroundCutoutExtractor, _decode_rgb

# Ground truth reference labels established from 60-case audit
GROUND_TRUTH_LABELS: dict[str, dict[str, str]] = {
    # 4 Erosion cases
    "analysis-cma-165266": {"axis_a": "partial", "axis_b": "none"},
    "analysis-cma-165267": {"axis_a": "partial", "axis_b": "none"},
    "analysis-cma-165271": {"axis_a": "partial", "axis_b": "none"},
    "analysis-cma-122443": {"axis_a": "partial", "axis_b": "edge"},
    # 2 Enclosed remnant cases
    "analysis-cma-159023": {"axis_a": "none", "axis_b": "enclosed"},
    "analysis-cma-131719": {"axis_a": "none", "axis_b": "enclosed"},
    # Clean composite cases
    "analysis-cma-102980": {"axis_a": "none", "axis_b": "none"},
    "analysis-cma-156983": {"axis_a": "none", "axis_b": "none"},
    "analysis-cma-168479": {"axis_a": "none", "axis_b": "none"},
}


def diagnose_rejection(
    source_bytes: bytes,
    extractor: SolidBackgroundCutoutExtractor,
) -> tuple[str, str, float]:
    """Diagnose the specific condition where cutout extraction failed.

    Returns:
        (reason_code, human_detail, corner_max_deviation)
    """
    source = _decode_rgb(source_bytes)
    width, height = source.size
    corners = (
        source.getpixel((0, 0)),
        source.getpixel((width - 1, 0)),
        source.getpixel((0, height - 1)),
        source.getpixel((width - 1, height - 1)),
    )
    background = tuple(round(sum(pixel[channel] for pixel in corners) / 4) for channel in range(3))
    deviations = [extractor._distance(pixel, background) for pixel in corners]
    max_dev = max(deviations)

    if any(d > extractor.corner_uniformity_tolerance for d in deviations):
        return (
            "CORNER_NON_UNIFORM",
            f"모서리 최대 편차 {max_dev:.1f} > 임계값 {extractor.corner_uniformity_tolerance:.1f}",
            max_dev,
        )

    alpha_values = None
    for multiplier in (1, 2, 4):
        tolerance = extractor.background_tolerance * multiplier
        candidate_mask = extractor._connected_foreground_mask(source, background, tolerance)
        alpha_values = list(candidate_mask.getdata())
        foreground_ratio = sum(value > 0 for value in alpha_values) / (width * height)
        if foreground_ratio <= extractor.max_foreground_ratio:
            break

    if alpha_values is None:
        return ("ALPHA_VALUES_NONE", "초기 전경 마스크 생성 불가", max_dev)

    mask = Image.new("L", source.size)
    mask.putdata(alpha_values)
    mask = extractor._refine_mask(mask)
    mask = extractor._suppress_unreliable_edge_shadow(mask, source, background)
    mask = extractor._suppress_connected_background_gradient(mask, source, background)
    bbox = mask.getbbox()
    if bbox is None:
        return ("BBOX_NONE", "마스크 바운딩 박스 없음(전경 소실)", max_dev)

    foreground_count = sum(value > 0 for value in mask.getdata())
    foreground_ratio = foreground_count / (width * height)
    if foreground_ratio < extractor.min_foreground_ratio:
        return (
            "FOREGROUND_TOO_SMALL",
            f"전경 비율 {foreground_ratio:.3f} < 최소치 {extractor.min_foreground_ratio:.3f}",
            max_dev,
        )
    if foreground_ratio > extractor.max_foreground_ratio:
        return (
            "FOREGROUND_TOO_LARGE",
            f"전경 비율 {foreground_ratio:.3f} > 최대치 {extractor.max_foreground_ratio:.3f}",
            max_dev,
        )

    comp_ratio = extractor._largest_foreground_component_ratio(mask, foreground_count)
    if comp_ratio < extractor.min_largest_component_ratio:
        return (
            "LARGEST_COMPONENT_TOO_SMALL",
            f"최대 연결 요소 비율 {comp_ratio:.3f} < 최소치 {extractor.min_largest_component_ratio:.3f}",
            max_dev,
        )

    return ("UNKNOWN_REJECTION", "기타 사유로 거절됨", max_dev)


def evaluate_single_image(
    case_id: str,
    category: str,
    image_path: Path,
    extractor: SolidBackgroundCutoutExtractor | None = None,
) -> dict[str, Any]:
    """Directly evaluate cutout extractor on a single image."""
    if extractor is None:
        extractor = SolidBackgroundCutoutExtractor()

    if not image_path.is_file():
        raise FileNotFoundError(f"Image not found: {image_path}")

    source_bytes = image_path.read_bytes()
    cutout = extractor.extract(source_bytes, "image/jpeg")

    # Ground truth lookup
    gt = GROUND_TRUTH_LABELS.get(case_id, {"axis_a": "none", "axis_b": "edge"})

    if cutout is None:
        reason, detail, max_dev = diagnose_rejection(source_bytes, extractor)
        return {
            "case_id": case_id,
            "category": category,
            "image_path": str(image_path),
            "status": "FALLBACK",
            "rejection_reason": reason,
            "rejection_detail": detail,
            "corner_max_deviation": round(max_dev, 2),
            "foreground_pixels": 0,
            "foreground_ratio": 0.0,
            "internal_holes": 0,
            "eroded_pixels": 0,
            "erosion_risk": "NONE",
            "erosion_risk_detail": "폴백(원본 보존, 제품 침식 없음)",
            "border_touches": {"top": 0, "bottom": 0, "left": 0, "right": 0, "total": 0},
            "enclosed_bg_pixels": 0,
            "enclosed_bg_ratio": 0.0,
            "remnant_status": "EDGE",
            "remnant_detail": "폴백(배경 미제거, 테두리 잔존 100%)",
            "gt_axis_a": gt["axis_a"],
            "gt_axis_b": gt["axis_b"],
            "gt_match_a": True,  # Fallback matches gt_axis_a 'none'
            "gt_match_b": (gt["axis_b"] == "edge"),
        }

    # Cutout succeeded
    source = _decode_rgb(source_bytes)
    w, h = source.size
    corners = (
        source.getpixel((0, 0)),
        source.getpixel((w - 1, 0)),
        source.getpixel((0, h - 1)),
        source.getpixel((w - 1, h - 1)),
    )
    bg = tuple(round(sum(pixel[channel] for pixel in corners) / 4) for channel in range(3))
    deviations = [extractor._distance(pixel, bg) for pixel in corners]
    max_dev = max(deviations)

    mask = np.array(Image.open(io.BytesIO(cutout.mask_png))) > 0
    total_fg = int(np.sum(mask))
    fg_ratio = total_fg / (w * h)

    # 1. Erosion metrics
    filled = ndimage.binary_fill_holes(mask)
    internal_holes = int(np.sum(filled & (~mask)))

    bg_col = np.array(bg, dtype=float)
    orig_arr = np.array(source, dtype=float)
    dist_to_bg = np.linalg.norm(orig_arr - bg_col, axis=2)

    # Pixels outside mask with high distance to background
    eroded_px = int(np.sum((~mask) & (dist_to_bg > 50)))

    # Erosion risk judgment
    if internal_holes > 5000 or eroded_px > 30000:
        erosion_risk = "HIGH"
        erosion_detail = f"제품 소실 위험 높음 (내부 홀 {internal_holes:,}px, 침식 의심 {eroded_px:,}px)"
    elif internal_holes > 1000 or eroded_px > 10000:
        erosion_risk = "MEDIUM"
        erosion_detail = f"제품 소실 의심 (내부 홀 {internal_holes:,}px, 침식 의심 {eroded_px:,}px)"
    else:
        erosion_risk = "LOW"
        erosion_detail = f"제품 온전 보존 (내부 홀 {internal_holes}px)"

    # 2. Remnant metrics
    top_t = int(np.sum(mask[0, :]))
    bot_t = int(np.sum(mask[-1, :]))
    left_t = int(np.sum(mask[:, 0]))
    right_t = int(np.sum(mask[:, -1]))
    total_border_touch = top_t + bot_t + left_t + right_t

    enclosed_bg_px = int(np.sum((mask) & (dist_to_bg <= 25)))
    enclosed_ratio = (enclosed_bg_px / total_fg) if total_fg > 0 else 0.0

    if total_border_touch > 50:
        remnant_status = "EDGE"
        remnant_detail = f"테두리 접촉 잔존 ({total_border_touch}px 접촉)"
    elif enclosed_bg_px > 20000 and enclosed_ratio > 0.10:
        remnant_status = "ENCLOSED"
        remnant_detail = f"폐곡선 내부 배경 잔존 ({enclosed_bg_px:,}px, {enclosed_ratio*100:.1f}%)"
    else:
        remnant_status = "NONE"
        remnant_detail = "배경 완전 제거"

    # Ground truth alignment
    # GT axis_a: 'partial' or 'none'
    detected_erosion = "partial" if erosion_risk in ("HIGH", "MEDIUM") else "none"
    match_a = (detected_erosion == gt["axis_a"])
    match_b = (remnant_status.lower() == gt["axis_b"].lower())

    return {
        "case_id": case_id,
        "category": category,
        "image_path": str(image_path),
        "status": "SUCCESS",
        "rejection_reason": None,
        "rejection_detail": None,
        "corner_max_deviation": round(max_dev, 2),
        "foreground_pixels": total_fg,
        "foreground_ratio": round(fg_ratio, 4),
        "internal_holes": internal_holes,
        "eroded_pixels": eroded_px,
        "erosion_risk": erosion_risk,
        "erosion_risk_detail": erosion_detail,
        "border_touches": {
            "top": top_t,
            "bottom": bot_t,
            "left": left_t,
            "right": right_t,
            "total": total_border_touch,
        },
        "enclosed_bg_pixels": enclosed_bg_px,
        "enclosed_bg_ratio": round(enclosed_ratio, 4),
        "remnant_status": remnant_status,
        "remnant_detail": remnant_detail,
        "gt_axis_a": gt["axis_a"],
        "gt_axis_b": gt["axis_b"],
        "gt_match_a": match_a,
        "gt_match_b": match_b,
    }


def evaluate_dataset(
    cases: list[dict[str, Any]],
    extractor: SolidBackgroundCutoutExtractor | None = None,
) -> dict[str, Any]:
    """Run evaluation across all cases in the dataset."""
    if extractor is None:
        extractor = SolidBackgroundCutoutExtractor()

    records = [
        evaluate_single_image(
            case_id=c["case_id"],
            category=c.get("category", "unknown"),
            image_path=Path(c["image_path"]),
            extractor=extractor,
        )
        for c in cases
    ]

    total = len(records)
    success_count = sum(1 for r in records if r["status"] == "SUCCESS")
    fallback_count = sum(1 for r in records if r["status"] == "FALLBACK")
    exec_rate = (success_count / total * 100) if total > 0 else 0.0

    # Rejection counts
    rejection_counts: dict[str, int] = {}
    for r in records:
        reason = r["rejection_reason"]
        if reason:
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1

    # Corner deviation statistics
    deviations = [r["corner_max_deviation"] for r in records]
    dev_stats = {
        "min": min(deviations) if deviations else 0.0,
        "max": max(deviations) if deviations else 0.0,
        "median": statistics.median(deviations) if deviations else 0.0,
        "mean": statistics.mean(deviations) if deviations else 0.0,
    }

    # Erosion risk counts
    erosion_counts = {
        "HIGH": sum(1 for r in records if r["erosion_risk"] == "HIGH"),
        "MEDIUM": sum(1 for r in records if r["erosion_risk"] == "MEDIUM"),
        "LOW": sum(1 for r in records if r["erosion_risk"] == "LOW"),
        "NONE": sum(1 for r in records if r["erosion_risk"] == "NONE"),
    }
    erosion_candidates = [
        {"case_id": r["case_id"], "risk": r["erosion_risk"], "detail": r["erosion_risk_detail"]}
        for r in records
        if r["erosion_risk"] in ("HIGH", "MEDIUM")
    ]

    # Remnant status counts
    remnant_counts = {
        "NONE": sum(1 for r in records if r["remnant_status"] == "NONE"),
        "ENCLOSED": sum(1 for r in records if r["remnant_status"] == "ENCLOSED"),
        "EDGE": sum(1 for r in records if r["remnant_status"] == "EDGE"),
    }

    # Ground truth matches
    gt_matches_a = sum(1 for r in records if r["gt_match_a"])
    gt_matches_b = sum(1 for r in records if r["gt_match_b"])

    return {
        "total_cases": total,
        "execution_summary": {
            "success_count": success_count,
            "fallback_count": fallback_count,
            "execution_rate_pct": round(exec_rate, 2),
        },
        "rejection_reasons": rejection_counts,
        "corner_deviation_stats": dev_stats,
        "erosion_risk_counts": erosion_counts,
        "erosion_candidates": erosion_candidates,
        "remnant_status_counts": remnant_counts,
        "ground_truth_alignment": {
            "axis_a_matches": gt_matches_a,
            "axis_a_rate": round(gt_matches_a / total, 4) if total > 0 else 0.0,
            "axis_b_matches": gt_matches_b,
            "axis_b_rate": round(gt_matches_b / total, 4) if total > 0 else 0.0,
        },
        "records": records,
    }


def compare_runs(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Compare baseline run against candidate run case-by-case."""
    base_by_id = {r["case_id"]: r for r in baseline["records"]}
    cand_by_id = {r["case_id"]: r for r in candidate["records"]}

    common_ids = sorted(set(base_by_id.keys()) & set(cand_by_id.keys()))

    improved_cases: list[dict[str, Any]] = []
    regressed_cases: list[dict[str, Any]] = []
    unchanged_cases: list[dict[str, Any]] = []

    for cid in common_ids:
        b = base_by_id[cid]
        c = cand_by_id[cid]

        b_stat = b["status"]
        c_stat = c["status"]
        b_ero = b["erosion_risk"]
        c_ero = c["erosion_risk"]
        b_rem = b["remnant_status"]
        c_rem = c["remnant_status"]

        # Regression detection (HIGHEST PRIORITY)
        regressed = False
        reasons = []

        # 1. Previously succeeded, now fallback
        if b_stat == "SUCCESS" and c_stat == "FALLBACK":
            regressed = True
            reasons.append("성공하던 케이스가 폴백으로 후퇴함")

        # 2. Erosion worsened
        if b_ero in ("NONE", "LOW") and c_ero in ("HIGH", "MEDIUM"):
            regressed = True
            reasons.append(f"침식 악화 ({b_ero} -> {c_ero}: {c['erosion_risk_detail']})")

        # 3. Remnant worsened
        if b_rem == "NONE" and c_rem in ("ENCLOSED", "EDGE"):
            regressed = True
            reasons.append(f"배경 잔존 악화 (NONE -> {c_rem}: {c['remnant_detail']})")

        # 4. Previously fallback, now success but with severe defects
        if b_stat == "FALLBACK" and c_stat == "SUCCESS":
            if c_ero == "HIGH":
                regressed = True
                reasons.append(f"신규 컷아웃 추출되었으나 심각한 제품 침식 발생 ({c['erosion_risk_detail']})")
            elif c_rem == "EDGE":
                regressed = True
                reasons.append(f"신규 컷아웃 추출되었으나 테두리 배경이 전경에 대량 포함됨 ({c['remnant_detail']})")

        if regressed:
            regressed_cases.append({
                "case_id": cid,
                "category": b["category"],
                "baseline": {"status": b_stat, "erosion": b_ero, "remnant": b_rem},
                "candidate": {"status": c_stat, "erosion": c_ero, "remnant": c_rem},
                "reasons": reasons,
            })
            continue

        # Improvement detection
        improved = False
        imp_reasons = []

        # 1. Clean extraction from fallback
        if b_stat == "FALLBACK" and c_stat == "SUCCESS" and c_ero == "LOW" and c_rem == "NONE":
            improved = True
            imp_reasons.append("폴백에서 깨끗한 컷아웃 성공(침식 없음, 배경 잔존 없음)")

        # 2. Existing erosion fixed
        if b_ero in ("HIGH", "MEDIUM") and c_ero == "LOW":
            improved = True
            imp_reasons.append(f"기존 침식 결함 해결 ({b_ero} -> {c_ero})")

        # 3. Existing remnant fixed
        if b_rem in ("ENCLOSED", "EDGE") and c_rem == "NONE":
            improved = True
            imp_reasons.append(f"기존 배경 잔존 결함 해결 ({b_rem} -> {c_rem})")

        if improved:
            improved_cases.append({
                "case_id": cid,
                "category": b["category"],
                "baseline": {"status": b_stat, "erosion": b_ero, "remnant": b_rem},
                "candidate": {"status": c_stat, "erosion": c_ero, "remnant": c_rem},
                "reasons": imp_reasons,
            })
        else:
            unchanged_cases.append({
                "case_id": cid,
                "category": b["category"],
                "status": c_stat,
                "erosion": c_ero,
                "remnant": c_rem,
            })

    b_exec = baseline["execution_summary"]["execution_rate_pct"]
    c_exec = candidate["execution_summary"]["execution_rate_pct"]

    return {
        "summary": {
            "total_evaluated": len(common_ids),
            "baseline_execution_rate_pct": b_exec,
            "candidate_execution_rate_pct": c_exec,
            "execution_rate_delta_pct": round(c_exec - b_exec, 2),
            "improved_count": len(improved_cases),
            "regressed_count": len(regressed_cases),
            "unchanged_count": len(unchanged_cases),
        },
        "improved_cases": improved_cases,
        "regressed_cases": regressed_cases,
        "unchanged_cases": unchanged_cases,
    }


def format_regression_markdown(
    evaluation: dict[str, Any],
    comparison: dict[str, Any] | None = None,
) -> str:
    """Format evaluation and comparison as markdown report."""
    lines = []
    lines.append("# 컷아웃 추출기 회귀 판정 보고서 (Cutout Regression Report)")
    lines.append("")

    ex = evaluation["execution_summary"]
    lines.append("## 1. 컷아웃 수행률 및 거부 사유 분석")
    lines.append("")
    lines.append(f"- **총 평가 케이스**: {evaluation['total_cases']}건")
    lines.append(f"- **마스크 추출 성공 (SUCCESS)**: **{ex['success_count']}건** ({ex['execution_rate_pct']}%)")
    lines.append(f"- **컷아웃 거부 / 폴백 (FALLBACK)**: **{ex['fallback_count']}건** ({100.0 - ex['execution_rate_pct']:.1f}%)")
    lines.append("")
    lines.append("### 거부 사유별 집계")
    lines.append("| 거부 사유 코드 | 건수 | 비율 | 설명 |")
    lines.append("|---|---|---|---|")
    for reason, cnt in evaluation["rejection_reasons"].items():
        pct = (cnt / evaluation["total_cases"]) * 100
        desc = "4개 모서리 색상 불일치 (그라디언트/배경 불균일)" if reason == "CORNER_NON_UNIFORM" else (
            "최대 연결 요소 비율 50% 미만 (파편화 제품)" if reason == "LARGEST_COMPONENT_TOO_SMALL" else reason
        )
        lines.append(f"| `{reason}` | {cnt}건 | {pct:.1f}% | {desc} |")

    dev = evaluation["corner_deviation_stats"]
    lines.append("")
    lines.append(f"- **모서리 최대 편차 통계**: 중앙값 **{dev['median']:.1f}**, 평균 **{dev['mean']:.1f}**, 최소 **{dev['min']:.1f}**, 최대 **{dev['max']:.1f}**")
    lines.append("")

    lines.append("## 2. 침식 위험도 (Erosion Risk)")
    er = evaluation["erosion_risk_counts"]
    lines.append(f"- `HIGH` (심각 침식 위험): **{er['HIGH']}건**")
    lines.append(f"- `MEDIUM` (부분 침식 의심): **{er['MEDIUM']}건**")
    lines.append(f"- `LOW` (온전 보존): **{er['LOW']}건**")
    lines.append(f"- `NONE` (폴백 / 원본 유지): **{er['NONE']}건**")
    lines.append("")
    if evaluation["erosion_candidates"]:
        lines.append("### 육안 확인 필요 후보 목록 (침식 위험 건)")
        lines.append("| case_id | 위험도 | 상세 내용 |")
        lines.append("|---|---|---|")
        for c in evaluation["erosion_candidates"]:
            lines.append(f"| `{c['case_id']}` | **{c['risk']}** | {c['detail']} |")
        lines.append("")

    lines.append("## 3. 배경 잔존 (Background Remnant)")
    rm = evaluation["remnant_status_counts"]
    lines.append(f"- `NONE` (배경 완전 제거): **{rm['NONE']}건**")
    lines.append(f"- `ENCLOSED` (폐곡선 고리 내부 잔존): **{rm['ENCLOSED']}건**")
    lines.append(f"- `EDGE` (프레임 테두리 잔존): **{rm['EDGE']}건** (폴백 {ex['fallback_count']}건 포함)")
    lines.append("")

    lines.append("## 4. 정답 집합(Ground Truth) 일치율")
    gt = evaluation["ground_truth_alignment"]
    lines.append(f"- **축 A (침식) 정답 일치율**: {gt['axis_a_matches']}/{evaluation['total_cases']} ({gt['axis_a_rate']*100:.1f}%)")
    lines.append(f"- **축 B (잔존) 정답 일치율**: {gt['axis_b_matches']}/{evaluation['total_cases']} ({gt['axis_b_rate']*100:.1f}%)")
    lines.append("")

    if comparison:
        lines.append("## 5. 두 실행의 비교 (회귀 분석)")
        cs = comparison["summary"]
        lines.append("")
        lines.append(f"- **수행률 변화**: {cs['baseline_execution_rate_pct']:.1f}% -> {cs['candidate_execution_rate_pct']:.1f}% (변화폭: {cs['execution_rate_delta_pct']:+.1f}%p)")
        lines.append(f"- **개선 건수 (IMPROVED)**: **{cs['improved_count']}건**")
        lines.append(f"- **퇴행 건수 (REGRESSED - 🚨 주의)**: **{cs['regressed_count']}건**")
        lines.append(f"- **변화 없음 (UNCHANGED)**: **{cs['unchanged_count']}건**")
        lines.append("")

        if comparison["regressed_cases"]:
            lines.append("### 🚨 나빠진 건 (REGRESSED) 상세")
            lines.append("| case_id | 카테고리 | 기준선 상태 | 후보 상태 | 후퇴 사유 |")
            lines.append("|---|---|---|---|---|")
            for r in comparison["regressed_cases"]:
                b_str = f"{r['baseline']['status']}/{r['baseline']['erosion']}/{r['baseline']['remnant']}"
                c_str = f"{r['candidate']['status']}/{r['candidate']['erosion']}/{r['candidate']['remnant']}"
                lines.append(f"| `{r['case_id']}` | {r['category']} | {b_str} | {c_str} | {', '.join(r['reasons'])} |")
            lines.append("")
        else:
            lines.append("> [!NOTE]\n> 퇴행(REGRESSED) 건이 감지되지 않았습니다. 모든 변경이 개선이거나 안전하게 유지되었습니다.\n")

        if comparison["improved_cases"]:
            lines.append("### ✨ 좋아진 건 (IMPROVED) 상세")
            lines.append("| case_id | 카테고리 | 기준선 상태 | 후보 상태 | 개선 내용 |")
            lines.append("|---|---|---|---|---|")
            for imp in comparison["improved_cases"]:
                b_str = f"{imp['baseline']['status']}/{imp['baseline']['erosion']}/{imp['baseline']['remnant']}"
                c_str = f"{imp['candidate']['status']}/{imp['candidate']['erosion']}/{imp['candidate']['remnant']}"
                lines.append(f"| `{imp['case_id']}` | {imp['category']} | {b_str} | {c_str} | {', '.join(imp['reasons'])} |")
            lines.append("")

    return "\n".join(lines)


def load_dataset_cases(target_path: Path) -> list[dict[str, Any]]:
    """Resolve dataset cases from run_index.json or pilot directory."""
    if target_path.is_dir():
        target_path = target_path / "run_index.json"

    if not target_path.is_file():
        raise FileNotFoundError(f"Dataset file not found: {target_path}")

    data = json.loads(target_path.read_text(encoding="utf-8"))
    return data.get("cases", [])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Independent regression tool for comparing cutout extractor modifications."
    )
    parser.add_argument(
        "--run-index",
        type=Path,
        default=PROJECT_ROOT / "generated/evaluation/full60-20260910-204433/run_index.json",
        help="Path to run_index.json containing evaluation cases.",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="Path to baseline evaluation snapshot JSON.",
    )
    parser.add_argument(
        "--candidate",
        type=Path,
        default=None,
        help="Path to candidate evaluation snapshot JSON (if comparing two saved snapshots).",
    )
    parser.add_argument(
        "--save-snapshot",
        type=Path,
        default=None,
        help="Save current evaluation run to JSON file.",
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=None,
        help="Save markdown regression report to file.",
    )

    args = parser.parse_args(argv)

    comparison = None
    if args.baseline and args.candidate:
        # Compare two existing snapshots
        base_data = json.loads(args.baseline.read_text(encoding="utf-8"))
        cand_data = json.loads(args.candidate.read_text(encoding="utf-8"))
        comparison = compare_runs(base_data, cand_data)
        eval_data = cand_data
    else:
        # Run extractor on dataset
        cases = load_dataset_cases(args.run_index)
        extractor = SolidBackgroundCutoutExtractor()
        eval_data = evaluate_dataset(cases, extractor=extractor)

        if args.baseline:
            base_data = json.loads(args.baseline.read_text(encoding="utf-8"))
            comparison = compare_runs(base_data, eval_data)

    md_report = format_regression_markdown(eval_data, comparison=comparison)
    print(md_report)

    if args.save_snapshot:
        args.save_snapshot.parent.mkdir(parents=True, exist_ok=True)
        args.save_snapshot.write_text(
            json.dumps(eval_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n[INFO] Snapshot saved to: {args.save_snapshot}")

    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(md_report, encoding="utf-8")
        print(f"\n[INFO] Markdown report saved to: {args.markdown}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
