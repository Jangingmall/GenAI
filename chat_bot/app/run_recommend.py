"""
A 파트 통합 — 검색(search) → 랭킹(ranking) 을 이어서 실행한다.

전체 파이프라인에서 A 담당 구간(②③④)의 흐름:
    query(접점1) → search → ranking → 상위 3개(접점2)

아직 B 담당(① intent, ⑤ generate)은 없으므로, 여기서는
  - 입력(접점1)을 직접 만들거나 CLI로 받고
  - 출력(접점2, 최종 랭킹)을 그대로 출력한다.
B가 붙으면: intent가 접점1을 만들고, generate가 이 출력을 받아 reply/reason을 생성한다.
"""

from app.pipeline.ranking import rank
from app.pipeline.search import search


def recommend(query: dict, top_k: int = 3) -> list[dict]:
    """접점1(query)을 받아 검색→랭킹을 거친 최종 추천 후보(접점2)를 돌려준다.

    Args:
        query: { query_text, filters, intent }  (B의 intent가 만들 형식. 지금은 직접 구성)
        top_k: 최종 추천 개수 (기본 3)

    Returns:
        [ { product_id, name, score, evidence }, ... ]  최대 top_k개
    """
    # 검색: 후보를 넉넉히 뽑아(랭킹이 등급 가중으로 재정렬하므로) 넘긴다
    candidates = search(query, top_k=10)
    # 랭킹: 유사도 + 등급 가중 → 상위 top_k
    return rank(candidates, top_k=top_k)


# 단독 실행용:
#   python -m app.run_recommend "차 마실 때 쓸 것"
#   (필터는 코드에서 직접 구성 — 실제로는 B의 intent가 채운다)
if __name__ == "__main__":
    import sys

    query_text = sys.argv[1] if len(sys.argv) > 1 else "차 마실 때 쓸 것"

    # 예시 접점1 — 지금은 직접 만든다. (B의 intent.py가 대체할 부분)
    query = {
        "query_text": query_text,
        "filters": {
            "max_price": None,
            "min_price": None,
            "color": None,
            "gift_theme": None,
        },
        "intent": "product_search",
    }

    print(f'질의: "{query_text}"\n최종 추천:')
    for i, r in enumerate(recommend(query), 1):
        grade = (r.get("evidence") or {}).get("verified")
        print(f"  {i}. {r['name']}  (score {r['score']:.4f}, 등급 {grade})")
