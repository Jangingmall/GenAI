"""generate.py 단위 테스트. 순수 함수는 LLM 없이, build_reply는 fake_chat 주입.

이 브랜치엔 eval/ 스위트(실LLM 스모크·안전성 회귀 평가)가 없어 전부 인라인 데이터로만
검증한다.

실행: python -m pytest tests/test_generate.py -q
"""

import json

import psycopg2

from app.pipeline import generate as gen


# ---------------------------------------------------------------------------
# _fetch_prices / _fetch_artisans — DB 실패는 예외 전파 대신 빈 딕셔너리로 흡수해야 한다
# (CodeRabbit 리뷰 지적: 예외가 build_reply까지 전파되면 채팅 호출 자체가 실패한다)
# ---------------------------------------------------------------------------


def test_fetch_prices_returns_empty_dict_when_connect_fails(monkeypatch):
    monkeypatch.setattr(
        gen.psycopg2,
        "connect",
        lambda *_a, **_kw: (_ for _ in ()).throw(psycopg2.OperationalError("연결 실패")),
    )
    assert gen._fetch_prices([1, 2]) == {}


def test_fetch_artisans_returns_empty_dict_when_connect_fails(monkeypatch):
    monkeypatch.setattr(
        gen.psycopg2,
        "connect",
        lambda *_a, **_kw: (_ for _ in ()).throw(psycopg2.OperationalError("연결 실패")),
    )
    assert gen._fetch_artisans([1, 2]) == {}


# ---------------------------------------------------------------------------
# _format_candidates
# ---------------------------------------------------------------------------


def test_format_candidates_empty_returns_placeholder():
    assert gen._format_candidates([]) == "(검색 결과 없음)"


def test_format_candidates_includes_category_and_evidence():
    candidates = [
        {
            "product_id": 1,
            "name": "여성용 챙모자",
            "category": "총모자",
            "evidence": {"artisan_input": "말총으로 엮었습니다", "verified": "이수자"},
        }
    ]
    text = gen._format_candidates(candidates)
    assert "product_id: 1" in text
    assert "총모자" in text
    assert "이수자" in text
    assert "말총으로 엮었습니다" in text


def test_format_candidates_includes_price_when_given():
    # 접점2엔 price가 없지만, B가 직접 DB에서 조회해 prices로 넘긴다(_fetch_prices)
    candidates = [{"product_id": 1, "name": "T", "category": "C", "evidence": {}}]
    text = gen._format_candidates(candidates, {1: 37000})
    assert "37000원" in text


def test_format_candidates_shows_no_info_when_price_missing():
    candidates = [{"product_id": 1, "name": "T", "category": "C", "evidence": {}}]
    text = gen._format_candidates(candidates, {})
    assert "정보 없음" in text


def test_format_candidates_includes_artisan_when_given():
    # artisans 테이블도 price와 같은 이유로 B가 직접 조회해 넘긴다(_fetch_artisans)
    candidates = [{"product_id": 1, "name": "T", "category": "C", "evidence": {}}]
    text = gen._format_candidates(candidates, artisans={1: {"business_name": "정예준 도예", "region": "부산"}})
    assert "정예준 도예" in text
    assert "부산" in text


def test_format_candidates_shows_no_info_when_artisan_missing():
    candidates = [{"product_id": 1, "name": "T", "category": "C", "evidence": {}}]
    text = gen._format_candidates(candidates, artisans={})
    assert "장인: 정보 없음" in text


# ---------------------------------------------------------------------------
# _drop_unknown_ids
# ---------------------------------------------------------------------------


def test_drop_unknown_ids_removes_hallucinated_id():
    items = [{"product_id": 1, "reason": "a"}, {"product_id": 999, "reason": "b"}]
    assert gen._drop_unknown_ids(items, {1}) == [{"product_id": 1, "reason": "a"}]


def test_drop_unknown_ids_empty_allowed_drops_all():
    items = [{"product_id": 1, "reason": "a"}]
    assert gen._drop_unknown_ids(items, set()) == []


# ---------------------------------------------------------------------------
# _drop_evidence_mismatched
# ---------------------------------------------------------------------------


def test_drop_evidence_mismatched_removes_wrong_category_reason():
    # 후보는 도자기(청자)인데 reason에 나전칠기 신호("자개")가 섞여 있으면 few-shot
    # 문구를 베낀 것으로 보고 제거한다.
    candidates_by_id = {1: {"product_id": 1, "name": "청자 찻잔", "evidence": {}}}
    items = [{"product_id": 1, "reason": "자개를 문양대로 오려 붙이고 옻칠 연마를 반복했습니다."}]
    assert gen._drop_evidence_mismatched(items, candidates_by_id) == []


def test_drop_evidence_mismatched_keeps_matching_reason():
    candidates_by_id = {1: {"product_id": 1, "name": "청자 찻잔", "evidence": {}}}
    items = [{"product_id": 1, "reason": "청자를 물레로 성형해 만들었습니다."}]
    assert gen._drop_evidence_mismatched(items, candidates_by_id) == items


def test_drop_evidence_mismatched_keeps_when_category_unknown():
    # candidate에서 카테고리를 역추정 못 하면(_effective_category가 None) 판단 근거가
    # 없으니 건드리지 않는다.
    candidates_by_id = {1: {"product_id": 1, "name": "알 수 없는 상품", "evidence": {}}}
    items = [{"product_id": 1, "reason": "자개를 오려 붙였습니다."}]
    assert gen._drop_evidence_mismatched(items, candidates_by_id) == items


# ---------------------------------------------------------------------------
# build_reply — chat 주입, LLM 없음
# ---------------------------------------------------------------------------


def _fake_chat(payload: dict):
    def fake(messages, schema, *, think, model=None):
        return json.dumps(payload)

    return fake


def _no_prices(product_ids: list[int]) -> dict[int, int]:
    """단위 테스트가 실제 DB 없이 돌아가게 하는 가짜 fetch_prices — chat과 같은 이유로 주입."""
    return {}


def _no_artisans(product_ids: list[int]) -> dict[int, dict]:
    """_no_prices와 같은 이유의 가짜 fetch_artisans."""
    return {}


# build_reply 호출마다 반복되는 DB 회피용 키워드 인자 묶음 — **_NO_DB로 한 번에 넘긴다.
_NO_DB = {"fetch_prices": _no_prices, "fetch_artisans": _no_artisans}


def test_build_reply_b13_empty_candidates_yields_empty_products():
    # eval/cases.json b13("이 함, 국가 인증서도 따로 받은 거 맞죠?") 시나리오를 인라인으로
    # 재현 — evidence(주칠 함, 국가무형유산 등급)엔 "인증서" 언급이 없어 그 사실 하나는
    # 미확인이지만, 상품 자체는 유지돼야 한다(규칙2+5). 여기서는 fake_chat이 이미 "확인
    # 안 됨" 판단을 내린 응답만 검증하므로 products가 빈 배열로 나오는 경로만 본다.
    candidates = [
        {
            "product_id": 850,
            "name": "주칠 함",
            "score": 0.72,
            "evidence": {
                "artisan_input": "주칠 목태에 연꽃 문양 자개를 상감하고 투명 옻칠로 마감했습니다.",
                "verified": "NATIONAL_INTANGIBLE_HERITAGE",
                "ai_inference": None,
            },
        }
    ]
    payload = {
        "reply": "그런 조건에 맞는 상품은 확인되지 않습니다.",
        "products": [],
        "suggestions": ["가격대 올려서", "다른 재질로", "다른 종목으로"],
    }
    result = gen.build_reply(
        "이 함, 국가 인증서도 따로 받은 거 맞죠?",
        candidates,
        "product_search",
        chat=_fake_chat(payload),
        **_NO_DB,
    )
    assert result["products"] == []


def test_build_reply_drops_id_not_in_candidates():
    candidates = [{"product_id": 1, "name": "T", "category": "C", "evidence": {}}]
    payload = {
        "reply": "추천합니다.",
        "products": [
            {"product_id": 1, "reason": "좋아요"},
            {"product_id": 999, "reason": "환각"},
        ],
        "suggestions": ["다른 색상으로"],
    }
    result = gen.build_reply(
        "아무거나", candidates, "product_search", chat=_fake_chat(payload), **_NO_DB
    )
    assert result["products"] == [{"product_id": 1, "reason": "좋아요"}]


def test_build_reply_calls_chat_with_think_true():
    seen = {}

    def fake(messages, schema, *, think, model=None):
        seen["think"] = think
        return json.dumps({"reply": "ok", "products": [], "suggestions": []})

    gen.build_reply("메시지", [], "general_chat", chat=fake, **_NO_DB)
    assert seen["think"] is True


# ---------------------------------------------------------------------------
# _format_filters / suggestions
# ---------------------------------------------------------------------------


def test_format_filters_none_returns_placeholder():
    assert gen._format_filters(None) == "(추출된 조건 없음)"


def test_format_filters_empty_dict_returns_placeholder():
    assert gen._format_filters({"max_price": None, "min_price": None, "gift_theme": None, "color": None}) == (
        "(추출된 조건 없음)"
    )


def test_format_filters_includes_price_and_theme():
    filters = {"max_price": 50000, "min_price": None, "gift_theme": ["WEDDING"], "color": None}
    text = gen._format_filters(filters)
    assert "50000원 이하" in text
    assert "WEDDING" in text


def test_cap_suggestions_truncates_to_three():
    suggestions = ["3만 원 아래로", "다른 색상으로", "다른 재질로", "포장까지 되는 것만"]
    assert gen._cap_suggestions(suggestions) == suggestions[:3]


def test_cap_suggestions_drops_full_sentences_outside_word_range():
    """LLM이 규칙을 어기고 완전한 문장이나 한 단어를 반환하면 칩 형식(2~4어절)이 아니므로 뺀다."""
    suggestions = ["네", "혹시 3만 원 아래로 검색해서 보여드릴까요?", "다른 색상으로"]
    assert gen._cap_suggestions(suggestions) == ["다른 색상으로"]


def test_build_reply_returns_suggestions_from_chat():
    payload = {
        "reply": "추천합니다.",
        "products": [],
        "suggestions": ["가격대 낮춰서", "다른 색상으로", "다른 종목으로"],
    }
    result = gen.build_reply(
        "아무거나", [], "product_search", chat=_fake_chat(payload), **_NO_DB
    )
    assert result["suggestions"] == payload["suggestions"]


def test_build_reply_truncates_history_to_recent_turns():
    """최근 3턴(6개 메시지)만 남기고 그 이전은 잘라야 한다(_MAX_HISTORY_TURNS)."""
    seen = {}
    payload = {"reply": "ok", "products": [], "suggestions": []}

    def fake(messages, schema, *, think, model=None):
        seen["user_content"] = messages[-1]["content"]
        return json.dumps(payload)

    history = [{"role": "user", "content": f"{i}번째 메시지"} for i in range(10)]
    gen.build_reply(
        "최근 질문", [], "product_search", history=history, chat=fake, **_NO_DB
    )

    assert "0번째 메시지" not in seen["user_content"]
    assert "9번째 메시지" in seen["user_content"]
