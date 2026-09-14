"""llm.py 단위 테스트. 재시도 정책 설정값·think 게이팅만 검증 — 실제 네트워크 호출은
_session.post를 monkeypatch로 갈아끼워 피한다.

실행: python -m pytest tests/test_llm.py -q
"""

from app.pipeline import llm


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_retry_only_retries_connection_and_server_errors_not_read_timeout():
    """읽기 타임아웃(연결은 됐지만 생성이 느려서 시간 초과)은 재시도하면 대기 시간만
    배로 늘 뿐이라 재시도 대상에서 뺀다(read=0) — 연결 실패·5xx만 자동 재시도한다."""
    assert llm._retry.connect == 2
    assert llm._retry.read == 0
    assert set(llm._retry.status_forcelist) == {500, 502, 503, 504}


def test_retry_allows_post():
    """urllib3 기본값은 POST를 비멱등으로 보고 재시도 대상에서 뺀다 — 우리 LLM 호출은
    두 번 보내도 부작용이 없어 명시적으로 허용해야 한다."""
    assert "POST" in llm._retry.allowed_methods


def test_session_mounted_with_retry_adapter():
    http_adapter = llm._session.get_adapter("http://example.com")
    https_adapter = llm._session.get_adapter("https://example.com")
    assert http_adapter.max_retries is llm._retry
    assert https_adapter.max_retries is llm._retry


# ---------------------------------------------------------------------------
# think 게이팅 — 모델명 접두사 하드코딩 대신 Ollama capabilities로 판단한다
# ---------------------------------------------------------------------------


def _install_fake_post(monkeypatch, *, capabilities: list[str]):
    """/api/show엔 capabilities를, /api/chat엔 빈 답을 주는 가짜 _session.post.
    실제로 /api/chat에 보낸 body를 캡처해 테스트가 검사할 수 있게 한다."""
    monkeypatch.setattr(llm, "_capabilities_cache", {})
    sent_bodies = []

    def fake_post(url, json=None, timeout=None):
        if url.endswith("/api/show"):
            return _FakeResponse({"capabilities": capabilities})
        sent_bodies.append(json)
        return _FakeResponse({"message": {"content": "{}"}})

    monkeypatch.setattr(llm._session, "post", fake_post)
    return sent_bodies


def test_chat_json_includes_think_key_when_model_supports_thinking(monkeypatch):
    """gemma4:12b-mlx처럼 capabilities에 "thinking"이 있는 모델은 think 키를 붙여야
    한다 — 안 붙이면 그 모델의 기본값(thinking 켜짐)으로 동작해 JSON이 깨진다(실측
    확인: "+1{...}" 같은 쓰레기 프리픽스가 섞여 파싱 실패)."""
    sent = _install_fake_post(monkeypatch, capabilities=["completion", "thinking"])

    llm.chat_json(
        [{"role": "user", "content": "hi"}], {}, think=False, model="gemma4:12b-mlx"
    )

    assert sent[0]["think"] is False


def test_chat_json_omits_think_key_when_model_lacks_thinking(monkeypatch):
    """gemma2:9b처럼 thinking을 지원하지 않는 모델엔 think 키 자체를 빼야 한다 — 무조건
    보내면 API가 하드 에러를 낸다(실측 확인: '"gemma2:9b" does not support thinking')."""
    sent = _install_fake_post(monkeypatch, capabilities=["completion"])

    llm.chat_json(
        [{"role": "user", "content": "hi"}], {}, think=True, model="gemma2:9b"
    )

    assert "think" not in sent[0]


def test_model_capabilities_caches_per_model(monkeypatch):
    """모델별로 /api/show를 한 번만 조회한다 — 매 채팅 호출마다 왕복이 늘면 안 된다."""
    monkeypatch.setattr(llm, "_capabilities_cache", {})
    calls = {"show": 0}

    def fake_post(url, json=None, timeout=None):
        if url.endswith("/api/show"):
            calls["show"] += 1
            return _FakeResponse({"capabilities": ["thinking"]})
        return _FakeResponse({"message": {"content": "{}"}})

    monkeypatch.setattr(llm._session, "post", fake_post)

    llm.chat_json(
        [{"role": "user", "content": "a"}], {}, think=False, model="gemma4:12b-mlx"
    )
    llm.chat_json(
        [{"role": "user", "content": "b"}], {}, think=False, model="gemma4:12b-mlx"
    )

    assert calls["show"] == 1
