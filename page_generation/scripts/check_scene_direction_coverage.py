#!/usr/bin/env python3
"""Scene direction branch coverage diagnostic tool.

Evaluates which background scene direction branch in `_product_scene_direction`
is selected for each product in a pilot run or the CMA real v1 evaluation dataset.
Directly imports and invokes `_product_scene_direction` from `src/detail_page_ai/prompts.py`.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from detail_page_ai.dto import ProductProfileDto
from detail_page_ai.prompts import _product_scene_direction

# ==============================================================================
# 카테고리별 기대 씬 분기 매핑 (Ground Truth)
#
# 근거:
# CMA Real v1 평가 데이터셋의 6대 카테고리 및 도메인 목표 배경 연출 방향:
# 1) textile   -> textile  (직물/섬유: 린넨 드레싱 및 텍스처 패브릭 무드)
# 2) box       -> box      (상자/칠기: 서가 및 데스크 연출)
# 3) ceramic   -> ceramic  (도자기/화병: 다이닝 코너 및 자연광 연출)
# 4) metalware -> metal    (금속 공예/기물: 모던 콘솔/사이드보드 및 스톤 표면)
# 5) furniture -> wood     (가구/도구: 원목 바닥 및 리딩 누크 서재 무드)
# 6) jewelry   -> jewelry  (장신구: 벨벳 트레이 및 미니멀 보석 디스플레이)
#    * jewelry 분기는 현재 prompts.py에 아직 구현되지 않음 (다른 워커 작업 중).
#    * 따라서 장신구 케이스가 metal/default 등으로 빠지는 것은 오분류/미구현으로 판정되어 회귀 게이트 실패(exit 1) 처리됨.
# ==============================================================================
CATEGORY_EXPECTED_BRANCH: dict[str, str] = {
    "textile": "textile",
    "box": "box",
    "ceramic": "ceramic",
    "metalware": "metal",
    "furniture": "wood",
    "jewelry": "jewelry",
}


def check_jewelry_branch_implemented() -> bool:
    """Check if _product_scene_direction in prompts.py implements a jewelry branch."""
    dummy = ProductProfileDto(
        product_type="장신구",
        display_name="보석 목걸이",
        summary="보석 장신구 목걸이",
        keywords=["jewelry", "목걸이", "장신구"],
    )
    try:
        direction = _product_scene_direction(dummy)
        branch, _ = identify_branch(direction)
        return branch == "jewelry"
    except Exception:
        return False


def identify_branch(direction: dict[str, Any]) -> tuple[str, bool]:
    """Identify which branch of _product_scene_direction produced the direction dict.

    Returns:
        (branch_name, is_unknown)
    """
    setting = direction.get("setting", "")
    combined = f"{setting} {direction.get('surface', '')} {direction.get('supporting', '')}".lower()

    if "tea table" in setting:
        return "tea", False
    if "bookcase" in setting or "writing desk" in setting:
        return "box", False
    if "linen-lined dressing" in setting:
        return "textile", False
    if "breakfast or dining corner" in setting:
        return "ceramic", False
    if "contemporary console or sideboard" in setting:
        return "metal", False
    if "reading nook" in setting:
        return "wood", False
    if any(k in combined for k in ("jewelry", "jewellery", "necklace", "ring", "earring", "brooch", "pendant", "velvet", "trinket", "vanity", "장신구", "보석")):
        return "jewelry", False
    if "lived-in interior with a clean matte tabletop" in setting:
        return "default", False

    # Setting did not match any predefined signatures
    return f"미상 ({setting[:30]}...)", True


def make_profile_from_summary(product_dict: dict[str, Any]) -> ProductProfileDto:
    """Instantiate ProductProfileDto from result_summary.json product dict."""
    valid_fields = set(ProductProfileDto.model_fields.keys())
    cleaned = {k: v for k, v in product_dict.items() if k in valid_fields}
    return ProductProfileDto.model_validate(cleaned)


def make_approximate_profile_from_source(
    asset_id: str,
    category: str,
    source_data: dict[str, Any],
    ref_facts: dict[str, Any],
) -> ProductProfileDto:
    """Create a minimal ProductProfileDto from CMA museum source record (approximate evaluation)."""
    title = source_data.get("title") or ref_facts.get("title") or asset_id
    technique = source_data.get("technique") or ref_facts.get("technique") or ""
    ptype = source_data.get("type") or ref_facts.get("type") or category
    culture = source_data.get("culture") or ref_facts.get("culture") or ""
    if isinstance(culture, list):
        culture = " ".join(str(c) for c in culture)

    summary = f"{title}. {technique}. {culture}".strip()
    return ProductProfileDto(
        product_type=str(ptype),
        display_name=str(title),
        summary=summary,
        keywords=[category],
        observations={"materials": [technique]} if technique else {},
    )


def evaluate_pilot_run(pilot_dir: Path) -> dict[str, Any]:
    """Evaluate cases in a pilot run directory."""
    index_path = pilot_dir / "run_index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"run_index.json not found in {pilot_dir}")

    run_index = json.loads(index_path.read_text(encoding="utf-8"))
    cases = run_index.get("cases", [])
    records = []

    for case in cases:
        case_id = case.get("case_id", "")
        asset_id = case.get("asset_id", "")
        category = case.get("category", "")
        output_dir = Path(case.get("output_dir", pilot_dir / case_id))

        summary_file = output_dir / "result_summary.json"
        if not summary_file.exists():
            records.append({
                "case_id": case_id,
                "asset_id": asset_id,
                "category": category,
                "product_name": "결과 파일 없음",
                "product_type": "",
                "expected_branch": CATEGORY_EXPECTED_BRANCH.get(category, "미상"),
                "branch": "오류 (파일 누락)",
                "match_status": "unknown",
                "setting": "",
                "is_default": False,
                "is_unknown": True,
            })
            continue

        summary_data = json.loads(summary_file.read_text(encoding="utf-8"))
        product = summary_data.get("product", {})
        profile = make_profile_from_summary(product)

        direction = _product_scene_direction(profile)
        branch, is_unknown = identify_branch(direction)
        is_default = (branch == "default")
        expected_branch = CATEGORY_EXPECTED_BRANCH.get(category, "미상")

        if is_unknown:
            match_status = "unknown"
        elif is_default:
            match_status = "default"
        elif branch == expected_branch:
            match_status = "match"
        else:
            match_status = "misclassified"

        records.append({
            "case_id": case_id,
            "asset_id": asset_id,
            "category": category,
            "product_name": profile.display_name or profile.product_type,
            "product_type": profile.product_type,
            "expected_branch": expected_branch,
            "branch": branch,
            "match_status": match_status,
            "setting": direction.get("setting", ""),
            "is_default": is_default,
            "is_unknown": is_unknown,
        })

    return {
        "mode": "pilot",
        "target": str(pilot_dir.resolve()),
        "approximate": False,
        "records": records,
    }


def evaluate_dataset(
    manifest_path: Path,
    sources_dir: Path,
) -> dict[str, Any]:
    """Evaluate 60 cases from CMA real v1 dataset (approximate evaluation)."""
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assets = manifest.get("assets", [])
    records = []

    for asset in assets:
        asset_id = asset.get("asset_id", "")
        category = asset.get("category", "")
        ref_facts = asset.get("reference_facts", {})

        source_file = sources_dir / f"{asset_id}.json"
        source_data = json.loads(source_file.read_text(encoding="utf-8")) if source_file.exists() else {}

        profile = make_approximate_profile_from_source(asset_id, category, source_data, ref_facts)
        direction = _product_scene_direction(profile)
        branch, is_unknown = identify_branch(direction)
        is_default = (branch == "default")
        expected_branch = CATEGORY_EXPECTED_BRANCH.get(category, "미상")

        if is_unknown:
            match_status = "unknown"
        elif is_default:
            match_status = "default"
        elif branch == expected_branch:
            match_status = "match"
        else:
            match_status = "misclassified"

        records.append({
            "case_id": f"analysis-{asset_id}",
            "asset_id": asset_id,
            "category": category,
            "product_name": profile.display_name or profile.product_type,
            "product_type": profile.product_type,
            "expected_branch": expected_branch,
            "branch": branch,
            "match_status": match_status,
            "setting": direction.get("setting", ""),
            "is_default": is_default,
            "is_unknown": is_unknown,
        })

    return {
        "mode": "dataset",
        "target": str(manifest_path.resolve()),
        "approximate": True,
        "records": records,
    }


def compute_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute aggregate matrix, match status counts, and failure cases."""
    categories = sorted({r["category"] for r in records})
    branches = sorted({r["branch"] for r in records})

    # Standard branch display order
    order_pref = ["tea", "box", "textile", "ceramic", "metal", "wood", "jewelry", "default"]
    ordered_branches = [b for b in order_pref if b in branches] + [b for b in branches if b not in order_pref]

    matrix: dict[str, dict[str, int]] = {}
    for cat in categories:
        matrix[cat] = {b: 0 for b in ordered_branches}

    for r in records:
        matrix[r["category"]][r["branch"]] += 1

    totals_by_branch = {b: sum(matrix[c][b] for c in categories) for b in ordered_branches}

    match_cases = [r for r in records if r["match_status"] == "match"]
    misclassified_cases = [r for r in records if r["match_status"] == "misclassified"]
    default_cases = [r for r in records if r["match_status"] == "default"]
    unknown_cases = [r for r in records if r["match_status"] == "unknown"]

    return {
        "categories": categories,
        "branches": ordered_branches,
        "matrix": matrix,
        "totals_by_branch": totals_by_branch,
        "total_count": len(records),
        "match_count": len(match_cases),
        "misclassified_count": len(misclassified_cases),
        "default_count": len(default_cases),
        "unknown_count": len(unknown_cases),
        "misclassified_cases": misclassified_cases,
        "default_cases": default_cases,
        "unknown_cases": unknown_cases,
    }


def print_report(data: dict[str, Any], verbose: bool = False, strict: bool = True) -> None:
    """Print formatted markdown report of coverage evaluation."""
    mode = data["mode"]
    target = data["target"]
    approximate = data["approximate"]
    records = data["records"]
    summary = compute_summary(records)
    jewelry_implemented = check_jewelry_branch_implemented()

    title_suffix = " (근사 판정)" if approximate else ""
    print(f"## 씬 분기 커버리지 진단 결과{title_suffix}")
    print(f"- 대상: `{target}`")
    print(f"- 평가 방식: {'sources 메타데이터 기반 근사 판정' if approximate else '파일럿 실제 산출물 판정'}")
    print(f"- 총 평가 건수: {summary['total_count']}건\n")

    # 1. Detail table with 기대 / 실제 / 판정
    print("### 1. 케이스별 씬 분기 판정 결과")
    print("| 카테고리 | case_id | asset_id | 제품명 / 유형 | 기대 분기 | 실제 분기 | 판정 |")
    print("|---|---|---|---|:---:|:---:|:---:|")

    for r in records:
        if r["match_status"] == "match":
            status_text = "일치 (정상)"
        elif r["match_status"] == "default":
            status_text = "**미대응 (default)**"
        elif r["match_status"] == "unknown":
            status_text = f"**미상 ({r['branch']})**"
        elif r["match_status"] == "misclassified":
            if r["expected_branch"] == "jewelry" and not jewelry_implemented:
                status_text = f"**오분류 ({r['branch']}, jewelry 미구현)**"
            else:
                status_text = f"**오분류 ({r['branch']})**"
        else:
            status_text = r["match_status"]

        prod_title = (r["product_name"][:25] + "...") if len(r["product_name"]) > 28 else r["product_name"]
        print(
            f"| {r['category']} | {r['case_id']} | {r['asset_id']} | {prod_title} "
            f"| `{r['expected_branch']}` | `{r['branch']}` | {status_text} |"
        )
    print()

    # 2. Matrix table
    print("### 2. 카테고리별 씬 분기 집계 (Coverage Matrix)")
    branches = summary["branches"]
    header = "| 카테고리 | " + " | ".join(f"`{b}`" for b in branches) + " | **합계** |"
    sep = "|---|" + "|".join(":---:" for _ in branches) + "|:---:|"
    print(header)
    print(sep)

    matrix = summary["matrix"]
    for cat in summary["categories"]:
        row_counts = [matrix[cat][b] for b in branches]
        row_total = sum(row_counts)
        row_str = " | ".join(str(c) if c > 0 else "-" for c in row_counts)
        print(f"| {cat} | {row_str} | {row_total} |")

    totals = [summary["totals_by_branch"][b] for b in branches]
    totals_str = " | ".join(f"**{c}**" if c > 0 else "-" for c in totals)
    print(f"| **전체 합계** | {totals_str} | **{summary['total_count']}** |")
    print()

    # 3. Summary stats & verdict
    print("### 3. 검증 통계 및 최종 판정")
    print(f"- 총 평가 건수: {summary['total_count']}건")
    print(f"- 기대 분기 일치: {summary['match_count']}건")
    print(f"- 오분류(기대 불일치): {summary['misclassified_count']}건")
    print(f"- 미대응(기본값 default): {summary['default_count']}건")
    if summary["unknown_count"] > 0:
        print(f"- 미상(알 수 없는 분기): {summary['unknown_count']}건")

    if not jewelry_implemented:
        print("- **참고: `prompts.py`에 `jewelry` 전용 분기가 아직 미구현된 상태입니다.**")

    is_passed = (summary["misclassified_count"] == 0 and summary["default_count"] == 0 and summary["unknown_count"] == 0)
    if not strict:
        is_passed = (summary["default_count"] == 0)
        print("- [옵션 적용] `--strict-off`: 오분류를 허용하고 기본값(default) 발생 시에만 실패로 판정합니다.")

    if is_passed:
        print("- **최종 판정: PASS (종료 코드 0)** - 모든 케이스가 기대 분기와 정상 매칭되었습니다.")
    else:
        print("- **최종 판정: FAIL (종료 코드 1)** - 오분류 또는 미대응(default) 케이스가 검출되었습니다.")
    print()

    # Misclassified cases detail
    if summary["misclassified_count"] > 0:
        print("#### [오분류 케이스 목록]")
        print("| 카테고리 | asset_id | 제품명 | 기대 분기 | 실제 분기 | 비고 |")
        print("|---|---|---|:---:|:---:|---|")
        for mc in summary["misclassified_cases"]:
            note = "jewelry 분기 미구현으로 metal 오분류" if mc["expected_branch"] == "jewelry" and not jewelry_implemented else "키워드 매칭 불일치"
            print(f"| {mc['category']} | {mc['asset_id']} | {mc['product_name']} | `{mc['expected_branch']}` | `{mc['branch']}` | {note} |")
        print()

    # Default cases detail
    if summary["default_count"] > 0:
        print("#### [기본값(default) 케이스 목록]")
        print("| 카테고리 | asset_id | 제품명 | 기대 분기 | setting 내용 일부 |")
        print("|---|---|---|:---:|---|")
        for dc in summary["default_cases"]:
            setting_snip = dc["setting"][:55] + "..." if len(dc["setting"]) > 55 else dc["setting"]
            print(f"| {dc['category']} | {dc['asset_id']} | {dc['product_name']} | `{dc['expected_branch']}` | {setting_snip} |")
        print()

    if verbose:
        print("### 4. 세부 setting 텍스트 전체")
        for r in records:
            print(f"- [{r['category']}] {r['asset_id']} ({r['branch']}):\n  `{r['setting']}`")
        print()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diagnose _product_scene_direction branch coverage on pilot runs or dataset."
    )
    parser.add_argument(
        "--pilot-dir",
        type=Path,
        default=None,
        help="Path to pilot run directory containing run_index.json and analysis-*/result_summary.json.",
    )
    parser.add_argument(
        "pilot_dir_pos",
        nargs="?",
        type=Path,
        default=None,
        help="Positional fallback for --pilot-dir.",
    )
    parser.add_argument(
        "--dataset",
        action="store_true",
        help="Evaluate coverage across all 60 cases in CMA real v1 dataset (approximate evaluation).",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=PROJECT_ROOT / "data/evaluation/cma_real_v1/manifest.json",
        help="Path to manifest.json (default: data/evaluation/cma_real_v1/manifest.json).",
    )
    parser.add_argument(
        "--sources-dir",
        type=Path,
        default=PROJECT_ROOT / "data/evaluation/cma_real_v1/sources",
        help="Path to sources/ directory (default: data/evaluation/cma_real_v1/sources).",
    )
    parser.add_argument(
        "--strict-off",
        action="store_true",
        help="Disable strict mode: fail only on default branch, treat misclassifications as warnings.",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        dest="json_output",
        help="Path to save JSON report output.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print full setting strings in output.",
    )

    args = parser.parse_args(argv)
    if args.pilot_dir is None and args.pilot_dir_pos is not None:
        args.pilot_dir = args.pilot_dir_pos

    if args.pilot_dir is None and not args.dataset:
        parser.error("Either --pilot-dir <path> or --dataset must be specified.")

    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        if args.dataset:
            data = evaluate_dataset(args.manifest, args.sources_dir)
        else:
            pilot_dir = args.pilot_dir.resolve()
            data = evaluate_pilot_run(pilot_dir)
    except Exception as exc:
        print(f"[ERROR] Coverage diagnosis failed: {exc}", file=sys.stderr)
        return 1

    strict = not args.strict_off
    print_report(data, verbose=args.verbose, strict=strict)

    summary = compute_summary(data["records"])

    if args.json_output:
        out_path = args.json_output.resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        is_passed = (summary["misclassified_count"] == 0 and summary["default_count"] == 0 and summary["unknown_count"] == 0) if strict else (summary["default_count"] == 0)
        json_payload = {
            "mode": data["mode"],
            "target": data["target"],
            "approximate": data["approximate"],
            "strict": strict,
            "pass": is_passed,
            "summary": {
                "total_count": summary["total_count"],
                "match_count": summary["match_count"],
                "misclassified_count": summary["misclassified_count"],
                "default_count": summary["default_count"],
                "unknown_count": summary["unknown_count"],
                "totals_by_branch": summary["totals_by_branch"],
                "matrix": summary["matrix"],
            },
            "misclassified_cases": summary["misclassified_cases"],
            "default_cases": summary["default_cases"],
            "records": data["records"],
        }
        out_path.write_text(json.dumps(json_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON 결과 저장 완료: {out_path}")

    # Exit code:
    # Strict mode (default): 1 if any misclassification, default, or unknown; 0 if all match
    # Strict-off mode: 1 if default_count > 0; 0 otherwise
    if strict:
        if summary["misclassified_count"] > 0 or summary["default_count"] > 0 or summary["unknown_count"] > 0:
            return 1
        return 0
    else:
        if summary["default_count"] > 0:
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(main())
