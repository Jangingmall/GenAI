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
        lambda *_a, **_kw: (_ for _ in ()).throw(
            psycopg2.OperationalError("연결 실패")
        ),
    )
    assert gen._fetch_prices([1, 2]) == {}


def test_fetch_artisans_returns_empty_dict_when_connect_fails(monkeypatch):
    monkeypatch.setattr(
        gen.psycopg2,
        "connect",
        lambda *_a, **_kw: (_ for _ in ()).throw(
            psycopg2.OperationalError("연결 실패")
        ),
    )
    assert gen._fetch_artisans([1, 2]) == {}


def test_fetch_attrs_returns_empty_dict_when_connect_fails(monkeypatch):
    """_fetch_prices·_fetch_artisans와 같은 이유(_fetch_rows 리팩토링으로 셋이 이제
    같은 경로를 타므로) — 원래 이 케이스만 테스트가 빠져 있었다."""
    monkeypatch.setattr(
        gen.psycopg2,
        "connect",
        lambda *_a, **_kw: (_ for _ in ()).throw(
            psycopg2.OperationalError("연결 실패")
        ),
    )
    assert gen._fetch_attrs([1, 2]) == {}


def test_fetch_rows_returns_empty_list_without_connecting_when_no_ids(monkeypatch):
    """product_ids가 비어 있으면 DB 연결 자체를 열지 않는다."""

    def fail_if_called(*_a, **_kw):
        raise AssertionError("product_ids가 비었으면 connect를 호출하면 안 된다")

    monkeypatch.setattr(gen.psycopg2, "connect", fail_if_called)
    assert gen._fetch_rows("SELECT 1", [], label="테스트") == []


# ---------------------------------------------------------------------------
# _format_candidates
# ---------------------------------------------------------------------------


def test_format_candidates_empty_returns_placeholder():
    assert gen._format_candidates([]) == "(검색 결과 없음)"


# ---------------------------------------------------------------------------
# _verified_label — evidence.verified 영문 enum(DB 실측: NATIONAL_INTANGIBLE_HERITAGE·
# MASTER_CRAFTSMAN·SENIOR_CRAFTSMAN·YOUNG_CRAFTSMAN 4종) → 한국어 라벨
# ---------------------------------------------------------------------------


def test_verified_label_translates_all_known_enum_values():
    assert (
        gen._verified_label({"verified": "NATIONAL_INTANGIBLE_HERITAGE"})
        == "국가무형유산"
    )
    assert gen._verified_label({"verified": "MASTER_CRAFTSMAN"}) == "명장"
    assert gen._verified_label({"verified": "SENIOR_CRAFTSMAN"}) == "숙련장인"
    assert gen._verified_label({"verified": "YOUNG_CRAFTSMAN"}) == "청년장인"


def test_verified_label_missing_value_returns_no_info():
    assert gen._verified_label({}) == "정보 없음"
    assert gen._verified_label({"verified": None}) == "정보 없음"


def test_verified_label_unknown_value_falls_back_to_no_info():
    """카탈로그에 새 등급이 추가돼도 원문 영문을 그대로 노출하지 않는다."""
    assert gen._verified_label({"verified": "SOME_NEW_GRADE"}) == "정보 없음"


def test_color_label_translates_known_values():
    assert gen._color_label("BROWN") == "갈색"
    assert gen._color_label("GRAY") == "회색"


def test_color_label_missing_or_unknown_returns_no_info():
    assert gen._color_label(None) == "정보 없음"
    assert gen._color_label("PURPLE") == "정보 없음"


def test_format_candidates_includes_material_and_color():
    """실측 확인: 이 두 필드가 후보 블록에 빠져 있어서 "무슨 색이야?" 질문에 실제
    DB 색(BROWN)과 다른 색(회색)을 모델이 지어내 답한 사례가 있었다 — 재발 방지."""
    candidates = [{"product_id": 1, "name": "T", "evidence": {}}]
    text = gen._format_candidates(
        candidates, attrs={1: {"material": "옹기토", "color": "BROWN"}}
    )
    assert "재질: 옹기토" in text
    assert "색상: 갈색" in text


def test_format_candidates_shows_no_info_when_attrs_missing():
    candidates = [{"product_id": 1, "name": "T", "evidence": {}}]
    text = gen._format_candidates(candidates)
    assert "재질: 정보 없음" in text
    assert "색상: 정보 없음" in text


def test_category_from_name_resolves_when_longer_term_contains_shorter_ones_category():
    """ "전통옻칠"(WOOD) 안에 "옻칠"(NACRE)이 부분 문자열로 들어있어도, 더 긴
    복합어를 우선해 WOOD 하나로만 판정한다(둘 다 매칭돼 중의적으로 무산되면
    안 된다)."""
    assert gen._category_from_name("전통옻칠 도마") == "WOOD"


def test_category_from_name_resolves_water_jar_despite_overbroad_substring():
    """ "물항아리"(ONGGI) 안에 "항아리"(POTTERY)가 부분 문자열로 들어있어도
    ONGGI로만 판정한다 — taxonomy.py에 비슷한 겹침 단어 쌍이 또 있어도
    일반적으로 통해야 한다(이 이름은 오늘 고친 예시에 없던 것)."""
    assert gen._category_from_name("물항아리") == "ONGGI"


def test_mentioned_category_resolves_water_jar_from_message_too():
    assert gen._mentioned_category("물항아리 있나요") == "ONGGI"


def test_mentioned_category_matches_compound_term_with_natural_spacing():
    """실측 확인된 버그: "금속공예"는 CATEGORY_SIGNALS에 공백 없이 등록돼 있는데,
    사용자가 자연스럽게 "금속 공예품"처럼 띄어 쓰면 원문 그대로는 매칭이 안 된다.
    원문에서 아무 종목도 못 찾았을 때만 공백을 없앤 버전으로 재시도해야 한다."""
    assert gen._mentioned_category("금속 공예품 추천해줄래?") == "METAL"


def test_mentioned_category_exact_match_takes_priority_over_spacing_fallback():
    """원문 그대로 뭔가 찾았으면 공백 제거 재시도 자체를 안 한다 — 안 그러면
    "이 도자 기울기가 예쁘네요"처럼 우연히 다른 단어가 합쳐져 종목으로 오탐되는
    사례가 늘어난다. 원문에 이미 명확한 종목("도자기")이 있으면 그것만 쓴다."""
    assert (
        gen._mentioned_category("도자기 물항아리 있나요") is None
    )  # 두 종목 혼재 → 중의적, None이 정상
    assert gen._mentioned_category("도자기 찻잔 있나요") == "POTTERY"


def test_filter_by_category_excludes_wood_item_hidden_by_ambiguous_match():
    candidates = [
        {"product_id": 900, "name": "전통옻칠 도마"},
        {"product_id": 78, "name": "청자 찻잔"},
    ]
    filtered = gen._filter_by_category(candidates, "도자기 선물 추천해줘")
    assert [c["product_id"] for c in filtered] == [78]


def test_is_explain_request_tolerates_accidental_space_in_keyword():
    """실측 확인된 버그: "설 명해줄래?"처럼 "설명해" 중간에 실수로 띄어쓰기가
    들어가면 "설명해" in message 검사가 실패해 설명 요청 자체를 못 알아챈다.
    _mentioned_category가 이미 쓰는 패턴(원문에서 못 찾으면 공백 제거 후
    재시도)을 여기도 적용한다."""
    assert gen.is_explain_request("각 상품들 설 명해줄래?") is True
    assert gen.is_explain_request("좀 더 자 세히 알려줘") is True


def test_is_explain_request_still_false_for_unrelated_message():
    assert gen.is_explain_request("찻잔 있나요") is False


def test_is_all_request_tolerates_accidental_space_in_keyword():
    assert gen.is_all_request("전 체 다 보여줘") is True


def test_build_reply_caps_candidates_at_max_displayed_even_with_larger_pool():
    """오케스트레이터가 검색 임베딩의 종목 혼입에 대비해 top_k=9로 넉넉히 받아오므로
    (실측: "선물로 좋은 도자기 찾아줘"가 top_k=3만 받으면 종목 필터 후 1개만 남던
    과소 노출 문제), build_reply가 여기서 다시 최종 3개로 자르지 않으면 9개를
    전부 노출할 수 있다."""
    captured = {}

    def capturing_chat(messages, schema, *, think, model=None):
        captured["user_content"] = messages[1]["content"]
        return json.dumps(
            {"reply": "여러 점을 골랐어요.", "allowed_ids": [], "suggestions": []}
        )

    candidates = [
        {"product_id": i, "name": f"청자 찻잔{i}", "evidence": {}} for i in range(9)
    ]
    gen.build_reply(
        "도자기 찻잔 있나요",
        candidates,
        "product_search",
        chat=capturing_chat,
        **_NO_DB,
    )
    shown_ids = [f"product_id: {i}" in captured["user_content"] for i in range(9)]
    assert sum(shown_ids) == gen._MAX_DISPLAYED_CANDIDATES


def test_purpose_relevance_warning_fires_for_unnamed_activity_word():
    """ "낚시"처럼 가르친 적 없는 활동 단어라도, 종목명이 아니라 용도로 검색된
    product_search면 경고를 붙인다(특정 단어에 하드코딩하지 않은 일반 조건)."""
    candidates = [{"product_id": 1, "name": "쪽염 파우치"}]
    warning = gen._purpose_relevance_warning(
        "낚시할 때 쓰기 좋은 것 3만원대로 있나요", candidates, "product_search"
    )
    assert "시스템 경고" in warning


def test_purpose_relevance_warning_skips_gift_recommendation():
    """ "부모님 선물로 좋은거"는 특정 활동 적합성을 따질 게 없는 gift_recommendation
    이라 경고를 붙이면 정상 선물 추천까지 잘못 거절해버린다(실측 확인) — intent가
    product_search·narrow_down이 아니면 항상 빈 문자열."""
    candidates = [{"product_id": 1, "name": "옻칠 함"}]
    warning = gen._purpose_relevance_warning(
        "부모님 선물로 좋은거 추천해줘", candidates, "gift_recommendation"
    )
    assert warning == ""


def test_purpose_relevance_warning_skips_when_category_named():
    """ "도자기 찻잔 있나요"처럼 종목명이 이미 있으면 검색이 종목으로 걸러졌으니
    경고가 필요 없다."""
    candidates = [{"product_id": 1, "name": "청자 찻잔"}]
    warning = gen._purpose_relevance_warning(
        "도자기 찻잔 있나요", candidates, "product_search"
    )
    assert warning == ""


def test_purpose_relevance_warning_skips_when_no_candidates():
    assert gen._purpose_relevance_warning("낚시용", [], "product_search") == ""


def test_build_reply_skips_purpose_warning_when_no_search_happened():
    """narrow_down이 새 조건 없이 직전 후보를 재사용하는 턴(예: "가격 얼마야?")은
    query_text에 주제어가 안 붙어 종목명이 없는 것처럼 보이는데, 이때 용도 불일치
    경고가 붙으면 정작 물어본 걸(가격 등) 무시하고 후보 재소개만 반복하는 회귀가
    실측 확인됐다 — did_search=False면 경고 자체를 안 붙여야 한다."""
    captured = {}

    def capturing_chat(messages, schema, *, think, model=None):
        captured["user_content"] = messages[1]["content"]
        return json.dumps(
            {
                "reply": "옹기토 술독은 99,000원입니다.",
                "allowed_ids": [130],
                "suggestions": [],
            }
        )

    candidates = [{"product_id": 130, "name": "옹기토 술독", "evidence": {}}]
    gen.build_reply(
        "가격 얼마야?",
        candidates,
        "narrow_down",
        query_text="가격 얼마야?",
        did_search=False,
        chat=capturing_chat,
        **_NO_DB,
    )
    assert "시스템 경고" not in captured["user_content"]


def test_build_reply_keeps_purpose_warning_when_search_happened():
    captured = {}

    def capturing_chat(messages, schema, *, think, model=None):
        captured["user_content"] = messages[1]["content"]
        return json.dumps(
            {"reply": "확인되는 상품이 없어요.", "allowed_ids": [], "suggestions": []}
        )

    candidates = [{"product_id": 130, "name": "옹기토 술독"}]
    gen.build_reply(
        "낚시할 때 쓰기 좋은 것 있나요",
        candidates,
        "product_search",
        query_text="낚시할 때 쓰기 좋은 것 있나요",
        did_search=True,
        chat=capturing_chat,
        **_NO_DB,
    )
    assert "시스템 경고" in captured["user_content"]


def test_format_candidates_includes_category_and_evidence():
    candidates = [
        {
            "product_id": 1,
            "name": "여성용 챙모자",
            "category": "총모자",
            "evidence": {
                "artisan_input": "말총으로 엮었습니다",
                "verified": "MASTER_CRAFTSMAN",
            },
        }
    ]
    text = gen._format_candidates(candidates)
    assert "product_id: 1" in text
    assert "총모자" in text
    # evidence.verified는 DB에 영문 enum으로 저장돼 있어 한국어 라벨로 바꿔 넘긴다
    # (_verified_label) — 원문 그대로 새는지 회귀 확인.
    assert "명장" in text
    assert "MASTER_CRAFTSMAN" not in text
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
    text = gen._format_candidates(
        candidates, artisans={1: {"business_name": "정예준 도예", "region": "부산"}}
    )
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
    assert gen._drop_unknown_ids([1, 999], {1}) == [1]


def test_drop_unknown_ids_empty_allowed_drops_all():
    assert gen._drop_unknown_ids([1], set()) == []


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


def _no_attrs(product_ids: list[int]) -> dict[int, dict]:
    """_no_prices와 같은 이유의 가짜 fetch_attrs."""
    return {}


# build_reply 호출마다 반복되는 DB 회피용 키워드 인자 묶음 — **_NO_DB로 한 번에 넘긴다.
_NO_DB = {
    "fetch_prices": _no_prices,
    "fetch_artisans": _no_artisans,
    "fetch_attrs": _no_attrs,
}


def test_build_reply_b13_empty_candidates_yields_empty_products():
    # "이 함, 국가 인증서도 따로 받은 거 맞죠?" 시나리오 — evidence(주칠 함, 국가무형유산
    # 등급)엔 "인증서" 언급이 없어 그 사실 하나는 미확인이지만, 상품 자체는 유지돼야
    # 한다(규칙2+5). 여기서는 fake_chat이 이미 "확인 안 됨" 판단을 내린 응답만 검증하므로
    # product_ids가 빈 배열로 나오는 경로만 본다.
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
        "allowed_ids": [],
        "suggestions": ["가격대 올려서", "다른 재질로", "다른 종목으로"],
    }
    result = gen.build_reply(
        "이 함, 국가 인증서도 따로 받은 거 맞죠?",
        candidates,
        "product_search",
        chat=_fake_chat(payload),
        **_NO_DB,
    )
    assert result["product_ids"] == []


def test_build_reply_drops_id_not_in_candidates():
    candidates = [{"product_id": 1, "name": "T", "category": "C", "evidence": {}}]
    payload = {
        "reply": "추천합니다.",
        "allowed_ids": [1, 999],
        "suggestions": ["다른 색상으로"],
    }
    result = gen.build_reply(
        "아무거나", candidates, "product_search", chat=_fake_chat(payload), **_NO_DB
    )
    assert result["product_ids"] == [1]


def test_build_reply_calls_chat_with_think_false_by_default():
    """think 기본값은 False다 — thinking을 지원하는 모델(qwen3·gemma4)이 실제로 쓰이지
    않는 한, thinking을 켤 이유가 없다(gemma4는 오히려 응답이 8배 느려지고 타임아웃까지
    난 것을 실측 확인했다)."""
    seen = {}

    def fake(messages, schema, *, think, model=None):
        seen["think"] = think
        return json.dumps({"reply": "ok", "allowed_ids": [], "suggestions": []})

    gen.build_reply("메시지", [], "general_chat", chat=fake, **_NO_DB)
    assert seen["think"] is False


def test_build_reply_filters_mismatched_category_by_name():
    # 종목 대조 방어: candidate에 category 필드가 없어도 name(청자 다완→POTTERY)에서
    # 역추정해, 사용자가 말한 종목(옹기)과 다르면 걸러낸다. LLM이 그래도 추천해도
    # allowed_ids에서 이미 빠져 있어 _drop_unknown_ids가 제거한다.
    candidates = [{"product_id": 1, "name": "청자 다완", "evidence": {}}]
    payload = {
        "reply": "추천합니다.",
        "allowed_ids": [1],
        "suggestions": [],
    }
    result = gen.build_reply(
        "옹기 있나요", candidates, "product_search", chat=_fake_chat(payload), **_NO_DB
    )
    assert result["product_ids"] == []


# ---------------------------------------------------------------------------
# _format_filters / suggestions
# ---------------------------------------------------------------------------


def test_format_filters_none_returns_placeholder():
    assert gen._format_filters(None) == "(추출된 조건 없음)"


def test_format_filters_empty_dict_returns_placeholder():
    assert gen._format_filters(
        {"max_price": None, "min_price": None, "gift_theme": None, "color": None}
    ) == ("(추출된 조건 없음)")


def test_format_filters_includes_price_and_theme():
    filters = {
        "max_price": 50000,
        "min_price": None,
        "gift_theme": ["WEDDING"],
        "color": None,
    }
    text = gen._format_filters(filters)
    assert "50000원 이하" in text
    assert "WEDDING" in text


def test_cap_suggestions_truncates_to_three():
    suggestions = [
        "3만 원 아래로",
        "다른 색상으로",
        "다른 재질로",
        "포장까지 되는 것만",
    ]
    assert gen._cap_suggestions(suggestions) == suggestions[:3]


def test_cap_suggestions_drops_full_sentences_outside_word_range():
    """LLM이 규칙을 어기고 완전한 문장이나 한 단어를 반환하면 칩 형식(2~4어절)이 아니므로 뺀다."""
    suggestions = ["네", "혹시 3만 원 아래로 검색해서 보여드릴까요?", "다른 색상으로"]
    assert gen._cap_suggestions(suggestions) == ["다른 색상으로"]


def test_build_reply_returns_suggestions_from_chat():
    payload = {
        "reply": "추천합니다.",
        "allowed_ids": [],
        "suggestions": ["가격대 낮춰서", "다른 색상으로", "다른 종목으로"],
    }
    result = gen.build_reply(
        "아무거나", [], "product_search", chat=_fake_chat(payload), **_NO_DB
    )
    assert result["suggestions"] == payload["suggestions"]


def test_build_reply_truncates_history_to_recent_turns():
    """최근 3턴(6개 메시지)만 남기고 그 이전은 잘라야 한다(_MAX_HISTORY_TURNS)."""
    seen = {}
    payload = {"reply": "ok", "allowed_ids": [], "suggestions": []}

    def fake(messages, schema, *, think, model=None):
        seen["user_content"] = messages[-1]["content"]
        return json.dumps(payload)

    history = [{"role": "user", "content": f"{i}번째 메시지"} for i in range(10)]
    gen.build_reply(
        "최근 질문", [], "product_search", history=history, chat=fake, **_NO_DB
    )

    assert "0번째 메시지" not in seen["user_content"]
    assert "9번째 메시지" in seen["user_content"]


# ---------------------------------------------------------------------------
# is_all_request / explain_products — "모두 설명해줘"류 일괄 선택 처리
# ---------------------------------------------------------------------------


def test_is_all_request_recognizes_batch_words():
    assert gen.is_all_request("모두 설명해줘")
    assert gen.is_all_request("전체 다 알려줘")
    assert gen.is_all_request("둘 다 궁금해요")


def test_is_all_request_false_for_single_ordinal():
    assert not gen.is_all_request("첫번째 설명해줘")
    assert not gen.is_all_request("1번 알려줘")


# ---------------------------------------------------------------------------
# extract_price_superlative — "가장 저렴한 것"류 가격 최상급 표현 판단
# ---------------------------------------------------------------------------


def test_extract_price_superlative_recognizes_cheapest():
    assert gen.extract_price_superlative("그중 가장 저렴한 것") == "min"
    assert gen.extract_price_superlative("제일 싼 거 설명해줘") == "min"


def test_extract_price_superlative_recognizes_most_expensive():
    assert gen.extract_price_superlative("가장 비싼 것 알려줘") == "max"
    assert gen.extract_price_superlative("최고가 상품") == "max"


def test_extract_price_superlative_none_for_ordinal_or_unrelated():
    assert gen.extract_price_superlative("1번 설명해줘") is None
    assert gen.extract_price_superlative("무슨 색이야?") is None


# ---------------------------------------------------------------------------
# extract_price_rank — "두번째로 저렴한 것"류 순번+가격 최상급 결합 표현 판단
# ---------------------------------------------------------------------------


def test_extract_price_rank_recognizes_ordinal_plus_direction():
    """ "가장"·"제일" 없이 "저렴"·"비싼"만 있어도 순번과 결합되면 뽑혀야 한다 —
    extract_price_superlative는 "가장"·"제일"을 요구해서 이 문장들은 못 잡는다."""
    assert gen.extract_price_rank("두번째로 저렴한 것 설명해줘", 3) == (2, "min")
    assert gen.extract_price_rank("2번째로 비싼 것 알려줘", 3) == (2, "max")
    assert gen.extract_price_rank("세번째로 싼 거 자세히 봐줘", 3) == (3, "min")


def test_extract_price_rank_none_without_ordinal_or_without_direction():
    """순번만 있고 가격 방향이 없으면(일반 순번 질문), 방향만 있고 순번이 없으면
    (예: "가장 비싼 것" — extract_price_superlative가 따로 처리) None이어야 한다."""
    assert gen.extract_price_rank("두번째 상품 설명해줘", 3) is None
    assert gen.extract_price_rank("가장 비싼 것 알려줘", 3) is None


def test_explain_products_calls_llm_once_and_shares_reply_across_products():
    """explain_product를 후보 수만큼 반복 호출하면 응답 시간이 배로 늘어난다 —
    explain_products는 LLM을 정확히 1번만 불러야 한다."""
    calls = {"n": 0}

    def fake(messages, schema, *, think, model=None):
        calls["n"] += 1
        return json.dumps(
            {
                "reply": "두 상품 모두 장인이 직접 만든 작품입니다.",
                "suggestions": ["다른 색상으로", "포장 여부 확인"],
            }
        )

    candidates = [
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
    ]
    result = gen.explain_products(
        "모두 설명해줘", candidates, chat=fake, fetch_attrs=_no_attrs
    )

    assert calls["n"] == 1
    assert result["product_ids"] == [1, 2]
    assert result["reply"] == "두 상품 모두 장인이 직접 만든 작품입니다."
    assert result["suggestions"] == ["다른 색상으로", "포장 여부 확인"]


def test_format_explain_block_includes_material_and_color():
    """실측 확인: explain_product·explain_products엔 재질·색상이 없어서 "무슨
    색이야?"류 질문에 실제 DB와 다른 색을 지어내 답한 사례가 있었다(build_reply와
    같은 사고) — 재발 방지."""
    candidate = {"product_id": 1, "name": "옹기토 장독", "evidence": {}}
    block = gen._format_explain_block(
        candidate, {"material": "옹기토", "color": "BROWN"}
    )
    assert "재질: 옹기토" in block
    assert "색상: 갈색" in block


def test_format_explain_block_shows_no_info_when_attr_missing():
    candidate = {"product_id": 1, "name": "T", "evidence": {}}
    block = gen._format_explain_block(candidate)
    assert "재질: 정보 없음" in block
    assert "색상: 정보 없음" in block


def test_explain_products_includes_history_for_purpose_context(monkeypatch):
    """실측 확인된 문제: "셰프 친구 개업 축하 선물로 15만원 이하 찾아줘" 다음
    "이유가 뭐야?"에 explain_products가 evidence만 기계적으로 나열하고 "개업 축하"라는
    원래 맥락을 전혀 반영하지 않았다 — history를 아예 안 받고 있어서 LLM이 그 맥락
    자체를 볼 수 없었던 게 원인이다. history를 받으면 user_content에 그 맥락이
    포함돼야 한다."""
    captured = {}

    def fake_chat(messages, schema, *, think, model=None):
        captured["user_content"] = messages[1]["content"]
        return json.dumps({"reply": "설명입니다.", "suggestions": []})

    candidates = [{"product_id": 1, "name": "치자염 방석", "evidence": {}}]
    history = [
        {"role": "user", "content": "셰프 친구 개업 선물로 15만원 이하 찾아줘"},
        {"role": "assistant", "content": "15만 원 이하로 3점을 골랐어요."},
    ]
    gen.explain_products(
        "이 제품들을 추천한 이유는 뭐야?",
        candidates,
        chat=fake_chat,
        fetch_attrs=_no_attrs,
        history=history,
    )
    assert "개업" in captured["user_content"]


def test_explain_product_includes_history_for_purpose_context():
    """explain_products와 같은 이유로 explain_product(단일 상품)도 history를 받아야 한다."""
    captured = {}

    def fake_chat(messages, schema, *, think, model=None):
        captured["user_content"] = messages[1]["content"]
        return json.dumps({"reply": "설명입니다.", "suggestions": []})

    candidate = {"product_id": 1, "name": "치자염 방석", "evidence": {}}
    history = [
        {"role": "user", "content": "셰프 친구 개업 선물로 15만원 이하 찾아줘"},
        {"role": "assistant", "content": "15만 원 이하로 3점을 골랐어요."},
    ]
    gen.explain_product(
        "이거 설명해줘",
        candidate,
        chat=fake_chat,
        fetch_attrs=_no_attrs,
        history=history,
    )
    assert "개업" in captured["user_content"]


def test_explain_product_fetches_attrs_by_product_id(monkeypatch):
    captured = {}

    def fake_chat(messages, schema, *, think, model=None):
        captured["prompt"] = messages[0]["content"]
        return json.dumps({"reply": "갈색 옹기예요.", "suggestions": []})

    def fake_fetch_attrs(product_ids):
        assert product_ids == [1]
        return {1: {"material": "옹기토", "color": "BROWN"}}

    candidate = {"product_id": 1, "name": "옹기토 장독", "evidence": {}}
    gen.explain_product(
        "무슨 색이야?", candidate, chat=fake_chat, fetch_attrs=fake_fetch_attrs
    )
    assert "색상: 갈색" in captured["prompt"]
