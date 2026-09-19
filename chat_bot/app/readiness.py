"""Fast, dependency-aware readiness checks for the Kubernetes probe."""

from __future__ import annotations

from pathlib import Path

import psycopg2
import requests

from app.config import settings

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


def _model_ids(payload: dict, backend: str) -> list[str]:
    if backend == "ollama":
        return [str(item.get("name", "")) for item in payload.get("models", [])]
    return [str(item.get("id", "")) for item in payload.get("data", [])]


def _check_llm() -> tuple[bool, str]:
    backend = settings.LLM_BACKEND.strip().lower()
    if backend == "ollama":
        url = f"{settings.OLLAMA_HOST.rstrip('/')}/api/tags"
    elif backend == "sglang":
        url = f"{settings.SGLANG_HOST.rstrip('/')}/v1/models"
    elif backend == "mlx-serve":
        url = f"{settings.MLX_SERVE_HOST.rstrip('/')}/v1/models"
    else:
        return False, f"unsupported LLM_BACKEND: {settings.LLM_BACKEND}"

    try:
        response = requests.get(url, timeout=_CHECK_TIMEOUT_SECONDS)
        response.raise_for_status()
        model_ids = _model_ids(response.json(), backend)
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"

    if settings.LLM_MODEL not in model_ids:
        return False, f"model {settings.LLM_MODEL!r} not listed by {url}"
    return True, f"model {settings.LLM_MODEL!r} available"


def check_readiness() -> dict:
    checks = {}
    for name, checker in (
        ("database", _check_database),
        ("embedding_model", _check_embedding_model),
        ("llm", _check_llm),
    ):
        ready, detail = checker()
        checks[name] = {"ready": ready, "detail": detail}

    return {
        "status": "ready"
        if all(item["ready"] for item in checks.values())
        else "not_ready",
        "checks": checks,
    }
