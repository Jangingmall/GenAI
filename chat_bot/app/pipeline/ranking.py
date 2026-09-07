"""
④ 등급 가중 랭킹 — 검색 후보를 최종 순위로 정렬한다.

콜드스타트 해결의 핵심: 후기·판매량이 아니라 국가 공인 인증 등급을 유사도에 가산한다.
후기 0건인 신규·전통 장인도 등급으로 상위 노출된다.

접점 2(search → ranking) 입력/출력 형식 동일:
  [ { "product_id", "name", "score", "evidence" }, ... ]
  - 입력: search가 넘긴 유사도(score) 기준 후보
  - 출력: 등급 가중이 더해진 최종 score로 재정렬, 최대 3개

등급은 evidence.verified 에서 읽는다 (적재 시 certification_level을 여기 저장함).
"""

# 인증 등급별 가중치 — 유사도 점수에 가산한다.
# 값은 가설이며 목데이터 평가 후 조정한다.
GRADE_WEIGHT = {
    "NATIONAL_INTANGIBLE_HERITAGE": 0.30,  # 국가무형유산
    "MASTER_CRAFTSMAN": 0.20,  # 명장
    "SENIOR_CRAFTSMAN": 0.10,  # 숙련장인
    "YOUNG_CRAFTSMAN": 0.05,  # 청년장인
}

# 추천 상한. 큐레이션 성격상 소수만. 하한은 없다(유사도 컷 통과분만).
MAX_RESULTS = 3


def _grade_bonus(candidate: dict) -> float:
    """후보의 인증 등급에 해당하는 가중치를 돌려준다. 등급 없거나 모르면 0."""
    evidence = candidate.get("evidence") or {}
    grade = evidence.get("verified")
    return GRADE_WEIGHT.get(grade, 0.0)


def rank(candidates: list[dict], top_k: int = MAX_RESULTS) -> list[dict]:
    """검색 후보를 (유사도 + 등급 가중)으로 재정렬해 상위 top_k개를 돌려준다.

    Args:
        candidates: search가 넘긴 접점 2 형식 리스트 (score=유사도)
        top_k: 최대 반환 개수 (기본 3)

    Returns:
        최종 score로 내림차순 정렬된 상위 top_k개. score는 가중이 더해진 값으로 갱신.
    """
    ranked = []
    for cand in candidates:
        base = cand.get("score", 0.0)  # 검색 유사도
        bonus = _grade_bonus(cand)  # 등급 가중
        final = base + bonus
        # 원본을 건드리지 않도록 복사해서 score만 최종값으로 교체
        item = dict(cand)
        item["score"] = final
        ranked.append(item)

    # 최종 점수 내림차순, 상위 top_k
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:top_k]


# 단독 실행용: 가짜 후보로 랭킹 동작 확인
# python -m app.pipeline.ranking
if __name__ == "__main__":
    fake = [
        {
            "product_id": 1,
            "name": "청년장인 다완",
            "score": 0.85,
            "evidence": {"verified": "YOUNG_CRAFTSMAN"},
        },
        {
            "product_id": 2,
            "name": "국가무형유산 다완",
            "score": 0.80,
            "evidence": {"verified": "NATIONAL_INTANGIBLE_HERITAGE"},
        },
        {
            "product_id": 3,
            "name": "명장 찻잔",
            "score": 0.78,
            "evidence": {"verified": "MASTER_CRAFTSMAN"},
        },
        {
            "product_id": 4,
            "name": "등급없는 접시",
            "score": 0.90,
            "evidence": {"verified": None},
        },
    ]
    print("등급 가중 전 (유사도 순):")
    for c in sorted(fake, key=lambda x: x["score"], reverse=True):
        print(f"  {c['name']}  유사도 {c['score']:.2f}")
    print("\n등급 가중 후 (최종 순, 상위 3):")
    for c in rank(fake):
        print(f"  {c['name']}  최종 {c['score']:.2f}")
