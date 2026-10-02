"""embedding._get_model이 동시 첫 요청에도 모델을 한 번만 적재하는지 검증한다.

실제 bge-m3 대신 적재가 느린 가짜 SentenceTransformer를 끼워 넣는다.
실행: python -m pytest tests/test_embedding_lock.py -q
"""

from __future__ import annotations

import sys
import threading
import time
import types

import pytest

from app.pipeline import embedding


class _FakeModel:
    loads = 0
    _count_lock = threading.Lock()

    def __init__(self, name: str) -> None:
        with _FakeModel._count_lock:
            _FakeModel.loads += 1
        time.sleep(0.2)  # 무거운 적재를 흉내 — 이 사이에 다른 요청이 끼어든다
        self.name = name

    def encode(self, text, normalize_embeddings=False):
        import numpy as np

        return np.array([1.0, 0.0])


@pytest.fixture(autouse=True)
def _fake_sentence_transformers(monkeypatch):
    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = _FakeModel
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    monkeypatch.setattr(embedding, "_model", None)
    _FakeModel.loads = 0
    yield


def test_concurrent_first_requests_load_model_once():
    """09:47:08 상황 재현: 첫 요청 여러 건이 동시에 들어와도 적재는 1회."""
    start = threading.Barrier(5)
    results = []

    def worker():
        start.wait()
        results.append(embedding._get_model())

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert _FakeModel.loads == 1
    assert len(results) == 5
    assert all(m is results[0] for m in results)  # 모두 같은 모델을 공유


def test_loaded_model_is_reused():
    first = embedding._get_model()
    second = embedding._get_model()

    assert first is second
    assert _FakeModel.loads == 1


def test_embed_query_output_unchanged():
    assert embedding.embed_query("도자기 컵") == [1.0, 0.0]
