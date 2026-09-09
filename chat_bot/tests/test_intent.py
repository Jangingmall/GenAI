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


def test_price_to_won_empty_is_none():
    assert it._price_to_won("") is None


def test_price_to_won_none_is_none():
    assert it._price_to_won(None) is None


def test_price_to_won_passthrough_int():
    assert it._price_to_won(300000) == 300000


def test_price_to_won_plain_digit_string():
    assert it._price_to_won("50000") == 50000


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
    result = it._to_contact1(raw, gift_themes=prompts.GIFT_THEMES, colors=prompts.COLORS)
    assert result == {
        "query_text": "환갑 선물",
        "filters": {
            "max_price": 300000,
            "min_price": None,
            "gift_theme": ["BIRTHDAY_60TH"],
            "color": None,
        },
        "intent": "gift_recommendation",
        "chat_reply": "",
    }


def test_to_contact1_passes_through_chat_reply():
    """chat_reply는 general_chat일 때 orchestrator가 generate.py 호출 없이 바로 쓰는
    필드다 — _to_contact1이 그대로 넘겨야 한다."""
    raw = {"intent": "general_chat", "query_text": "", "chat_reply": "안녕하세요! 무엇을 도와드릴까요?"}
    result = it._to_contact1(raw, gift_themes=prompts.GIFT_THEMES, colors=prompts.COLORS)
    assert result["chat_reply"] == "안녕하세요! 무엇을 도와드릴까요?"


def test_to_contact1_missing_chat_reply_defaults_empty():
    raw = {"intent": "product_search", "query_text": "찻잔"}
    result = it._to_contact1(raw, gift_themes=prompts.GIFT_THEMES, colors=prompts.COLORS)
    assert result["chat_reply"] == ""


def test_to_contact1_unknown_intent_becomes_general_chat():
    raw = {"intent": "made_up_intent", "query_text": "아무말"}
    result = it._to_contact1(raw, gift_themes=prompts.GIFT_THEMES, colors=prompts.COLORS)
    assert result["intent"] == "general_chat"


def test_to_contact1_drops_hallucinated_gift_theme():
    raw = {"intent": "gift_recommendation", "gift_theme": ["NOT_A_REAL_THEME"], "query_text": ""}
    result = it._to_contact1(raw, gift_themes=prompts.GIFT_THEMES, colors=prompts.COLORS)
    assert result["filters"]["gift_theme"] is None


def test_to_contact1_missing_query_text_defaults_empty():
    raw = {"intent": "general_chat"}
    result = it._to_contact1(raw, gift_themes=prompts.GIFT_THEMES, colors=prompts.COLORS)
    assert result["query_text"] == ""


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
    assert result["filters"]["max_price"] == 300000
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

    history = [
        {"role": "user", "content": f"{i}번째 메시지"} for i in range(10)
    ]
    it.classify_and_extract("최근 질문", history=history, chat=fake)

    assert "0번째 메시지" not in seen["user_content"]
    assert "9번째 메시지" in seen["user_content"]


@pytest.mark.parametrize(
    "message",
    ["차 마실 때 쓸 것 추천해줘", "다완 추천해줘", "테이블러너 추천해줘"],
)
def test_smoke_no_gift_hallucination_without_recipient_real_llm(message):
    """받는 사람·선물 언급이 전혀 없는 "~추천해줘" 문장은 product_search여야 한다.

    docs/b-metaprompt.md에 이미 기록된 회귀("차 마실 때 쓸 것 추천해줘" → gift_theme이
    근거 없이 FRIEND로 채워짐) — gift_recommendation을 보여주는 few-shot 예시가 프롬프트에
    하나도 없어서, 모델이 "추천해줘"를 선물 요청으로 과대 일반화하고 프롬프트에서 유일하게
    본 실제 gift_theme 값(FRIEND)으로 fallback하는 것으로 확인됐다(실험으로 검증: 대조
    예시 2개를 추가하니 재현됐던 케이스가 전부 정상화됨).
    """
    result = it.classify_and_extract(message)

    assert result["intent"] == "product_search"
    assert result["filters"]["gift_theme"] is None
