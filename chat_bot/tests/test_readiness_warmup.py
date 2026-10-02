"""/ai/ready 판정에 앱 워밍업 완료 여부가 반영되는지 검증한다.

DB·임베딩·LLM 확인은 실제 접속 없이 결과를 고정하고, 워밍업 상태만 바꿔 본다.
실행: python -m pytest tests/test_readiness_warmup.py -q
"""

from __future__ import annotations

import pytest

from app import readiness, warmup_state


@pytest.fixture(autouse=True)
def _deps_ready(monkeypatch):
    monkeypatch.setattr(readiness, "_check_database", lambda: (True, "ok"))
    monkeypatch.setattr(readiness, "_check_embedding_model", lambda: (True, "ok"))
    monkeypatch.setattr(readiness, "_check_llm", lambda: (True, "ok"))
    warmup_state.reset()
    yield
    warmup_state.reset()


def test_not_ready_until_app_warmup_done():
    """모델이 적재됐어도(llm=ok) 앱 워밍업 전이면 not_ready — 첫 요청이 콜드이기 때문."""
    result = readiness.check_readiness()

    assert result["status"] == "not_ready"
    assert result["checks"]["warmup"]["ready"] is False


def test_ready_after_app_warmup_done():
    warmup_state.mark_done()

    result = readiness.check_readiness()

    assert result["status"] == "ready"
    assert result["checks"]["warmup"]["ready"] is True


def test_llm_restarting_is_not_ready_even_if_warmed_before(monkeypatch):
    """한 번 워밍업됐어도 LLM 사이드카가 재시작 중이면 not_ready여야 트래픽이 막힌다."""
    warmup_state.mark_done()
    monkeypatch.setattr(readiness, "_check_llm", lambda: (False, "model not loaded"))

    result = readiness.check_readiness()

    assert result["status"] == "not_ready"
    assert result["checks"]["llm"]["ready"] is False
