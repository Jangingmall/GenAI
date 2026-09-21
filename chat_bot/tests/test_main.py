"""app/main.py(/ai/chat) 계약 테스트. dependency_overrides로 실제 LLM·DB·임베딩 모델을
전혀 안 거치고 HTTP 요청/응답 구조·세션 배선만 검증한다.

TestClient(app)를 컨텍스트 매니저(with) 없이 쓰면 lifespan(=orchestrator.warmup())이
실행되지 않는다 — 여기서 실제 Ollama·DB를 태우지 않으려고 의도적으로 그렇게 뒀다.

실행: python -m pytest tests/test_main.py -q
"""

import json

import psycopg2
import pytest
import requests
from fastapi.testclient import TestClient

from app import main, session_store

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def _clean_state():
    """모듈 전역 세션 저장소·dependency_overrides가 테스트 간에 새지 않게 정리한다."""
    session_store._store.clear()
    yield
    main.app.dependency_overrides.clear()
    session_store._store.clear()


def _sequenced_chat(intent_payload: dict, generate_payload: dict):
    """1번째 호출(intent)엔 intent_payload, 2번째 호출(generate)엔 generate_payload를 준다."""
    calls = {"n": 0}

    def fake(messages, schema, *, think, model=None):
        calls["n"] += 1
        return json.dumps(intent_payload if calls["n"] == 1 else generate_payload)

    return fake


def _no_prices(product_ids):
    return {}


def _no_artisans(product_ids):
    return {}


def _no_cache_lookup(message):
    return None


def _no_cache_store(message, contact1):
    pass


def _override(*, chat, search_and_rank):
    """실LLM·실DB·실임베딩 없이 /ai/chat을 테스트하기 위한 dependency_overrides 일괄 세팅."""
    main.app.dependency_overrides[main._default_chat] = lambda: chat
    main.app.dependency_overrides[main._default_search_and_rank] = (
        lambda: search_and_rank
    )
    main.app.dependency_overrides[main._default_fetch_prices] = lambda: _no_prices
    main.app.dependency_overrides[main._default_fetch_artisans] = lambda: _no_artisans
    main.app.dependency_overrides[main._default_cache_lookup] = lambda: _no_cache_lookup
    main.app.dependency_overrides[main._default_cache_store] = lambda: _no_cache_store


_INTENT_PRODUCT_SEARCH = {
    "intent": "product_search",
    "max_price": None,
    "min_price": None,
    "gift_theme": [],
    "color": [],
    "query_text": "찻잔",
    "chat_reply": "",
}
_GENERATE_OK = {
    "reply": "이 찻잔을 추천드려요.",
    "allowed_ids": [9],
    "suggestions": ["다른 색상으로", "가격대 낮춰서", "포장까지 되는 것만"],
}
_CANDIDATES = [
    {
        "product_id": 9,
        "name": "청자 다완",
        "score": 0.8,
        "evidence": {"artisan_input": "", "verified": None},
    }
]


def test_chat_returns_only_external_contract_fields():
    """candidates·filters는 확정 계약(§0)에 없는 내부 전용 필드라 응답에 유출되면 안 된다."""

    def spy(contact1, top_k=3):
        return _CANDIDATES

    _override(
        chat=_sequenced_chat(_INTENT_PRODUCT_SEARCH, _GENERATE_OK),
        search_and_rank=spy,
    )

    response = client.post(
        "/ai/chat", json={"session_id": "s1", "message": "찻잔 있나요", "history": []}
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"reply", "intent", "product_ids", "suggestions"}
    assert body["product_ids"] == [9]


def test_chat_returns_friendly_reply_on_llm_timeout():
    """llm.py의 chat_json은 Ollama에 requests로 붙어 타임아웃·연결 실패 시
    requests.exceptions.RequestException을 던진다 — 잡지 않으면 FastAPI 기본 500
    에러(안내 문구 없음)로 나간다(사용자 시나리오 E29: AI 응답 지연/타임아웃 →
    Timeout 처리 및 재시도 제공). 200으로 안내 문구를 돌려줘야 한다."""

    def timeout_chat(messages, schema, *, think, model=None):
        raise requests.exceptions.Timeout("연결 시간 초과")

    _override(chat=timeout_chat, search_and_rank=lambda contact1, top_k=3: [])

    response = client.post(
        "/ai/chat", json={"session_id": "s1", "message": "찻잔 있나요", "history": []}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["product_ids"] == []
    assert "다시 시도" in body["reply"]


def test_chat_returns_friendly_reply_on_malformed_llm_json():
    """SGLang의 outlines 그래마 백엔드로 실측 확인: response_format(JSON 스키마 강제)을
    보내도 특정 프롬프트에서 조용히 무시하고 순수 텍스트를 반환하는 경우가 있었다.
    이러면 intent.py의 json.loads가 json.JSONDecodeError(ValueError의 서브클래스)를
    던지는데, 이것도 E29와 같은 방식으로 200 안내 문구로 처리해야 한다."""

    def malformed_chat(messages, schema, *, think, model=None):
        return "죄송해요, 요청을 이해하지 못했어요."  # JSON이 아닌 순수 텍스트

    _override(chat=malformed_chat, search_and_rank=lambda contact1, top_k=3: [])

    response = client.post(
        "/ai/chat", json={"session_id": "s1", "message": "찻잔 있나요", "history": []}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["product_ids"] == []
    assert "다시 시도" in body["reply"]


def test_chat_returns_friendly_reply_on_db_connection_failure():
    """search.py의 psycopg2.connect()는 try/except 밖에 있어 DB 접속 실패 시
    psycopg2.OperationalError를 던진다(A담당 파일이라 여기서 직접 안 고치고, main.py의
    except 튜플만 넓힌다). 지금 except엔 이 타입이 없어서 안 잡히면 E29와 같은
    "친절한 fallback" 대신 FastAPI 기본 500이 나간다 — 실측 확인된 버그."""

    def db_down_search_and_rank(contact1, top_k=3):
        raise psycopg2.OperationalError("could not connect to server")

    _override(
        chat=_sequenced_chat(_INTENT_PRODUCT_SEARCH, _GENERATE_OK),
        search_and_rank=db_down_search_and_rank,
    )

    response = client.post(
        "/ai/chat", json={"session_id": "s1", "message": "찻잔 있나요", "history": []}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["product_ids"] == []
    assert "다시 시도" in body["reply"]


def test_chat_returns_friendly_reply_on_embedding_failure():
    """embedding.py의 embed_query()는 DB·LLM 호출과 달리 try/except가 전혀 없다(보안
    리서치 중 발견 — sentence-transformers 공식 GitHub 이슈에서도 모델 파일 누락·버전
    불일치가 실제로 흔한 실패 유형으로 보고됨). 임베딩 모델 로딩·추론 실패는 보통
    OSError(파일 없음 등)로 올라오는데, 지금 except 튜플엔 이 타입이 없어서 DB·LLM
    장애와 달리 임베딩만 FastAPI 기본 500으로 나간다."""

    def embedding_down_search_and_rank(contact1, top_k=3):
        raise OSError("모델 파일을 찾을 수 없음: /models/bge-m3")

    _override(
        chat=_sequenced_chat(_INTENT_PRODUCT_SEARCH, _GENERATE_OK),
        search_and_rank=embedding_down_search_and_rank,
    )

    response = client.post(
        "/ai/chat", json={"session_id": "s1", "message": "찻잔 있나요", "history": []}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["product_ids"] == []
    assert "다시 시도" in body["reply"]


# ---------------------------------------------------------------------------
# /ai/products — 에러 메시지에 내부 예외 원문이 그대로 노출되지 않아야 한다
# (보안 리서치 중 발견: detail=f"...: {e}"는 DB 연결 정보 등 내부 구조가 클라이언트
# 응답에 그대로 노출될 위험이 있다).
# ---------------------------------------------------------------------------

_ARTISAN_BODY = {
    "artisan_id": 1,
    "business_name": "테스트공방",
}
_PRODUCT_BODY = {
    "product_id": 1,
    "name": "테스트 상품",
}


def test_create_product_does_not_leak_internal_exception_detail(monkeypatch):
    def boom(artisan, product):
        raise RuntimeError("host=internal-db.private port=5432 password=s3cr3t")

    monkeypatch.setattr(main.products_service, "upsert_product", boom)

    response = client.post(
        "/ai/products", json={"artisan": _ARTISAN_BODY, "product": _PRODUCT_BODY}
    )
    assert response.status_code == 500
    assert "s3cr3t" not in response.text
    assert "internal-db" not in response.text


def test_update_product_does_not_leak_internal_exception_detail(monkeypatch):
    def boom(product_id, changed):
        raise RuntimeError("host=internal-db.private port=5432 password=s3cr3t")

    monkeypatch.setattr(main.products_service, "update_product", boom)

    response = client.put("/ai/products/1", json={"product": {"price": 1000}})
    assert response.status_code == 500
    assert "s3cr3t" not in response.text
    assert "internal-db" not in response.text


def test_delete_product_does_not_leak_internal_exception_detail(monkeypatch):
    def boom(product_id):
        raise RuntimeError("host=internal-db.private port=5432 password=s3cr3t")

    monkeypatch.setattr(main.products_service, "delete_product", boom)

    response = client.delete("/ai/products/1")
    assert response.status_code == 500
    assert "s3cr3t" not in response.text
    assert "internal-db" not in response.text


def test_narrow_down_reuses_previous_candidates_via_session_id():
    """같은 session_id로 새 하드필터 없는 narrow_down을 보내면 재검색하지 않는다."""
    calls = {"n": 0}

    def spy_search_and_rank(contact1, top_k=3):
        calls["n"] += 1
        return _CANDIDATES

    _override(
        chat=_sequenced_chat(_INTENT_PRODUCT_SEARCH, _GENERATE_OK),
        search_and_rank=spy_search_and_rank,
    )
    client.post(
        "/ai/chat", json={"session_id": "s1", "message": "찻잔 있나요", "history": []}
    )
    assert calls["n"] == 1

    intent_narrow_down = {**_INTENT_PRODUCT_SEARCH, "intent": "narrow_down"}
    _override(
        chat=_sequenced_chat(intent_narrow_down, _GENERATE_OK),
        search_and_rank=spy_search_and_rank,
    )
    response = client.post(
        "/ai/chat",
        json={
            "session_id": "s1",
            "message": "그중 더 싼 거",
            "history": [{"sender": "USER", "content": "찻잔 있나요"}],
        },
    )

    assert response.status_code == 200
    assert calls["n"] == 1  # 재검색 없이 이전 후보를 그대로 재사용했다


def test_repeated_narrow_down_suppresses_duplicate_cards_via_session_id():
    """세션 저장소를 거쳐 previous_product_ids가 실제로 전달되는지 HTTP 계층까지
    확인한다 — 1턴과 완전히 같은 product_ids가 2턴에도 나오면 카드를 비워야 한다."""
    _override(
        chat=_sequenced_chat(_INTENT_PRODUCT_SEARCH, _GENERATE_OK),
        search_and_rank=lambda contact1, top_k=3: _CANDIDATES,
    )
    first = client.post(
        "/ai/chat", json={"session_id": "s1", "message": "찻잔 있나요", "history": []}
    )
    assert first.json()["product_ids"] == [9]

    intent_narrow_down = {**_INTENT_PRODUCT_SEARCH, "intent": "narrow_down"}
    _override(
        chat=_sequenced_chat(intent_narrow_down, _GENERATE_OK),  # 같은 allowed_ids=[9]
        search_and_rank=lambda contact1, top_k=3: _CANDIDATES,
    )
    second = client.post(
        "/ai/chat",
        json={
            "session_id": "s1",
            "message": "가격대 확인해줘",
            "history": [{"sender": "USER", "content": "찻잔 있나요"}],
        },
    )

    assert second.json()["product_ids"] == []  # 완전히 같은 세트라 카드 억제


def test_history_sender_field_is_mapped_to_role_for_pipeline():
    """백엔드가 보내는 {sender, content}를 orchestrator가 기대하는 {role, content}로
    바꿔야 한다 — 안 바뀌면 intent.py의 _format_history가 매 줄을 "챗봇:"으로만
    표시해(m['role']을 못 찾아 KeyError 나거나) 소비자 발화와 구분이 안 된다."""
    seen = {}
    calls = {"n": 0}

    def sequenced(messages, schema, *, think, model=None):
        calls["n"] += 1
        if calls["n"] == 1:
            seen["user_content"] = messages[-1]["content"]
            return json.dumps(_INTENT_PRODUCT_SEARCH)
        return json.dumps(_GENERATE_OK)

    _override(chat=sequenced, search_and_rank=lambda contact1, top_k=3: _CANDIDATES)

    client.post(
        "/ai/chat",
        json={
            "session_id": "s1",
            "message": "그중 더 싼 거",
            "history": [
                {"sender": "USER", "content": "찻잔 있나요"},
                {"sender": "ADMIN", "content": "청자 찻잔을 추천드려요"},
            ],
        },
    )

    assert "소비자: 찻잔 있나요" in seen["user_content"]
    assert "챗봇: 청자 찻잔을 추천드려요" in seen["user_content"]


def test_lifespan_survives_warmup_failure(monkeypatch):
    """워밍업(orchestrator.warmup)이 실패해도(Ollama·DB 접속 불가 등) 서버 기동 자체는
    끝까지 진행돼야 한다 — CodeRabbit 지적: 이전엔 예외가 그대로 전파돼 서버가 안 떴다."""

    def boom(**kwargs):
        raise RuntimeError("Ollama 접속 실패")

    monkeypatch.setattr(main.orchestrator, "warmup", boom)

    with TestClient(main.app) as c:
        # with 블록에 진입한 시점에 lifespan이 이미 실행됐다 — boom()이 예외를 던졌는데도
        # 여기까지 도달했다는 것 자체가 서버가 죽지 않았다는 증거다.
        response = c.get("/ai/health")
        assert response.status_code == 200


def test_ready_returns_503_when_a_dependency_is_not_ready(monkeypatch):
    monkeypatch.setattr(
        main.readiness,
        "check_readiness",
        lambda: {
            "status": "not_ready",
            "checks": {
                "database": {"ready": False, "detail": "connection failed"},
                "embedding_model": {"ready": True, "detail": "configured"},
                "llm": {"ready": True, "detail": "model available"},
            },
        },
    )

    response = client.get("/ai/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["checks"]["database"]["ready"] is False


def test_ready_returns_200_when_all_dependencies_are_ready(monkeypatch):
    monkeypatch.setattr(
        main.readiness,
        "check_readiness",
        lambda: {
            "status": "ready",
            "checks": {
                "database": {"ready": True, "detail": "database query succeeded"},
                "embedding_model": {"ready": True, "detail": "configured"},
                "llm": {"ready": True, "detail": "model available"},
            },
        },
    )

    response = client.get("/ai/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_different_session_ids_do_not_share_state():
    """session_id가 다르면 narrow_down이어도 이전 후보를 못 물려받아 새로 검색한다."""
    calls = {"n": 0}

    def spy_search_and_rank(contact1, top_k=3):
        calls["n"] += 1
        return _CANDIDATES

    _override(
        chat=_sequenced_chat(_INTENT_PRODUCT_SEARCH, _GENERATE_OK),
        search_and_rank=spy_search_and_rank,
    )
    client.post(
        "/ai/chat", json={"session_id": "s1", "message": "찻잔 있나요", "history": []}
    )
    assert calls["n"] == 1

    intent_narrow_down = {**_INTENT_PRODUCT_SEARCH, "intent": "narrow_down"}
    _override(
        chat=_sequenced_chat(intent_narrow_down, _GENERATE_OK),
        search_and_rank=spy_search_and_rank,
    )
    client.post(
        "/ai/chat", json={"session_id": "s2", "message": "그중 더 싼 거", "history": []}
    )

    assert calls["n"] == 2  # s2는 s1의 후보를 모르니 새로 검색했다
