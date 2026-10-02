"""main.py lifespan의 백그라운드 워밍업 배선 테스트 — 기동 순서 문제(API가 LLM 사이드카보다
먼저 뜸) 대응이 실제 FastAPI 기동·종료 흐름에서 동작하는지 본다.

with TestClient(app)로 lifespan을 실제로 실행한다. 실제 Ollama·DB는 쓰지 않는다.
실행: python -m pytest tests/test_main_warmup.py -q
"""

from __future__ import annotations

import threading
import time

import pytest
import requests
from fastapi.testclient import TestClient

from app import main, readiness, warmup_state


@pytest.fixture(autouse=True)
def _reset():
    warmup_state.reset()
    yield
    main.app.dependency_overrides.clear()
    warmup_state.reset()


def _wait_until(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def _warmup_threads():
    return [t for t in threading.enumerate() if t.name == "app-warmup" and t.is_alive()]


def test_startup_is_not_blocked_while_llm_is_still_loading(monkeypatch):
    """Ollama가 모델을 적재하는 동안(워밍업이 오래 걸림)에도 서버는 즉시 떠서
    /ai/health에 응답해야 한다 — 막히면 livenessProbe가 컨테이너를 재시작시킨다."""
    release = threading.Event()
    monkeypatch.setattr(main.orchestrator, "warmup", lambda **kw: release.wait(5))

    started = time.monotonic()
    with TestClient(main.app) as c:
        elapsed = time.monotonic() - started
        assert c.get("/ai/health").status_code == 200
        release.set()

    assert elapsed < 2.0


def test_background_warmup_retries_then_ready_endpoint_turns_200(monkeypatch):
    """처음엔 LLM 미준비로 실패하다 성공하면, /ai/ready가 503 → 200으로 바뀐다."""
    monkeypatch.setattr(readiness, "_check_database", lambda: (True, "ok"))
    monkeypatch.setattr(readiness, "_check_embedding_model", lambda: (True, "ok"))
    monkeypatch.setattr(readiness, "_check_llm", lambda: (True, "ok"))

    attempts = {"n": 0}
    llm_up = threading.Event()

    def warmup(**kwargs):
        attempts["n"] += 1
        if not llm_up.is_set():
            raise requests.exceptions.ConnectionError("Connection refused")

    monkeypatch.setattr(main.orchestrator, "warmup", warmup)
    # 기본 interval은 함수 기본값으로 묶여 있어 테스트 시간 단축용으로 짧게 넘긴다
    original_start = warmup_state.start_background
    monkeypatch.setattr(
        warmup_state,
        "start_background",
        lambda fn, **kw: original_start(fn, interval=0.05, **kw),
    )

    with TestClient(main.app) as c:
        assert _wait_until(lambda: attempts["n"] >= 2)
        assert c.get("/ai/ready").status_code == 503  # 아직 콜드

        llm_up.set()  # LLM 사이드카 준비 완료
        assert _wait_until(lambda: c.get("/ai/ready").status_code == 200)

    assert attempts["n"] >= 3


def test_shutdown_stops_background_retry_thread(monkeypatch):
    """LLM이 끝내 안 떠도 앱이 종료되면 재시도 스레드가 남지 않아야 한다."""

    def boom(**kwargs):
        raise requests.exceptions.ConnectionError("Connection refused")

    monkeypatch.setattr(main.orchestrator, "warmup", boom)

    with TestClient(main.app) as c:
        assert c.get("/ai/health").status_code == 200
        assert _wait_until(lambda: len(_warmup_threads()) == 1)

    assert _wait_until(lambda: len(_warmup_threads()) == 0)
    assert warmup_state.is_done() is False  # 종료 중엔 fail-open으로 바꾸지 않는다


def test_successful_rewarmup_marks_app_ready(monkeypatch):
    """기동 워밍업이 실패했더라도 대화 중 재예열(_background_rewarmup)이 성공하면 준비 상태가 된다."""
    monkeypatch.setattr(main.orchestrator, "warmup", lambda **kw: None)

    main._background_rewarmup()

    assert warmup_state.is_done() is True


def test_failed_rewarmup_keeps_app_not_ready(monkeypatch):
    def boom(**kwargs):
        raise requests.exceptions.ConnectionError("Connection refused")

    monkeypatch.setattr(main.orchestrator, "warmup", boom)

    main._background_rewarmup()

    assert warmup_state.is_done() is False
