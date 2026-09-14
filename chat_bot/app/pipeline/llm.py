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
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.config import settings

_DEFAULT_TIMEOUT_SECONDS = 180

# 연결 실패(Ollama 재시작 중 등)만 짧은 backoff로 자동 재시도하고, 읽기 타임아웃(연결은
# 됐지만 생성이 느려서 시간 초과)은 재시도하지 않는다 — 이미 느린 생성을 그대로 다시
# 기다리게 하면 대기 시간만 배로 늘 뿐 성공 확률이 오르지 않는다(read=0). POST는
# urllib3 기본값상 비멱등으로 보고 재시도 대상에서 빠지지만, 이 호출은 채팅 완성
# 요청이라 두 번 보내도 부작용(중복 주문 등)이 없어 명시적으로 허용한다.
_retry = Retry(
    total=2,
    connect=2,
    read=0,
    backoff_factor=0.5,
    status_forcelist=[500, 502, 503, 504],
    allowed_methods=["POST"],
)
_session = requests.Session()
_session.mount("http://", HTTPAdapter(max_retries=_retry))
_session.mount("https://", HTTPAdapter(max_retries=_retry))

# think 지원 여부를 모델명 접두사로 하드코딩(과거 "qwen3"만 허용)했더니 gemma4:12b-mlx
# 처럼 thinking을 지원하는 다른 모델이 붙는 순간 안 맞았다 — think 키가 아예 안 실려
# 그 모델의 기본값(thinking 켜짐)으로 동작하면서 JSON 스키마 출력이 깨지고 응답도
# 8배 느려졌다(실측 확인). 반대로 무조건 think 키를 보내면 thinking 미지원 모델엔 API가
# 하드 에러를 낸다(실측: gemma2:9b에 think:true를 보내면 '"gemma2:9b" does not support
# thinking'). 그래서 Ollama가 /api/show로 실제로 알려주는 capabilities로 판단한다 —
# 모델별로 한 번만 조회하고 캐싱해 매 호출마다 왕복이 늘지 않게 한다.
_capabilities_cache: dict[str, set[str]] = {}


def _model_capabilities(model_name: str) -> set[str]:
    if model_name not in _capabilities_cache:
        resp = _session.post(
            f"{settings.OLLAMA_HOST.rstrip('/')}/api/show",
            json={"model": model_name},
            timeout=10,
        )
        resp.raise_for_status()
        _capabilities_cache[model_name] = set(resp.json().get("capabilities", []))
    return _capabilities_cache[model_name]


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
        # num_ctx는 반드시 모든 호출에서 같은 값을 써야 한다 — 값이 다르면 시스템 프롬프트
        # 글자가 같아도 Ollama의 프롬프트 캐시가 깨진다(실측 확인). intent.py·generate.py가
        # 둘 다 이 함수 하나를 거치므로, 여기서 한 번만 고정하면 자동으로 맞는다. 8192는
        # 시스템 프롬프트+대화 맥락+후보 목록+출력을 합쳐도 여유 있는 크기로 실측 확인했다
        # (기존 기본값 4096보다 넉넉하게 잡음).
        "keep_alive": -1,  # 모델을 VRAM에서 내리지 않고 상시 유지
        "options": {"temperature": 0.3, "seed": 42, "num_ctx": 8192},
        "stream": False,
    }
    if "thinking" in _model_capabilities(model_name):
        body["think"] = think

    resp = _session.post(
        f"{settings.OLLAMA_HOST.rstrip('/')}/api/chat",
        json=body,
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]
