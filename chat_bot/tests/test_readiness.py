"""Dependency readiness checks for the Kubernetes probe contract."""

from app import readiness
from app.config import settings


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_readiness_is_not_ready_when_database_check_fails(monkeypatch):
    monkeypatch.setattr(
        readiness, "_check_database", lambda: (False, "connection failed")
    )
    monkeypatch.setattr(
        readiness, "_check_embedding_model", lambda: (True, "configured")
    )
    monkeypatch.setattr(readiness, "_check_llm", lambda: (True, "model available"))

    result = readiness.check_readiness()

    assert result["status"] == "not_ready"
    assert result["checks"]["database"] == {
        "ready": False,
        "detail": "connection failed",
    }


def test_local_embedding_model_requires_modules_and_config(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "EMBED_MODEL", str(tmp_path))

    ready, detail = readiness._check_embedding_model()

    assert ready is False
    assert "modules.json" in detail


def test_ollama_readiness_requires_model_actually_loaded_with_expected_context(
    monkeypatch,
):
    """Stage 실측(2026-10-01): /api/tags는 "설치돼 있나"만 보고 "로드됐나"는 안 본다 —
    준비 완료(ready=1)인데 GPU 메모리 0%가 20분 넘게 지속되는 게 Grafana로 확인됐다.
    /api/ps(현재 실행 중인 모델 목록)로 바꿔서, 모델이 실제로 떠있는지까지 봐야 한다."""
    monkeypatch.setattr(settings, "LLM_BACKEND", "ollama")
    monkeypatch.setattr(settings, "OLLAMA_HOST", "http://llm")
    monkeypatch.setattr(settings, "LLM_MODEL", "gemma2:9b")
    monkeypatch.setattr(
        readiness.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(
            {
                "models": [
                    {
                        "name": "gemma2:9b",
                        "context_length": readiness.llm.OLLAMA_NUM_CTX,
                    }
                ]
            }
        ),
    )

    ready, detail = readiness._check_llm()

    assert ready is True
    assert "gemma2:9b" in detail


def test_ollama_readiness_fails_when_model_installed_but_not_running(monkeypatch):
    """/api/tags였다면 설치만 돼 있어도 통과했을 상황 — /api/ps엔 실행 중인 모델만
    나오므로, 모델이 설치는 됐지만 아직 메모리에 안 올라온 경우(= 우리가 재현한 버그
    상황)엔 목록 자체가 비어 not_ready가 나와야 한다."""
    monkeypatch.setattr(settings, "LLM_BACKEND", "ollama")
    monkeypatch.setattr(settings, "OLLAMA_HOST", "http://llm")
    monkeypatch.setattr(settings, "LLM_MODEL", "gemma2:9b")
    monkeypatch.setattr(
        readiness.requests,
        "get",
        lambda *args, **kwargs: FakeResponse({"models": []}),
    )

    ready, detail = readiness._check_llm()

    assert ready is False
    assert "gemma2:9b" in detail


def test_ollama_readiness_fails_when_loaded_context_does_not_match(monkeypatch):
    """모델은 떠있지만 사전 로딩 호출이 실제 앱과 다른 num_ctx로 불렀다면(설정 실수 등),
    모델은 있는데 context가 달라 실제 호출에서 쓰는 설정과 어긋난다 — 이것도 not_ready로
    잡아야 조용히 묻히지 않는다(Codex 검증에서 지적된 위험)."""
    monkeypatch.setattr(settings, "LLM_BACKEND", "ollama")
    monkeypatch.setattr(settings, "OLLAMA_HOST", "http://llm")
    monkeypatch.setattr(settings, "LLM_MODEL", "gemma2:9b")
    monkeypatch.setattr(
        readiness.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(
            {"models": [{"name": "gemma2:9b", "context_length": 4096}]}
        ),
    )

    ready, detail = readiness._check_llm()

    assert ready is False
    assert "context" in detail.lower()


def test_sglang_readiness_requires_requested_model(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BACKEND", "sglang")
    monkeypatch.setattr(settings, "SGLANG_HOST", "http://llm")
    monkeypatch.setattr(settings, "LLM_MODEL", "qwen-text")
    monkeypatch.setattr(
        readiness.requests,
        "get",
        lambda *args, **kwargs: FakeResponse({"data": [{"id": "other"}]}),
    )

    ready, detail = readiness._check_llm()

    assert ready is False
    assert "qwen-text" in detail
