"""Fast, dependency-aware readiness checks for the Kubernetes probe."""

from __future__ import annotations

from pathlib import Path

import psycopg2
import requests

from app import warmup_state
from app.config import settings
from app.pipeline import llm

_CHECK_TIMEOUT_SECONDS = 2
_LOCAL_MODEL_MARKERS = (
    "modules.json",
    "config.json",
    "1_Pooling/config.json",
    "tokenizer.json",
)
_LOCAL_MODEL_WEIGHTS = ("pytorch_model.bin", "model.safetensors")


def _check_database() -> tuple[bool, str]:
    try:
        conn = psycopg2.connect(settings.dsn(), connect_timeout=_CHECK_TIMEOUT_SECONDS)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"
    return True, "database query succeeded"


def _check_embedding_model() -> tuple[bool, str]:
    model_name = settings.EMBED_MODEL.strip()
    model_path = Path(model_name).expanduser()

    # A Hub ID is valid configuration for local development. Native's EKS
    # deployment supplies an absolute PVC path, which is checked on disk.
    is_local_path = model_path.is_absolute() or model_name.startswith(("./", "../"))
    if not is_local_path:
        return True, f"model id configured: {model_name}"

    if not model_path.is_dir():
        return False, f"model directory does not exist: {model_path}"

    missing = [
        marker for marker in _LOCAL_MODEL_MARKERS if not (model_path / marker).is_file()
    ]
    if not any((model_path / weight).is_file() for weight in _LOCAL_MODEL_WEIGHTS):
        missing.append("pytorch_model.bin or model.safetensors")
    if missing:
        return False, "missing model files: " + ", ".join(missing)

    return True, f"local model files present: {model_path}"


def _model_ids(payload: dict) -> list[str]:
    """sglang·mlx-serve는 OpenAI 호환 /v1/models 형식(data[].id)을 쓴다. ollama는
    별도로 _check_ollama_running()이 /api/ps를 직접 처리한다."""
    return [str(item.get("id", "")) for item in payload.get("data", [])]


def _check_ollama_running(host: str) -> tuple[bool, str]:
    """/api/tags(설치된 모델 목록)가 아니라 /api/ps(현재 메모리에 로드돼 실행 중인
    모델 목록)를 본다 — Stage 실측(2026-10-01): 재시작 직후 /api/tags 기준으로는
    "준비 완료"였는데 실제로는 GPU에 모델이 전혀 안 올라온 채 20분 넘게 머문 사례를
    Grafana로 확인했다. 또한 로드된 context 길이가 실제 호출(llm.OLLAMA_NUM_CTX)과
    다르면, 모델은 있어도 다른 설정으로 떠있는 것이라 not_ready로 본다."""
    url = f"{host.rstrip('/')}/api/ps"
    try:
        response = requests.get(url, timeout=_CHECK_TIMEOUT_SECONDS)
        response.raise_for_status()
        running = response.json().get("models", [])
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"

    matching = next(
        (m for m in running if str(m.get("name", "")) == settings.LLM_MODEL), None
    )
    if matching is None:
        return False, f"model {settings.LLM_MODEL!r} not currently loaded by {url}"

    loaded_ctx = matching.get("context_length")
    if loaded_ctx != llm.OLLAMA_NUM_CTX:
        return False, (
            f"model {settings.LLM_MODEL!r} loaded but context length "
            f"{loaded_ctx!r} != expected {llm.OLLAMA_NUM_CTX!r}"
        )
    return True, f"model {settings.LLM_MODEL!r} loaded with context {loaded_ctx}"


def _check_llm() -> tuple[bool, str]:
    backend = settings.LLM_BACKEND.strip().lower()
    if backend == "ollama":
        return _check_ollama_running(settings.OLLAMA_HOST)
    if backend == "sglang":
        url = f"{settings.SGLANG_HOST.rstrip('/')}/v1/models"
    elif backend == "mlx-serve":
        url = f"{settings.MLX_SERVE_HOST.rstrip('/')}/v1/models"
    else:
        return False, f"unsupported LLM_BACKEND: {settings.LLM_BACKEND}"

    try:
        response = requests.get(url, timeout=_CHECK_TIMEOUT_SECONDS)
        response.raise_for_status()
        model_ids = _model_ids(response.json())
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"

    if settings.LLM_MODEL not in model_ids:
        return False, f"model {settings.LLM_MODEL!r} not listed by {url}"
    return True, f"model {settings.LLM_MODEL!r} available"


def _check_warmup() -> tuple[bool, str]:
    """모델이 적재돼도 앱 워밍업(BGE-M3 로딩 + 시스템 프롬프트 캐시)이 안 끝났으면 첫
    요청이 여전히 콜드다(main.py lifespan 주석 참고). 챗봇 API가 LLM 사이드카보다
    먼저 떠 기동 시 워밍업이 실패하던 문제(Stage 실측, 2026-10-01) 때문에 워밍업
    완료까지 준비 조건에 넣는다."""
    if warmup_state.is_done():
        return True, "app warmup completed"
    return False, "app warmup in progress (waiting for LLM sidecar)"


def check_readiness() -> dict:
    checks = {}
    for name, checker in (
        ("database", _check_database),
        ("embedding_model", _check_embedding_model),
        ("llm", _check_llm),
        ("warmup", _check_warmup),
    ):
        ready, detail = checker()
        checks[name] = {"ready": ready, "detail": detail}

    return {
        "status": (
            "ready" if all(item["ready"] for item in checks.values()) else "not_ready"
        ),
        "checks": checks,
    }
