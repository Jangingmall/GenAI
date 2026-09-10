"""검색 및 추천 평가 채점 스크립트 — eval_set.json으로 Recall@3·MRR을 재고 score 분포를 본다.

개선 사항:
  1) intent.py를 호출하여 query_text로부터 filters(가격, 색상 등)와 intent를 동적으로 추출
  2) 장인 등급 가중치(+0.3 ~ +0.05)가 적용된 recommend()를 호출하여 최종 UI 노출 품질 검증
  3) search.py에서 반환한 BGE-M3 코사인 유사도(similarity) 점수로 유사도 컷 τ 기준점 측정

실행:
  python -m eval.run_eval
  python -m eval.run_eval --show-scores   # 질의별 score 상세까지
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

import psycopg2

from app.config import settings

# intent.py 및 recommend() 연동
try:
    from app.pipeline.intent import classify_and_extract
except ImportError:
    classify_and_extract = None

import logging

logger = logging.getLogger(__name__)

from app.run_recommend import recommend

EVAL_PATH = Path(__file__).resolve().parent / "eval_set.json"
TOP_K = 3  # 화면에 최대 3개 노출 → @3 기준


def _load_eval() -> list[dict]:
    data = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    return data["items"]


def _fetch_product_attrs(product_ids: list[int]) -> dict[int, dict]:
    """검색 결과 상품들의 실제 속성을 DB에서 읽는다 (정답 대조용)."""
    if not product_ids:
        return {}
    conn = psycopg2.connect(settings.dsn())
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT product_id, subcategory_code, category_code, material,"
                " purpose_tags, price FROM products WHERE product_id = ANY(%s)",
                (product_ids,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    attrs = {}
    for pid, sub, cat, mat, purpose, price in rows:
        attrs[pid] = {
            "subcategory_code": sub,
            "category_code": cat,
            "material": mat,
            "purpose_tags": purpose or [],
            "price": price,
        }
    return attrs


def _is_relevant(attr: dict, expected: dict) -> bool:
    """상품 속성이 정답 규칙을 만족하는가. 규칙 중 하나라도 명시되면 그 기준으로 판정."""
    sub = expected.get("relevant_subcategory")
    if sub and attr.get("subcategory_code") in sub:
        return True

    cat = expected.get("relevant_category")
    if cat and attr.get("category_code") in cat:
        return True

    mat_kws = expected.get("relevant_material_contains")
    if mat_kws:
        mat = attr.get("material") or ""
        if any(kw in mat for kw in mat_kws):
            return True

    want_tags = expected.get("relevant_purpose_tags")
    if want_tags and (set(attr.get("purpose_tags") or []) & set(want_tags)):
        return True

    max_price = expected.get("max_price")
    price = attr.get("price")
    return max_price is not None and price is not None and price <= max_price


def _eval_query(query_text: str, item: dict, attrs_cache: dict) -> dict:
    """질의 하나를 의도분류 + 추천(장인 가중치 포함)하여 정답 여부·순위·score를 계산."""

    # 1. intent.py를 통해 filters(max_price 등) 및 intent 동적 추출
    intent_type = "product_search"
    filters = {}
    if classify_and_extract is not None:
        try:
            intent_res = classify_and_extract(query_text)
            intent_type = intent_res.get("intent", "product_search")
            filters = intent_res.get("filters", {})
        except Exception:
            logger.exception("intent 분류 실패: %s", query_text)

    contact1 = {
        "query_text": query_text,
        "filters": filters,
        "intent": intent_type,
    }

    # 2. 장인 등급 가중치(+0.3 ~ +0.05)가 합산된 최종 recommend() 호출
    results = recommend(
        contact1, top_k=TOP_K
    )  # [{product_id, name, score, similarity, evidence}]

    pids = [r["product_id"] for r in results]
    attrs = _fetch_product_attrs(pids)

    expected = item["expected"]

    # 엣지 케이스: 빈 결과가 정답
    if expected.get("should_be_empty"):
        passed = len(results) == 0
        # 코사인 유사도(similarity)가 제공되면 우선 사용, 없으면 final score 사용
        scores = [r.get("similarity", r["score"]) for r in results]
        return {
            "query": query_text,
            "type": "edge",
            "passed": passed,
            "returned": len(results),
            "scores": scores,
        }

    # 일반 검색/추천: 상위 K개 중 정답이 있나 + 첫 정답 순위
    relevant_ranks = []
    relevant_scores, irrelevant_scores = [], []

    for rank, r in enumerate(results, start=1):
        attr = attrs.get(r["product_id"], {})
        # 유사도 컷 판단 지표로 활용할 코사인 유사도 점수 추출
        score_val = r.get("similarity", r["score"])

        if _is_relevant(attr, expected):
            relevant_ranks.append(rank)
            relevant_scores.append(score_val)
        else:
            irrelevant_scores.append(score_val)

    recall_at_k = 1 if relevant_ranks else 0  # 상위 K에 정답 하나라도 존재하는지
    rr = 1.0 / relevant_ranks[0] if relevant_ranks else 0.0  # 첫 정답 순위 역수

    return {
        "query": query_text,
        "type": "search",
        "recall": recall_at_k,
        "rr": rr,
        "relevant_scores": relevant_scores,
        "irrelevant_scores": irrelevant_scores,
        "results": [
            (r["name"], round(r.get("similarity", r["score"]), 4), round(r["score"], 4))
            for r in results
        ],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="검색 및 장인 가중치 추천 통합 평가")
    parser.add_argument(
        "--show-scores", action="store_true", help="질의별 결과·score 상세 출력"
    )
    args = parser.parse_args(argv)

    items = _load_eval()
    attrs_cache: dict = {}

    search_results, edge_results, human_items = [], [], []

    for item in items:
        if item.get("judge") == "human":
            human_items.append(item)
            continue
        for q in item["queries"]:
            r = _eval_query(q, item, attrs_cache)
            if r["type"] == "edge":
                edge_results.append(r)
            else:
                search_results.append(r)

    # ── 검색 및 추천 평가 지표 ──
    print("\n" + "=" * 50)
    print("검색/추천 평가 (judge=auto, type=search)")
    print("=" * 50)
    n = len(search_results)
    if n:
        recall = sum(r["recall"] for r in search_results) / n
        mrr = sum(r["rr"] for r in search_results) / n
        print(f"  질의 수: {n}")
        print(f"  Recall@{TOP_K}: {recall:.3f}  (목표 ≥0.7)")
        print(f"  MRR:       {mrr:.3f}  (목표 ≥0.6)")

    # ── score 분포 (유사도 컷 τ 결정 근거) ──
    all_rel = [s for r in search_results for s in r.get("relevant_scores", [])]
    all_irr = [s for r in search_results for s in r.get("irrelevant_scores", [])]
    print("\n" + "-" * 50)
    print("score 분포 (BGE-M3 코사인 유사도 컷 τ 결정 근거)")
    print("-" * 50)
    if all_rel:
        print(
            f"  정답 상품 score : 최소 {min(all_rel):.4f} / 중앙 {statistics.median(all_rel):.4f} / 최대 {max(all_rel):.4f}"
        )
    if all_irr:
        print(
            f"  오답 상품 score : 최소 {min(all_irr):.4f} / 중앙 {statistics.median(all_irr):.4f} / 최대 {max(all_irr):.4f}"
        )
    print("  → 정답 최소와 오답 최대 사이 어딘가가 τ 후보. 엣지 결과도 함께 보라.")

    # ── 엣지 케이스 ──
    print("\n" + "-" * 50)
    print(f"엣지 케이스 (빈 결과가 정답) — {len(edge_results)}건")
    print("-" * 50)
    for r in edge_results:
        mark = "✅" if r["passed"] else "❌"
        top_score = f"최고 score {max(r['scores']):.4f}" if r["scores"] else "빈 결과"
        print(f"  {mark} \"{r['query']}\" → {r['returned']}개 반환 ({top_score})")

    print("  → 유사도 컷이 적용되어 빈 결과(0개)가 되어야 정답.")

    # ── 사람 판정 대상 ──
    print("\n" + "-" * 50)
    print(f"사람 판정 필요 (judge=human) — {len(human_items)}건")
    print("-" * 50)
    for item in human_items:
        print(f"  · {item['id']}: {item['queries'][0]} ...")
    print("  → 감각·취향 질의는 검색 후 상위 3개를 사람이 직접 보고 판정.")

    # ── 상세 ──
    if args.show_scores:
        print("\n" + "=" * 50)
        print("질의별 상세 (Cosine Sim | Final Score | 상품명)")
        print("=" * 50)
        for r in search_results:
            print(f"\n\"{r['query']}\"  recall={r['recall']} rr={r['rr']:.2f}")
            for item_info in r["results"]:
                if len(item_info) == 3:
                    name, sim, final_score = item_info
                    print(f"    [Sim: {sim:.4f} | Final: {final_score:.4f}]  {name}")
                else:
                    name, score = item_info
                    print(f"    [{score:.4f}]  {name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
