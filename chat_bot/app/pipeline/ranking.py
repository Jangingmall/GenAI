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
    """검색 후보를 (유사도 + 등급 가중)으로 재정렬한 뒤,
    동명 상품 중복을 걷어내고(다양성) 상위 top_k개를 돌려준다."""
    ranked = []
    for cand in candidates:
        base = cand.get("score", 0.0)
        bonus = _grade_bonus(cand)
        item = dict(cand)
        item["score"] = base + bonus
        ranked.append(item)

    ranked.sort(key=lambda x: x["score"], reverse=True)

    # 다양성: 같은 이름이 이미 뽑혔으면 건너뛴다.
    # (데이터에 동명의 서로 다른 상품이 다수 존재 → 사용자에겐 선택지 하나로 보임)
    seen_names = set()
    diversified = []
    for item in ranked:
        name = item.get("name")
        if name in seen_names:
            continue
        seen_names.add(name)
        diversified.append(item)
        if len(diversified) >= top_k:
            break

    # 동명이 너무 많아 top_k를 못 채우면 남은 것으로 보충(순위 유지)
    if len(diversified) < top_k:
        for item in ranked:
            if item not in diversified:
                diversified.append(item)
                if len(diversified) >= top_k:

                    break

    return diversified


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
