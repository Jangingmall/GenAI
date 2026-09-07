"""generate.py 단위 테스트. 순수 함수는 LLM 없이, build_reply는 fake_chat 주입.

이 브랜치엔 eval/ 스위트(실LLM 스모크·안전성 회귀 평가)가 없어 전부 인라인 데이터로만
검증한다. eval/ 기반의 더 넓은 회귀 테스트는 feat/b-pipeline에 별도로 있다.

실행: python -m pytest tests/test_generate.py -q
"""

import json

from app.pipeline import generate as gen


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


def test_format_candidates_omits_price():
    # 접점 2(§0)엔 price가 없다 — 프로토타입과 달리 가격 줄을 만들지 않는다
    candidates = [{"product_id": 1, "name": "T", "category": "C", "evidence": {}}]
    assert "가격" not in gen._format_candidates(candidates)


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


def test_build_reply_empty_candidates_yields_empty_products():
    payload = {
        "reply": "그런 조건에 맞는 상품은 확인되지 않습니다.",
        "products": [],
        "suggestions": ["가격대 올려서", "다른 재질로", "다른 종목으로"],
    }
    result = gen.build_reply("존재하지 않는 조합", [], "product_search", chat=_fake_chat(payload))
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
    result = gen.build_reply("아무거나", candidates, "product_search", chat=_fake_chat(payload))
    assert result["products"] == [{"product_id": 1, "reason": "좋아요"}]


def test_build_reply_calls_chat_with_think_true():
    seen = {}

    def fake(messages, schema, *, think, model=None):
        seen["think"] = think
        return json.dumps({"reply": "ok", "products": [], "suggestions": []})

    gen.build_reply("메시지", [], "general_chat", chat=fake)
    assert seen["think"] is True


def test_build_reply_filters_mismatched_category_by_name():
    # 종목 대조 방어: candidate에 category 필드가 없어도 name(청자 다완→POTTERY)에서
    # 역추정해, 사용자가 말한 종목(옹기)과 다르면 걸러낸다. LLM이 그래도 추천해도
    # allowed_ids에서 이미 빠져 있어 _drop_unknown_ids가 제거한다.
    candidates = [{"product_id": 1, "name": "청자 다완", "evidence": {}}]
    payload = {"reply": "추천합니다.", "products": [{"product_id": 1, "reason": "..."}], "suggestions": []}
    result = gen.build_reply("옹기 있나요", candidates, "product_search", chat=_fake_chat(payload))
    assert result["products"] == []


# ---------------------------------------------------------------------------
# _format_filters / suggestions
# ---------------------------------------------------------------------------


def test_format_filters_none_returns_placeholder():
    assert gen._format_filters(None) == "(추출된 조건 없음)"


def test_format_filters_includes_price_and_theme():
    filters = {"max_price": 50000, "min_price": None, "gift_theme": ["WEDDING"], "color": None}
    text = gen._format_filters(filters)
    assert "50000원 이하" in text
    assert "WEDDING" in text


def test_cap_suggestions_truncates_to_three():
    assert gen._cap_suggestions(["a", "b", "c", "d"]) == ["a", "b", "c"]


def test_build_reply_returns_suggestions_from_chat():
    payload = {
        "reply": "추천합니다.",
        "products": [],
        "suggestions": ["가격대 낮춰서", "다른 색상으로", "다른 종목으로"],
    }
    result = gen.build_reply("아무거나", [], "product_search", chat=_fake_chat(payload))
    assert result["suggestions"] == payload["suggestions"]
