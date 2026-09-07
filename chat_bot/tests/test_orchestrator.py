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
        },
    )
    search_and_rank = _fake_search_and_rank(
        [{"product_id": 9, "name": "청자 다완", "score": 0.8, "evidence": {"artisan_input": "", "verified": None}}]
    )

    result = rr.run("찻잔 있나요", chat=chat, search_and_rank=search_and_rank)

    assert set(result.keys()) == {"reply", "intent", "products"}
    assert result["intent"] == "product_search"
    assert result["products"] == [{"product_id": 9, "reason": "청자 다완입니다."}]


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
        generate_payload={"reply": "ok", "products": []},
    )
    rr.run("찻잔 있나요", chat=chat, search_and_rank=spy_search_and_rank)

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
        },
    )
    search_and_rank = _fake_search_and_rank(
        [{"product_id": 9, "name": "청자 다완", "score": 0.8, "evidence": {}}]
    )
    result = rr.run("찻잔 있나요", chat=chat, search_and_rank=search_and_rank)

    assert result["products"] == []
