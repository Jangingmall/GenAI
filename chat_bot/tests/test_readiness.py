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
