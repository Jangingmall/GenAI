"""app/warmup_state.py 단위 테스트 — 실제 LLM·DB 없이 시간을 흉내 내 검증한다.

실행: python -m pytest tests/test_warmup_state.py -q
"""

from __future__ import annotations

import threading

import pytest

from app import warmup_state


class FakeClock:
    """sleep을 호출할 때만 시간이 흐르는 가짜 시계."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture(autouse=True)
def _reset_state():
    warmup_state.reset()
    yield
    warmup_state.reset()


def test_first_try_success_marks_done_without_sleep():
    fake = FakeClock()
    calls = []

    ok = warmup_state.run_until_ready(
        lambda: calls.append(1), sleep=fake.sleep, clock=fake.clock
    )

    assert ok is True
    assert warmup_state.is_done() is True
    assert calls == [1]
    assert fake.sleeps == []


def test_retries_until_llm_sidecar_becomes_ready():
    """Ollama가 아직 안 떠서 두 번 연결 거부된 뒤 세 번째에 성공하는 기동 순서 상황."""
    fake = FakeClock()
    attempts = {"n": 0}

    def warmup():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ConnectionError("Connection refused (127.0.0.1:11434)")

    ok = warmup_state.run_until_ready(
        warmup, interval=5, max_wait=60, sleep=fake.sleep, clock=fake.clock
    )

    assert ok is True
    assert attempts["n"] == 3
    assert fake.sleeps == [5, 5]
    assert warmup_state.is_done() is True


def test_gives_up_after_max_wait_and_fails_open():
    """끝내 실패해도 영구 NotReady가 되지 않도록 준비 상태로 연다(fail-open)."""
    fake = FakeClock()

    def warmup():
        raise ConnectionError("Connection refused")

    ok = warmup_state.run_until_ready(
        warmup, interval=5, max_wait=20, sleep=fake.sleep, clock=fake.clock
    )

    assert ok is False
    assert warmup_state.is_done() is True
    # 0·5·10·15초 실패 후 대기, 20초 시도에서 마감 도달로 포기
    assert fake.sleeps == [5, 5, 5, 5]


def test_stop_request_ends_retry_without_marking_done():
    """앱 종료(should_stop)면 준비 상태를 바꾸지 않고 멈춘다 — 종료 중 fail-open 금지."""
    fake = FakeClock()
    stop = {"flag": False}

    def warmup():
        stop["flag"] = True  # 첫 실패 직후 종료 신호
        raise ConnectionError("Connection refused")

    ok = warmup_state.run_until_ready(
        warmup,
        interval=5,
        max_wait=60,
        sleep=fake.sleep,
        clock=fake.clock,
        should_stop=lambda: stop["flag"],
    )

    assert ok is False
    assert warmup_state.is_done() is False


def test_background_does_not_block_and_marks_done():
    handle = warmup_state.start_background(lambda: None, interval=0.01, max_wait=1)
    handle.thread.join(timeout=2)

    assert not handle.thread.is_alive()
    assert handle.thread.daemon is True
    assert warmup_state.is_done() is True


def test_background_stop_wakes_sleeping_retry_immediately():
    """재시도 간격이 길어도(5초) stop()이 대기 중인 스레드를 바로 깨워 끝낸다."""
    entered = threading.Event()

    def always_fail():
        entered.set()
        raise ConnectionError("Connection refused")

    handle = warmup_state.start_background(always_fail, interval=5, max_wait=600)
    assert entered.wait(timeout=2)

    handle.stop(timeout=2)

    assert not handle.thread.is_alive()
    assert warmup_state.is_done() is False
