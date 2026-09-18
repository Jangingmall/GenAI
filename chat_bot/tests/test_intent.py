"""intent.py 단위 테스트. 순수 함수는 LLM 없이, classify_and_extract는 fake_chat 주입.

이 브랜치엔 eval/ 스위트가 없어 실LLM 검증은 인라인 메시지로만 한다(gift_theme 환각
회귀 재현이 대표적).

실행: python -m pytest tests/test_intent.py -q
"""

import json

import pytest

from app.pipeline import intent as it
from app.pipeline import prompts

# ---------------------------------------------------------------------------
# _price_to_won
# ---------------------------------------------------------------------------


def test_price_to_won_parses_man_unit():
    assert it._price_to_won("5만원") == 50000


def test_price_to_won_parses_man_dae():
    assert it._price_to_won("3만원대") == 30000


def test_price_to_won_parses_cheon_unit():
    """실측 확인된 버그: "천" 단위 처리가 없어서 "5천원"이 5원으로 파싱됐다
    ("만"만 처리하고 나머지는 맨 숫자만 뽑는 폴백으로 떨어졌기 때문)."""
    assert it._price_to_won("5천원") == 5000
    assert it._price_to_won("5천원대") == 5000


def test_price_to_won_parses_eok_unit():
    assert it._price_to_won("1억원") == 100000000


def test_price_to_won_parses_cheonman_compound_unit():
    """실측 확인된 버그: "천만"처럼 만 단위 앞에 "천"이 붙는 복합 단위는 "만" 바로
    앞에 숫자가 없어서(그 자리엔 "천"이 있음) "만" 매칭이 실패하고 "천" 매칭으로
    떨어져 1000배 작게 파싱됐다("1천만원" → 1000원). "3백만원"도 같은 이유로
    "만" 앞이 "백"이라 매칭이 아예 안 되고 맨 숫자 폴백(3)까지 떨어졌다."""
    assert it._price_to_won("1천만원") == 10000000
    assert it._price_to_won("3백만원") == 3000000


def test_price_to_won_empty_is_none():
    assert it._price_to_won("") is None


def test_price_to_won_none_is_none():
    assert it._price_to_won(None) is None


def test_price_to_won_passthrough_int():
    assert it._price_to_won(300000) == 300000


def test_price_to_won_plain_digit_string():
    assert it._price_to_won("50000") == 50000


# ---------------------------------------------------------------------------
# _to_contact1의 query_text 덮어쓰기 — product_search·gift_recommendation은
# LLM이 뭘 뽑든 원문(message)으로 코드에서 확정한다(검색팀 실측: 축약·수식어
# 제거 없이 원문 그대로 넘길 때 임베딩 검색이 가장 잘 됨 — 프롬프트 판단에
# 맡기지 않고 코드로 보장).
# ---------------------------------------------------------------------------


def test_to_contact1_overrides_query_text_with_raw_message_for_product_search():
    raw = {"intent": "product_search", "query_text": "혼수용 반상기"}
    result = it._to_contact1(
        raw,
        gift_themes=prompts.GIFT_THEMES,
        colors=prompts.COLORS,
        message="혼수용으로 쓸 만한 반상기 보여줘",
    )
    assert result["query_text"] == "혼수용으로 쓸 만한 반상기 보여줘"


def test_to_contact1_overrides_query_text_with_raw_message_for_gift_recommendation():
    raw = {"intent": "gift_recommendation", "query_text": "환갑 선물"}
    result = it._to_contact1(
        raw,
        gift_themes=prompts.GIFT_THEMES,
        colors=prompts.COLORS,
        message="환갑 맞은 부모님께 드릴 선물 찾아줘",
    )
    assert result["query_text"] == "환갑 맞은 부모님께 드릴 선물 찾아줘"


def test_to_contact1_skips_query_text_override_for_narrow_down():
    """narrow_down은 이전 대화 주제어를 이어 붙이는 별도 로직이 LLM에 있어
    여기서 원문으로 덮어쓰면 그 맥락이 깨진다 — LLM이 뽑은 값을 그대로 둔다."""
    raw = {"intent": "narrow_down", "query_text": "3만원으로 낮춰서 도자기"}
    result = it._to_contact1(
        raw,
        gift_themes=prompts.GIFT_THEMES,
        colors=prompts.COLORS,
        message="그럼 3만원으로 낮춰서 좋은 것도 있어요?",
    )
    assert result["query_text"] == "3만원으로 낮춰서 도자기"


# ---------------------------------------------------------------------------
# _keep_known
# ---------------------------------------------------------------------------


def test_keep_known_filters_hallucinated_values():
    assert it._keep_known(["BIRTHDAY_60TH", "made_up"], prompts.GIFT_THEMES) == [
        "BIRTHDAY_60TH"
    ]


def test_keep_known_empty_list():
    assert it._keep_known([], prompts.GIFT_THEMES) == []


def test_keep_known_none_input():
    assert it._keep_known(None, prompts.GIFT_THEMES) == []


def test_keep_known_all_known():
    assert it._keep_known(["WHITE", "BLACK"], prompts.COLORS) == ["WHITE", "BLACK"]


# ---------------------------------------------------------------------------
# _to_contact1
# ---------------------------------------------------------------------------


def test_to_contact1_assembles_filters():
    raw = {
        "intent": "gift_recommendation",
        "max_price": 300000,
        "min_price": None,
        "gift_theme": ["BIRTHDAY_60TH"],
        "color": [],
        "query_text": "환갑 선물",
    }
    result = it._to_contact1(
        raw,
        gift_themes=prompts.GIFT_THEMES,
        colors=prompts.COLORS,
        message="환갑 맞은 부모님께 드릴 선물 찾아줘",
    )
    assert result == {
        "query_text": "환갑 맞은 부모님께 드릴 선물 찾아줘",
        "wants_reason": False,
        "needs_clarification": False,
        "wants_alternatives": False,
        "filters": {
            "max_price": 300000,
            "min_price": None,
            "gift_theme": ["BIRTHDAY_60TH"],
            "color": None,
        },
        "intent": "gift_recommendation",
        "chat_reply": "",
    }


def test_to_contact1_corrects_llm_putting_lower_bound_into_max_price():
    """ "100만원 이상"처럼 하한 표현인데 LLM이 습관적으로 max_price에 넣는 경우
    (실측 확인: 전용 예시를 추가해도 재현됨) 메시지의 실제 방향에 맞게 min_price로
    옮긴다."""
    raw = {
        "intent": "product_search",
        "max_price": 1000000,
        "min_price": None,
        "gift_theme": [],
        "color": [],
        "query_text": "금속공예 100만원 이상 찾아줘",
    }
    result = it._to_contact1(
        raw,
        gift_themes=prompts.GIFT_THEMES,
        colors=prompts.COLORS,
        message="금속공예 100만원 이상 찾아줘",
    )
    assert result["filters"]["max_price"] is None
    assert result["filters"]["min_price"] == 1000000


def test_to_contact1_corrects_llm_putting_upper_bound_into_min_price_for_andoeneun():
    """팀원 공유 실사용 리포트: "5만원 안 되는 선물"(상한 표현)이 min_price로
    뒤집혀 나왔다 — "안 되는"이 방향 판단 키워드 목록에 없어서 코드 보정 자체가
    아예 안 걸렸던 게 원인이었다. "안 되는"·"안되는" 둘 다 커버해야 한다."""
    for phrase, message in [
        (
            "5만원 안 되는 선물 찾아줘",
            "5만원 안 되는 선물 찾아줘",
        ),
        (
            "5만원 안되는 선물 찾아줘",
            "5만원 안되는 선물 찾아줘",
        ),
    ]:
        raw = {
            "intent": "gift_recommendation",
            "max_price": None,
            "min_price": 50000,
            "gift_theme": [],
            "color": [],
            "query_text": phrase,
        }
        result = it._to_contact1(
            raw,
            gift_themes=prompts.GIFT_THEMES,
            colors=prompts.COLORS,
            message=message,
        )
        assert result["filters"]["max_price"] == 50000
        assert result["filters"]["min_price"] is None


def test_to_contact1_corrects_llm_putting_upper_bound_into_min_price_for_an_neomneun():
    """사용자 공유 실사용 리포트: "5만원 안 넘는 것"(상한 표현)이 min_price로
    뒤집혀 나왔다 — "안 넘는"이 부정어라 상한을 뜻하는데, _MIN_PRICE_WORDS의
    "넘는"이 그 안에 부분 문자열로 그대로 들어있어 min으로 잘못 판정됐던 게 원인
    (안 되는/안되는과 같은 부정 패턴). "안 넘는"·"안넘는" 둘 다 커버해야 한다."""
    for phrase in ("5만원 안 넘는 것 추천해줘", "5만원 안넘는 것 추천해줘"):
        raw = {
            "intent": "gift_recommendation",
            "max_price": None,
            "min_price": 50000,
            "gift_theme": [],
            "color": [],
            "query_text": phrase,
        }
        result = it._to_contact1(
            raw,
            gift_themes=prompts.GIFT_THEMES,
            colors=prompts.COLORS,
            message=phrase,
        )
        assert result["filters"]["max_price"] == 50000
        assert result["filters"]["min_price"] is None


def test_price_direction_still_treats_plain_neomneun_as_lower_bound():
    """부정어 처리를 추가해도 "넘는"(부정어 없음)은 그대로 하한(min)으로 남아야
    한다 — "안 넘는" 관련 부분만 지우고 판정하므로 일반 넘는 표현은 영향 없다."""
    assert it._price_direction("5만원 넘는 것 추천해줘") == "min"


def test_to_contact1_keeps_max_price_when_message_says_upper_bound():
    raw = {
        "intent": "product_search",
        "max_price": 30000,
        "min_price": None,
        "gift_theme": [],
        "color": [],
        "query_text": "도자기 3만원 이하로",
    }
    result = it._to_contact1(
        raw,
        gift_themes=prompts.GIFT_THEMES,
        colors=prompts.COLORS,
        message="도자기 3만원 이하로",
    )
    assert result["filters"]["max_price"] == 30000
    assert result["filters"]["min_price"] is None


def test_to_contact1_resolves_dae_suffix_into_decade_range():
    """사용자 지적: "5만원대"는 "50,000원 이하"가 아니라 "50,000~59,999원 사이"를
    뜻한다. 실측 확인: 기존엔 그냥 숫자 50000 하나로만 취급돼 51,000~59,999원
    사이 실제 상품(DB 확인 17건)이 전부 검색에서 빠졌다. LLM이 이미 max_price에
    50000을 넣었어도 "-대" 구간으로 덮어써야 한다."""
    raw = {
        "intent": "product_search",
        "max_price": 50000,
        "min_price": None,
        "gift_theme": [],
        "color": [],
        "query_text": "5만원대 도자기 추천해줘",
    }
    result = it._to_contact1(
        raw,
        gift_themes=prompts.GIFT_THEMES,
        colors=prompts.COLORS,
        message="5만원대 도자기 추천해줘",
    )
    assert result["filters"]["min_price"] == 50000
    assert result["filters"]["max_price"] == 59999


def test_to_contact1_dae_suffix_works_for_cheon_unit():
    raw = {
        "intent": "product_search",
        "max_price": None,
        "min_price": None,
        "gift_theme": [],
        "color": [],
        "query_text": "3천원대 소품 있어요",
    }
    result = it._to_contact1(
        raw,
        gift_themes=prompts.GIFT_THEMES,
        colors=prompts.COLORS,
        message="3천원대 소품 있어요",
    )
    assert result["filters"]["min_price"] == 3000
    assert result["filters"]["max_price"] == 3999


def test_to_contact1_dae_suffix_widens_with_two_digit_coefficient():
    """ "50만원대"는 "20대"(나이 20~29)와 같은 원리로, 계수("50")의 마지막 자리가
    변하는 것으로 본다 — 500,000~509,999(1만원 폭)가 아니라 500,000~599,999
    (10만원 폭)여야 한다. 한 자리 계수("3만원대"→3만원 폭 1만원)와 자릿수만
    다를 뿐 같은 규칙이다."""
    raw = {
        "intent": "product_search",
        "max_price": None,
        "min_price": None,
        "gift_theme": [],
        "color": [],
        "query_text": "50만원대 도자기 추천해줘",
    }
    result = it._to_contact1(
        raw,
        gift_themes=prompts.GIFT_THEMES,
        colors=prompts.COLORS,
        message="50만원대 도자기 추천해줘",
    )
    assert result["filters"]["min_price"] == 500000
    assert result["filters"]["max_price"] == 599999


def test_to_contact1_dae_suffix_widens_with_three_digit_coefficient():
    raw = {
        "intent": "product_search",
        "max_price": None,
        "min_price": None,
        "gift_theme": [],
        "color": [],
        "query_text": "120만원대 가구 있어요",
    }
    result = it._to_contact1(
        raw,
        gift_themes=prompts.GIFT_THEMES,
        colors=prompts.COLORS,
        message="120만원대 가구 있어요",
    )
    assert result["filters"]["min_price"] == 1200000
    assert result["filters"]["max_price"] == 1299999


def test_price_direction_range_question_not_overridden_by_dae_logic():
    """ "3만원 이상 5만원 이하"처럼 이미 명확한 이상·이하 범위 질문은 "-대" 보정
    대상이 아니다(direction이 None이 아니라서 애초에 안 걸림) — 기존 동작 유지."""
    raw = {
        "intent": "product_search",
        "max_price": 50000,
        "min_price": 30000,
        "gift_theme": [],
        "color": [],
        "query_text": "도자기 3만원 이상 5만원 이하로",
    }
    result = it._to_contact1(
        raw,
        gift_themes=prompts.GIFT_THEMES,
        colors=prompts.COLORS,
        message="도자기 3만원 이상 5만원 이하로",
    )
    assert result["filters"]["min_price"] == 30000
    assert result["filters"]["max_price"] == 50000


def test_to_contact1_leaves_price_untouched_when_message_has_no_direction_word():
    """ "5만원으로"처럼 방향 표현이 아예 없으면 코드가 함부로 방향을 정하지 않고
    LLM 추출을 그대로 둔다."""
    raw = {
        "intent": "narrow_down",
        "max_price": 50000,
        "min_price": None,
        "gift_theme": [],
        "color": [],
        "query_text": "도자기 그럼 5만원으로 다시",
    }
    result = it._to_contact1(
        raw,
        gift_themes=prompts.GIFT_THEMES,
        colors=prompts.COLORS,
        message="그럼 5만원으로 다시",
    )
    assert result["filters"]["max_price"] == 50000
    assert result["filters"]["min_price"] is None


def test_to_contact1_leaves_price_untouched_when_both_directions_mentioned():
    """ "3만원 이상 5만원 이하"처럼 범위 질문은 어느 숫자가 어느 쪽인지 코드로
    안전하게 갈라낼 근거가 없어 LLM 추출을 그대로 둔다."""
    raw = {
        "intent": "product_search",
        "max_price": 50000,
        "min_price": 30000,
        "gift_theme": [],
        "color": [],
        "query_text": "도자기 3만원 이상 5만원 이하로",
    }
    result = it._to_contact1(
        raw,
        gift_themes=prompts.GIFT_THEMES,
        colors=prompts.COLORS,
        message="도자기 3만원 이상 5만원 이하로",
    )
    assert result["filters"]["max_price"] == 50000
    assert result["filters"]["min_price"] == 30000


def test_to_contact1_passes_through_chat_reply():
    """chat_reply는 general_chat일 때 orchestrator가 generate.py 호출 없이 바로 쓰는
    필드다 — _to_contact1이 그대로 넘겨야 한다."""
    raw = {
        "intent": "general_chat",
        "query_text": "",
        "chat_reply": "안녕하세요! 무엇을 도와드릴까요?",
    }
    result = it._to_contact1(
        raw,
        gift_themes=prompts.GIFT_THEMES,
        colors=prompts.COLORS,
        message="안녕하세요",
    )
    assert result["chat_reply"] == "안녕하세요! 무엇을 도와드릴까요?"


def test_to_contact1_missing_chat_reply_defaults_empty():
    raw = {"intent": "product_search", "query_text": "찻잔"}
    result = it._to_contact1(
        raw, gift_themes=prompts.GIFT_THEMES, colors=prompts.COLORS, message="찻잔"
    )
    assert result["chat_reply"] == ""


def test_to_contact1_general_chat_with_blank_chat_reply_falls_back_to_generic_reply():
    """실측 확인된 버그: 대화 히스토리가 있는 상태에서 "고마워요"류 짧은 인사에
    LLM이 intent는 general_chat으로 맞게 분류하면서도 chat_reply를 빈 문자열로
    돌려주는 경우가 100% 재현됐다 — _RawIntent.chat_reply에 min_length 제약이
    없어(query_text와 같은 문제) 스키마상 빈 문자열도 "정답"으로 통과된다.
    orchestrator.py는 general_chat일 때 이 chat_reply를 그대로 사용자에게
    보여주므로, 비어 있으면 빈 말풍선이 그대로 나간다 — 안전한 기본 문구로
    대체해야 한다."""
    raw = {
        "intent": "general_chat",
        "query_text": "",
        "chat_reply": "",
    }
    result = it._to_contact1(
        raw, gift_themes=prompts.GIFT_THEMES, colors=prompts.COLORS, message="고마워요"
    )
    assert result["chat_reply"] != ""


def test_to_contact1_needs_clarification_with_blank_chat_reply_falls_back_to_generic_reply():
    """needs_clarification=true일 때도 chat_reply가 그대로 사용자에게 나가므로
    (orchestrator.py의 되묻기 분기) 같은 방어가 필요하다."""
    raw = {
        "intent": "product_search",
        "query_text": "",
        "needs_clarification": True,
        "chat_reply": "",
    }
    result = it._to_contact1(
        raw, gift_themes=prompts.GIFT_THEMES, colors=prompts.COLORS, message="선물"
    )
    assert result["chat_reply"] != ""


def test_to_contact1_unknown_intent_becomes_general_chat():
    raw = {"intent": "made_up_intent", "query_text": "아무말"}
    result = it._to_contact1(
        raw, gift_themes=prompts.GIFT_THEMES, colors=prompts.COLORS, message="아무말"
    )
    assert result["intent"] == "general_chat"


def test_to_contact1_drops_hallucinated_gift_theme():
    raw = {
        "intent": "gift_recommendation",
        "gift_theme": ["NOT_A_REAL_THEME"],
        "query_text": "",
    }
    result = it._to_contact1(
        raw, gift_themes=prompts.GIFT_THEMES, colors=prompts.COLORS, message="선물 추천"
    )
    assert result["filters"]["gift_theme"] is None


def test_to_contact1_missing_query_text_defaults_empty():
    raw = {"intent": "general_chat"}
    result = it._to_contact1(
        raw, gift_themes=prompts.GIFT_THEMES, colors=prompts.COLORS, message="안녕"
    )
    assert result["query_text"] == ""


def test_to_contact1_passes_through_wants_reason_true():
    """ "왜 추천했어?"류 이유 질문 판단은 LLM이 하고, _to_contact1은 그 신호를
    그대로 넘기기만 한다."""
    raw = {"intent": "narrow_down", "wants_reason": True, "query_text": "추천 이유"}
    result = it._to_contact1(
        raw,
        gift_themes=prompts.GIFT_THEMES,
        colors=prompts.COLORS,
        message="왜 이 상품들을 추천한거야?",
    )
    assert result["wants_reason"] is True


def test_to_contact1_missing_wants_reason_defaults_false():
    raw = {"intent": "product_search", "query_text": "찻잔"}
    result = it._to_contact1(
        raw, gift_themes=prompts.GIFT_THEMES, colors=prompts.COLORS, message="찻잔"
    )
    assert result["wants_reason"] is False


def test_to_contact1_passes_through_needs_clarification_true():
    """ "선물"처럼 검색 단서가 하나도 없는 문장인지 판단은 LLM이 하고, _to_contact1은
    그 신호를 그대로 넘기기만 한다(사용자 시나리오 E23 대응)."""
    raw = {
        "intent": "gift_recommendation",
        "needs_clarification": True,
        "query_text": "선물",
        "chat_reply": "어떤 분께 드릴 선물인가요?",
    }
    result = it._to_contact1(
        raw, gift_themes=prompts.GIFT_THEMES, colors=prompts.COLORS, message="선물"
    )
    assert result["needs_clarification"] is True


def test_to_contact1_missing_needs_clarification_defaults_false():
    raw = {"intent": "product_search", "query_text": "찻잔"}
    result = it._to_contact1(
        raw, gift_themes=prompts.GIFT_THEMES, colors=prompts.COLORS, message="찻잔"
    )
    assert result["needs_clarification"] is False


def test_to_contact1_passes_through_wants_alternatives_true():
    """ "다른 거 추천해줘"처럼 새 조건 없이 그냥 다른 상품을 원하는지 판단은 LLM이
    하고, _to_contact1은 그 신호를 그대로 넘기기만 한다."""
    raw = {
        "intent": "narrow_down",
        "wants_alternatives": True,
        "query_text": "도자기 찻잔",
    }
    result = it._to_contact1(
        raw,
        gift_themes=prompts.GIFT_THEMES,
        colors=prompts.COLORS,
        message="다른 거 추천해줘",
    )
    assert result["wants_alternatives"] is True


def test_to_contact1_missing_wants_alternatives_defaults_false():
    raw = {"intent": "product_search", "query_text": "찻잔"}
    result = it._to_contact1(
        raw, gift_themes=prompts.GIFT_THEMES, colors=prompts.COLORS, message="찻잔"
    )
    assert result["wants_alternatives"] is False


# ---------------------------------------------------------------------------
# classify_and_extract — chat 주입, LLM 없음
# ---------------------------------------------------------------------------


def _fake_chat(payload: dict):
    def fake(messages, schema, *, think, model=None):
        return json.dumps(payload)

    return fake


def test_classify_and_extract_parses_injected_response():
    payload = {
        "intent": "gift_recommendation",
        "max_price": 300000,
        "min_price": None,
        "gift_theme": ["BIRTHDAY_60TH"],
        "color": [],
        "query_text": "환갑 선물",
    }
    result = it.classify_and_extract(
        "어머니 환갑 선물로 30만원대 찾아요", chat=_fake_chat(payload)
    )
    assert result["intent"] == "gift_recommendation"
    # "30만원대"는 "-대" 구간 보정이 300000~399999로 확정한다(아래 별도 테스트
    # 참고 — "20대"=20~29와 같은 원리로 계수 "30"의 마지막 자리가 변한다) — 이
    # 테스트는 원래 파싱 배선 자체를 보는 것이라 그 보정된 값을 그대로 기대하도록
    # 갱신했다.
    assert result["filters"]["max_price"] == 399999
    assert result["filters"]["min_price"] == 300000
    assert result["filters"]["gift_theme"] == ["BIRTHDAY_60TH"]


def test_classify_and_extract_calls_chat_with_think_false():
    seen = {}

    def fake(messages, schema, *, think, model=None):
        seen["think"] = think
        return json.dumps({"intent": "general_chat", "query_text": ""})

    it.classify_and_extract("안녕", chat=fake)
    assert seen["think"] is False


def test_classify_and_extract_includes_history():
    seen = {}

    def fake(messages, schema, *, think, model=None):
        seen["user_content"] = messages[-1]["content"]
        return json.dumps({"intent": "general_chat", "query_text": ""})

    history = [{"role": "user", "content": "안녕하세요"}]
    it.classify_and_extract("더 저렴한 거 없나요", history=history, chat=fake)
    assert "안녕하세요" in seen["user_content"]


def test_classify_and_extract_truncates_history_to_recent_turns():
    """최근 3턴(6개 메시지)만 남기고 그 이전은 잘라야 한다(_MAX_HISTORY_TURNS)."""
    seen = {}

    def fake(messages, schema, *, think, model=None):
        seen["user_content"] = messages[-1]["content"]
        return json.dumps({"intent": "general_chat", "query_text": ""})

    history = [{"role": "user", "content": f"{i}번째 메시지"} for i in range(10)]
    it.classify_and_extract("최근 질문", history=history, chat=fake)

    assert "0번째 메시지" not in seen["user_content"]
    assert "9번째 메시지" in seen["user_content"]


@pytest.mark.parametrize(
    "message",
    ["차 마실 때 쓸 것 추천해줘", "다완 추천해줘", "테이블러너 추천해줘"],
)
def test_smoke_no_gift_hallucination_without_recipient_real_llm(message):
    """받는 사람·선물 언급이 전혀 없는 "~추천해줘" 문장은 product_search여야 한다.

    회귀 재현: "차 마실 때 쓸 것 추천해줘" → gift_theme이 근거 없이 FRIEND로 채워짐 —
    gift_recommendation을 보여주는 few-shot 예시가 프롬프트에 하나도 없어서, 모델이
    "추천해줘"를 선물 요청으로 과대 일반화하고 프롬프트에서 유일하게 본 실제 gift_theme
    값(FRIEND)으로 fallback하는 것으로 확인됐다(실험으로 검증: 대조 예시 2개를 추가하니
    재현됐던 케이스가 전부 정상화됨).
    """
    result = it.classify_and_extract(message)

    assert result["intent"] == "product_search"
    assert result["filters"]["gift_theme"] is None
