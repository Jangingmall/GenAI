#!/usr/bin/env python3
"""Section plan diversity evaluation tool.

Measures how much section page plans actually differ across cases in a pilot run
by analyzing block_type sequences, set Jaccard similarities, common blocks,
length distributions, and positional fixedness.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def compute_common_blocks(plans: list[list[str]]) -> list[str]:
    """Find block_types that appear in every single case.

    Returns:
        Alphabetically sorted list of common block types.
    """
    if not plans:
        return []
    common = set(plans[0])
    for p in plans[1:]:
        common &= set(p)
    return sorted(common)


def compute_jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Compute Jaccard similarity: |A ∩ B| / |A ∪ B|.

    If both sets are empty, similarity is defined as 1.0.
    """
    if not set_a and not set_b:
        return 1.0
    union = set_a | set_b
    if not union:
        return 1.0
    return len(set_a & set_b) / len(union)


def compute_pairwise_similarities(
    case_ids: list[str],
    plans: list[list[str]],
) -> tuple[float, list[dict[str, Any]], list[tuple[str, str]]]:
    """Compute pairwise Jaccard similarities across all unique case pairs.

    Returns:
        (avg_jaccard, pairwise_records, identical_pairs)
    """
    n = len(plans)
    if n < 2:
        return 0.0, [], []

    sets = [set(p) for p in plans]
    pairwise_records: list[dict[str, Any]] = []
    identical_pairs: list[tuple[str, str]] = []
    total_jaccard = 0.0

    for i, j in itertools.combinations(range(n), 2):
        s_a, s_b = sets[i], sets[j]
        cid_a, cid_b = case_ids[i], case_ids[j]
        jaccard = compute_jaccard_similarity(s_a, s_b)
        total_jaccard += jaccard
        is_identical = (s_a == s_b)
        if is_identical:
            identical_pairs.append((cid_a, cid_b))

        intersection = s_a & s_b
        union = s_a | s_b
        pairwise_records.append({
            "case_a": cid_a,
            "case_b": cid_b,
            "jaccard": round(jaccard, 6),
            "jaccard_pct": round(jaccard * 100, 2),
            "intersection_count": len(intersection),
            "union_count": len(union),
            "common_blocks": sorted(intersection),
            "is_identical": is_identical,
        })

    avg_jaccard = total_jaccard / len(pairwise_records)
    return avg_jaccard, pairwise_records, identical_pairs


def compute_length_distribution(plans: list[list[str]]) -> dict[int, int]:
    """Count plans by sequence length.

    Returns:
        Dictionary mapping length -> case count, sorted by length.
    """
    counter: Counter[int] = Counter(len(p) for p in plans)
    return dict(sorted(counter.items()))


def compute_positional_fixedness(plans: list[list[str]]) -> list[dict[str, Any]]:
    """Analyze the most frequent block_type at each position across plans.

    Returns:
        List of positional statistics for position 1..max_length.
    """
    if not plans:
        return []

    max_len = max(len(p) for p in plans)
    positions: list[dict[str, Any]] = []

    for pos_idx in range(max_len):
        pos_num = pos_idx + 1
        blocks_at_pos = [p[pos_idx] for p in plans if len(p) > pos_idx]
        total_at_pos = len(blocks_at_pos)
        counts = Counter(blocks_at_pos)
        most_common_block, most_common_count = counts.most_common(1)[0]
        ratio = most_common_count / total_at_pos if total_at_pos > 0 else 0.0

        positions.append({
            "position": pos_num,
            "most_frequent_block": most_common_block,
            "most_frequent_count": most_common_count,
            "total_at_position": total_at_pos,
            "fixedness_ratio": round(ratio, 4),
            "fixedness_pct": round(ratio * 100, 1),
            "distribution": dict(counts.most_common()),
        })

    return positions


def compute_sequence_diversity(plans: list[list[str]]) -> dict[str, Any]:
    """Count unique ordered block sequences and max frequency."""
    seq_counter: Counter[tuple[str, ...]] = Counter(tuple(p) for p in plans)
    unique_count = len(seq_counter)
    max_freq = max(seq_counter.values()) if seq_counter else 0

    sequences = [
        {"sequence": list(seq), "count": count}
        for seq, count in seq_counter.most_common()
    ]
    return {
        "unique_sequence_count": unique_count,
        "max_frequency": max_freq,
        "total_cases": len(plans),
        "sequences": sequences,
    }


def load_pilot_plans(pilot_dir: Path) -> list[dict[str, Any]]:
    """Load case plans from a pilot run directory.

    Reads `run_index.json` if available, otherwise globs subdirectories.
    """
    if not pilot_dir.is_dir():
        raise FileNotFoundError(f"Pilot directory not found: {pilot_dir}")

    run_index_path = pilot_dir / "run_index.json"
    records: list[dict[str, Any]] = []

    if run_index_path.is_file():
        try:
            run_index = json.loads(run_index_path.read_text(encoding="utf-8"))
            cases = run_index.get("cases", [])
            for c in cases:
                case_id = c.get("case_id") or Path(c.get("output_dir", "")).name
                category = c.get("category", "unknown")
                out_dir_str = c.get("output_dir")
                out_dir = Path(out_dir_str) if out_dir_str else pilot_dir / case_id
                summary_file = out_dir / "result_summary.json"

                if not summary_file.is_file():
                    # Fallback to pilot_dir / case_id / result_summary.json
                    alt_summary = pilot_dir / case_id / "result_summary.json"
                    if alt_summary.is_file():
                        summary_file = alt_summary
                    else:
                        continue

                summary_data = json.loads(summary_file.read_text(encoding="utf-8"))
                plan = (
                    summary_data.get("product", {}).get("page_plan")
                    or summary_data.get("draft", {}).get("page_plan")
                    or summary_data.get("page_plan")
                    or []
                )
                blocks = [
                    b.get("block_type")
                    for b in plan
                    if isinstance(b, dict) and "block_type" in b
                ]
                records.append({
                    "case_id": case_id,
                    "category": category,
                    "blocks": blocks,
                    "block_count": len(blocks),
                    "summary_path": str(summary_file),
                })
        except Exception as exc:
            print(f"[WARN] Failed parsing run_index.json ({exc}); falling back to glob", file=sys.stderr)
            records = []

    if not records:
        for summary_file in sorted(pilot_dir.glob("*/result_summary.json")):
            case_id = summary_file.parent.name
            try:
                summary_data = json.loads(summary_file.read_text(encoding="utf-8"))
                plan = (
                    summary_data.get("product", {}).get("page_plan")
                    or summary_data.get("draft", {}).get("page_plan")
                    or summary_data.get("page_plan")
                    or []
                )
                blocks = [
                    b.get("block_type")
                    for b in plan
                    if isinstance(b, dict) and "block_type" in b
                ]
                category = summary_data.get("product", {}).get("product_type", "unknown")
                records.append({
                    "case_id": case_id,
                    "category": category,
                    "blocks": blocks,
                    "block_count": len(blocks),
                    "summary_path": str(summary_file),
                })
            except Exception as exc:
                print(f"[WARN] Skipping unreadable {summary_file}: {exc}", file=sys.stderr)

    if not records:
        raise ValueError(f"No valid result_summary.json cases found in {pilot_dir}")

    return records


def evaluate_plan_diversity(
    records: list[dict[str, Any]],
    *,
    max_avg_jaccard: float = 0.60,
    max_common_blocks: int = 4,
    max_identical_pairs: int = 0,
) -> dict[str, Any]:
    """Evaluate plan diversity against quality gates.

    Quality Gate Thresholds:
      1. Average Jaccard Similarity <= max_avg_jaccard (default 0.60 / 60%)
      2. Common block types count <= max_common_blocks (default 4)
      3. Identical set pairs count <= max_identical_pairs (default 0)
    """
    case_ids = [r["case_id"] for r in records]
    plans = [r["blocks"] for r in records]

    common_blocks = compute_common_blocks(plans)
    avg_jaccard, pairwise_records, identical_pairs = compute_pairwise_similarities(case_ids, plans)
    length_distribution = compute_length_distribution(plans)
    positional_fixedness = compute_positional_fixedness(plans)
    sequence_diversity = compute_sequence_diversity(plans)

    # Gate evaluations
    gate_avg_jaccard_pass = (avg_jaccard <= max_avg_jaccard)
    gate_common_blocks_pass = (len(common_blocks) <= max_common_blocks)
    gate_identical_pairs_pass = (len(identical_pairs) <= max_identical_pairs)

    overall_pass = (
        gate_avg_jaccard_pass
        and gate_common_blocks_pass
        and gate_identical_pairs_pass
    )

    failures: list[str] = []
    if not gate_avg_jaccard_pass:
        failures.append(
            f"평균 집합 일치도 초과: {avg_jaccard * 100:.1f}% (기준: <= {max_avg_jaccard * 100:.1f}%)"
        )
    if not gate_common_blocks_pass:
        failures.append(
            f"공통 블록 종수 초과: {len(common_blocks)}종 (기준: <= {max_common_blocks}종) {common_blocks}"
        )
    if not gate_identical_pairs_pass:
        pairs_repr = ", ".join(f"({a}, {b})" for a, b in identical_pairs)
        failures.append(
            f"완전 일치 쌍 존재: {len(identical_pairs)}쌍 (기준: <= {max_identical_pairs}쌍) [{pairs_repr}]"
        )

    return {
        "pass": overall_pass,
        "failures": failures,
        "thresholds": {
            "max_avg_jaccard": max_avg_jaccard,
            "max_common_blocks": max_common_blocks,
            "max_identical_pairs": max_identical_pairs,
        },
        "gates": {
            "avg_jaccard": {
                "value": round(avg_jaccard, 6),
                "value_pct": round(avg_jaccard * 100, 2),
                "threshold_pct": round(max_avg_jaccard * 100, 2),
                "pass": gate_avg_jaccard_pass,
            },
            "common_blocks": {
                "count": len(common_blocks),
                "blocks": common_blocks,
                "threshold": max_common_blocks,
                "pass": gate_common_blocks_pass,
            },
            "identical_pairs": {
                "count": len(identical_pairs),
                "pairs": [list(p) for p in identical_pairs],
                "threshold": max_identical_pairs,
                "pass": gate_identical_pairs_pass,
            },
        },
        "metrics": {
            "total_cases": len(records),
            "common_blocks": common_blocks,
            "common_block_count": len(common_blocks),
            "avg_jaccard": round(avg_jaccard, 6),
            "avg_jaccard_pct": round(avg_jaccard * 100, 2),
            "identical_pairs_count": len(identical_pairs),
            "identical_pairs": [list(p) for p in identical_pairs],
            "length_distribution": length_distribution,
            "positional_fixedness": positional_fixedness,
            "sequence_diversity": sequence_diversity,
        },
        "cases": records,
        "pairwise": pairwise_records,
    }


def print_report(results: dict[str, Any]) -> None:
    """Print a clean Markdown report of the diversity metrics and gate evaluation."""
    metrics = results["metrics"]
    gates = results["gates"]
    total = metrics["total_cases"]

    print("=" * 72)
    print("      파일럿 섹션 구성 다양성 측정 보고서 (Section Plan Diversity)      ")
    print("=" * 72)
    print()

    # 1. Cases overview
    print(f"### 1. 대상 케이스 목록 (총 {total}건)")
    print("| 번호 | case_id | 카테고리 | 블록 수 | 블록 시퀀스 |")
    print("|:---:|---|---|:---:|---|")
    for idx, c in enumerate(results["cases"], start=1):
        seq_str = " → ".join(c["blocks"])
        print(f"| {idx} | {c['case_id']} | {c['category']} | {c['block_count']}개 | `{seq_str}` |")
    print()

    # 2. Key metrics
    print("### 2. 다양성 정량 측정 결과")
    print(f"1. **공통 블록 수**: {metrics['common_block_count']}종")
    if metrics["common_blocks"]:
        print(f"   - 전 케이스 공통 블록: `{', '.join(metrics['common_blocks'])}`")
    else:
        print("   - 전 케이스 공통 블록 없음 (완전 분기)")

    print(f"2. **평균 집합 일치도 (Jaccard)**: {metrics['avg_jaccard_pct']:.1f}%")
    print(f"3. **완전 일치 쌍 수 (100% 동일 집합)**: {metrics['identical_pairs_count']}쌍")
    if metrics["identical_pairs"]:
        for a, b in metrics["identical_pairs"]:
            print(f"   - `{a}` ↔ `{b}` (100.0%)")

    print(f"4. **길이 분포**: {', '.join(f'{l}블록: {cnt}건' for l, cnt in metrics['length_distribution'].items())}")

    seq_div = metrics["sequence_diversity"]
    print(f"5. **고유 시퀀스 종수**: {seq_div['unique_sequence_count']}종 / {total}건 (최빈 시퀀스 {seq_div['max_frequency']}회 반복)")
    print()

    # 3. Positional fixedness table
    print("### 3. 위치별 고정도 (Positional Fixedness)")
    print("| 위치 | 1위 블록_type | 빈도 / 대상 | 고정도 비율 | 기타 등장 블록 |")
    print("|:---:|---|:---:|:---:|---|")
    for pos in metrics["positional_fixedness"]:
        dist = pos["distribution"]
        others = [f"{b} ({c})" for b, c in dist.items() if b != pos["most_frequent_block"]]
        others_str = ", ".join(others) if others else "-"
        print(
            f"| {pos['position']} | `{pos['most_frequent_block']}` | "
            f"{pos['most_frequent_count']}/{pos['total_at_position']} | "
            f"**{pos['fixedness_pct']:.1f}%** | {others_str} |"
        )
    print()

    # 4. Pairwise similarity matrix
    print("### 4. 케이스 쌍별 Jaccard 유사도 매트릭스")
    case_ids = [c["case_id"] for c in results["cases"]]
    header = "| 케이스 | " + " | ".join(cid.replace("analysis-cma-", "") for cid in case_ids) + " |"
    sep = "|---|" + "|".join(":---:" for _ in case_ids) + "|"
    print(header)
    print(sep)

    # Build lookup
    pair_map: dict[tuple[str, str], float] = {}
    for p in results["pairwise"]:
        pair_map[(p["case_a"], p["case_b"])] = p["jaccard"]
        pair_map[(p["case_b"], p["case_a"])] = p["jaccard"]

    for cid_a in case_ids:
        row = [cid_a.replace("analysis-cma-", "")]
        for cid_b in case_ids:
            if cid_a == cid_b:
                row.append("1.00")
            else:
                j = pair_map.get((cid_a, cid_b), 0.0)
                row.append(f"{j:.2f}")
        print("| " + " | ".join(row) + " |")
    print()

    # 5. Quality gates judgment
    print("=" * 72)
    print("### 5. 품질 게이트 판정 결과 (Quality Gates)")
    g_jaccard = gates["avg_jaccard"]
    g_common = gates["common_blocks"]
    g_pairs = gates["identical_pairs"]

    j_mark = "[PASS]" if g_jaccard["pass"] else "[FAIL]"
    c_mark = "[PASS]" if g_common["pass"] else "[FAIL]"
    p_mark = "[PASS]" if g_pairs["pass"] else "[FAIL]"

    print(
        f"- {j_mark} **평균 집합 일치도**: {g_jaccard['value_pct']:.1f}% "
        f"(기준: <= {g_jaccard['threshold_pct']:.1f}%)"
    )
    print(
        f"- {c_mark} **공통 블록 종수**: {g_common['count']}종 "
        f"(기준: <= {g_common['threshold']}종) {g_common['blocks']}"
    )
    print(
        f"- {p_mark} **완전 일치 쌍 수**: {g_pairs['count']}쌍 "
        f"(기준: <= {g_pairs['threshold']}쌍)"
    )
    print()

    if results["pass"]:
        print("최종 판정: [PASS] 구성 다양성 기준을 전부 만족했습니다. (종료 코드 0)")
    else:
        print("최종 판정: [FAIL] 구성 다양성 기준 미달로 탈락했습니다. (종료 코드 1)")
        print("실패 사유:")
        for idx, reason in enumerate(results["failures"], start=1):
            print(f"  {idx}) {reason}")
    print("=" * 72)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure section plan diversity across pilot cases."
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
        "--max-avg-jaccard",
        type=float,
        default=0.60,
        help="Maximum allowed average Jaccard similarity across all pairs (default: 0.60 / 60%%).",
    )
    parser.add_argument(
        "--max-common-blocks",
        type=int,
        default=4,
        help="Maximum allowed count of block_types present in all cases (default: 4).",
    )
    parser.add_argument(
        "--max-identical-pairs",
        type=int,
        default=0,
        help="Maximum allowed count of pairs with 100%% identical block sets (default: 0).",
    )
    parser.add_argument(
        "--json",
        type=Path,
        dest="json_output",
        default=None,
        help="Path to save evaluation output as JSON.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output.",
    )

    args = parser.parse_args(argv)
    if args.pilot_dir is None and args.pilot_dir_pos is not None:
        args.pilot_dir = args.pilot_dir_pos

    if args.pilot_dir is None:
        parser.error("A pilot directory must be specified via --pilot-dir <path>.")

    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        records = load_pilot_plans(args.pilot_dir.resolve())
    except Exception as exc:
        print(f"[ERROR] Failed loading pilot plans: {exc}", file=sys.stderr)
        return 1

    results = evaluate_plan_diversity(
        records,
        max_avg_jaccard=args.max_avg_jaccard,
        max_common_blocks=args.max_common_blocks,
        max_identical_pairs=args.max_identical_pairs,
    )

    print_report(results)

    if args.json_output:
        out_path = args.json_output.resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON 결과가 저장되었습니다: {out_path}")

    return 0 if results["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
