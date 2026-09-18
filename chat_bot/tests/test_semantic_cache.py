"""semantic_cache.py 단위 테스트. embed_query를 가짜로 주입해 실제 임베딩 모델 없이 검증한다.

실행: python -m pytest tests/test_semantic_cache.py -q
"""

import time

from app.pipeline import semantic_cache as sc


def _fake_embed(vectors: dict[str, list[float]]):
    """메시지 문자열 → 미리 정해둔 벡터. 실제 임베딩 모델 대신 쓴다."""

    def fake(text: str) -> list[float]:
        return vectors[text]

    return fake


def setup_function():
    """모듈 전역 캐시를 매 테스트마다 비운다 — 테스트 간 상태가 새면 안 된다."""
    sc._cache.clear()


def test_lookup_returns_none_when_cache_empty(monkeypatch):
    monkeypatch.setattr(
        sc, "embed_query", _fake_embed({"선물로 도자기 찾아줘": [1.0, 0.0]})
    )
    assert sc.lookup("선물로 도자기 찾아줘") is None


def test_store_then_lookup_similar_message_hits(monkeypatch):
    monkeypatch.setattr(
        sc,
        "embed_query",
        _fake_embed(
            {
                "선물로 좋은 도자기 찾아줘": [1.0, 0.0],
                "선물용 도자기 추천해줘": [
                    0.99,
                    0.14,
                ],  # 코사인 유사도 ~0.99, 거의 같은 뜻
            }
        ),
    )
    contact1 = {
        "intent": "gift_recommendation",
        "filters": {
            "max_price": None,
            "min_price": None,
            "gift_theme": None,
            "color": None,
        },
        "query_text": "선물용 도자기",
        "chat_reply": "",
    }
    sc.store("선물로 좋은 도자기 찾아줘", contact1)

    result = sc.lookup("선물용 도자기 추천해줘")

    assert result == contact1


def test_lookup_misses_when_message_is_unrelated(monkeypatch):
    monkeypatch.setattr(
        sc,
        "embed_query",
        _fake_embed(
            {
                "선물로 좋은 도자기 찾아줘": [1.0, 0.0],
                "나전으로 만든 곡물독 있어요?": [
                    0.0,
                    1.0,
                ],  # 코사인 유사도 0, 완전히 다른 질문
            }
        ),
    )
    sc.store(
        "선물로 좋은 도자기 찾아줘",
        {
            "intent": "gift_recommendation",
            "filters": {
                "max_price": None,
                "min_price": None,
                "gift_theme": None,
                "color": None,
            },
            "query_text": "선물용 도자기",
            "chat_reply": "",
        },
    )

    assert sc.lookup("나전으로 만든 곡물독 있어요?") is None


def test_lookup_rejects_high_similarity_when_category_differs(monkeypatch):
    """실측 확인된 버그: "부모님 퇴직선물 도자기 50만원 이하로 추천해줘"와 "부모님
    퇴직선물용 목공예품 50만원 이하로 추천해줘"는 종목만 다를 뿐인데 실제 임베딩
    유사도가 0.93까지 나와(임계값 0.82를 훨씬 넘음) 서로 다른 종목인데도 캐시가
    맞다고 판단해버렸다 — 도자기로 물어본 캐시를 목공예품 질문에 그대로 재사용해
    엉뚱한 query_text·filters가 새어나갔다. 임베딩 유사도가 임계값을 넘어도,
    두 문장 모두에서 종목이 특정되고 그 종목이 다르면 캐시를 쓰지 않아야 한다."""
    monkeypatch.setattr(
        sc,
        "embed_query",
        _fake_embed(
            {
                "부모님 퇴직선물 도자기 50만원 이하로 추천해줘": [1.0, 0.0],
                "부모님 퇴직선물용 목공예품 50만원 이하로 추천해줘": [
                    0.93,
                    0.368,
                ],  # 임계값(0.82)보다 높은 유사도 — 실측 재현
            }
        ),
    )
    sc.store(
        "부모님 퇴직선물 도자기 50만원 이하로 추천해줘",
        {
            "intent": "gift_recommendation",
            "filters": {
                "max_price": 500000,
                "min_price": None,
                "gift_theme": None,
                "color": None,
            },
            "query_text": "부모님 퇴직선물 도자기 50만원 이하로 추천해줘",
            "chat_reply": "",
        },
    )

    assert sc.lookup("부모님 퇴직선물용 목공예품 50만원 이하로 추천해줘") is None


def test_lookup_rejects_high_similarity_when_price_digits_differ(monkeypatch):
    """실측 확인된 버그(사용자 직접 재현 요청으로 종목 외 다른 축도 점검하다 발견):
    "도자기 5만원 이하로 추천해줘"와 "도자기 10만원 이하로 추천해줘"도 가격
    숫자만 다를 뿐인데 실제 임베딩 유사도가 0.871까지 나온다(임계값 0.82 초과) —
    가격이 다른데 캐시가 옛 max_price를 그대로 돌려주면 손님이 요청한 가격과
    다른 조건으로 검색된다."""
    monkeypatch.setattr(
        sc,
        "embed_query",
        _fake_embed(
            {
                "도자기 5만원 이하로 추천해줘": [1.0, 0.0],
                "도자기 10만원 이하로 추천해줘": [0.871, 0.491],  # 실측 유사도
            }
        ),
    )
    sc.store(
        "도자기 5만원 이하로 추천해줘",
        {
            "intent": "product_search",
            "filters": {
                "max_price": 50000,
                "min_price": None,
                "gift_theme": None,
                "color": None,
            },
            "query_text": "도자기 5만원 이하로 추천해줘",
            "chat_reply": "",
        },
    )

    assert sc.lookup("도자기 10만원 이하로 추천해줘") is None


def test_lookup_rejects_high_similarity_when_color_differs(monkeypatch):
    """같은 이유로 "빨간색 도자기 찾아줘"·"파란색 도자기 찾아줘"도 실측 유사도
    0.876(임계값 초과)이라, 색상만 다른데 캐시가 잘못된 color 필터를 재사용할
    위험이 있다."""
    monkeypatch.setattr(
        sc,
        "embed_query",
        _fake_embed(
            {
                "빨간색 도자기 찾아줘": [1.0, 0.0],
                "파란색 도자기 찾아줘": [0.876, 0.482],  # 실측 유사도
            }
        ),
    )
    sc.store(
        "빨간색 도자기 찾아줘",
        {
            "intent": "product_search",
            "filters": {
                "max_price": None,
                "min_price": None,
                "gift_theme": None,
                "color": ["RED"],
            },
            "query_text": "빨간색 도자기 찾아줘",
            "chat_reply": "",
        },
    )

    assert sc.lookup("파란색 도자기 찾아줘") is None


def test_lookup_ignores_expired_entries(monkeypatch):
    monkeypatch.setattr(
        sc,
        "embed_query",
        _fake_embed({"선물로 도자기 찾아줘": [1.0, 0.0], "선물 도자기": [1.0, 0.0]}),
    )
    sc.store(
        "선물로 도자기 찾아줘",
        {
            "intent": "gift_recommendation",
            "filters": {
                "max_price": None,
                "min_price": None,
                "gift_theme": None,
                "color": None,
            },
            "query_text": "도자기",
            "chat_reply": "",
        },
    )
    sc._cache[0]["ts"] = time.time() - sc._TTL_SECONDS - 1  # 강제로 만료시킴

    assert sc.lookup("선물 도자기") is None


def test_cache_evicts_oldest_when_over_capacity(monkeypatch):
    monkeypatch.setattr(sc, "_MAX_ENTRIES", 2)
    monkeypatch.setattr(
        sc,
        "embed_query",
        _fake_embed({"a": [1.0, 0.0, 0.0], "b": [0.0, 1.0, 0.0], "c": [0.0, 0.0, 1.0]}),
    )
    base = {
        "intent": "product_search",
        "filters": {
            "max_price": None,
            "min_price": None,
            "gift_theme": None,
            "color": None,
        },
        "query_text": "",
        "chat_reply": "",
    }
    sc.store("a", base)
    sc.store("b", base)
    sc.store("c", base)

    assert len(sc._cache) == 2
    assert sc.lookup("a") is None  # 가장 오래된 것부터 버려짐
