"""run_recommend.py 오케스트레이터 테스트. chat·search_and_rank 둘 다 가짜로 주입해
실제 LLM·DB 없이 intent→search→generate 배선(합체 순서·필드 부착)만 검증한다.

실행: python -m pytest tests/test_run_recommend.py -q
"""

import json

from app.pipeline import orchestrator as rr


def _sequenced_chat(intent_payload: dict, generate_payload: dict):
    """1번째 호출(intent)엔 intent_payload, 2번째 호출(generate)엔 generate_payload를 준다."""
    calls = {"n": 0}

    def fake(messages, schema, *, think, model=None):
        calls["n"] += 1
        return json.dumps(intent_payload if calls["n"] == 1 else generate_payload)

    return fake


def _fake_search_and_rank(candidates: list[dict]):
    def fake(contact1: dict, top_k: int = 3) -> list[dict]:
        return candidates

    return fake


def _no_prices(product_ids: list[int]) -> dict[int, int]:
    """단위 테스트가 실제 DB 없이 돌아가게 하는 가짜 fetch_prices."""
    return {}


def _no_artisans(product_ids: list[int]) -> dict[int, dict]:
    """_no_prices와 같은 이유의 가짜 fetch_artisans."""
    return {}


def _no_attrs(product_ids: list[int]) -> dict[int, dict]:
    """_no_prices와 같은 이유의 가짜 fetch_attrs."""
    return {}


def _no_cache_lookup(message: str):
    """의미 기반 캐시 기본값은 실제 임베딩 모델을 부르므로, 단위 테스트에선 항상 미스로 만든다."""
    return


def _no_cache_store(message: str, contact1: dict) -> None:
    pass


# rr.run 호출마다 반복되는 DB·캐시 회피용 키워드 인자 묶음 — **_NO_DB로 한 번에 넘긴다.
_NO_DB = {
    "fetch_prices": _no_prices,
    "fetch_artisans": _no_artisans,
    "fetch_attrs": _no_attrs,
    "cache_lookup": _no_cache_lookup,
    "cache_store": _no_cache_store,
}


def test_run_assembles_final_contract():
    chat = _sequenced_chat(
        intent_payload={
            "intent": "product_search",
            "max_price": None,
            "min_price": None,
            "gift_theme": [],
            "color": [],
            "query_text": "찻잔",
        },
        generate_payload={
            "reply": "이 찻잔을 추천드려요.",
            "allowed_ids": [9],
            "suggestions": ["다른 색상으로", "가격대 낮춰서", "포장까지 되는 것만"],
        },
    )
    search_and_rank = _fake_search_and_rank(
        [
            {
                "product_id": 9,
                "name": "청자 다완",
                "score": 0.8,
                "evidence": {"artisan_input": "", "verified": None},
            }
        ]
    )

    result = rr.run("찻잔 있나요", chat=chat, search_and_rank=search_and_rank, **_NO_DB)

    assert set(result.keys()) == {
        "reply",
        "intent",
        "product_ids",
        "suggestions",
        "candidates",
        "filters",
        "shown_product_ids",
        "query_text",
    }
    assert result["intent"] == "product_search"
    assert result["product_ids"] == [9]
    assert result["suggestions"] == [
        "다른 색상으로",
        "가격대 낮춰서",
        "포장까지 되는 것만",
    ]


def test_run_passes_contact1_to_search_and_rank():
    seen = {}

    def spy_search_and_rank(contact1, top_k=3):
        seen["contact1"] = contact1
        return []

    chat = _sequenced_chat(
        intent_payload={
            "intent": "product_search",
            "max_price": None,
            "min_price": None,
            "gift_theme": [],
            "color": [],
            "query_text": "찻잔",
        },
        generate_payload={"reply": "ok", "allowed_ids": [], "suggestions": []},
    )
    rr.run("찻잔 있나요", chat=chat, search_and_rank=spy_search_and_rank, **_NO_DB)

    # product_search는 intent.py가 query_text를 원문(message)으로 확정 덮어쓴다
    # (검색팀 실측: 축약 없이 원문 그대로가 임베딩 검색에 가장 잘 맞음) — LLM이
    # 낸 "찻잔"이 아니라 원문 "찻잔 있나요"가 그대로 전달돼야 한다.
    assert seen["contact1"]["query_text"] == "찻잔 있나요"
    assert seen["contact1"]["intent"] == "product_search"


def test_run_drops_hallucinated_product_id():
    chat = _sequenced_chat(
        intent_payload={
            "intent": "product_search",
            "max_price": None,
            "min_price": None,
            "gift_theme": [],
            "color": [],
            "query_text": "찻잔",
        },
        generate_payload={
            "reply": "ok",
            "allowed_ids": [999],
            "suggestions": [],
        },
    )
    search_and_rank = _fake_search_and_rank(
        [{"product_id": 9, "name": "청자 다완", "score": 0.8, "evidence": {}}]
    )
    result = rr.run("찻잔 있나요", chat=chat, search_and_rank=search_and_rank, **_NO_DB)

    assert result["product_ids"] == []


def test_run_narrow_down_reuses_previous_candidates_instead_of_searching():
    """narrow_down("그중 더 싼 거" 등)은 새로 검색하면 원래 주제를 잃어버릴 수 있다(실측
    확인: query_text가 "가장 저렴한 제품"처럼 되면서 "도자기" 맥락이 사라지고 완전히
    다른 종목이 나옴) — previous_candidates가 있으면 search_and_rank를 아예 호출하지
    않고 그 후보 안에서만 답해야 한다.
    """
    chat = _sequenced_chat(
        intent_payload={
            "intent": "narrow_down",
            "max_price": None,
            "min_price": None,
            "gift_theme": [],
            "color": [],
            "query_text": "가장 저렴한 제품",
        },
        generate_payload={
            "reply": "가격 정보는 확인되지 않습니다.",
            "allowed_ids": [78],
            "suggestions": ["다른 색상으로"],
        },
    )
    previous = [{"product_id": 78, "name": "청자 찻잔", "score": 0.9, "evidence": {}}]

    def search_and_rank_must_not_be_called(contact1):
        raise AssertionError(
            "narrow_down + previous_candidates가 있으면 재검색하면 안 된다"
        )

    result = rr.run(
        "그중 제일 싼거는 뭐야?",
        chat=chat,
        search_and_rank=search_and_rank_must_not_be_called,
        previous_candidates=previous,
        **_NO_DB,
    )

    assert result["candidates"] == previous
    assert result["product_ids"] == [78]


def test_run_narrow_down_treats_zero_price_as_new_filter():
    """max_price=0(예: "0원짜리 무료 나눔")도 유효한 값이라 새 조건으로 봐야 한다 — 0은
    falsy라서 진리값 검사(and)로 판단하면 "조건 없음"으로 오판돼 재검색을 건너뛰는
    버그가 있었다(CodeRabbit 리뷰 지적).
    """
    chat = _sequenced_chat(
        intent_payload={
            "intent": "narrow_down",
            "max_price": 0,
            "min_price": None,
            "gift_theme": [],
            "color": [],
            "query_text": "도자기",
        },
        generate_payload={"reply": "ok", "allowed_ids": [], "suggestions": []},
    )
    fresh = [
        {"product_id": 5, "name": "무료 나눔 도자기", "score": 0.5, "evidence": {}}
    ]
    previous = [{"product_id": 78, "name": "청자 찻잔", "score": 0.9, "evidence": {}}]

    result = rr.run(
        "0원짜리 나눔도 있나요?",
        chat=chat,
        search_and_rank=_fake_search_and_rank(fresh),
        previous_candidates=previous,
        **_NO_DB,
    )

    assert result["candidates"] == fresh


def test_run_narrow_down_reuses_when_filter_unchanged_from_previous_turn():
    """intent.py는 이전 턴에 이미 확정된 조건(예: "집들이"→gift_theme=HOUSEWARMING)을
    맥락 유지를 위해 매 턴 계속 다시 채워 넣는다 — 이게 실제로 "새 조건"은 아니므로
    재검색을 유발하면 안 된다(실측 확인: 안 그러면 후보가 매 턴 바뀌어버림).
    previous_filters와 값이 같으면 재사용을 유지해야 한다.
    """
    chat = _sequenced_chat(
        intent_payload={
            "intent": "narrow_down",
            "max_price": None,
            "min_price": None,
            "gift_theme": ["HOUSEWARMING"],
            "color": [],
            "query_text": "옹기 가격대",
        },
        generate_payload={
            "reply": "가격 정보는 확인되지 않습니다.",
            "allowed_ids": [834],
            "suggestions": [],
        },
    )
    previous = [
        {"product_id": 834, "name": "옹기 항아리", "score": 0.9, "evidence": {}}
    ]

    def search_and_rank_must_not_be_called(contact1):
        raise AssertionError(
            "이전 턴과 같은 필터면 새 조건이 아니므로 재검색하면 안 된다"
        )

    result = rr.run(
        "가격대 확인해줘",
        chat=chat,
        search_and_rank=search_and_rank_must_not_be_called,
        previous_candidates=previous,
        previous_filters={
            "max_price": None,
            "min_price": None,
            "gift_theme": ["HOUSEWARMING"],
            "color": None,
        },
        **_NO_DB,
    )

    assert result["candidates"] == previous


def test_run_narrow_down_ignores_color_reorder_for_new_filter_check():
    """실측 확인된 버그: color는 리스트라 LLM이 매 턴 재추출할 때 값은 같아도 순서가
    흔들릴 수 있는데(gift_theme과 같은 종류의 불안정성), 리스트를 `!=`로 그대로
    비교하면 순서만 바뀌어도 "새 조건"으로 오판해 불필요한 재검색을 유발한다."""
    chat = _sequenced_chat(
        intent_payload={
            "intent": "narrow_down",
            "max_price": None,
            "min_price": None,
            "gift_theme": [],
            "color": ["BLUE", "RED"],
            "query_text": "도자기",
        },
        generate_payload={
            "reply": "ok",
            "allowed_ids": [834],
            "suggestions": [],
        },
    )
    previous = [
        {"product_id": 834, "name": "옹기 항아리", "score": 0.9, "evidence": {}}
    ]

    def search_and_rank_must_not_be_called(contact1, top_k=3):
        raise AssertionError(
            "색상 순서만 바뀐 건 새 조건이 아니므로 재검색하면 안 된다"
        )

    result = rr.run(
        "그중에 더 싼거",
        chat=chat,
        search_and_rank=search_and_rank_must_not_be_called,
        previous_candidates=previous,
        previous_filters={
            "max_price": None,
            "min_price": None,
            "gift_theme": [],
            "color": ["RED", "BLUE"],
        },
        **_NO_DB,
    )

    assert result["candidates"] == previous


def test_run_narrow_down_ignores_gift_theme_change_for_new_filter_check():
    """gift_theme은 search.py 문서상 하드필터가 아니라 부스팅용이다. 게다가 같은 문장도
    턴마다 추출이 흔들릴 수 있다(실측: 완전히 같은 문장인데 한 번은 뽑히고 한 번은 안
    뽑힘) — 그래서 이전 턴엔 없다가 이번 턴에 갑자기 생겨도(진짜 "새 조건"처럼 보여도)
    재검색을 유발하면 안 된다. max_price·min_price·color만 진짜 새 조건으로 센다.
    """
    chat = _sequenced_chat(
        intent_payload={
            "intent": "narrow_down",
            "max_price": None,
            "min_price": None,
            "gift_theme": ["HOUSEWARMING"],
            "color": [],
            "query_text": "옹기 가격대",
        },
        generate_payload={"reply": "ok", "allowed_ids": [], "suggestions": []},
    )
    previous = [
        {"product_id": 834, "name": "옹기 항아리", "score": 0.9, "evidence": {}}
    ]

    def search_and_rank_must_not_be_called(contact1):
        raise AssertionError("gift_theme만 바뀐 건 재검색 트리거가 아니다")

    result = rr.run(
        "가격대 확인해줘",
        chat=chat,
        search_and_rank=search_and_rank_must_not_be_called,
        previous_candidates=previous,
        previous_filters={
            "max_price": None,
            "min_price": None,
            "gift_theme": None,
            "color": None,
        },
        **_NO_DB,
    )

    assert result["candidates"] == previous


def test_run_narrow_down_with_new_filter_triggers_fresh_search():
    """narrow_down이라도 이번 턴에 새 하드필터(예: max_price)가 실제로 뽑혔으면
    "3만 원 아래로"처럼 진짜 반영돼야 하는 요청이다 — 이전 후보를 재사용하지 않고
    search_and_rank를 다시 호출해야 한다(재사용해버리면 가격을 낮춰달라는 요청에
    아무 변화 없는 답이 나가는 문제가 실측으로 확인됨).
    """
    chat = _sequenced_chat(
        intent_payload={
            "intent": "narrow_down",
            "max_price": 30000,
            "min_price": None,
            "gift_theme": [],
            "color": [],
            "query_text": "도자기",
        },
        generate_payload={"reply": "ok", "allowed_ids": [], "suggestions": []},
    )
    previous = [{"product_id": 78, "name": "청자 찻잔", "score": 0.9, "evidence": {}}]
    fresh = [{"product_id": 38, "name": "백자 대접", "score": 0.7, "evidence": {}}]
    seen = {}

    def spy_search_and_rank(contact1, top_k=3):
        seen["called"] = True
        return fresh

    result = rr.run(
        "3만원 아래로 보여줘",
        chat=chat,
        search_and_rank=spy_search_and_rank,
        previous_candidates=previous,
        **_NO_DB,
    )

    assert seen.get("called") is True
    assert result["candidates"] == fresh


def test_run_narrow_down_price_filter_keeps_previously_shown_matching_candidate():
    """실측 확인된 버그: "선물용 도자기 추천해줘"(3개 중 일부가 5만원 이하) → "5만원
    아래 제품들 뭐뭐있어?"에서 재검색이 카탈로그 전체를 새로 훑다 보니, 방금 보여준
    5만원 이하 상품이 순위 밖으로 밀려 빠지고 전혀 다른 상품으로 바뀌었다 — 새
    상품도 조건엔 맞지만 사용자 입장에선 "방금 그거 왜 빠졌지"로 보인다.
    previous_candidates 중 새 필터에도 맞는 것은 재검색 결과보다 우선 살아남아야
    한다."""
    chat = _sequenced_chat(
        intent_payload={
            "intent": "narrow_down",
            "max_price": 50000,
            "min_price": None,
            "gift_theme": [],
            "color": [],
            "query_text": "도자기",
        },
        generate_payload={"reply": "ok", "allowed_ids": [], "suggestions": []},
    )
    previous = [
        {"product_id": 78, "name": "청자 찻잔", "score": 0.9, "evidence": {}},
        {"product_id": 27, "name": "백자 머그", "score": 0.8, "evidence": {}},
    ]
    fresh = [
        {"product_id": 802, "name": "청자 접시", "score": 0.7, "evidence": {}},
        {"product_id": 68, "name": "도기토 다완", "score": 0.6, "evidence": {}},
    ]

    def fake_prices(product_ids):
        return {78: 37000, 27: 72000}  # 78만 5만원 이하

    result = rr.run(
        "5만원 아래 제품들 뭐뭐있어?",
        chat=chat,
        search_and_rank=lambda contact1, top_k=3: fresh,
        previous_candidates=previous,
        fetch_prices=fake_prices,
        fetch_artisans=_no_artisans,
        fetch_attrs=_no_attrs,
        cache_lookup=_no_cache_lookup,
        cache_store=_no_cache_store,
    )

    ids = [c["product_id"] for c in result["candidates"]]
    assert 78 in ids  # 여전히 5만원 이하인 이전 후보는 안 빠진다
    assert 27 not in ids  # 이제 5만원 넘는 이전 후보는 정상적으로 빠진다
    assert 802 in ids and 68 in ids  # 부족한 자리는 재검색으로 채운다


def test_run_narrow_down_color_filter_keeps_previously_shown_matching_candidate():
    chat = _sequenced_chat(
        intent_payload={
            "intent": "narrow_down",
            "max_price": None,
            "min_price": None,
            "gift_theme": [],
            "color": ["WHITE"],
            "query_text": "도자기",
        },
        generate_payload={"reply": "ok", "allowed_ids": [], "suggestions": []},
    )
    previous = [
        {"product_id": 78, "name": "백자 찻잔", "score": 0.9, "evidence": {}},
        {"product_id": 27, "name": "청자 찻잔", "score": 0.8, "evidence": {}},
    ]

    def fake_attrs(product_ids):
        return {78: {"color": "WHITE"}, 27: {"color": "BLUE"}}

    result = rr.run(
        "흰색만 보여줘",
        chat=chat,
        search_and_rank=lambda contact1, top_k=3: [],
        previous_candidates=previous,
        fetch_prices=_no_prices,
        fetch_artisans=_no_artisans,
        fetch_attrs=fake_attrs,
        cache_lookup=_no_cache_lookup,
        cache_store=_no_cache_store,
    )

    ids = [c["product_id"] for c in result["candidates"]]
    assert ids == [78]


def test_run_narrow_down_category_change_triggers_fresh_search():
    """ "아니 그거 말고 목공예로" — 가격·색상 필터는 안 바뀌었지만 종목 자체가 바뀐
    요청이다. 실측 확인된 버그: 이걸 순수 속성 질문으로 오인해 이전(도자기) 후보를
    그대로 재사용하면, generate.py의 종목 대조가 전부 걸러내 "카탈로그에 없다"고
    답해버린다 — 실제로는 새 종목 재검색을 안 해본 것뿐인데 "진짜 없음"과 구별이
    안 된다. 종목이 바뀌었으면 반드시 재검색해야 한다."""
    chat = _sequenced_chat(
        intent_payload={
            "intent": "narrow_down",
            "max_price": None,
            "min_price": None,
            "gift_theme": [],
            "color": [],
            "query_text": "목공예로 보여줘",
        },
        generate_payload={"reply": "ok", "allowed_ids": [], "suggestions": []},
    )
    previous = [{"product_id": 78, "name": "청자 찻잔", "score": 0.9, "evidence": {}}]
    fresh = [{"product_id": 466, "name": "소나무 의자", "score": 0.7, "evidence": {}}]
    seen = {}

    def spy_search_and_rank(contact1, top_k=3):
        seen["called"] = True
        return fresh

    result = rr.run(
        "아니 그거 말고 목공예로 보여줘",
        chat=chat,
        search_and_rank=spy_search_and_rank,
        previous_candidates=previous,
        **_NO_DB,
    )

    assert seen.get("called") is True
    assert result["candidates"] == fresh


def test_run_narrow_down_category_change_does_not_prepend_stale_topic():
    """실측 확인된 버그: 종목이 바뀐 재검색에 옛 주제어("도자기 찻잔 추천해줘")를
    이어 붙이면 검색 임베딩이 옛 종목과 새 종목 사이에서 오염돼 엉뚱한(옛 종목)
    상품만 나온다(직접 검색 재현 확인 — "도자기 찻잔 추천해줘 금속 공예품
    추천해줄래?"는 도자기만 나오는데 "금속 공예품 추천해줄래?"만 검색하면 진짜
    금속공예 상품이 잘 나옴). 종목이 바뀐 문장은 그 자체로 완결된 새 주제이므로
    옛 주제를 붙이지 않아야 한다 — 가격만 바뀐 경우(위 테스트)와 다른 점이다."""
    chat = _sequenced_chat(
        intent_payload={
            "intent": "narrow_down",
            "max_price": None,
            "min_price": None,
            "gift_theme": [],
            "color": [],
            "query_text": "금속 공예품 추천해줄래?",
        },
        generate_payload={"reply": "ok", "allowed_ids": [], "suggestions": []},
    )
    history = [
        {"role": "user", "content": "도자기 찻잔 추천해줘"},
        {"role": "assistant", "content": "도자기 찻잔 3점을 소개해 드릴게요..."},
    ]
    previous = [{"product_id": 78, "name": "청자 찻잔", "score": 0.9, "evidence": {}}]
    seen = {}

    def spy_search_and_rank(contact1, top_k=3):
        seen["query_text"] = contact1["query_text"]
        return []

    rr.run(
        "아니 그거말고 그냥 금속 공예품 추천해줄래?",
        history,
        chat=chat,
        search_and_rank=spy_search_and_rank,
        previous_candidates=previous,
        previous_query_text="도자기 찻잔 추천해줘",
        **_NO_DB,
    )

    assert seen["query_text"] == "금속 공예품 추천해줄래?"


def test_run_narrow_down_same_category_mention_does_not_force_search():
    """이미 보여준 후보와 같은 종목을 다시 언급한 것뿐이면(예: "이 도자기 얼마예요?")
    종목이 바뀐 게 아니므로 재검색을 강제하지 않는다 — 과하게 트리거되면 순수 속성
    질문("가격대 확인해줘"류)까지 불필요하게 재검색하게 된다."""
    chat = _sequenced_chat(
        intent_payload={
            "intent": "narrow_down",
            "max_price": None,
            "min_price": None,
            "gift_theme": [],
            "color": [],
            "query_text": "이 도자기 얼마예요?",
        },
        generate_payload={"reply": "ok", "allowed_ids": [78], "suggestions": []},
    )
    previous = [{"product_id": 78, "name": "청자 찻잔", "score": 0.9, "evidence": {}}]
    seen = {}

    def spy_search_and_rank(contact1, top_k=3):
        seen["called"] = True
        return []

    result = rr.run(
        "이 도자기 얼마예요?",
        chat=chat,
        search_and_rank=spy_search_and_rank,
        previous_candidates=previous,
        **_NO_DB,
    )

    assert seen.get("called") is None
    assert result["candidates"] == previous


def test_run_narrow_down_new_filter_injects_previous_topic_into_query_text():
    """intent.py가 "이전 대화 주제어 + 현재 문장"을 프롬프트만으로 합치도록 시켜도
    실측 확인 결과 새 문장이 조금만 바뀌면 주제어가 빠졌다(예: "찻잔"·"옹기"·"목공예"
    전부 재현) — 여기(orchestrator)에서 직전 사용자 발화를 코드로 확정 이어 붙인다."""
    chat = _sequenced_chat(
        intent_payload={
            "intent": "narrow_down",
            "max_price": 30000,
            "min_price": None,
            "gift_theme": [],
            "color": [],
            # LLM이 주제어("도자기")를 놓친 것으로 가정 — 실측에서 재현된 실패 형태.
            "query_text": "그럼 3만원으로 낮춰서 좋은 것도 있어요?",
        },
        generate_payload={"reply": "ok", "allowed_ids": [], "suggestions": []},
    )
    history = [
        {"role": "user", "content": "선물로 좋은 도자기 찾아줘"},
        {
            "role": "assistant",
            "content": "친구에게 선물로 추천드릴 도자기 작품을 소개합니다...",
        },
    ]
    previous = [{"product_id": 78, "name": "청자 찻잔", "score": 0.9, "evidence": {}}]
    seen = {}

    def spy_search_and_rank(contact1, top_k=3):
        seen["query_text"] = contact1["query_text"]
        return []

    rr.run(
        "그럼 3만원으로 낮춰서 좋은 것도 있어요?",
        history,
        chat=chat,
        search_and_rank=spy_search_and_rank,
        previous_candidates=previous,
        **_NO_DB,
    )

    assert (
        seen["query_text"]
        == "선물로 좋은 도자기 찾아줘 그럼 3만원으로 낮춰서 좋은 것도 있어요?"
    )


def test_run_narrow_down_new_filter_without_history_leaves_query_text_untouched():
    """history가 없으면(직전 발화를 알 길이 없음) 원래 query_text를 그대로 둔다 —
    없는 값을 억지로 만들어 붙이지 않는다."""
    chat = _sequenced_chat(
        intent_payload={
            "intent": "narrow_down",
            "max_price": 30000,
            "min_price": None,
            "gift_theme": [],
            "color": [],
            "query_text": "3만원 이하로 낮춰서",
        },
        generate_payload={"reply": "ok", "allowed_ids": [], "suggestions": []},
    )
    previous = [{"product_id": 78, "name": "청자 찻잔", "score": 0.9, "evidence": {}}]
    seen = {}

    def spy_search_and_rank(contact1, top_k=3):
        seen["query_text"] = contact1["query_text"]
        return []

    rr.run(
        "3만원 이하로 낮춰서",
        chat=chat,
        search_and_rank=spy_search_and_rank,
        previous_candidates=previous,
        **_NO_DB,
    )

    assert seen["query_text"] == "3만원 이하로 낮춰서"


def test_run_narrow_down_new_filter_prefers_previous_query_text_over_last_message():
    """narrow_down이 새 하드필터로 두 번 연달아 이어지면("도자기 선물 찾아줘" →
    "3만원 이하로" → "그럼 5만원으로 다시"), "직전 사용자 발화 1개"만 봐서는 두 번째
    재검색부터 주제어가 다시 사라진다(실측 확인: 세 번째 턴의 "직전 발화"가 "3만원
    이하로"라 "도자기"가 이미 없음). previous_query_text(직전 턴이 실제로 검색에 쓴
    누적 문장)를 넘기면 이 문제가 없어야 한다."""
    chat = _sequenced_chat(
        intent_payload={
            "intent": "narrow_down",
            "max_price": 50000,
            "min_price": None,
            "gift_theme": [],
            "color": [],
            "query_text": "그럼 5만원으로 다시",
        },
        generate_payload={"reply": "ok", "allowed_ids": [], "suggestions": []},
    )
    history = [
        {"role": "user", "content": "도자기 선물 찾아줘"},
        {"role": "assistant", "content": "도자기 작품을 소개합니다."},
        {"role": "user", "content": "3만원 이하로"},
        {"role": "assistant", "content": "3만 원 이하로 3점을 골랐어요."},
    ]
    previous = [{"product_id": 78, "name": "청자 찻잔", "score": 0.9, "evidence": {}}]
    seen = {}

    def spy_search_and_rank(contact1, top_k=3):
        seen["query_text"] = contact1["query_text"]
        return []

    rr.run(
        "그럼 5만원으로 다시",
        history,
        chat=chat,
        search_and_rank=spy_search_and_rank,
        previous_candidates=previous,
        # 2턴이 실제로 검색에 썼던 누적 문장 — history의 마지막 사용자 발화("3만원
        # 이하로")엔 이미 "도자기"가 없다는 게 이 테스트의 핵심.
        previous_query_text="도자기 선물 찾아줘 3만원 이하로",
        **_NO_DB,
    )

    assert seen["query_text"] == "도자기 선물 찾아줘 3만원 이하로 그럼 5만원으로 다시"


def test_run_returns_resolved_query_text_after_fresh_search():
    """다음 턴 previous_query_text로 이어 붙일 수 있게, 이번 턴이 실제로 검색에 쓴
    최종 query_text를 결과에 담아 돌려줘야 한다."""
    chat = _sequenced_chat(
        intent_payload={
            "intent": "product_search",
            "max_price": None,
            "min_price": None,
            "gift_theme": [],
            "color": [],
            "query_text": "찻잔",
        },
        generate_payload={"reply": "ok", "allowed_ids": [], "suggestions": []},
    )
    result = rr.run(
        "찻잔 있나요",
        chat=chat,
        search_and_rank=_fake_search_and_rank([]),
        **_NO_DB,
    )
    # product_search는 intent.py가 query_text를 원문으로 확정 덮어쓴다.
    assert result["query_text"] == "찻잔 있나요"


def test_run_returns_previous_query_text_unchanged_when_reusing_candidates():
    """검색을 안 하고 직전 후보를 재사용한 턴(narrow_down, 새 필터 없음)은 이번 턴
    LLM이 뽑은 query_text가 검색에 안 쓰였으니, 그걸로 previous_query_text를
    덮어쓰지 않고 원래 값을 그대로 다음 턴에 넘긴다."""
    chat = _sequenced_chat(
        intent_payload={
            "intent": "narrow_down",
            "max_price": None,
            "min_price": None,
            "gift_theme": [],
            "color": [],
            "query_text": "가격대 확인",
        },
        generate_payload={
            "reply": "가격 정보는 확인되지 않습니다.",
            "allowed_ids": [78],
            "suggestions": [],
        },
    )
    previous = [{"product_id": 78, "name": "청자 찻잔", "score": 0.9, "evidence": {}}]

    def search_and_rank_must_not_be_called(contact1):
        raise AssertionError("새 필터가 없으면 재검색하면 안 된다")

    result = rr.run(
        "가격대 확인해줘",
        chat=chat,
        search_and_rank=search_and_rank_must_not_be_called,
        previous_candidates=previous,
        previous_query_text="도자기 선물 찾아줘",
        **_NO_DB,
    )

    assert result["query_text"] == "도자기 선물 찾아줘"


def test_run_returns_fresh_candidates_when_no_previous_given():
    """previous_candidates 없이 narrow_down이 와도(예: 대화 첫 턴) 정상적으로 새로 검색한다."""
    chat = _sequenced_chat(
        intent_payload={
            "intent": "narrow_down",
            "max_price": None,
            "min_price": None,
            "gift_theme": [],
            "color": [],
            "query_text": "그중 저렴한 것",
        },
        generate_payload={"reply": "ok", "allowed_ids": [], "suggestions": []},
    )
    fresh = [{"product_id": 1, "name": "옹기 항아리", "score": 0.5, "evidence": {}}]
    search_and_rank = _fake_search_and_rank(fresh)

    result = rr.run(
        "그중 저렴한 것", chat=chat, search_and_rank=search_and_rank, **_NO_DB
    )

    assert result["candidates"] == fresh


def test_run_narrow_down_new_filter_with_zero_results_preserves_previous_context():
    """새 하드필터로 재검색했는데 결과가 0건이면(예: "3만원 아래로"에 맞는 게 없음),
    다음 턴이 참조할 candidates·shown_product_ids·query_text는 이전 값을 그대로
    들고 가야 한다 — 안 그러면 곧바로 이어지는 "그중 가장 저렴한 것 설명해줘"·색상
    질문 같은 후속 참조가 통째로 끊긴다(실측 확인: 0건 응답 직후 방금 전까지 보여준
    상품 정보까지 다 사라져서 "아직 없어요"로 잘못 답함). 이번 턴 reply·product_ids는
    그대로 "못 찾았다"고 답한다 — 되돌리는 건 다음 턴이 볼 내부 상태뿐이다."""
    chat = _sequenced_chat(
        intent_payload={
            "intent": "narrow_down",
            "max_price": 30000,
            "min_price": None,
            "gift_theme": [],
            "color": [],
            "query_text": "도자기",
        },
        generate_payload={
            "reply": "3만 원 이하로는 찾지 못했어요.",
            "allowed_ids": [],
            "suggestions": [],
        },
    )
    previous = [{"product_id": 78, "name": "청자 찻잔", "score": 0.9, "evidence": {}}]

    result = rr.run(
        "3만원 아래로 보여줘",
        chat=chat,
        search_and_rank=_fake_search_and_rank([]),
        previous_candidates=previous,
        previous_product_ids=[78],
        previous_query_text="찻잔 있나요",
        **_NO_DB,
    )

    assert result["reply"] == "3만 원 이하로는 찾지 못했어요."
    assert result["product_ids"] == []
    assert result["candidates"] == previous
    assert result["shown_product_ids"] == [78]
    assert result["query_text"] == "찻잔 있나요"


# ---------------------------------------------------------------------------
# 카드 중복 노출 억제 — previous_product_ids와 완전히 같은 세트면 카드를 안 띄운다
# ---------------------------------------------------------------------------


def test_run_suppresses_product_ids_when_identical_to_previous_turn():
    """ "가격대 확인해줘"처럼 순수 속성 질문이 이어져 후보가 하나도 안 바뀌면,
    매 턴 같은 카드가 또 뜨지 않도록 product_ids를 비워서 반환해야 한다."""
    chat = _sequenced_chat(
        intent_payload={
            "intent": "narrow_down",
            "max_price": None,
            "min_price": None,
            "gift_theme": [],
            "color": [],
            "query_text": "도자기",
        },
        generate_payload={
            "reply": "가격 정보는 확인되지 않습니다.",
            "allowed_ids": [1, 2, 6],
            "suggestions": [],
        },
    )
    previous = [
        {"product_id": 1, "name": "A", "score": 0.9, "evidence": {}},
        {"product_id": 2, "name": "B", "score": 0.8, "evidence": {}},
        {"product_id": 6, "name": "C", "score": 0.7, "evidence": {}},
    ]

    result = rr.run(
        "가격대 확인해줘",
        chat=chat,
        previous_candidates=previous,
        previous_product_ids=[1, 2, 6],
        **_NO_DB,
    )

    assert result["product_ids"] == []
    # 화면엔 안 띄워도 "실제로 관련된 상품이 뭔지"는 다음 턴 비교를 위해 그대로 넘긴다.
    assert result["shown_product_ids"] == [1, 2, 6]
    assert result["reply"] == "가격 정보는 확인되지 않습니다."


def test_run_does_not_suppress_when_narrowed_to_subset():
    """ "포장되는 것만"처럼 3개 중 1개로 좁혀지면, 이전과 다른 세트이므로 진짜 새
    정보다 — 억제하지 않고 그대로 보여준다."""
    chat = _sequenced_chat(
        intent_payload={
            "intent": "narrow_down",
            "max_price": None,
            "min_price": None,
            "gift_theme": [],
            "color": [],
            "query_text": "도자기",
        },
        generate_payload={
            "reply": "포장 가능한 상품은 이것뿐입니다.",
            "allowed_ids": [1],
            "suggestions": [],
        },
    )
    previous = [
        {"product_id": 1, "name": "A", "score": 0.9, "evidence": {}},
        {"product_id": 2, "name": "B", "score": 0.8, "evidence": {}},
        {"product_id": 6, "name": "C", "score": 0.7, "evidence": {}},
    ]

    result = rr.run(
        "포장되는 것만 보여줘",
        chat=chat,
        previous_candidates=previous,
        previous_product_ids=[1, 2, 6],
        **_NO_DB,
    )

    assert result["product_ids"] == [1]
    assert result["shown_product_ids"] == [1]


def test_run_does_not_suppress_on_first_turn_without_previous_product_ids():
    """previous_product_ids가 없는 첫 턴은 비교 대상이 없으니 당연히 억제하지 않는다."""
    chat = _sequenced_chat(
        intent_payload={
            "intent": "product_search",
            "max_price": None,
            "min_price": None,
            "gift_theme": [],
            "color": [],
            "query_text": "도자기",
        },
        generate_payload={"reply": "ok", "allowed_ids": [1], "suggestions": []},
    )
    candidates = [{"product_id": 1, "name": "A", "score": 0.9, "evidence": {}}]

    result = rr.run(
        "도자기 추천해줘",
        chat=chat,
        search_and_rank=_fake_search_and_rank(candidates),
        **_NO_DB,
    )

    assert result["product_ids"] == [1]


# ---------------------------------------------------------------------------
# general_chat이면 검색·두 번째 LLM 호출을 모두 스킵 — 잡담에 엉뚱한 상품이 끼어드는 것 방지
# ---------------------------------------------------------------------------


def test_run_general_chat_skips_second_llm_call_and_search():
    """general_chat이면 검색도, generate.py의 두 번째 LLM 호출도 안 해야 한다 — intent.py가
    이미 만들어둔 chat_reply를 그대로 쓴다. 실LLM 재현 확인: 빈 query_text로 검색하면
    검색 엔진이 엉뚱한 상품을 반환하고, 그걸 candidates로 넘기면 생성 단계가 잡담에
    상품을 끼워 넣는 회귀가 있었다 — 애초에 두 번째 호출 자체를 안 하면 이 문제가 원천
    차단된다.
    """
    calls = {"n": 0}

    def chat_counts_calls(messages, schema, *, think, model=None):
        calls["n"] += 1
        return json.dumps(
            {
                "intent": "general_chat",
                "max_price": None,
                "min_price": None,
                "gift_theme": [],
                "color": [],
                "query_text": "",
                "chat_reply": "안녕하세요! 어떤 공예품을 찾으시나요?",
            }
        )

    def search_and_rank_must_not_be_called(contact1):
        raise AssertionError("general_chat인데 search_and_rank가 호출됐다")

    result = rr.run(
        "안녕하십니까?",
        chat=chat_counts_calls,
        search_and_rank=search_and_rank_must_not_be_called,
        **_NO_DB,
    )
    assert result["product_ids"] == []
    assert result["reply"] == "안녕하세요! 어떤 공예품을 찾으시나요?"
    assert (
        calls["n"] == 1
    ), "general_chat인데 LLM이 2번 호출됐다(generate 호출을 안 건너뛰었다)"


# ---------------------------------------------------------------------------
# 의미 기반 캐시 연동 — 대화 맥락 없는 첫 턴만 캐시를 타야 한다
# ---------------------------------------------------------------------------


def test_run_uses_cache_hit_and_skips_classify_and_extract():
    """캐시 히트면 intent 분류(LLM 호출 1번째)는 건너뛰고, 응답생성(2번째)만 실행돼야
    한다 — chat이 정확히 1번만 불렸는지로 확인한다(intent까지 불렸으면 2번이 됨)."""
    cached_contact1 = {
        "intent": "product_search",
        "filters": {
            "max_price": None,
            "min_price": None,
            "gift_theme": None,
            "color": None,
        },
        "query_text": "도자기",
        "chat_reply": "",
    }
    calls = {"n": 0}

    def chat_counts_calls(messages, schema, *, think, model=None):
        calls["n"] += 1
        return json.dumps({"reply": "ok", "allowed_ids": [], "suggestions": []})

    result = rr.run(
        "선물용 도자기 추천해줘",
        chat=chat_counts_calls,
        search_and_rank=_fake_search_and_rank([]),
        cache_lookup=lambda message: cached_contact1,
        cache_store=_no_cache_store,
        fetch_prices=_no_prices,
        fetch_artisans=_no_artisans,
    )

    assert result["intent"] == "product_search"
    assert (
        calls["n"] == 1
    ), "캐시 히트인데 chat이 2번 불렸다(intent 호출을 못 건너뛴 것)"


def test_run_stores_to_cache_on_miss():
    stored = {}

    def fake_store(message, contact1):
        stored["message"] = message
        stored["contact1"] = contact1

    chat = _sequenced_chat(
        intent_payload={
            "intent": "product_search",
            "max_price": None,
            "min_price": None,
            "gift_theme": [],
            "color": [],
            "query_text": "찻잔",
        },
        generate_payload={"reply": "ok", "allowed_ids": [], "suggestions": []},
    )
    rr.run(
        "찻잔 있나요",
        chat=chat,
        search_and_rank=_fake_search_and_rank([]),
        cache_lookup=lambda message: None,
        cache_store=fake_store,
        fetch_prices=_no_prices,
        fetch_artisans=_no_artisans,
    )

    assert stored["message"] == "찻잔 있나요"
    assert stored["contact1"]["query_text"] == "찻잔 있나요"


def test_run_skips_cache_when_history_present():
    """narrow_down처럼 맥락 의존적인 턴은 문장만으로 캐시를 맞히면 위험하므로, history가
    있으면 캐시를 아예 조회하지 않아야 한다."""

    def cache_lookup_must_not_be_called(message):
        raise AssertionError("history가 있는데 캐시를 조회했다")

    chat = _sequenced_chat(
        intent_payload={
            "intent": "narrow_down",
            "max_price": None,
            "min_price": None,
            "gift_theme": [],
            "color": [],
            "query_text": "가격대 확인",
        },
        generate_payload={"reply": "ok", "allowed_ids": [], "suggestions": []},
    )
    history = [
        {"role": "user", "content": "선물로 좋은 도자기 찾아줘"},
        {"role": "assistant", "content": "도자기 작품을 소개합니다."},
    ]
    previous = [{"product_id": 1, "name": "청자 찻잔", "score": 0.9, "evidence": {}}]

    rr.run(
        "가격대 확인해줘",
        history=history,
        chat=chat,
        previous_candidates=previous,
        cache_lookup=cache_lookup_must_not_be_called,
        cache_store=_no_cache_store,
        fetch_prices=_no_prices,
        fetch_artisans=_no_artisans,
    )


# ---------------------------------------------------------------------------
# warmup() — 서버 부팅 시 프롬프트 캐시를 미리 만들어두는 더미 호출
# ---------------------------------------------------------------------------


def test_warmup_calls_chat_exactly_twice():
    """intent 분류 1번 + 응답생성 1번, 총 2번만 호출해야 한다(그 이상은 낭비, 그 이하면
    둘 중 하나의 프롬프트가 안 데워진다)."""
    calls = {"n": 0}

    def chat_counts_calls(messages, schema, *, think, model=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return json.dumps(
                {
                    "intent": "general_chat",
                    "max_price": None,
                    "min_price": None,
                    "gift_theme": [],
                    "color": [],
                    "query_text": "",
                    "chat_reply": "",
                }
            )
        return json.dumps({"reply": "ok", "allowed_ids": [], "suggestions": []})

    rr.warmup(
        chat=chat_counts_calls,
        fetch_prices=_no_prices,
        fetch_artisans=_no_artisans,
        search_and_rank=_fake_search_and_rank([]),
    )

    assert calls["n"] == 2


def test_warmup_also_warms_search_and_rank():
    """LLM 프롬프트만 예열하고 검색(임베딩 모델 최초 로딩)을 빼먹으면, 첫 실사용자가
    product_search 계열 의도를 말하는 순간 그 로딩 비용을 고스란히 떠안는다(실측
    확인: LLM은 빨라졌는데 전체 턴은 여전히 28초 — 검색 임베딩 모델 로딩이 그대로
    남아있었기 때문). search_and_rank도 반드시 호출돼야 한다."""
    seen = {"called": False}

    def spy_search_and_rank(contact1, top_k=3):
        seen["called"] = True
        return []

    def fake_chat(messages, schema, *, think, model=None):
        return json.dumps(
            {
                "intent": "general_chat",
                "max_price": None,
                "min_price": None,
                "gift_theme": [],
                "color": [],
                "query_text": "",
                "chat_reply": "",
                "reply": "ok",
                "allowed_ids": [],
                "suggestions": [],
            }
        )

    rr.warmup(
        chat=fake_chat,
        fetch_prices=_no_prices,
        fetch_artisans=_no_artisans,
        search_and_rank=spy_search_and_rank,
    )

    assert seen["called"] is True


# ---------------------------------------------------------------------------
# "몇 번째 상품 설명해줘" 및 그 되물음에 대한 후속 답변("모두"류) 처리
# ---------------------------------------------------------------------------


def _explain_chat(reply_text: str, suggestions: list[str] | None = None):
    def fake(messages, schema, *, think, model=None):
        return json.dumps({"reply": reply_text, "suggestions": suggestions or []})

    return fake


_CANDIDATES_3 = [
    {
        "product_id": 1,
        "name": "도기토 수반",
        "evidence": {"artisan_input": "물레 성형"},
    },
    {
        "product_id": 2,
        "name": "도기토 찻잔",
        "evidence": {"artisan_input": "유약 흘림"},
    },
    {"product_id": 6, "name": "분청 화병", "evidence": {"artisan_input": "문양 새김"}},
]


def test_run_explain_request_without_ordinal_asks_which_one_with_all_chip():
    """순번을 못 찾으면 되묻는데, 이번엔 "전체 설명" 칩도 같이 나가야 한다."""

    def chat_must_not_be_called(messages, schema, *, think, model=None):
        raise AssertionError("순번을 못 찾았으면 LLM을 부르지 않고 바로 되물어야 한다")

    result = rr.run(
        "이 상품들 설명해줘",
        chat=chat_must_not_be_called,
        previous_candidates=_CANDIDATES_3,
        **_NO_DB,
    )

    assert result["suggestions"] == ["1번", "2번", "3번", "전체 설명"]
    assert "몇 번째" in result["reply"]


def test_run_disambiguation_followup_all_chip_explains_all_in_one_call():
    """되물음("몇 번째예요?") 직후 "전체 설명"류로 답하면, "설명해" 키워드가 없어도
    explain_products(LLM 1회 호출)로 이어져야 한다 — 예전엔 이 답변이 새 메시지로
    재분류되면서 근거 없는 뭉뚱그린 답이 나갔었다(실측 확인된 버그)."""
    calls = {"n": 0}

    def fake(messages, schema, *, think, model=None):
        calls["n"] += 1
        return json.dumps(
            {
                "reply": "세 상품 모두 전통 기법으로 만들어졌습니다.",
                "suggestions": ["다른 색상으로", "포장 여부 확인"],
            }
        )

    history = [
        {"role": "user", "content": "이 상품들 설명해줘"},
        {
            "role": "assistant",
            "content": "몇 번째 상품을 말씀하시는 건가요? (1번/2번/3번/전체 설명 중에서 골라주세요)",
        },
    ]

    result = rr.run(
        "전체 설명",
        history=history,
        chat=fake,
        previous_candidates=_CANDIDATES_3,
        **_NO_DB,
    )

    assert calls["n"] == 1
    assert result["product_ids"] == [1, 2, 6]
    assert result["reply"] == "세 상품 모두 전통 기법으로 만들어졌습니다."
    assert result["suggestions"] == ["다른 색상으로", "포장 여부 확인"]


def test_run_disambiguation_followup_ordinal_answer_explains_single_product():
    """되물음 직후 "1번"처럼 순번만 답해도("설명해" 키워드 없이도) 그 상품 하나를
    explain_product로 설명해야 한다."""
    history = [
        {"role": "user", "content": "이 상품들 설명해줘"},
        {
            "role": "assistant",
            "content": "몇 번째 상품을 말씀하시는 건가요? (1번/2번/3번/전체 설명 중에서 골라주세요)",
        },
    ]

    result = rr.run(
        "1번",
        history=history,
        chat=_explain_chat(
            "도기토 수반은 물레로 직접 성형한 작품입니다.",
            suggestions=["다른 재질로"],
        ),
        previous_candidates=_CANDIDATES_3,
        **_NO_DB,
    )

    assert result["product_ids"] == [1]
    assert result["suggestions"] == ["다른 재질로"]


def test_run_deduplicates_history_when_backend_echoes_current_message_last():
    """실제 백엔드(ChatService.sendMessage)는 사용자 메시지를 먼저 DB에 저장한
    다음에야 history를 조회해서 우리한테 넘긴다 — 그래서 실전 history의 마지막
    줄은 항상 지금 막 받은 message와 똑같은 내용으로 중복된다(코드로 직접 확인된
    버그). 이 중복이 있으면 _is_disambiguation_followup이 보는 history[-1]이
    "방금 내가 한 말"이 돼버려서 직전 봇의 되물음을 절대 못 본다. history 마지막이
    지금 message와 똑같은 사용자 발화면 그 한 줄은 버리고 시작해야 한다."""
    history = [
        {"role": "user", "content": "이 상품들 설명해줘"},
        {
            "role": "assistant",
            "content": "몇 번째 상품을 말씀하시는 건가요? (1번/2번/3번/전체 설명 중에서 골라주세요)",
        },
        {"role": "user", "content": "1번"},  # 백엔드가 실어 보내는 중복
    ]

    result = rr.run(
        "1번",
        history=history,
        chat=_explain_chat(
            "도기토 수반은 물레로 직접 성형한 작품입니다.",
            suggestions=["다른 재질로"],
        ),
        previous_candidates=_CANDIDATES_3,
        **_NO_DB,
    )

    assert result["product_ids"] == [1]
    assert result["suggestions"] == ["다른 재질로"]


def test_run_disambiguation_followup_with_new_category_escapes_the_loop():
    """실측 확인된 버그: 봇이 "몇 번째 상품을 말씀하시는 건가요?"라고 되물은 다음,
    사용자가 순번·"모두"·가격최상급 어느 것도 아닌 완전히 다른 화제(다른 종목)로
    답하면, ordinal이 계속 None으로 나와 매번 같은 되물음을 반복해 대화가 갇혀버렸다.
    적어도 이전 후보와 다른 종목이 명확히 언급된 경우는(taxonomy 대조로 추가 LLM
    호출 없이 판단 가능) 되물음 루프에서 빠져나와 새 종목으로 재검색해야 한다."""
    history = [
        {"role": "user", "content": "이 상품들 설명해줘"},
        {
            "role": "assistant",
            "content": "몇 번째 상품을 말씀하시는 건가요? (1번/2번/3번/전체 설명 중에서 골라주세요)",
        },
    ]
    chat = _sequenced_chat(
        intent_payload={
            "intent": "narrow_down",
            "max_price": None,
            "min_price": None,
            "gift_theme": [],
            "color": [],
            "query_text": "목공예로 보여줘",
        },
        generate_payload={"reply": "ok", "allowed_ids": [], "suggestions": []},
    )
    fresh = [{"product_id": 466, "name": "소나무 의자", "score": 0.7, "evidence": {}}]
    seen = {}

    def spy_search_and_rank(contact1, top_k=3):
        seen["called"] = True
        return fresh

    result = rr.run(
        "아 됐고 목공예로 보여줘",
        history=history,
        chat=chat,
        search_and_rank=spy_search_and_rank,
        previous_candidates=_CANDIDATES_3,
        **_NO_DB,
    )

    assert seen.get("called") is True
    assert "몇 번째" not in result["reply"]


def _prices_for_candidates_3(product_ids: list[int]) -> dict[int, int]:
    """_CANDIDATES_3 기준 가격 — product_id 1이 최저가, 2가 최고가다."""
    return {1: 45000, 2: 234000, 6: 167000}


def test_run_explain_request_cheapest_resolves_without_asking_which_one():
    """ "가장 저렴한 것"은 순번이 아니라 가격 표현이라 extract_ordinal은 못 잡지만,
    직전 턴에 이미 가격을 알려줬으므로 되묻지 않고 바로 최저가 상품(product_id=1)을
    설명해야 한다(실측 확인된 버그: 매번 "몇 번째예요?"로 되물었었다)."""
    result = rr.run(
        "그중 가장 저렴한 것에 대해 더 자세히 알려줘",
        chat=_explain_chat("도기토 수반은 물레로 직접 성형한 작품입니다."),
        previous_candidates=_CANDIDATES_3,
        **{**_NO_DB, "fetch_prices": _prices_for_candidates_3},
    )

    assert result["product_ids"] == [1]
    assert "몇 번째" not in result["reply"]


def test_run_explain_request_most_expensive_resolves_correct_product():
    result = rr.run(
        "가장 비싼 것 설명해줘",
        chat=_explain_chat("도기토 찻잔은 유약을 흘려 무늬를 낸 작품입니다."),
        previous_candidates=_CANDIDATES_3,
        **{**_NO_DB, "fetch_prices": _prices_for_candidates_3},
    )

    assert result["product_ids"] == [2]


def test_run_explain_request_cheapest_falls_back_to_asking_when_prices_unavailable():
    """가격 조회 자체가 실패하면(빈 딕셔너리) 잘못 추측하지 말고 기존처럼 되물어야
    안전하다."""
    result = rr.run(
        "가장 저렴한 것 설명해줘",
        chat=lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("가격을 못 구했으면 LLM을 부르면 안 된다")
        ),
        previous_candidates=_CANDIDATES_3,
        **_NO_DB,  # fetch_prices=_no_prices → 항상 빈 딕셔너리
    )

    assert "몇 번째" in result["reply"]


def test_run_history_with_null_content_does_not_crash():
    """백엔드가 history 항목에 content:null을 실어 보내도(예: {"sender":"ARTISAN",
    "content":null}) _to_pipeline_history는 그 None을 그대로 통과시킨다(item.get으로
    키가 있을 땐 기본값이 안 먹으므로). _is_disambiguation_followup이 매 턴 무조건
    history[-1]을 보는데, 거기서 None.startswith(...)를 호출하면 AttributeError로
    죽는다(실측 확인된 버그) — 친절한 fallback 대신 날것 그대로의 500이 나간다."""
    chat = _sequenced_chat(
        intent_payload={
            "intent": "product_search",
            "max_price": None,
            "min_price": None,
            "gift_theme": [],
            "color": [],
            "query_text": "찻잔",
        },
        generate_payload={
            "reply": "이 찻잔을 추천드려요.",
            "allowed_ids": [9],
            "suggestions": [],
        },
    )
    search_and_rank = _fake_search_and_rank(
        [
            {
                "product_id": 9,
                "name": "청자 다완",
                "score": 0.8,
                "evidence": {"artisan_input": "", "verified": None},
            }
        ]
    )
    history = [{"role": "assistant", "content": None}]

    result = rr.run(
        "찻잔 있나요",
        history=history,
        chat=chat,
        search_and_rank=search_and_rank,
        **_NO_DB,
    )

    assert result["reply"]


def test_run_plain_message_without_disambiguation_history_is_not_treated_as_explain():
    """직전 봇 턴이 되물음이 아니었으면, "모두"류 메시지는 평소처럼 일반 경로로
    가야 한다(오탐 방지) — is_explain_request도 False이므로 explain 경로에 들어가면
    안 된다."""

    def search_and_rank_must_not_be_called(contact1):
        raise AssertionError(
            "narrow_down + previous_candidates가 있으면 재검색하면 안 된다"
        )

    chat = _sequenced_chat(
        intent_payload={
            "intent": "narrow_down",
            "max_price": None,
            "min_price": None,
            "gift_theme": [],
            "color": [],
            "query_text": "도자기",
        },
        generate_payload={"reply": "ok", "allowed_ids": [1, 2, 6], "suggestions": []},
    )
    history = [
        {"role": "user", "content": "도자기 추천해줘"},
        {"role": "assistant", "content": "도자기 3점을 소개해 드릴게요."},
    ]

    result = rr.run(
        "모두",
        history=history,
        chat=chat,
        search_and_rank=search_and_rank_must_not_be_called,
        previous_candidates=_CANDIDATES_3,
        **_NO_DB,
    )

    assert result["reply"] == "ok"


# ---------------------------------------------------------------------------
# wants_reason — "왜 추천했어?"류 이유 질문(키워드 하드코딩이 아니라 intent 분류
# LLM의 판단 신호를 그대로 씀)
# ---------------------------------------------------------------------------


def test_run_wants_reason_routes_to_explain_products():
    """intent 분류가 wants_reason=true를 주면, "설명해"·"자세히" 키워드가 전혀
    없어도 explain_products로 이어져야 한다."""
    calls = {"n": 0}

    def chat(messages, schema, *, think, model=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return json.dumps(
                {
                    "intent": "narrow_down",
                    "wants_reason": True,
                    "max_price": None,
                    "min_price": None,
                    "gift_theme": [],
                    "color": [],
                    "query_text": "추천 이유",
                }
            )
        return json.dumps(
            {"reply": "세 상품 모두 전통 기법으로 만들어졌습니다.", "suggestions": []}
        )

    history = [
        {"role": "user", "content": "도자기 추천해줘"},
        {"role": "assistant", "content": "도자기 3점을 소개해 드릴게요."},
    ]

    result = rr.run(
        "왜 이 상품들을 추천한거야?",
        history=history,
        chat=chat,
        previous_candidates=_CANDIDATES_3,
        **_NO_DB,
    )

    assert calls["n"] == 2
    assert result["product_ids"] == [1, 2, 6]
    assert result["reply"] == "세 상품 모두 전통 기법으로 만들어졌습니다."


def test_run_wants_reason_without_previous_candidates_asks_to_search_first():
    """추천받은 상품이 아직 없는 상태에서 이유를 물으면, explain_products를 부르지
    않고 먼저 검색을 유도해야 한다."""

    def chat(messages, schema, *, think, model=None):
        return json.dumps(
            {
                "intent": "narrow_down",
                "wants_reason": True,
                "max_price": None,
                "min_price": None,
                "gift_theme": [],
                "color": [],
                "query_text": "",
            }
        )

    result = rr.run(
        "왜 그걸 추천한거야?", chat=chat, previous_candidates=None, **_NO_DB
    )

    assert result["product_ids"] == []
    assert "먼저" in result["reply"]


def test_run_wants_reason_with_category_change_does_not_explain_stale_candidates():
    """실측 확인된 버그: wants_reason 분기가 category_changed 계산(더 아래)보다
    먼저 실행돼서, "금속 공예품이 왜 좋은지 설명해줘"처럼 이유를 물으면서 동시에
    종목도 바꾼 문장이 previous_candidates(도자기)를 그대로 explain_products에
    넘겨버렸다 — 엉뚱한 종목을 설명하고 새 종목으로 재검색할 기회가 없어졌다.
    종목이 바뀌었으면 이유 질문이어도 먼저 재검색해야 한다."""
    chat = _sequenced_chat(
        intent_payload={
            "intent": "narrow_down",
            "wants_reason": True,
            "max_price": None,
            "min_price": None,
            "gift_theme": [],
            "color": [],
            "query_text": "금속 공예품 추천해줄래?",
        },
        generate_payload={"reply": "ok", "allowed_ids": [], "suggestions": []},
    )
    previous = [{"product_id": 78, "name": "청자 찻잔", "score": 0.9, "evidence": {}}]
    fresh = [{"product_id": 466, "name": "은장도", "score": 0.7, "evidence": {}}]
    seen = {}

    def spy_search_and_rank(contact1, top_k=3):
        seen["called"] = True
        return fresh

    result = rr.run(
        # "설명해"·"자세히" 키워드가 없어야 is_explain_request(키워드 판단) 분기가 아니라
        # wants_reason(LLM 판단) 분기를 실제로 탄다 — 이 둘은 서로 다른 코드 경로다.
        "아니 그거 말고 금속 공예품이 왜 좋아?",
        chat=chat,
        search_and_rank=spy_search_and_rank,
        previous_candidates=previous,
        **_NO_DB,
    )

    assert seen.get("called") is True
    assert result["candidates"] == fresh


def test_run_wants_reason_false_does_not_shortcut_to_explain():
    """wants_reason=false면 평소처럼 일반 경로(build_reply)로 가야 한다."""
    chat = _sequenced_chat(
        intent_payload={
            "intent": "product_search",
            "wants_reason": False,
            "max_price": None,
            "min_price": None,
            "gift_theme": [],
            "color": [],
            "query_text": "찻잔",
        },
        generate_payload={"reply": "ok", "allowed_ids": [1], "suggestions": []},
    )

    result = rr.run(
        "찻잔 추천해줘",
        chat=chat,
        search_and_rank=_fake_search_and_rank(_CANDIDATES_3),
        **_NO_DB,
    )

    assert result["reply"] == "ok"


def test_run_needs_clarification_skips_search_and_returns_chat_reply():
    """ "선물"처럼 검색 단서가 하나도 없으면 검색을 건너뛰고 되묻는 chat_reply를
    그대로 반환한다(사용자 시나리오 E23: 의도 불명확 → 추가 질문으로 구체화)."""
    chat = _sequenced_chat(
        intent_payload={
            "intent": "gift_recommendation",
            "needs_clarification": True,
            "max_price": None,
            "min_price": None,
            "gift_theme": [],
            "color": [],
            "query_text": "선물",
            "chat_reply": "어떤 분께 드릴 선물인가요?",
        },
        generate_payload={"reply": "ok", "allowed_ids": [], "suggestions": []},
    )

    def search_and_rank_must_not_be_called(contact1):
        raise AssertionError("needs_clarification이 true면 검색하면 안 된다")

    result = rr.run(
        "선물",
        chat=chat,
        search_and_rank=search_and_rank_must_not_be_called,
        **_NO_DB,
    )

    assert result["reply"] == "어떤 분께 드릴 선물인가요?"
    assert result["product_ids"] == []
    assert result["intent"] == "gift_recommendation"
    # 열린 질문만 던지지 않고 후보 답까지 칩으로 같이 준다(clarifying question 연구 —
    # 답 후보 제시가 사용자 응답 부담을 줄인다).
    assert result["suggestions"] == rr._CLARIFICATION_CHIPS_GIFT


def test_run_needs_clarification_product_search_uses_category_chips():
    """product_search에서 되물을 땐 선물용 칩이 아니라 실제 카탈로그 카테고리 칩을
    준다 — intent에 안 맞는 칩(예: 선물 아닌데 "생일 선물")을 내면 안 된다."""
    chat = _sequenced_chat(
        intent_payload={
            "intent": "product_search",
            "needs_clarification": True,
            "max_price": None,
            "min_price": None,
            "gift_theme": [],
            "color": [],
            "query_text": "아무거나",
            "chat_reply": "어떤 종류의 공예품을 찾으시나요?",
        },
        generate_payload={"reply": "ok", "allowed_ids": [], "suggestions": []},
    )

    result = rr.run(
        "아무거나",
        chat=chat,
        search_and_rank=lambda contact1: (_ for _ in ()).throw(
            AssertionError("needs_clarification이 true면 검색하면 안 된다")
        ),
        **_NO_DB,
    )

    assert result["suggestions"] == rr._CLARIFICATION_CHIPS_PRODUCT


def test_run_needs_clarification_false_does_not_shortcut():
    """단서가 하나라도 있으면(needs_clarification=false) 평소처럼 검색한다."""
    chat = _sequenced_chat(
        intent_payload={
            "intent": "product_search",
            "needs_clarification": False,
            "max_price": None,
            "min_price": None,
            "gift_theme": [],
            "color": [],
            "query_text": "찻잔",
        },
        generate_payload={"reply": "ok", "allowed_ids": [1], "suggestions": []},
    )

    result = rr.run(
        "찻잔 추천해줘",
        chat=chat,
        search_and_rank=_fake_search_and_rank(_CANDIDATES_3),
        **_NO_DB,
    )

    assert result["reply"] == "ok"


def test_run_wants_alternatives_excludes_already_shown_products():
    """ "다른 거 추천해줘"는 새 하드필터가 없어도 재검색해야 한다 — 그냥 속성
    질문처럼 후보를 재사용하면 직전과 똑같은 상품을 "다른 거"라고 거짓 응답하게
    된다(실측 확인). 이미 보여준 product_id는 결과에서 빠져야 한다."""
    chat = _sequenced_chat(
        intent_payload={
            "intent": "narrow_down",
            "wants_alternatives": True,
            "max_price": None,
            "min_price": None,
            "gift_theme": [],
            "color": [],
            "query_text": "도자기 찻잔",
        },
        generate_payload={"reply": "ok", "allowed_ids": [], "suggestions": []},
    )
    previous = [{"product_id": 78, "name": "청자 찻잔", "score": 0.9, "evidence": {}}]
    fresh_pool = [
        {"product_id": 78, "name": "청자 찻잔", "score": 0.9, "evidence": {}},
        {"product_id": 816, "name": "분청 찻잔", "score": 0.8, "evidence": {}},
        {"product_id": 2, "name": "도기토 찻잔", "score": 0.7, "evidence": {}},
    ]
    seen = {}

    def spy_search_and_rank(contact1, top_k=3):
        seen["top_k"] = top_k
        return fresh_pool

    rr.run(
        "다른 거 추천해줘",
        chat=chat,
        search_and_rank=spy_search_and_rank,
        previous_candidates=previous,
        previous_product_ids=[78],
        **_NO_DB,
    )

    # 더 넉넉히 받아오는지(top_k 확장), 이미 보여준 78번은 빠지는지 spy로 확인.
    assert seen["top_k"] == 9


def test_run_wants_alternatives_passes_only_unseen_candidates_to_build_reply():
    """이미 보여준 product_id(78)는 build_reply에 넘기는 candidates에서 빠져야
    한다 — 그래야 카피라이터가 그 상품을 다시 "다른 것"이라고 말하지 않는다."""
    chat = _sequenced_chat(
        intent_payload={
            "intent": "narrow_down",
            "wants_alternatives": True,
            "max_price": None,
            "min_price": None,
            "gift_theme": [],
            "color": [],
            "query_text": "도자기 찻잔",
        },
        generate_payload={"reply": "ok", "allowed_ids": [816, 2], "suggestions": []},
    )
    previous = [{"product_id": 78, "name": "청자 찻잔", "score": 0.9, "evidence": {}}]
    fresh_pool = [
        {"product_id": 78, "name": "청자 찻잔", "score": 0.9, "evidence": {}},
        {"product_id": 816, "name": "분청 찻잔", "score": 0.8, "evidence": {}},
        {"product_id": 2, "name": "도기토 찻잔", "score": 0.7, "evidence": {}},
    ]

    result = rr.run(
        "다른 거 추천해줘",
        chat=chat,
        search_and_rank=lambda contact1, top_k=3: fresh_pool,
        previous_candidates=previous,
        previous_product_ids=[78],
        **_NO_DB,
    )

    candidate_ids = {c["product_id"] for c in result["candidates"]}
    assert 78 not in candidate_ids
    assert candidate_ids == {816, 2}


def test_run_wants_alternatives_false_reuses_candidates_as_before():
    """wants_alternatives가 false면 기존 동작(새 필터 없으면 재사용) 그대로다 —
    이번 변경이 다른 narrow_down 흐름에 영향을 주면 안 된다."""
    chat = _sequenced_chat(
        intent_payload={
            "intent": "narrow_down",
            "wants_alternatives": False,
            "max_price": None,
            "min_price": None,
            "gift_theme": [],
            "color": [],
            "query_text": "가격대 확인",
        },
        generate_payload={
            "reply": "가격 정보는 확인되지 않습니다.",
            "allowed_ids": [78],
            "suggestions": [],
        },
    )
    previous = [{"product_id": 78, "name": "청자 찻잔", "score": 0.9, "evidence": {}}]

    def search_and_rank_must_not_be_called(contact1, top_k=3):
        raise AssertionError("wants_alternatives가 false면 재검색하면 안 된다")

    result = rr.run(
        "가격대 확인해줘",
        chat=chat,
        search_and_rank=search_and_rank_must_not_be_called,
        previous_candidates=previous,
        **_NO_DB,
    )

    assert result["candidates"] == previous
