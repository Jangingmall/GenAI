"""session_store.py 단위 테스트. 기본 get/set 동작과, 락(threading.Lock)이 실제로

동시 요청 상황에서 KeyError/RuntimeError 없이 버티는지 확인한다(CodeRabbit 지적:
락 없이는 get의 만료 삭제와 set의 최대 개수 제거가 동시에 같은 딕셔너리를 건드릴 수
있었다).

실행: python -m pytest tests/test_session_store.py -q
"""

from __future__ import annotations

import sys
import threading

import pytest

from app import session_store


@pytest.fixture(autouse=True)
def _clean_store():
    session_store._store.clear()
    yield
    session_store._store.clear()


def test_get_returns_none_when_missing():
    assert session_store.get("없는세션") is None


def test_set_then_get_roundtrip():
    session_store.set(
        "s1",
        candidates=[{"product_id": 1}],
        filters={"max_price": 50000},
        product_ids=[1],
    )
    result = session_store.get("s1")
    assert result == {
        "candidates": [{"product_id": 1}],
        "filters": {"max_price": 50000},
        "product_ids": [1],
    }


def test_get_expires_after_ttl(monkeypatch):
    session_store.set("s1", candidates=[], filters={}, product_ids=[])
    # TTL을 넘긴 것처럼 보이게 저장된 타임스탬프를 과거로 되돌린다.
    session_store._store["s1"]["ts"] -= session_store._TTL_SECONDS + 1
    assert session_store.get("s1") is None
    assert "s1" not in session_store._store


def test_set_evicts_oldest_when_over_max_entries(monkeypatch):
    monkeypatch.setattr(session_store, "_MAX_ENTRIES", 2)
    session_store.set("s1", candidates=[], filters={}, product_ids=[])
    session_store._store["s1"]["ts"] -= 10  # s1이 가장 오래된 것으로 보이게 한다.
    session_store.set("s2", candidates=[], filters={}, product_ids=[])
    session_store.set(
        "s3", candidates=[], filters={}, product_ids=[]
    )  # 3개째 → 가장 오래된 s1 제거
    assert set(session_store._store) == {"s2", "s3"}


def test_concurrent_get_on_expired_session_does_not_raise():
    """만료된 같은 session_id를 여러 스레드가 동시에 get()해도 KeyError 없이 끝나야 한다.

    get()은 "만료 확인 → del" 두 단계라, 락이 없으면 두 스레드가 둘 다 "만료됐다"고
    확인한 뒤 각자 del을 시도해 두 번째 del이 KeyError로 죽을 수 있다(CodeRabbit 지적).
    기본 스레드 전환 주기(5ms)로는 이 좁은 틈이 거의 안 걸려서, sys.setswitchinterval로
    전환을 아주 잦게 만들어야 실제로 재현된다 — 이 값 없이 돌리면(락이 없는 버전이라도)
    수백 번 반복해도 대부분 통과해버려 회귀를 못 잡는 가짜 통과 테스트가 된다(직접 확인).
    """
    original_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        errors: list[Exception] = []

        def trial():
            session_store._store.clear()
            session_store.set("x", candidates=[], filters={}, product_ids=[])
            session_store._store["x"]["ts"] -= session_store._TTL_SECONDS + 1

            barrier = threading.Barrier(20)

            def worker():
                barrier.wait()
                try:
                    session_store.get("x")
                except Exception as e:  # noqa: BLE001
                    errors.append(e)

            threads = [threading.Thread(target=worker) for _ in range(20)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        for _ in range(300):
            trial()

        assert errors == []
    finally:
        sys.setswitchinterval(original_interval)
