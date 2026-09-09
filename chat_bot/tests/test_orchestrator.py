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
    def fake(contact1: dict) -> list[dict]:
        return candidates

    return fake


def _no_prices(product_ids: list[int]) -> dict[int, int]:
    """단위 테스트가 실제 DB 없이 돌아가게 하는 가짜 fetch_prices."""
    return {}


def _no_artisans(product_ids: list[int]) -> dict[int, dict]:
    """_no_prices와 같은 이유의 가짜 fetch_artisans."""
    return {}


# rr.run 호출마다 반복되는 DB 회피용 키워드 인자 묶음 — **_NO_DB로 한 번에 넘긴다.
_NO_DB = {"fetch_prices": _no_prices, "fetch_artisans": _no_artisans}


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
            "products": [{"product_id": 9, "reason": "청자 다완입니다."}],
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
        "products",
        "suggestions",
        "candidates",
        "filters",
    }
    assert result["intent"] == "product_search"
    assert result["products"] == [{"product_id": 9, "reason": "청자 다완입니다."}]
    assert result["suggestions"] == [
        "다른 색상으로",
        "가격대 낮춰서",
        "포장까지 되는 것만",
    ]


def test_run_passes_contact1_to_search_and_rank():
    seen = {}

    def spy_search_and_rank(contact1):
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
        generate_payload={"reply": "ok", "products": [], "suggestions": []},
    )
    rr.run("찻잔 있나요", chat=chat, search_and_rank=spy_search_and_rank, **_NO_DB)

    assert seen["contact1"]["query_text"] == "찻잔"
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
            "products": [{"product_id": 999, "reason": "존재하지 않는 상품"}],
            "suggestions": [],
        },
    )
    search_and_rank = _fake_search_and_rank(
        [{"product_id": 9, "name": "청자 다완", "score": 0.8, "evidence": {}}]
    )
    result = rr.run("찻잔 있나요", chat=chat, search_and_rank=search_and_rank, **_NO_DB)

    assert result["products"] == []


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
            "products": [{"product_id": 78, "reason": "청자 찻잔입니다."}],
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
    assert result["products"] == [{"product_id": 78, "reason": "청자 찻잔입니다."}]


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
            "products": [{"product_id": 834, "reason": "..."}],
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
        generate_payload={"reply": "ok", "products": [], "suggestions": []},
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
        fetch_prices=_no_prices,
        fetch_artisans=_no_artisans,
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
        generate_payload={"reply": "ok", "products": [], "suggestions": []},
    )
    previous = [{"product_id": 78, "name": "청자 찻잔", "score": 0.9, "evidence": {}}]
    fresh = [{"product_id": 38, "name": "백자 대접", "score": 0.7, "evidence": {}}]
    seen = {}

    def spy_search_and_rank(contact1):
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
        generate_payload={"reply": "ok", "products": [], "suggestions": []},
    )
    fresh = [{"product_id": 1, "name": "옹기 항아리", "score": 0.5, "evidence": {}}]
    search_and_rank = _fake_search_and_rank(fresh)

    result = rr.run(
        "그중 저렴한 것", chat=chat, search_and_rank=search_and_rank, **_NO_DB
    )

    assert result["candidates"] == fresh
