"""Ollama 호출을 한 곳에 모은다 — intent.py/generate.py가 공유하는 유일한 LLM 진입점.

ollama 파이썬 패키지 대신 requests로 HTTP `/api/chat`를 직접 부른다(팀 고정 스택).
`format`으로 JSON 스키마를 강제한다.
반환은 `message.content` 문자열(스키마에 맞는 JSON) — 파싱은 호출부가 한다.

temperature=0(그리디 디코딩) 대신 낮은 temperature + 고정 seed를 쓴다: 그리디 디코딩은
자유 텍스트 필드에서 같은 토큰을 반복하는 루프에 빠져 타임아웃까지 갈 수 있다(Qwen
공식 가이드도 그리디 디코딩이 "성능 저하와 끝없는 반복"을 유발한다고 명시한다). seed로
재현성은 그대로 유지한다.
"""

from __future__ import annotations

import os

import requests

from app.config import settings

_DEFAULT_TIMEOUT_SECONDS = 180

# think 파라미터는 Qwen3 계열 전용이다. exaone3.5·llama3.1·qwen2.5·dna는 지원 안 할 수 있어
# 모델명이 qwen3로 시작하지 않으면 body에서 "think" 키를 아예 뺀다.
_THINK_SUPPORTED_PREFIX = "qwen3"


def chat_json(
    messages: list[dict],
    schema: dict,
    *,
    think: bool,
    model: str | None = None,
) -> str:
    """messages를 보내고 schema를 만족하는 JSON 문자열을 받는다."""
    model_name = model or settings.LLM_MODEL
    timeout = float(os.environ.get("CHAT_TIMEOUT_SECONDS", _DEFAULT_TIMEOUT_SECONDS))

    body = {
        "model": model_name,
        "messages": messages,
        "format": schema,
        "options": {"temperature": 0.3, "seed": 42},
        "stream": False,
    }
    if model_name.startswith(_THINK_SUPPORTED_PREFIX):
        body["think"] = think

    resp = requests.post(
        f"{settings.OLLAMA_HOST.rstrip('/')}/api/chat",
        json=body,
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]
