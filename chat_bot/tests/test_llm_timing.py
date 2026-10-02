"""llm._chat_ollama가 Ollama 타이밍을 로그로 남기고, 로그 때문에 응답이 깨지지 않는지 검증.

실행: python -m pytest tests/test_llm_timing.py -q
"""

from __future__ import annotations

import logging

from app.pipeline import llm


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def _patch_post(monkeypatch, payload):
    monkeypatch.setattr(llm, "_model_capabilities", lambda name: set())
    monkeypatch.setattr(llm._session, "post", lambda *a, **k: _FakeResponse(payload))


def test_logs_prefill_and_generation_timing(monkeypatch, caplog):
    _patch_post(
        monkeypatch,
        {
            "message": {"content": '{"ok": true}'},
            "prompt_eval_count": 8044,
            "prompt_eval_duration": 9_500_000_000,  # 9.5초
            "eval_count": 148,
            "eval_duration": 4_200_000_000,
            "load_duration": 12_000_000,
            "total_duration": 13_800_000_000,
        },
    )

    with caplog.at_level(logging.WARNING, logger=llm.__name__):
        out = llm._chat_ollama([], {}, False, "gemma4:12b", 180)

    assert out == '{"ok": true}'
    line = next(
        r.getMessage() for r in caplog.records if "ollama timing" in r.getMessage()
    )
    assert "prompt_tokens=8044" in line
    assert "prompt_ms=9500" in line
    assert "gen_tokens=148" in line
    assert "load_ms=12" in line
    assert "total_ms=13800" in line


def test_missing_timing_fields_do_not_break_response(monkeypatch):
    _patch_post(monkeypatch, {"message": {"content": "hi"}})

    assert llm._chat_ollama([], {}, False, "gemma4:12b", 180) == "hi"


def test_unexpected_timing_values_do_not_break_response(monkeypatch):
    _patch_post(
        monkeypatch,
        {"message": {"content": "hi"}, "prompt_eval_duration": "not-a-number"},
    )

    assert llm._chat_ollama([], {}, False, "gemma4:12b", 180) == "hi"
