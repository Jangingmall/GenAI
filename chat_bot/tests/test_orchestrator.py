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


def _no_cache_lookup(message: str):
    """의미 기반 캐시 기본값은 실제 임베딩 모델을 부르므로, 단위 테스트에선 항상 미스로 만든다."""
    return


def _no_cache_store(message: str, contact1: dict) -> None:
    pass


# rr.run 호출마다 반복되는 DB·캐시 회피용 키워드 인자 묶음 — **_NO_DB로 한 번에 넘긴다.
_NO_DB = {
    "fetch_prices": _no_prices,
    "fetch_artisans": _no_artisans,
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
        generate_payload={"reply": "ok", "allowed_ids": [], "suggestions": []},
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
        generate_payload={"reply": "ok", "allowed_ids": [], "suggestions": []},
    )
    fresh = [{"product_id": 1, "name": "옹기 항아리", "score": 0.5, "evidence": {}}]
    search_and_rank = _fake_search_and_rank(fresh)

    result = rr.run(
        "그중 저렴한 것", chat=chat, search_and_rank=search_and_rank, **_NO_DB
    )

    assert result["candidates"] == fresh


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
    assert stored["contact1"]["query_text"] == "찻잔"


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

    def spy_search_and_rank(contact1):
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
