"""검수용 CSV 내보내기 — eval_set.json의 각 질의에 대해
'질문 / 정답규칙 / 추천상품 3개 / 사람판정 빈칸'을 CSV로 저장한다.

목적: Recall@3·MRR 같은 자동 지표가 아니라, 사람이 눈으로
      "이 질문에 이 상품이 맞나"를 직접 검수하기 위한 표를 만든다.
      (우리가 만든 정답표 자체가 맞는지 사람이 확인하는 작업)

기존 run_eval.py를 건드리지 않는 독립 스크립트다.

── 검색 경로 두 가지 ──
  기본(--raw-query 없음): intent(classify_and_extract)를 거쳐 검색.
      실사용과 동일한 경로 — "실제 서비스에서 이렇게 나온다"를 본다.
  --raw-query: intent를 건너뛰고 질문 원문으로 바로 검색.
      검색·랭킹의 순수 성능만 본다 — intent 단계 문제(예: query_text가
      원문보다 짧게 축약되는 현상)에 오염되지 않는다.
      *정답표(eval_set)가 맞는지 검수하는 목적이라면 이쪽을 권장.*

실행:
    python -m eval.export_review_csv                       # intent 경로
    python -m eval.export_review_csv --raw-query           # 순수 검색(검수 권장)
    python -m eval.export_review_csv --raw-query --out 검수.csv
    python -m eval.export_review_csv --first-query-only    # 항목당 첫 질의만

CSV는 UTF-8 BOM(utf-8-sig)으로 저장해 엑셀에서 한글이 깨지지 않는다.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from app.run_recommend import recommend

# intent 연동: 현재 코드의 함수명은 classify_and_extract 다.
# --raw-query 모드에서는 아예 쓰지 않는다.
try:
    from app.pipeline.intent import classify_and_extract
except ImportError:
    classify_and_extract = None

EVAL_PATH = Path(__file__).resolve().parent / "eval_set.json"
TOP_K = 3  # 화면 노출과 동일하게 상위 3개

# category 영문 코드 → 한글. load_products.py의 CATEGORY_KO와 같은 매핑이라
# 검수자가 "METAL, POTTERY" 대신 "금속공예, 도자기"로 읽는다.
CATEGORY_KO = {
    "POTTERY": "도자기",
    "ONGGI": "옹기",
    "NACRE": "나전칠기",
    "DYEING": "염색",
    "WOOD": "목공예",
    "METAL": "금속공예",
}


def _load_eval() -> list[dict]:
    data = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    return data["items"]


def _format_expected(expected: dict) -> str:
    """정답 규칙(expected)을 사람이 읽기 쉬운 한 줄 문자열로 변환한다."""
    if expected.get("should_be_empty"):
        return "빈 결과여야 함 (억지 추천 방지 — 상품이 안 나와야 정답)"

    parts: list[str] = []

    sub = expected.get("relevant_subcategory")
    if sub:
        parts.append("세부품목: " + ", ".join(sub))

    cat = expected.get("relevant_category")
    if cat:
        cat_ko = [CATEGORY_KO.get(c, c) for c in cat]
        parts.append("카테고리: " + ", ".join(cat_ko))

    mat = expected.get("relevant_material_contains")
    if mat:
        parts.append("재료에 포함: " + ", ".join(mat))

    tags = expected.get("relevant_purpose_tags")
    if tags:
        parts.append("용도태그: " + ", ".join(tags))

    max_price = expected.get("max_price")
    if max_price is not None:
        parts.append(f"가격: {max_price}원 이하")

    min_price = expected.get("min_price")
    if min_price is not None:
        parts.append(f"가격: {min_price}원 이상")

    return " / ".join(parts) if parts else "(규칙 없음 — 사람이 감각으로 판정)"


def _recommend_names(query_text: str, *, raw_query: bool) -> list[str]:
    """질의 하나를 검색해 추천 상품명 리스트(최대 3개)를 얻는다.

    raw_query=True  : intent를 건너뛰고 원문으로 검색(순수 검색 성능).
    raw_query=False : intent(classify_and_extract)를 거쳐 검색(실사용 경로).

    검수 CSV 생성이 목적이므로 개별 실패는 표에 흔적을 남기고 계속 진행한다.
    """
    intent_type = "product_search"
    filters: dict = {}
    query_for_search = query_text

    if not raw_query and classify_and_extract is not None:
        try:
            res = classify_and_extract(query_text)
            intent_type = res.get("intent", "product_search")
            filters = res.get("filters", {}) or {}
            query_for_search = res.get("query_text") or query_text
        except Exception as e:  # noqa: BLE001
            return [f"[intent 오류: {e}]"]

    contact1 = {
        "query_text": query_for_search,
        "filters": filters,
        "intent": intent_type,
    }
    try:
        results = recommend(contact1, top_k=TOP_K)
    except Exception as e:  # noqa: BLE001
        return [f"[검색 오류: {e}]"]

    return [r["name"] for r in results]


def export(out_path: Path, *, first_query_only: bool, raw_query: bool) -> int:
    items = _load_eval()

    rows: list[dict] = []
    for item in items:
        item_id = item.get("id", "")
        judge = item.get("judge", "auto")
        expected = item.get("expected", {})
        rule_text = _format_expected(expected)

        if judge == "human":
            kind = "감각판정(사람)"
        elif expected.get("should_be_empty"):
            kind = "빈결과기대"
        else:
            kind = "일반"

        queries = item.get("queries", [])
        if first_query_only and queries:
            queries = queries[:1]

        for q in queries:
            names = _recommend_names(q, raw_query=raw_query)
            rank1 = names[0] if len(names) > 0 else ""
            rank2 = names[1] if len(names) > 1 else ""
            rank3 = names[2] if len(names) > 2 else ""

            rows.append(
                {
                    "id": item_id,
                    "성격": kind,
                    "질문": q,
                    "정답규칙": rule_text,
                    "추천상품1": rank1,
                    "추천상품2": rank2,
                    "추천상품3": rank3,
                    "사람판정": "",
                    "메모": "",
                }
            )

    fieldnames = [
        "id",
        "성격",
        "질문",
        "정답규칙",
        "추천상품1",
        "추천상품2",
        "추천상품3",
        "사람판정",
        "메모",
    ]
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    mode = "원문검색(raw-query)" if raw_query else "intent 경로"
    print(f"검수용 CSV 저장 완료: {out_path}  (총 {len(rows)}행, {mode})")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="검수용 CSV 내보내기")
    parser.add_argument(
        "--out",
        default="review.csv",
        help="출력 CSV 경로 (기본: review.csv)",
    )
    parser.add_argument(
        "--raw-query",
        action="store_true",
        help="intent를 건너뛰고 질문 원문으로 검색(순수 검색 성능, 정답표 검수 권장)",
    )
    parser.add_argument(
        "--first-query-only",
        action="store_true",
        help="항목당 첫 질의만 내보내 표를 줄인다(빠른 훑어보기용)",
    )
    args = parser.parse_args(argv)
    return export(
        Path(args.out),
        first_query_only=args.first_query_only,
        raw_query=args.raw_query,
    )


if __name__ == "__main__":
    raise SystemExit(main())
