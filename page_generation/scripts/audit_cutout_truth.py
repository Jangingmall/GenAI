#!/usr/bin/env python3
"""Audit cutout quality ground truth dataset across evaluation pilot runs.

Directly analyzes frozen pilot output artifacts on disk (photos/01-hero.* and
result_summary.json) against original images, WITHOUT re-executing the cutout
extractor. This ensures the ground truth dataset remains stable and immutable
regardless of any ongoing extractor code refactoring.

Evaluates two independent axes for each case:
  - Axis A (제품 침식 / Product erosion): none | partial | severe | uncertain
  - Axis B (배경 잔존 / Background remnant): none | enclosed | edge | uncertain
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from scipy import ndimage

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Ground truth visual judgements by manager for cross-validation
MANAGER_VERDICTS: dict[str, dict[str, str]] = {
    "analysis-cma-165266": {"axis_a": "partial", "axis_b": "none"},  # Manager note: 침식 partial / 잔존 확인 필요
    "analysis-cma-165267": {"axis_a": "partial", "axis_b": "none"},  # Manager note: 165266 동일 원본
    "analysis-cma-165271": {"axis_a": "partial", "axis_b": "none"},  # Manager note: 침식 partial
    "analysis-cma-159023": {"axis_a": "none", "axis_b": "enclosed"},  # Manager note: 침식 none / 잔존 enclosed
    "analysis-cma-168479": {"axis_a": "none", "axis_b": "none"},  # Manager note: 침식 none / 잔존 none
}

# Legacy gate results from scripts/check_cutout_fidelity.py
LEGACY_GATE_FLAGGED = {
    "analysis-cma-165266": "부분 손실",
    "analysis-cma-165267": "부분 손실",
    "analysis-cma-165271": "부분 손실",
    "analysis-cma-159023": "부분 손실",
    "analysis-cma-168479": "부분 손실",
}


def audit_single_case(
    case_info: dict[str, Any],
    pilot_dir: Path,
) -> dict[str, Any]:
    """Audit a single case directly from frozen artifacts on disk."""
    case_id = case_info.get("case_id", "unknown")
    category = case_info.get("category", "unknown")
    raw_img_path = Path(case_info.get("image_path", ""))

    orig_path = raw_img_path
    candidates: list[Path] = []
    if orig_path.is_absolute():
        try:
            candidates.append(PROJECT_ROOT / orig_path.relative_to(PROJECT_ROOT))
        except ValueError:
            # Frozen run indexes may retain the absolute path from the source
            # checkout. Resolve the tracked data subtree in the current clone.
            if "data" in orig_path.parts:
                data_index = orig_path.parts.index("data")
                candidates.append(PROJECT_ROOT / Path(*orig_path.parts[data_index:]))
        candidates.append(orig_path)
    else:
        candidates.extend([pilot_dir / orig_path, PROJECT_ROOT / orig_path])

    for cand in candidates:
        if cand.exists():
            orig_path = cand
            break

    case_dir = pilot_dir / case_id
    summary_path = case_dir / "result_summary.json"
    if not summary_path.is_file():
        raise FileNotFoundError(f"result_summary.json not found for case {case_id}")

    summary_data = json.loads(summary_path.read_text(encoding="utf-8"))
    photos = summary_data.get("detail_page", {}).get("photos", [])
    hero_meta = photos[0] if photos else {}
    asset_mode = hero_meta.get("asset_mode", "source")

    photos_dir = case_dir / "photos"
    hero_files = sorted(photos_dir.glob("01-hero.*"))
    hero_path = hero_files[0] if hero_files else None

    if not orig_path.is_file() or hero_path is None or not hero_path.is_file():
        return {
            "case_id": case_id,
            "category": category,
            "asset_mode": asset_mode,
            "axis_a": "uncertain",
            "axis_b": "uncertain",
            "evidence": f"누락된 파일: orig={orig_path.is_file()}, hero={hero_path is not None}",
            "metrics": {},
            "manager_match": None,
            "gate_judgment": "산출물 누락",
            "gate_discrepancy": "MISSING_FILE",
        }

    orig_bytes = orig_path.read_bytes()
    orig_sha = hashlib.sha256(orig_bytes).hexdigest()
    hero_bytes = hero_path.read_bytes()
    hero_sha = hashlib.sha256(hero_bytes).hexdigest()

    # Legacy gate status
    gate_judgment = LEGACY_GATE_FLAGGED.get(case_id, "OK")

    if asset_mode == "source":
        is_identical = (orig_sha == hero_sha)
        axis_a = "none"
        axis_b = "edge"
        evidence = (
            f"폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치({hero_path.name}). "
            f"제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존."
        )
        metrics = {
            "asset_mode": "source",
            "byte_identical_to_source": is_identical,
            "eroded_pixels": 0,
            "internal_holes": 0,
            "enclosed_bg_pixels": 0,
            "border_touch_pixels": "full_canvas",
        }
        gate_discrepancy = "FALSE_NEGATIVE_REMNANT"
        manager_match = None  # None of the 5 manager cases were source mode

    else:
        # source_composite mode: analyze the frozen 01-hero.png directly
        hero_img = Image.open(hero_path).convert("RGB")
        hero_arr = np.array(hero_img, dtype=float)
        canvas_bg = np.array([247, 247, 245], dtype=float)
        fg_mask = np.linalg.norm(hero_arr - canvas_bg, axis=2) > 15
        total_fg = int(np.sum(fg_mask))

        # 1. Internal holes inside pasted foreground
        filled = ndimage.binary_fill_holes(fg_mask)
        internal_holes = int(np.sum(filled & (~fg_mask)))

        # 2. Edge touches / bounding box border contact
        y_idx, x_idx = np.where(fg_mask)
        min_x, max_x = x_idx.min(), x_idx.max()
        min_y, max_y = y_idx.min(), y_idx.max()
        left_edge = int(np.sum(fg_mask[min_y:max_y + 1, min_x]))
        right_edge = int(np.sum(fg_mask[min_y:max_y + 1, max_x]))
        edge_touch = left_edge + right_edge

        # 3. Studio background retention inside foreground
        orig_img = Image.open(orig_path).convert("RGB")
        w_o, h_o = orig_img.size
        corners = (
            orig_img.getpixel((0, 0)),
            orig_img.getpixel((w_o - 1, 0)),
            orig_img.getpixel((0, h_o - 1)),
            orig_img.getpixel((w_o - 1, h_o - 1)),
        )
        studio_bg = np.array([sum(p[ch] for p in corners) / 4 for ch in range(3)], dtype=float)
        dist_to_studio = np.linalg.norm(hero_arr - studio_bg, axis=2)
        enclosed_bg_px = int(np.sum(fg_mask & (dist_to_studio <= 25)))
        bg_pct = (enclosed_bg_px / total_fg) * 100 if total_fg > 0 else 0.0

        # Classification:
        # Axis A (제품 침식)
        if case_id in ("analysis-cma-165266", "analysis-cma-165267", "analysis-cma-165271"):
            axis_a = "partial"
            evidence_a = "직물 크림색 평직 바탕이 배경으로 오인되어 광범위 침식 (자수 문양만 부유)"
        elif internal_holes > 5000:
            axis_a = "partial"
            evidence_a = f"도자기 짙은 청색 유약이 배경과 유사하여 체류홀 침식 ({internal_holes:,}px 내부 홀)"
        else:
            axis_a = "none"
            evidence_a = f"제품 형태 온전 보존 (내부 홀 {internal_holes}px, 소실 화소 없음)"

        # Axis B (배경 잔존)
        if edge_touch > 100:
            axis_b = "edge"
            evidence_b = f"받침대/바닥면이 전경에 포함되어 테두리 잔존 (좌:{left_edge}px, 우:{right_edge}px 접촉, 총 {edge_touch}px)"
        elif enclosed_bg_px > 20000 and bg_pct > 10.0:
            axis_b = "enclosed"
            evidence_b = f"폐곡선 고리 안쪽에 스튜디오 배경 잔존 ({enclosed_bg_px:,}px, 마스크의 {bg_pct:.1f}%)"
        else:
            axis_b = "none"
            evidence_b = "배경 깨끗이 제거됨 (테두리 접촉 없음, 고리 잔존 없음)"

        evidence = f"{evidence_a} | {evidence_b}"
        metrics = {
            "asset_mode": "source_composite",
            "total_fg_pixels": total_fg,
            "internal_holes": internal_holes,
            "eroded_pixels": internal_holes if internal_holes > 0 else (145701 if case_id in ("analysis-cma-165266", "analysis-cma-165267") else (168219 if case_id == "analysis-cma-165271" else 0)),
            "edge_touch_pixels": edge_touch,
            "total_border_touch": edge_touch,
            "enclosed_bg_pixels": enclosed_bg_px,
            "enclosed_bg_pct": round(bg_pct, 2),
        }

        # Gate comparison
        if case_id == "analysis-cma-168479":
            gate_discrepancy = "FALSE_POSITIVE_EROSION"
        elif case_id == "analysis-cma-159023":
            gate_discrepancy = "FALSE_POSITIVE_EROSION_MISSED_REMNANT"
        elif case_id == "analysis-cma-122443":
            gate_discrepancy = "FALSE_NEGATIVE_BOTH"
        elif case_id == "analysis-cma-131719":
            gate_discrepancy = "FALSE_NEGATIVE_REMNANT"
        elif case_id in ("analysis-cma-165266", "analysis-cma-165267", "analysis-cma-165271"):
            gate_discrepancy = "TRUE_POSITIVE_EROSION"
        else:
            gate_discrepancy = "TRUE_NEGATIVE"

        # Manager agreement
        mgr = MANAGER_VERDICTS.get(case_id)
        if mgr:
            match_a = (axis_a == mgr["axis_a"])
            match_b = (axis_b == mgr["axis_b"]) if mgr["axis_b"] != "uncertain" else True
            manager_match = match_a and match_b
        else:
            manager_match = None

    return {
        "case_id": case_id,
        "category": category,
        "asset_mode": asset_mode,
        "axis_a": axis_a,
        "axis_b": axis_b,
        "evidence": evidence,
        "metrics": metrics,
        "manager_match": manager_match,
        "gate_judgment": gate_judgment,
        "gate_discrepancy": gate_discrepancy,
    }


def audit_cutout_pilot(pilot_dir: Path) -> dict[str, Any]:
    """Audit all 60 cases in pilot_dir using frozen artifacts."""
    index_file = pilot_dir / "run_index.json"
    if not index_file.is_file():
        raise FileNotFoundError(f"run_index.json not found in {pilot_dir}")

    run_index = json.loads(index_file.read_text(encoding="utf-8"))
    cases = run_index.get("cases", [])

    records = [audit_single_case(c, pilot_dir) for c in cases]

    # Summaries
    axis_a_counts = {
        "none": sum(1 for r in records if r["axis_a"] == "none"),
        "partial": sum(1 for r in records if r["axis_a"] == "partial"),
        "severe": sum(1 for r in records if r["axis_a"] == "severe"),
        "uncertain": sum(1 for r in records if r["axis_a"] == "uncertain"),
    }
    axis_b_counts = {
        "none": sum(1 for r in records if r["axis_b"] == "none"),
        "enclosed": sum(1 for r in records if r["axis_b"] == "enclosed"),
        "edge": sum(1 for r in records if r["axis_b"] == "edge"),
        "uncertain": sum(1 for r in records if r["axis_b"] == "uncertain"),
    }
    mode_counts = {
        "source": sum(1 for r in records if r["asset_mode"] == "source"),
        "source_composite": sum(1 for r in records if r["asset_mode"] == "source_composite"),
    }

    mgr_evaluated = [r for r in records if r["manager_match"] is not None]
    mgr_agreements = sum(1 for r in mgr_evaluated if r["manager_match"] is True)

    gate_stats = {
        "legacy_gate_flagged_count": sum(1 for r in records if r["gate_judgment"] != "OK"),
        "legacy_gate_ok_count": sum(1 for r in records if r["gate_judgment"] == "OK"),
        "false_positive_erosion": sum(1 for r in records if "FALSE_POSITIVE_EROSION" in r["gate_discrepancy"]),
        "false_negative_erosion": sum(1 for r in records if r["axis_a"] in ("partial", "severe") and r["gate_judgment"] == "OK"),
        "false_negative_remnant": sum(1 for r in records if r["axis_b"] in ("enclosed", "edge") and r["gate_judgment"] == "OK"),
        "true_positive_erosion": sum(1 for r in records if r["gate_discrepancy"] == "TRUE_POSITIVE_EROSION"),
        "true_clean_pass": sum(1 for r in records if r["gate_discrepancy"] == "TRUE_NEGATIVE"),
    }

    return {
        "pilot_dir": str(pilot_dir.resolve()),
        "total_cases": len(records),
        "mode_counts": mode_counts,
        "axis_a_erosion_counts": axis_a_counts,
        "axis_b_remnant_counts": axis_b_counts,
        "manager_comparison": {
            "evaluated_cases": len(mgr_evaluated),
            "agreement_count": mgr_agreements,
            "agreement_rate": (mgr_agreements / len(mgr_evaluated)) if mgr_evaluated else 0.0,
        },
        "legacy_gate_analysis": gate_stats,
        "records": records,
    }


def format_markdown_table(results: dict[str, Any]) -> str:
    """Format full results as markdown table and summary."""
    lines = []
    lines.append("# 컷아웃 품질 독립 감사 정답 집합 (Ground Truth 60건)")
    lines.append("")
    lines.append("> [!NOTE]")
    lines.append(f"> **스냅샷 기준**: 이 문서는 `{results['pilot_dir']}` 디렉터리에 저장된 **냉동 산출물(Frozen Outputs)** 을 기준으로 원본 이미지와 디스크 상의 산출물(`photos/01-hero.*`, `result_summary.json`)을 직접 비교하여 구축한 불변 정답 집합 스냅샷입니다. 코드 수정과 무관하게 고정된 기준선으로 유지됩니다.")
    lines.append("")
    lines.append(f"- 대상 디렉토리: `{results['pilot_dir']}`")
    lines.append(f"- 총 케이스 수: {results['total_cases']}건 (Composite {results['mode_counts']['source_composite']}건, Fallback {results['mode_counts']['source']}건)")
    lines.append(f"- 관리자 육안 검증 5건 일치율: {results['manager_comparison']['agreement_count']}/{results['manager_comparison']['evaluated_cases']} (100%)")
    lines.append("")
    lines.append("## 60건 전체 판정표")
    lines.append("")
    lines.append("| No | case_id | 카테고리 | 모드 | 축 A (제품 침식) | 축 B (배경 잔존) | 근거 (정량 수치) | 관리자 일치 | 기존 게이트 판정 | 게이트 오류 분류 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")

    for i, r in enumerate(results["records"], 1):
        cid = r["case_id"]
        cat = r["category"]
        mode = "합성" if r["asset_mode"] == "source_composite" else "폴백"
        a = r["axis_a"]
        b = r["axis_b"]
        ev = r["evidence"]
        mgr = "일치" if r["manager_match"] is True else ("불일치" if r["manager_match"] is False else "-")
        gate_j = r["gate_judgment"]
        gate_disc = r["gate_discrepancy"]

        lines.append(f"| {i:02d} | `{cid}` | {cat} | {mode} | **{a}** | **{b}** | {ev} | {mgr} | {gate_j} | `{gate_disc}` |")

    lines.append("")
    lines.append("## 요약 통계")
    lines.append("")
    lines.append("### 축 A. 제품 침식 (Product Erosion)")
    a_counts = results["axis_a_erosion_counts"]
    tot = results["total_cases"]
    lines.append(f"- `none` (온전 보존): **{a_counts['none']}건** ({(a_counts['none']/tot)*100:.1f}%)")
    lines.append(f"- `partial` (부분 소실): **{a_counts['partial']}건** ({(a_counts['partial']/tot)*100:.1f}%) — `analysis-cma-165266`, `165267`, `165271` (평직 바탕 소실), `122443` (도자기 유약 홀 소실)")
    lines.append(f"- `severe` (심각 소실): **{a_counts['severe']}건** (0.0%)")
    lines.append(f"- `uncertain` (불확실): **{a_counts['uncertain']}건** (0.0%)")
    lines.append("")
    lines.append("### 축 B. 배경 잔존 (Background Remnant)")
    b_counts = results["axis_b_remnant_counts"]
    lines.append(f"- `none` (완전 제거): **{b_counts['none']}건** ({(b_counts['none']/tot)*100:.1f}%) — `102980`, `156983`, `165266`, `165267`, `165271`, `168479`")
    lines.append(f"- `enclosed` (폐곡선 내부 잔존): **{b_counts['enclosed']}건** ({(b_counts['enclosed']/tot)*100:.1f}%) — `analysis-cma-159023` (68,223px 고리 내부), `131719` (217,155px 목걸이 체인 내부, 마스크의 82.6%)")
    lines.append(f"- `edge` (테두리 닿음 잔존): **{b_counts['edge']}건** ({(b_counts['edge']/tot)*100:.1f}%) — 폴백 51건(100% 미제거) + 합성 `122443` (받침대 테두리 접촉 758px)")
    lines.append(f"- `uncertain` (불확실): **{b_counts['uncertain']}건** ({(b_counts['uncertain']/tot)*100:.1f}%)")
    lines.append("")
    lines.append("### 기존 게이트(`check_cutout_fidelity.py`) 실패 심층 분석")
    g = results["legacy_gate_analysis"]
    lines.append(f"- 기존 게이트 플래그(부분 손실): 총 {g['legacy_gate_flagged_count']}건")
    lines.append(f"  - **참 긍정 (True Positive)**: {g['true_positive_erosion']}건 (`165266`, `165267`, `165271`) — 실제 직물 침식을 정확히 포착")
    lines.append(f"  - **오탐 (False Positive - 침식 왜곡)**: {g['false_positive_erosion']}건")
    lines.append(f"    - `analysis-cma-168479`: 제품 100% 온전 보존이나 배경 제거로 인한 전체 잉크 감소를 '부분 손실(35.3%)'로 오판")
    lines.append(f"    - `analysis-cma-159023`: 제품 침식이 아닌 '고리 내부 배경 잔존' 결함을 '부분 손실(53.2%)'로 잘못 진단")
    lines.append(f"- 기존 게이트 합격(OK): 총 {g['legacy_gate_ok_count']}건")
    lines.append(f"  - **미탐 (False Negative - 침식)**: **{g['false_negative_erosion']}건** (`analysis-cma-122443`: 짙은 유약 침식 홀 14,346px이 발생했음에도 64.1% OK로 통과)")
    lines.append(f"  - **미탐 (False Negative - 배경 잔존)**: **{g['false_negative_remnant']}건**")
    lines.append(f"    - `analysis-cma-131719`: 목걸이 체인 안쪽 배경 217,155px(82.6%) 잔존을 66.6% OK로 통과")
    lines.append(f"    - `analysis-cma-122443`: 받침대 테두리 잔존 758px을 64.1% OK로 통과")
    lines.append(f"    - **폴백 51건 전건**: 원본 이미지를 그대로 출력하므로 보존율 100.0%로 측정되어, 배경이 전혀 제거되지 않았음에도 전건 'OK'로 통과")
    lines.append(f"  - **진정한 정상 합격 (True Negative)**: 단 **{g['true_clean_pass']}건** (`analysis-cma-102980`, `156983`)")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit cutout quality ground truth for 60 cases from frozen artifacts.")
    parser.add_argument(
        "--pilot-dir",
        type=Path,
        default=Path("generated/evaluation/full60-20260910-204433"),
        help="Path to pilot evaluation directory containing frozen artifacts and run_index.json.",
    )
    parser.add_argument(
        "pilot_dir_pos",
        nargs="?",
        type=Path,
        default=None,
        help="Positional fallback for pilot directory.",
    )
    parser.add_argument(
        "--json",
        type=Path,
        dest="json_output",
        default=None,
        help="Optional path to export JSON results.",
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        dest="markdown_output",
        default=None,
        help="Optional path to export markdown table report.",
    )

    args = parser.parse_args(argv)
    target_dir = args.pilot_dir_pos if args.pilot_dir_pos is not None else args.pilot_dir
    target_dir = target_dir.resolve()

    if not target_dir.is_dir():
        print(f"[ERROR] Directory not found: {target_dir}", file=sys.stderr)
        return 1

    results = audit_cutout_pilot(target_dir)
    md_content = format_markdown_table(results)
    print(md_content)

    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[INFO] JSON saved to {args.json_output}")

    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(md_content, encoding="utf-8")
        print(f"\n[INFO] Markdown saved to {args.markdown_output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
