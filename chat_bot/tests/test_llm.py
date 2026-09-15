"""llm.py 단위 테스트. 재시도 정책 설정값·think 게이팅만 검증 — 실제 네트워크 호출은
_session.post를 monkeypatch로 갈아끼워 피한다.

실행: python -m pytest tests/test_llm.py -q
"""

from app.config import settings
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


# ---------------------------------------------------------------------------
# LLM_BACKEND="mlx-serve" — OpenAI 호환 API로 대신 부른다
# ---------------------------------------------------------------------------


def test_chat_json_posts_to_mlx_serve_when_backend_configured(monkeypatch):
    """LLM_BACKEND가 mlx-serve면 Ollama 전용 엔드포인트(/api/chat, format 키)가 아니라
    OpenAI 호환 엔드포인트(/v1/chat/completions, response_format 키)로 보내야 한다 —
    실측 확인: mlx-serve는 이 형식만 받는다."""
    monkeypatch.setattr(settings, "LLM_BACKEND", "mlx-serve")
    monkeypatch.setattr(settings, "MLX_SERVE_HOST", "http://localhost:11234")
    sent = {}

    def fake_post(url, json=None, timeout=None):
        sent["url"] = url
        sent["body"] = json
        return _FakeResponse({"choices": [{"message": {"content": '{"ok": true}'}}]})

    monkeypatch.setattr(llm._session, "post", fake_post)

    result = llm.chat_json(
        [{"role": "user", "content": "hi"}],
        {"type": "object"},
        think=False,
        model="lmstudio-community/gemma-4-12B-it-MLX-4bit",
    )

    assert sent["url"] == "http://localhost:11234/v1/chat/completions"
    assert sent["body"]["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "output", "schema": {"type": "object"}},
    }
    assert "format" not in sent["body"]
    assert result == '{"ok": true}'


def test_chat_json_mlx_serve_does_not_call_ollama_capabilities_endpoint(monkeypatch):
    """mlx-serve 백엔드는 Ollama의 /api/show(capabilities 조회)를 아예 부르면 안 된다 —
    실측 확인: mlx-serve는 think 키 없이도 JSON이 안 깨지고 정상 동작해서, Ollama
    전용 게이팅 로직 자체가 필요 없다."""
    monkeypatch.setattr(settings, "LLM_BACKEND", "mlx-serve")

    def fake_post(url, json=None, timeout=None):
        assert "/api/show" not in url
        return _FakeResponse({"choices": [{"message": {"content": "{}"}}]})

    monkeypatch.setattr(llm._session, "post", fake_post)

    llm.chat_json([{"role": "user", "content": "hi"}], {}, think=False)


# ---------------------------------------------------------------------------
# LLM_BACKEND="sglang" — 팀이 실제 배포할 CUDA 서버용, OpenAI 호환 API
# ---------------------------------------------------------------------------


def test_strip_code_fence_removes_json_markdown_wrapper():
    """SGLang outlines 그래마 백엔드가 JSON을 마크다운 코드 펜스로 감싸는 경우가
    실측 확인됐다(````json\\n{...}\\n````) — 벗겨내야 pydantic 파싱이 성공한다."""
    wrapped = '```json\n{"name": "Gemma"}\n```'
    assert llm._strip_code_fence(wrapped) == '{"name": "Gemma"}'


def test_strip_code_fence_leaves_plain_json_untouched():
    """Ollama·mlx-serve처럼 애초에 안 감싸져 있으면 그대로 둔다."""
    plain = '{"name": "Gemma"}'
    assert llm._strip_code_fence(plain) == plain


def test_chat_json_posts_to_sglang_when_backend_configured(monkeypatch):
    """LLM_BACKEND가 sglang이면 mlx-serve와 같은 OpenAI 호환 엔드포인트로 보내되,
    SGLANG_HOST를 쓴다."""
    monkeypatch.setattr(settings, "LLM_BACKEND", "sglang")
    monkeypatch.setattr(settings, "SGLANG_HOST", "http://localhost:30000")
    sent = {}

    def fake_post(url, json=None, timeout=None):
        sent["url"] = url
        sent["body"] = json
        return _FakeResponse({"choices": [{"message": {"content": '{"ok": true}'}}]})

    monkeypatch.setattr(llm._session, "post", fake_post)

    result = llm.chat_json(
        [{"role": "user", "content": "hi"}],
        {"type": "object"},
        think=False,
        model="google/gemma-2-2b-it",
    )

    assert sent["url"] == "http://localhost:30000/v1/chat/completions"
    assert sent["body"]["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "output", "schema": {"type": "object"}},
    }
    assert result == '{"ok": true}'


def test_chat_json_sglang_strips_code_fence_from_response(monkeypatch):
    """실제로 마크다운 코드 펜스로 감싸서 응답이 와도 chat_json 최종 반환값은 순수
    JSON이어야 한다 — 안 그러면 호출부의 model_validate_json이 실패한다."""
    monkeypatch.setattr(settings, "LLM_BACKEND", "sglang")

    def fake_post(url, json=None, timeout=None):
        return _FakeResponse(
            {"choices": [{"message": {"content": '```json\n{"ok": true}\n```'}}]}
        )

    monkeypatch.setattr(llm._session, "post", fake_post)

    result = llm.chat_json([{"role": "user", "content": "hi"}], {}, think=False)

    assert result == '{"ok": true}'


def test_merge_system_into_user_prepends_to_first_user_message():
    """gemma 계열처럼 system 롤을 거부하는 모델(실측 확인: "System role not
    supported")을 위한 우회 — system 내용을 첫 user 메시지 앞에 이어 붙인다."""
    merged = llm._merge_system_into_user(
        [
            {"role": "system", "content": "너는 친절한 챗봇이다."},
            {"role": "user", "content": "안녕"},
        ]
    )

    assert merged == [{"role": "user", "content": "너는 친절한 챗봇이다.\n\n안녕"}]


def test_merge_system_into_user_no_op_without_system_role():
    messages = [{"role": "user", "content": "안녕"}]
    assert llm._merge_system_into_user(messages) == messages


def test_chat_json_sglang_sends_merged_messages_without_system_role(monkeypatch):
    """실제 요청 본문에 system 롤이 남아있으면 SGLang이 거부하므로, chat_json이
    보내는 최종 body에도 system 롤이 없어야 한다."""
    monkeypatch.setattr(settings, "LLM_BACKEND", "sglang")
    sent = {}

    def fake_post(url, json=None, timeout=None):
        sent["body"] = json
        return _FakeResponse({"choices": [{"message": {"content": "{}"}}]})

    monkeypatch.setattr(llm._session, "post", fake_post)

    llm.chat_json(
        [
            {"role": "system", "content": "시스템 지시문"},
            {"role": "user", "content": "질문"},
        ],
        {},
        think=False,
    )

    roles = [m["role"] for m in sent["body"]["messages"]]
    assert "system" not in roles
    assert sent["body"]["messages"][0]["content"] == "시스템 지시문\n\n질문"


def test_chat_json_sglang_does_not_call_ollama_capabilities_endpoint(monkeypatch):
    """mlx-serve와 같은 이유로 sglang도 Ollama의 /api/show를 부르면 안 된다."""
    monkeypatch.setattr(settings, "LLM_BACKEND", "sglang")

    def fake_post(url, json=None, timeout=None):
        assert "/api/show" not in url
        return _FakeResponse({"choices": [{"message": {"content": "{}"}}]})

    monkeypatch.setattr(llm._session, "post", fake_post)

    llm.chat_json([{"role": "user", "content": "hi"}], {}, think=False)
