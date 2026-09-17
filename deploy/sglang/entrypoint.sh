#!/usr/bin/env bash
set -Eeuo pipefail

TEXT_MODEL_PATH="${TEXT_MODEL_PATH:-cyankiwi/Qwen3.8-27B-AWQ-INT4}"
TEXT_MODEL_REVISION="${TEXT_MODEL_REVISION:-6e134bae811fb5adac50ee042ae5f029ac6779aa}"
TEXT_SERVED_MODEL_NAME="${TEXT_SERVED_MODEL_NAME:-qwen-text}"
TEXT_MEM_FRACTION="${TEXT_MEM_FRACTION:-0.50}"
TEXT_CONTEXT_LENGTH="${TEXT_CONTEXT_LENGTH:-8192}"
IMAGE_MODEL_PATH="${IMAGE_MODEL_PATH:-circulus/FLUX.2-klein-9B-bnb-4bit}"
IMAGE_MODEL_REVISION="${IMAGE_MODEL_REVISION:-58c2804f31af12c8888504b96250010c50b55e44}"
IMAGE_SERVED_MODEL_NAME="${IMAGE_SERVED_MODEL_NAME:-flux-klein}"

# A PVC mounted over this path hides the image-layer directories. The service
# code creates the SQLite parent and asset-store directories itself, while the
# entrypoint creates model/cache directories before SGLang starts on a blank
# PVC. This assumes the PVC is writable by UID/GID 10001 (for example via
# Kubernetes fsGroup/securityContext).
mkdir -p \
    "${ASSET_STORE_DIR:-/var/lib/detail-page-ai/assets}" \
    "${U2NET_HOME:-/var/lib/detail-page-ai/models/u2net}" \
    "${HF_HOME:-/var/lib/detail-page-ai/models/huggingface}" \
    "${HF_HUB_CACHE:-/var/lib/detail-page-ai/models/huggingface/hub}" \
    "${HF_DATASETS_CACHE:-/var/lib/detail-page-ai/models/huggingface/datasets}" \
    "${TRANSFORMERS_CACHE:-/var/lib/detail-page-ai/models/huggingface/hub}" \
    "${XDG_CACHE_HOME:-/var/lib/detail-page-ai/cache}" \
    "${TORCH_HOME:-/var/lib/detail-page-ai/models/torch}" \
    "${SGLANG_CACHE_DIR:-/var/lib/detail-page-ai/cache/sglang}" \
    "${FLASHINFER_CACHE_DIR:-/var/lib/detail-page-ai/cache/flashinfer}" \
    "${TRITON_CACHE_DIR:-/var/lib/detail-page-ai/cache/triton}" \
    "${TORCHINDUCTOR_CACHE_DIR:-/var/lib/detail-page-ai/cache/torchinductor}" \
    "${CUDA_CACHE_PATH:-/var/lib/detail-page-ai/cache/cuda}" \
    "$(dirname "${SQLITE_PATH:-/var/lib/detail-page-ai/state.sqlite3}")"

echo "Starting SGLang text server on 127.0.0.1:30000" >&2
sglang-python -m sglang.launch_server \
    --model-path "$TEXT_MODEL_PATH" \
    --revision "$TEXT_MODEL_REVISION" \
    --served-model-name "$TEXT_SERVED_MODEL_NAME" \
    --host 127.0.0.1 \
    --port 30000 \
    --mem-fraction-static "$TEXT_MEM_FRACTION" \
    --context-length "$TEXT_CONTEXT_LENGTH" \
    --trust-remote-code &
text_pid=$!

echo "Starting SGLang image server on 127.0.0.1:30001" >&2
sglang serve \
    --model-path "$IMAGE_MODEL_PATH" \
    --revision "$IMAGE_MODEL_REVISION" \
    --served-model-name "$IMAGE_SERVED_MODEL_NAME" \
    --host 127.0.0.1 \
    --port 30001 \
    --num-gpus 1 \
    --dit-cpu-offload false \
    --text-encoder-cpu-offload false &
image_pid=$!

# kill -0 also succeeds for a zombie on Linux. Inspecting /proc lets the
# watcher notice a crashed server before it can leave the API running alone.
process_is_running() {
    local pid="$1"
    local state

    kill -0 "$pid" 2>/dev/null || return 1
    if [[ -r "/proc/$pid/stat" ]]; then
        state="$(cut -d ' ' -f3 "/proc/$pid/stat" 2>/dev/null || true)"
        [[ "$state" != "Z" ]] || return 1
    fi
}

# Keep the API as PID 1/foreground while this watcher supervises the two
# background SGLang children. Docker stops the whole container when PID 1
# exits; explicit child termination also makes local script tests clean.
main_pid=$$
watch_processes() {
    while process_is_running "$text_pid" \
        && process_is_running "$image_pid" \
        && process_is_running "$main_pid"; do
        sleep 1
    done

    local server_failure=0
    if ! process_is_running "$text_pid"; then
        echo "SGLang text server exited; stopping container" >&2
        server_failure=1
    elif ! process_is_running "$image_pid"; then
        echo "SGLang image server exited; stopping container" >&2
        server_failure=1
    else
        echo "FastAPI service exited; stopping SGLang children" >&2
    fi

    kill -TERM "$text_pid" "$image_pid" 2>/dev/null || true
    if (( server_failure )) && process_is_running "$main_pid"; then
        # A model-server failure is fatal even if uvicorn handles TERM
        # gracefully; use KILL so the container reports a failed workload.
        kill -KILL "$main_pid" 2>/dev/null || true
    fi
}

watch_processes &

echo "Starting FastAPI service on 0.0.0.0:8000" >&2
exec serve-ai
