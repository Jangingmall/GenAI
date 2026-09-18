#!/usr/bin/env python3
"""Section plan diversity evaluation tool.

Measures how much section page plans actually differ across cases in a pilot run
by analyzing block_type sequences, set Jaccard similarities, common blocks,
length distributions, and positional fixedness.

Criteria are grounded in a Monte Carlo baseline computed from the catalog
archetypes (assets/references/detail-page-layouts.json):
  1. Average Jaccard similarity <= the batch-size baseline P95 + validation padding (default: +1.0%p)
  2. Effective common blocks (excluding mandatory hero & closing) <= 4
  3. Identical set pairs <= 1 (allows incidental birthday-paradox collision for small batches)
"""

from __future__ import annotations

import argparse
import itertools
import json
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = PROJECT_ROOT / "assets" / "references" / "detail-page-layouts.json"

# Structural fixed blocks enforced as first/last in all layouts by DTO and prompts.
# These cannot vary by design, so they are excluded from effective common block checks.
STRUCTURAL_BLOCKS: frozenset[str] = frozenset({"hero", "closing"})

# Default simulation parameters
DEFAULT_SIMULATION_ITERATIONS: int = 2000
DEFAULT_SIMULATION_SEED: int = 42

# Historical rationale for max_jaccard_delta = 0.10 (+10.0%p above catalog baseline):
#   1. Statistical variance: In sampling 6 distinct archetypes from 25 without replacement,
#      the 95th percentile is ~71.6% (mean is ~64.1%, std is ~4.5%p; +2σ is ~73.1%).
#   2. Archetype category collision: With replacement across 25 archetypes, expected similarity
#      rises to ~65.4% (+1.4%p) due to the birthday problem.
#   3. Normalization padding: validation.py guarantees minimum craft invariants (notice, info_table),
#      adding a slight (~1.0%p) upward drift in set overlap.
#   Total headroom: 7.5%p (variance) + 1.5%p (collisions) + 1.0%p (validation) = 10.0%p.
# This remains available as an explicit legacy CLI override, but is no longer the default:
# the default baseline now uses the actual batch-size P95, so variance and replacement
# collisions are already represented instead of being counted again in a fixed delta.
DEFAULT_MAX_JACCARD_DELTA: float = 0.10

# The only padding retained by the default P95-derived gate comes from the validation.py
# craft-invariant adjustment described above.
DEFAULT_JACCARD_VALIDATION_PADDING: float = 0.01

# Rationale for max_effective_common_blocks = 4:
#   In the 25 catalog archetypes, notice (24/25), info_table (24/25), detail_split (22/25),
#   and usage_scene (21/25) are core craft page blocks. Sampling 5~6 archetypes without
#   replacement yields an average of 2.4~2.7 effective common blocks, with the 95th percentile at 4.
#   5 or more effective common blocks only occurs under severe model monotony.
DEFAULT_MAX_EFFECTIVE_COMMON: int = 4

# Kept as an explicit CLI override for historical comparisons. The default gate threshold
# is derived from the catalog baseline's identical-pair P95 instead.
DEFAULT_MAX_IDENTICAL_PAIRS: int = 1

# Previous absolute criteria (for historical tracking and comparison)
LEGACY_MAX_AVG_JACCARD: float = 0.60
LEGACY_MAX_COMMON_BLOCKS: int = 4
LEGACY_MAX_IDENTICAL_PAIRS: int = 0


def compute_common_blocks(
    plans: list[list[str]],
    exclude: set[str] | frozenset[str] | None = None,
) -> list[str]:
    """Find block_types that appear in every single case.

    Args:
        plans: List of plan sequences (each sequence is a list of block_type strings).
        exclude: Optional set of block types to exclude from common blocks.

    Returns:
        Alphabetically sorted list of common block types.
    """
    if not plans:
        return []
    common = set(plans[0])
    for p in plans[1:]:
        common &= set(p)
    if exclude:
        common -= set(exclude)
    return sorted(common)


def compute_effective_common_blocks(
    plans: list[list[str]],
    structural_blocks: set[str] | frozenset[str] = STRUCTURAL_BLOCKS,
) -> list[str]:
    """Find common block_types excluding mandatory structural blocks (hero, closing)."""
    return compute_common_blocks(plans, exclude=structural_blocks)


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


def compute_catalog_baseline(
    catalog_path: Path = CATALOG_PATH,
    sample_size: int = 6,
    candidate_pool_size: int | None = None,
    iterations: int = DEFAULT_SIMULATION_ITERATIONS,
    seed: int = DEFAULT_SIMULATION_SEED,
) -> dict[str, Any]:
    """Compute deterministic ideal diversity baseline from catalog layouts.

    Simulates independently drawing `sample_size` archetypes with replacement
    from the reference catalog to match the production per-case selection model.
    ``candidate_pool_size`` optionally restricts the catalog prefix used as the
    null-model candidate pool; when omitted, the full catalog is used.
    """
    layout_sets: list[set[str]] = []
    if catalog_path.is_file():
        try:
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            layout_sets = [set(item["sequence"]) for item in catalog if "sequence" in item]
        except Exception as exc:
            print(f"[WARN] Failed to load catalog from {catalog_path}: {exc}", file=sys.stderr)

    catalog_archetypes_total = len(layout_sets)
    if candidate_pool_size is not None:
        if candidate_pool_size <= 0:
            raise ValueError("candidate_pool_size must be greater than zero")
        layout_sets = layout_sets[:candidate_pool_size]

    if not layout_sets or len(layout_sets) < 2:
        # Fallback baseline when catalog is unavailable
        return {
            "sample_size": sample_size,
            "candidate_pool_size": len(layout_sets),
            "iterations": 0,
            "seed": seed,
            "mean_jaccard": 0.640,
            "mean_jaccard_pct": 64.0,
            "p95_jaccard": 0.716,
            "p95_jaccard_pct": 71.6,
            "mean_effective_common": 2.4,
            "p95_effective_common": 4,
            "mean_identical_pairs": 0.0,
            "p95_identical_pairs": 0,
            "catalog_archetypes_count": len(layout_sets),
            "catalog_archetypes_total": catalog_archetypes_total,
            "source": "fallback_default",
        }

    rng = random.Random(seed)
    jaccards: list[float] = []
    eff_commons: list[int] = []
    identical_pairs_counts: list[int] = []

    for _ in range(iterations):
        sample = [rng.choice(layout_sets) for _ in range(sample_size)]
        pairs_j: list[float] = []
        for s1, s2 in itertools.combinations(sample, 2):
            u = s1 | s2
            pairs_j.append(len(s1 & s2) / len(u) if u else 1.0)
        jaccards.append(sum(pairs_j) / len(pairs_j) if pairs_j else 0.0)

        common = set.intersection(*sample) - STRUCTURAL_BLOCKS if sample else set()
        eff_commons.append(len(common))
        identical_pairs_counts.append(
            sum(s1 == s2 for s1, s2 in itertools.combinations(sample, 2))
        )

    mean_j = sum(jaccards) / len(jaccards)
    sorted_j = sorted(jaccards)
    p95_j = sorted_j[int(0.95 * len(sorted_j))]

    mean_eff_c = sum(eff_commons) / len(eff_commons)
    sorted_c = sorted(eff_commons)
    p95_eff_c = sorted_c[int(0.95 * len(sorted_c))]

    mean_identical_pairs = sum(identical_pairs_counts) / len(identical_pairs_counts)
    sorted_identical_pairs = sorted(identical_pairs_counts)
    p95_identical_pairs = sorted_identical_pairs[int(0.95 * len(sorted_identical_pairs))]

    return {
        "sample_size": sample_size,
        "candidate_pool_size": len(layout_sets),
        "iterations": iterations,
        "seed": seed,
        "mean_jaccard": round(mean_j, 4),
        "mean_jaccard_pct": round(mean_j * 100, 2),
        "p95_jaccard": round(p95_j, 4),
        "p95_jaccard_pct": round(p95_j * 100, 2),
        "mean_effective_common": round(mean_eff_c, 2),
        "p95_effective_common": p95_eff_c,
        "mean_identical_pairs": round(mean_identical_pairs, 2),
        "p95_identical_pairs": p95_identical_pairs,
        "catalog_archetypes_count": len(layout_sets),
        "catalog_archetypes_total": catalog_archetypes_total,
        "source": str(catalog_path),
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
    catalog_path: Path = CATALOG_PATH,
    candidate_pool_size: int | None = None,
    max_jaccard_delta: float | None = None,
    max_effective_common: int = DEFAULT_MAX_EFFECTIVE_COMMON,
    max_identical_pairs: int | None = None,
    simulation_iterations: int = DEFAULT_SIMULATION_ITERATIONS,
    simulation_seed: int = DEFAULT_SIMULATION_SEED,
    max_avg_jaccard: float | None = None,
    max_common_blocks: int | None = None,
) -> dict[str, Any]:
    """Evaluate plan diversity against quality gates.

    Quality Gate Thresholds (Catalog-grounded):
      1. Average Jaccard Similarity <= catalog_baseline_p95 + 1.0%p by default.
         An explicitly supplied max_jaccard_delta retains the historical
         catalog_baseline_mean + delta behavior. max_avg_jaccard is an absolute override.
      2. Effective common block types count (excluding hero & closing) <= max_effective_common (default: 4)
         (Can be overridden explicitly via max_common_blocks)
      3. Identical set pairs count <= catalog baseline P95 by default.
         (Can be overridden explicitly via max_identical_pairs)
    """
    case_ids = [r["case_id"] for r in records]
    plans = [r["blocks"] for r in records]

    # Baseline simulation
    sample_size = len(records)
    baseline = compute_catalog_baseline(
        catalog_path=catalog_path,
        sample_size=sample_size,
        candidate_pool_size=candidate_pool_size,
        iterations=simulation_iterations,
        seed=simulation_seed,
    )

    # 1. Common blocks (all vs effective non-structural)
    all_common_blocks = compute_common_blocks(plans)
    effective_common_blocks = compute_effective_common_blocks(plans, structural_blocks=STRUCTURAL_BLOCKS)
    excluded_structural = sorted(set(all_common_blocks) & STRUCTURAL_BLOCKS)

    # 2. Pairwise Jaccard and identical sets
    avg_jaccard, pairwise_records, identical_pairs = compute_pairwise_similarities(case_ids, plans)

    # 3. Distributions
    length_distribution = compute_length_distribution(plans)
    positional_fixedness = compute_positional_fixedness(plans)
    sequence_diversity = compute_sequence_diversity(plans)

    # Threshold resolution
    if max_avg_jaccard is not None:
        threshold_avg_jaccard = max_avg_jaccard
        is_dynamic_jaccard = False
        jaccard_threshold_mode = "absolute_override"
    elif max_jaccard_delta is not None:
        threshold_avg_jaccard = round(baseline["mean_jaccard"] + max_jaccard_delta, 4)
        is_dynamic_jaccard = True
        jaccard_threshold_mode = "explicit_delta"
    else:
        threshold_avg_jaccard = round(
            baseline["p95_jaccard"] + DEFAULT_JACCARD_VALIDATION_PADDING,
            4,
        )
        is_dynamic_jaccard = True
        jaccard_threshold_mode = "baseline_p95_plus_padding"

    effective_max_common = max_common_blocks if max_common_blocks is not None else max_effective_common
    if max_identical_pairs is not None:
        effective_max_identical_pairs = max_identical_pairs
        is_dynamic_identical_pairs = False
    else:
        effective_max_identical_pairs = baseline["p95_identical_pairs"]
        is_dynamic_identical_pairs = True

    # Gate evaluations (New Grounded Criteria)
    gate_avg_jaccard_pass = (avg_jaccard <= threshold_avg_jaccard)
    gate_effective_common_pass = (len(effective_common_blocks) <= effective_max_common)
    gate_identical_pairs_pass = (len(identical_pairs) <= effective_max_identical_pairs)

    overall_pass = (
        gate_avg_jaccard_pass
        and gate_effective_common_pass
        and gate_identical_pairs_pass
    )

    failures: list[str] = []
    if not gate_avg_jaccard_pass:
        if jaccard_threshold_mode == "baseline_p95_plus_padding":
            failures.append(
                f"평균 집합 일치도 초과: {avg_jaccard * 100:.1f}% "
                f"(기준: <= {threshold_avg_jaccard * 100:.1f}%, 기준선 p95 "
                f"{baseline['p95_jaccard_pct']:.1f}% + 패딩 "
                f"{DEFAULT_JACCARD_VALIDATION_PADDING * 100:.1f}%p)"
            )
        elif jaccard_threshold_mode == "explicit_delta":
            failures.append(
                f"평균 집합 일치도 초과: {avg_jaccard * 100:.1f}% "
                f"(기준: <= {threshold_avg_jaccard * 100:.1f}%, 카탈로그 기대치 {baseline['mean_jaccard_pct']:.1f}% + {max_jaccard_delta * 100:.1f}%p)"
            )
        else:
            failures.append(
                f"평균 집합 일치도 초과: {avg_jaccard * 100:.1f}% (기준: <= {threshold_avg_jaccard * 100:.1f}%)"
            )
    if not gate_effective_common_pass:
        failures.append(
            f"유효 공통 블록 종수 초과: {len(effective_common_blocks)}종 "
            f"(기준: <= {effective_max_common}종, 구조적 고정 {excluded_structural} 제외) {effective_common_blocks}"
        )
    if not gate_identical_pairs_pass:
        pairs_repr = ", ".join(f"({a}, {b})" for a, b in identical_pairs)
        if is_dynamic_identical_pairs:
            failures.append(
                f"완전 일치 쌍 허용치 초과: {len(identical_pairs)}쌍 "
                f"(기준: <= {effective_max_identical_pairs}쌍, 카탈로그 기대치 "
                f"{baseline['p95_identical_pairs']}쌍(p95)) [{pairs_repr}]"
            )
        else:
            failures.append(
                f"완전 일치 쌍 허용치 초과: {len(identical_pairs)}쌍 "
                f"(기준: <= {effective_max_identical_pairs}쌍, CLI override) [{pairs_repr}]"
            )

    # Legacy criteria evaluation (for comparison)
    legacy_jaccard_pass = (avg_jaccard <= LEGACY_MAX_AVG_JACCARD)
    legacy_common_pass = (len(all_common_blocks) <= LEGACY_MAX_COMMON_BLOCKS)
    legacy_identical_pass = (len(identical_pairs) <= LEGACY_MAX_IDENTICAL_PAIRS)
    legacy_overall_pass = (
        legacy_jaccard_pass
        and legacy_common_pass
        and legacy_identical_pass
    )
    legacy_failures: list[str] = []
    if not legacy_jaccard_pass:
        legacy_failures.append(
            f"평균 집합 일치도 초과: {avg_jaccard * 100:.1f}% (구 기준: <= {LEGACY_MAX_AVG_JACCARD * 100:.1f}%)"
        )
    if not legacy_common_pass:
        legacy_failures.append(
            f"전체 공통 블록 종수 초과: {len(all_common_blocks)}종 (구 기준: <= {LEGACY_MAX_COMMON_BLOCKS}종) {all_common_blocks}"
        )
    if not legacy_identical_pass:
        pairs_repr = ", ".join(f"({a}, {b})" for a, b in identical_pairs)
        legacy_failures.append(
            f"완전 일치 쌍 존재: {len(identical_pairs)}쌍 (구 기준: <= {LEGACY_MAX_IDENTICAL_PAIRS}쌍) [{pairs_repr}]"
        )

    return {
        "pass": overall_pass,
        "failures": failures,
        "catalog_baseline": baseline,
        "thresholds": {
            "max_avg_jaccard": threshold_avg_jaccard,
            "max_jaccard_delta": max_jaccard_delta,
            "is_dynamic_jaccard": is_dynamic_jaccard,
            "jaccard_threshold_mode": jaccard_threshold_mode,
            "jaccard_validation_padding": DEFAULT_JACCARD_VALIDATION_PADDING,
            "max_effective_common": effective_max_common,
            "max_identical_pairs": effective_max_identical_pairs,
            "is_dynamic_identical_pairs": is_dynamic_identical_pairs,
            "candidate_pool_size": baseline["candidate_pool_size"],
            "structural_blocks_excluded": sorted(STRUCTURAL_BLOCKS),
        },
        "gates": {
            "avg_jaccard": {
                "value": round(avg_jaccard, 6),
                "value_pct": round(avg_jaccard * 100, 2),
                "threshold": threshold_avg_jaccard,
                "threshold_pct": round(threshold_avg_jaccard * 100, 2),
                "baseline_mean_pct": baseline["mean_jaccard_pct"],
                "baseline_p95_pct": baseline["p95_jaccard_pct"],
                "delta_pct": (
                    round(max_jaccard_delta * 100, 2)
                    if max_jaccard_delta is not None
                    else None
                ),
                "validation_padding_pct": round(
                    DEFAULT_JACCARD_VALIDATION_PADDING * 100, 2
                ),
                "threshold_mode": jaccard_threshold_mode,
                "pass": gate_avg_jaccard_pass,
            },
            "effective_common_blocks": {
                "count": len(effective_common_blocks),
                "blocks": effective_common_blocks,
                "all_common_blocks": all_common_blocks,
                "excluded_structural": excluded_structural,
                "threshold": effective_max_common,
                "pass": gate_effective_common_pass,
            },
            "common_blocks": {
                "count": len(effective_common_blocks),
                "blocks": effective_common_blocks,
                "threshold": effective_max_common,
                "pass": gate_effective_common_pass,
            },
            "identical_pairs": {
                "count": len(identical_pairs),
                "pairs": [list(p) for p in identical_pairs],
                "threshold": effective_max_identical_pairs,
                "baseline_mean": baseline["mean_identical_pairs"],
                "baseline_p95": baseline["p95_identical_pairs"],
                "is_dynamic": is_dynamic_identical_pairs,
                "pass": gate_identical_pairs_pass,
            },
        },
        "legacy_evaluation": {
            "pass": legacy_overall_pass,
            "failures": legacy_failures,
            "thresholds": {
                "max_avg_jaccard": LEGACY_MAX_AVG_JACCARD,
                "max_common_blocks": LEGACY_MAX_COMMON_BLOCKS,
                "max_identical_pairs": LEGACY_MAX_IDENTICAL_PAIRS,
            },
            "gates": {
                "avg_jaccard": {
                    "value_pct": round(avg_jaccard * 100, 2),
                    "threshold_pct": round(LEGACY_MAX_AVG_JACCARD * 100, 2),
                    "pass": legacy_jaccard_pass,
                },
                "common_blocks": {
                    "count": len(all_common_blocks),
                    "blocks": all_common_blocks,
                    "threshold": LEGACY_MAX_COMMON_BLOCKS,
                    "pass": legacy_common_pass,
                },
                "identical_pairs": {
                    "count": len(identical_pairs),
                    "threshold": LEGACY_MAX_IDENTICAL_PAIRS,
                    "pass": legacy_identical_pass,
                },
            },
        },
        "metrics": {
            "total_cases": len(records),
            "common_blocks": all_common_blocks,
            "common_block_count": len(all_common_blocks),
            "effective_common_blocks": effective_common_blocks,
            "effective_common_block_count": len(effective_common_blocks),
            "excluded_structural": excluded_structural,
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
    legacy = results.get("legacy_evaluation", {})
    baseline = results.get("catalog_baseline", {})
    total = metrics["total_cases"]

    print("=" * 76)
    print("      파일럿 섹션 구성 다양성 측정 보고서 (Section Plan Diversity)      ")
    print("=" * 76)
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
    eff_count = metrics["effective_common_block_count"]
    total_common_count = metrics["common_block_count"]
    excluded_struct = metrics.get("excluded_structural", [])
    print(f"1. **공통 블록 수**: 유효 {eff_count}종 (전체 {total_common_count}종)")
    if metrics["effective_common_blocks"]:
        print(f"   - 유효 공통 블록 (구조적 고정 제외): `{', '.join(metrics['effective_common_blocks'])}`")
    else:
        print("   - 유효 공통 블록 없음 (완전 분기)")
    if excluded_struct:
        print(f"   - 제외된 구조적 고정 블록: `{', '.join(excluded_struct)}` (DTO/프롬프트 강제 필수 블록)")

    print(f"2. **평균 집합 일치도 (Jaccard)**: {metrics['avg_jaccard_pct']:.1f}%")
    if baseline.get("mean_jaccard_pct") is not None:
        print(
            f"   - 카탈로그 기준치 (복원 {baseline['sample_size']}건, "
            f"후보 {baseline['candidate_pool_size']}종, 시뮬레이션 {baseline['iterations']}회 평균): "
            f"{baseline['mean_jaccard_pct']:.1f}% (P95: {baseline['p95_jaccard_pct']:.1f}%)"
        )

    print(f"3. **완전 일치 쌍 수 (100% 동일 집합)**: {metrics['identical_pairs_count']}쌍")
    if "p95_identical_pairs" in baseline:
        print(
            f"   - 카탈로그 기대치 {baseline['p95_identical_pairs']}쌍(p95) / "
            f"관측 {metrics['identical_pairs_count']}쌍"
        )
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
    print("=" * 76)
    print("### 5. 품질 게이트 판정 결과 (Quality Gates)")
    g_jaccard = gates["avg_jaccard"]
    g_eff_common = gates["effective_common_blocks"]
    g_pairs = gates["identical_pairs"]

    j_mark = "[PASS]" if g_jaccard["pass"] else "[FAIL]"
    c_mark = "[PASS]" if g_eff_common["pass"] else "[FAIL]"
    p_mark = "[PASS]" if g_pairs["pass"] else "[FAIL]"

    print("#### [신규 기준: 카탈로그 도달성 기반 게이트]")
    if g_jaccard.get("threshold_mode") == "baseline_p95_plus_padding":
        print(
            f"- {j_mark} **평균 집합 일치도**: {g_jaccard['value_pct']:.1f}% "
            f"(기준: <= {g_jaccard['threshold_pct']:.1f}% | 기준선 p95 "
            f"{g_jaccard['baseline_p95_pct']:.1f}% + 패딩 "
            f"{g_jaccard['validation_padding_pct']:.1f}%p)"
        )
    elif g_jaccard.get("threshold_mode") == "explicit_delta":
        print(
            f"- {j_mark} **평균 집합 일치도**: {g_jaccard['value_pct']:.1f}% "
            f"(기준: <= {g_jaccard['threshold_pct']:.1f}% | 카탈로그 기대치 {g_jaccard['baseline_mean_pct']:.1f}% + {g_jaccard['delta_pct']:.1f}%p)"
        )
    else:
        print(
            f"- {j_mark} **평균 집합 일치도**: {g_jaccard['value_pct']:.1f}% "
            f"(기준: <= {g_jaccard['threshold_pct']:.1f}%)"
        )
    print(
        f"- {c_mark} **유효 공통 블록 종수**: {g_eff_common['count']}종 "
        f"(기준: <= {g_eff_common['threshold']}종, 구조적 고정 {g_eff_common['excluded_structural']} 제외) {g_eff_common['blocks']}"
    )
    print(
        f"- {p_mark} **완전 일치 쌍 수**: {g_pairs['count']}쌍 "
        f"(기준: <= {g_pairs['threshold']}쌍 | 기대치 "
        f"{g_pairs['baseline_p95']}쌍(p95) / 관측 {g_pairs['count']}쌍)"
    )
    print()

    if results["pass"]:
        print("신규 기준 최종 판정: [PASS] 구성 다양성 기준을 전부 만족했습니다. (종료 코드 0)")
    else:
        print("신규 기준 최종 판정: [FAIL] 구성 다양성 기준 미달로 탈락했습니다. (종료 코드 1)")
        print("실패 사유:")
        for idx, reason in enumerate(results["failures"], start=1):
            print(f"  {idx}) {reason}")
    print()

    # 6. Legacy comparison
    if legacy:
        print("#### [참고: 기존 절대 기준과의 비교 (Historical Comparison)]")
        lg_j = legacy["gates"]["avg_jaccard"]
        lg_c = legacy["gates"]["common_blocks"]
        lg_p = legacy["gates"]["identical_pairs"]
        lj_mark = "[PASS]" if lg_j["pass"] else "[FAIL]"
        lc_mark = "[PASS]" if lg_c["pass"] else "[FAIL]"
        lp_mark = "[PASS]" if lg_p["pass"] else "[FAIL]"
        lo_mark = "[PASS]" if legacy["pass"] else "[FAIL]"

        print(
            f"- {lj_mark} **평균 집합 일치도**: {lg_j['value_pct']:.1f}% "
            f"(구 기준: <= {lg_j['threshold_pct']:.1f}%)"
        )
        print(
            f"- {lc_mark} **전체 공통 블록 종수**: {lg_c['count']}종 "
            f"(구 기준: <= {lg_c['threshold']}종, 고정블록 미제외) {lg_c['blocks']}"
        )
        print(
            f"- {lp_mark} **완전 일치 쌍 수**: {lg_p['count']}쌍 "
            f"(구 기준: <= {lg_p['threshold']}쌍)"
        )
        print(f"기존 기준 최종 판정: {lo_mark} (기존 기준 적용 시 결과)")
        if not legacy["pass"]:
            for idx, reason in enumerate(legacy["failures"], start=1):
                print(f"  - 구 실패 사유 {idx}: {reason}")
    print("=" * 76)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure section plan diversity across pilot cases grounded in catalog baselines."
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
        "--catalog-path",
        type=Path,
        default=CATALOG_PATH,
        help=f"Path to catalog layouts JSON (default: {CATALOG_PATH}).",
    )
    parser.add_argument(
        "--candidate-pool-size",
        type=int,
        default=None,
        help="Override the catalog candidate-pool size used by the null model (default: full catalog).",
    )
    parser.add_argument(
        "--max-jaccard-delta",
        type=float,
        default=None,
        help=(
            "Legacy compatibility override: use baseline mean Jaccard + this delta "
            "when explicitly supplied (default: baseline P95 + validation padding)."
        ),
    )
    parser.add_argument(
        "--max-avg-jaccard",
        type=float,
        default=None,
        help="Explicit absolute maximum allowed average Jaccard similarity (overrides catalog baseline simulation).",
    )
    parser.add_argument(
        "--max-effective-common",
        type=int,
        default=DEFAULT_MAX_EFFECTIVE_COMMON,
        help=f"Maximum allowed count of non-structural common block_types (default: {DEFAULT_MAX_EFFECTIVE_COMMON}).",
    )
    parser.add_argument(
        "--max-common-blocks",
        type=int,
        default=None,
        help="Explicit maximum allowed common blocks (overrides --max-effective-common).",
    )
    parser.add_argument(
        "--max-identical-pairs",
        type=int,
        default=None,
        help=(
            "Explicit maximum allowed count of pairs with 100%% identical block sets "
            f"(default: catalog baseline P95; pass {DEFAULT_MAX_IDENTICAL_PAIRS} for the historical override)."
        ),
    )
    parser.add_argument(
        "--simulation-iterations",
        type=int,
        default=DEFAULT_SIMULATION_ITERATIONS,
        help=f"Number of Monte Carlo simulation iterations for catalog baseline (default: {DEFAULT_SIMULATION_ITERATIONS}).",
    )
    parser.add_argument(
        "--simulation-seed",
        type=int,
        default=DEFAULT_SIMULATION_SEED,
        help=f"Random seed for deterministic catalog baseline simulation (default: {DEFAULT_SIMULATION_SEED}).",
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
        catalog_path=args.catalog_path,
        candidate_pool_size=args.candidate_pool_size,
        max_jaccard_delta=args.max_jaccard_delta,
        max_effective_common=args.max_effective_common,
        max_identical_pairs=args.max_identical_pairs,
        simulation_iterations=args.simulation_iterations,
        simulation_seed=args.simulation_seed,
        max_avg_jaccard=args.max_avg_jaccard,
        max_common_blocks=args.max_common_blocks,
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
