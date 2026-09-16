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
import re

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
    """messages를 보내고 schema를 만족하는 JSON 문자열을 받는다.

    LLM_BACKEND 설정("ollama" 기본 또는 "mlx-serve")에 따라 실제 호출 방식이 갈린다 —
    두 서버가 요청·응답 형식이 달라서다(아래 각 헬퍼 함수 참고).
    """
    model_name = model or settings.LLM_MODEL
    timeout = float(os.environ.get("CHAT_TIMEOUT_SECONDS", _DEFAULT_TIMEOUT_SECONDS))

    if settings.LLM_BACKEND == "mlx-serve":
        return _chat_mlx_serve(messages, schema, model_name, timeout)
    if settings.LLM_BACKEND == "sglang":
        return _chat_sglang(messages, schema, model_name, timeout)
    return _chat_ollama(messages, schema, think, model_name, timeout)


def _chat_ollama(
    messages: list[dict], schema: dict, think: bool, model_name: str, timeout: float
) -> str:
    body = {
        "model": model_name,
        "messages": messages,
        "format": schema,
        # num_ctx는 반드시 모든 호출에서 같은 값을 써야 한다 — 값이 다르면 시스템 프롬프트
        # 글자가 같아도 Ollama의 프롬프트 캐시가 깨진다(실측 확인). intent.py·generate.py가
        # 둘 다 이 함수 하나를 거치므로, 여기서 한 번만 고정하면 자동으로 맞는다.
        # 실측 확인된 크래시: GENERATE_SYSTEM에 규칙·예시를 추가해 프롬프트가 커졌을 때
        # "나전칠기 보석함 있어요?"에서 JSON이 suggestions 배열 중간에 잘려 pydantic
        # ValidationError로 이어졌다. 원인은 num_predict가 아니라 num_ctx(전체 컨텍스트)
        # 자체가 꽉 찬 것이었다 — prompt_eval_count(8044) + eval_count(148) = 8192로
        # 정확히 num_ctx 한도와 일치했다. 이후 프롬프트를 다시 줄여서(원래 크기보다도
        # 작아짐) 지금 당장은 8192로도 여유가 있지만, 대화 이력·후보 블록이 긴 조합에서
        # 재발할 여지가 있어 16384로 미리 여유를 둔다. 다만 이 값이 실제로 서버 한도를
        # 늘려주는지는 검증 못 했다 — mlx-serve에서 서버 자체 실행 시점의 용량(`-c`
        # 플래그)이 요청값보다 우선해 조용히 클램프되는 걸 실측으로 확인한 적이 있어
        # (app/config.py SGLANG_HOST 주석 참고와 같은 종류의 함정), Ollama도 서버가
        # 이미 -c 8192로 떠 있으면 이 16384 요청이 무시될 수 있다. 진짜 16384가
        # 필요한 상황이 오면 서버 실행 옵션(`OLLAMA_CONTEXT_LENGTH` 등)도 같이 확인할 것.
        "keep_alive": -1,  # 모델을 VRAM에서 내리지 않고 상시 유지
        "options": {
            "temperature": 0.3,
            "seed": 42,
            "num_ctx": 16384,
        },
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


def _chat_mlx_serve(
    messages: list[dict], schema: dict, model_name: str, timeout: float
) -> str:
    """mlx-serve(OpenAI 호환 API, Apple Silicon 전용 네이티브 서버) 호출.

    Ollama의 /api/show(capabilities) 조회·think 게이팅이 여기선 필요 없다 — 실측
    확인: mlx-serve는 think 키를 아예 안 보내도 JSON이 안 깨지고 정상 동작했다
    (Ollama의 MLX 프리뷰 백엔드와 달리 reasoning이 JSON 스키마 출력을 방해하지 않음).
    """
    body = {
        "model": model_name,
        "messages": messages,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "output", "schema": schema},
        },
        "temperature": 0.3,
        "stream": False,
    }
    resp = _session.post(
        f"{settings.MLX_SERVE_HOST.rstrip('/')}/v1/chat/completions",
        json=body,
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


# outlines 그래마 백엔드가 JSON 스키마 출력을 마크다운 코드 펜스로 감싸는 경우가
# 실측 확인됐다("```json\n{...}\n```") — Ollama·mlx-serve는 이런 감싸기가 없었다.
_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL)


def _strip_code_fence(text: str) -> str:
    """마크다운 코드 펜스로 감싸져 있으면 벗겨내고, 아니면 그대로 반환한다."""
    match = _CODE_FENCE_RE.match(text.strip())
    return match.group(1) if match else text


def _merge_system_into_user(messages: list[dict]) -> list[dict]:
    """gemma 계열처럼 채팅 템플릿이 system 롤을 아예 거부하는 모델을 위한 우회.

    실측 확인: google/gemma-2-2b-it을 SGLang에 올리면 system 메시지를 보내는 순간
    "System role not supported"로 하드 거부한다 — Ollama는 자체 템플릿에서 이걸
    알아서 user 메시지에 흡수해주지만, SGLang은 HuggingFace 원본 템플릿을 그대로
    적용해 그런 보정이 없다. system 내용을 첫 user 메시지 앞에 이어 붙여 우회한다.
    """
    if not messages or messages[0].get("role") != "system":
        return messages
    system_content = messages[0]["content"]
    rest = messages[1:]
    if rest and rest[0].get("role") == "user":
        merged_first = {
            "role": "user",
            "content": f"{system_content}\n\n{rest[0]['content']}",
        }
        return [merged_first] + rest[1:]
    return [{"role": "user", "content": system_content}] + rest


def _chat_sglang(
    messages: list[dict], schema: dict, model_name: str, timeout: float
) -> str:
    """SGLang(팀이 실제 배포할 CUDA 서버용, OpenAI 호환 API) 호출.

    요청 형식은 mlx-serve와 같다(둘 다 OpenAI 호환 response_format). Ollama의
    think 게이팅은 여기서도 필요 없다 — SGLang은 think 키 자체를 안 쓴다.
    """
    body = {
        "model": model_name,
        "messages": _merge_system_into_user(messages),
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "output", "schema": schema},
        },
        "temperature": 0.3,
        "stream": False,
    }
    resp = _session.post(
        f"{settings.SGLANG_HOST.rstrip('/')}/v1/chat/completions",
        json=body,
        timeout=timeout,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return _strip_code_fence(content)
