#!/usr/bin/env bash
# ==============================================================================
# measure_vram.sh
#
# Measure GPU VRAM usage during model loading and inference on L40S/CUDA pod.
# Usage:
#   measure_vram.sh text <sample_image.jpg>
#   measure_vram.sh image <sample_image.jpg>
#
# Output:
#   mode baseline_MiB loaded_MiB peak_MiB request_ok elapsed_s
#   CSV: /path/to/vram_log.csv
# ==============================================================================
set -Eeuo pipefail

usage() {
    cat <<'EOF' >&2
Usage: measure_vram.sh <text|image> <sample_image_path>

Arguments:
  text|image          Target server to benchmark
  sample_image_path   Path to sample image file (e.g., sample.jpg)

Environment variables (optional):
  ENTRYPOINT_BIN      Path to entrypoint script (default: /usr/local/bin/detail-page-ai-entrypoint)
  TIMEOUT_STARTUP     Max seconds to wait for server /v1/models (default: 1800)
  TIMEOUT_REQUEST     Max seconds to wait for inference request (default: 180)
  BASELINE_MAX_MIB    Max allowed baseline VRAM in MiB before starting (default: 1024)
  IMAGE_SIZE          Image resolution for image edits (default: 1024x1024)
  CSV_DIR             Directory to store VRAM CSV log (default: /tmp)
EOF
    exit 1
}

if [[ $# -lt 2 ]]; then
    usage
fi

MODE="$1"
SAMPLE_IMAGE="$2"

if [[ "$MODE" != "text" && "$MODE" != "image" ]]; then
    echo "ERROR: Invalid mode '$MODE'. Must be 'text' or 'image'." >&2
    usage
fi

if [[ ! -f "$SAMPLE_IMAGE" ]]; then
    echo "ERROR: Sample image file '$SAMPLE_IMAGE' not found." >&2
    exit 1
fi

if [[ ! -r "$SAMPLE_IMAGE" ]]; then
    echo "ERROR: Sample image file '$SAMPLE_IMAGE' is not readable." >&2
    exit 1
fi

# ------------------------------------------------------------------------------
# Check required commands
# ------------------------------------------------------------------------------
for required_cmd in curl base64 setsid nvidia-smi; do
    if ! command -v "$required_cmd" >/dev/null 2>&1; then
        echo "ERROR: Required command '$required_cmd' not found in PATH." >&2
        exit 1
    fi
done

# ------------------------------------------------------------------------------
# 1. Resolve Server Command from Entrypoint DRY_RUN
# ------------------------------------------------------------------------------
ENTRYPOINT_BIN="${ENTRYPOINT_BIN:-/usr/local/bin/detail-page-ai-entrypoint}"
if [[ ! -f "$ENTRYPOINT_BIN" && ! -x "$ENTRYPOINT_BIN" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
    if [[ -f "$REPO_ROOT/deploy/sglang/entrypoint.sh" ]]; then
        ENTRYPOINT_BIN="$REPO_ROOT/deploy/sglang/entrypoint.sh"
    else
        echo "ERROR: Entrypoint script not found at $ENTRYPOINT_BIN" >&2
        exit 1
    fi
fi

echo "[INFO] Running entrypoint dry run: $ENTRYPOINT_BIN" >&2
if [[ -x "$ENTRYPOINT_BIN" ]]; then
    dry_run_output="$(DRY_RUN=1 "$ENTRYPOINT_BIN")"
else
    dry_run_output="$(DRY_RUN=1 bash "$ENTRYPOINT_BIN")"
fi

if [[ "$MODE" == "text" ]]; then
    raw_cmd="$(echo "$dry_run_output" | grep -E '^TEXT:' | head -n 1 || true)"
    if [[ -z "$raw_cmd" ]]; then
        echo "ERROR: Failed to find 'TEXT:' command in entrypoint dry run output." >&2
        exit 1
    fi
    SERVER_CMD="${raw_cmd#TEXT: }"
    DEFAULT_PORT="30000"
    DEFAULT_MODEL="qwen-text"
else
    raw_cmd="$(echo "$dry_run_output" | grep -E '^IMAGE:' | head -n 1 || true)"
    if [[ -z "$raw_cmd" ]]; then
        echo "ERROR: Failed to find 'IMAGE:' command in entrypoint dry run output." >&2
        exit 1
    fi
    SERVER_CMD="${raw_cmd#IMAGE: }"
    DEFAULT_PORT="30001"
    DEFAULT_MODEL="flux-klein"
fi

PORT="$DEFAULT_PORT"
if [[ "$SERVER_CMD" =~ --port[[:space:]]+([0-9]+) ]]; then
    PORT="${BASH_REMATCH[1]}"
fi

MODEL_NAME="$DEFAULT_MODEL"
if [[ "$SERVER_CMD" =~ --served-model-name[[:space:]]+([^[:space:]]+) ]]; then
    MODEL_NAME="${BASH_REMATCH[1]}"
fi

echo "[INFO] Mode: $MODE, Port: $PORT, Model: $MODEL_NAME" >&2
echo "[INFO] Server command: $SERVER_CMD" >&2

# ------------------------------------------------------------------------------
# 2. Configuration & Process Cleanup Setup
# ------------------------------------------------------------------------------
CSV_DIR="${CSV_DIR:-/tmp}"
mkdir -p "$CSV_DIR" 2>/dev/null || true
CSV_FILE="${CSV_DIR}/vram_${MODE}_$(date +%Y%m%d_%H%M%S).csv"

TIMEOUT_STARTUP="${TIMEOUT_STARTUP:-1800}"
TIMEOUT_REQUEST="${TIMEOUT_REQUEST:-180}"
BASELINE_MAX_MIB="${BASELINE_MAX_MIB:-1024}"
IMAGE_SIZE="${IMAGE_SIZE:-1024x1024}"

SAMPLER_PID=""
SERVER_PID=""
PAYLOAD_FILE=""
HTTP_RESP_FILE=""

stop_server_group() {
    local pid="${SERVER_PID:-}"
    SERVER_PID=""

    if [[ -n "$pid" ]]; then
        echo "[INFO] Terminating server process group (PGID: $pid)..." >&2
        kill -TERM -- "-$pid" 2>/dev/null || true

        for _ in {1..10}; do
            if ! kill -0 -- "-$pid" 2>/dev/null && ! kill -0 "$pid" 2>/dev/null; then
                break
            fi
            sleep 1
        done

        if kill -0 -- "-$pid" 2>/dev/null || kill -0 "$pid" 2>/dev/null; then
            echo "[INFO] Server group still running; sending SIGKILL (PGID: $pid)..." >&2
            kill -KILL -- "-$pid" 2>/dev/null || true
            kill -KILL "$pid" 2>/dev/null || true
        fi

        wait "$pid" 2>/dev/null || true
    fi
}

server_is_alive() {
    if [[ -n "${SERVER_PID:-}" ]]; then
        kill -0 "$SERVER_PID" 2>/dev/null
    else
        return 1
    fi
}

cleanup() {
    local exit_code=$?
    trap - EXIT INT TERM
    echo "[INFO] Cleaning up background processes and temporary files..." >&2

    # Stop sampler
    if [[ -n "$SAMPLER_PID" ]] && kill -0 "$SAMPLER_PID" 2>/dev/null; then
        kill -TERM "$SAMPLER_PID" 2>/dev/null || true
        for _ in {1..3}; do
            kill -0 "$SAMPLER_PID" 2>/dev/null || break
            sleep 0.2
        done
        if kill -0 "$SAMPLER_PID" 2>/dev/null; then
            kill -KILL "$SAMPLER_PID" 2>/dev/null || true
        fi
        wait "$SAMPLER_PID" 2>/dev/null || true
        SAMPLER_PID=""
    fi

    # Stop server process group
    stop_server_group

    # Remove temporary files
    [[ -n "$PAYLOAD_FILE" && -f "$PAYLOAD_FILE" ]] && rm -f "$PAYLOAD_FILE"
    [[ -n "$HTTP_RESP_FILE" && -f "$HTTP_RESP_FILE" ]] && rm -f "$HTTP_RESP_FILE"

    exit "$exit_code"
}
trap cleanup EXIT INT TERM

# ------------------------------------------------------------------------------
# 3. Start Sampler & Measure/Verify Baseline VRAM
# ------------------------------------------------------------------------------
echo "[INFO] Starting VRAM sampler to $CSV_FILE..." >&2
nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -lms 500 > "$CSV_FILE" 2>/dev/null &
SAMPLER_PID=$!

sleep 1
baseline_MiB=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | tr -d ' ' | head -n 1 || true)
if [[ -z "$baseline_MiB" ]]; then
    baseline_MiB=$(head -n 1 "$CSV_FILE" 2>/dev/null | tr -d ' ' || true)
fi
if [[ -z "$baseline_MiB" || ! "$baseline_MiB" =~ ^[0-9]+$ ]]; then
    echo "ERROR: Failed to read baseline VRAM from nvidia-smi." >&2
    exit 1
fi
echo "[INFO] Baseline VRAM: ${baseline_MiB} MiB (threshold: ${BASELINE_MAX_MIB} MiB)" >&2

if (( baseline_MiB > BASELINE_MAX_MIB )); then
    echo "ERROR: Baseline VRAM (${baseline_MiB} MiB) exceeds threshold (${BASELINE_MAX_MIB} MiB)." >&2
    echo "       The GPU may already be in use by another workload or residual process." >&2
    echo "--- Current Compute Apps ---" >&2
    nvidia-smi --query-compute-apps=pid,used_memory --format=csv >&2 || true
    echo "----------------------------" >&2
    exit 1
fi

# ------------------------------------------------------------------------------
# 4. Start Server with setsid & Wait for /v1/models (Health Check)
# ------------------------------------------------------------------------------
echo "[INFO] Launching server on port ${PORT} with setsid..." >&2
setsid bash -c "$SERVER_CMD" &
SERVER_PID=$!
echo "[INFO] Server launched (PID/PGID: $SERVER_PID)" >&2

echo "[INFO] Waiting for server on 127.0.0.1:${PORT}/v1/models (timeout: ${TIMEOUT_STARTUP}s)..." >&2
start_wait=$(date +%s)

while true; do
    if ! server_is_alive; then
        echo "ERROR: Server process ($SERVER_PID) exited unexpectedly during startup." >&2
        wait "$SERVER_PID" 2>/dev/null || true
        exit 1
    fi

    http_code=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${PORT}/v1/models" 2>/dev/null || echo "000")
    if [[ "$http_code" == "200" ]]; then
        break
    fi

    now=$(date +%s)
    if (( now - start_wait > TIMEOUT_STARTUP )); then
        echo "ERROR: Timed out waiting for server on port ${PORT} to be ready after ${TIMEOUT_STARTUP}s." >&2
        exit 1
    fi
    sleep 1
done

echo "[INFO] Server is ready." >&2
sleep 1

loaded_MiB=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | tr -d ' ' | head -n 1 || true)
if [[ -z "$loaded_MiB" ]]; then
    loaded_MiB=$(tail -n 1 "$CSV_FILE" 2>/dev/null | tr -d ' ' || true)
fi
if [[ -z "$loaded_MiB" || ! "$loaded_MiB" =~ ^[0-9]+$ ]]; then
    echo "ERROR: Failed to read loaded VRAM from nvidia-smi." >&2
    exit 1
fi
echo "[INFO] Loaded VRAM: ${loaded_MiB} MiB" >&2

# ------------------------------------------------------------------------------
# 5. Send Real Inference Request (1 request)
# ------------------------------------------------------------------------------
get_mime_type() {
    local file="$1"
    case "${file##*.}" in
        jpg|jpeg|JPG|JPEG) echo "image/jpeg" ;;
        png|PNG)           echo "image/png" ;;
        webp|WEBP)         echo "image/webp" ;;
        *)                 echo "image/jpeg" ;;
    esac
}
MIME_TYPE="$(get_mime_type "$SAMPLE_IMAGE")"

req_start_line=$(wc -l < "$CSV_FILE" 2>/dev/null || echo 0)
req_start_line=$(( req_start_line + 1 ))

HTTP_RESP_FILE=$(mktemp)
echo "[INFO] Sending 1 inference request for mode '$MODE'..." >&2

if [[ "$MODE" == "text" ]]; then
    IMAGE_B64=$(base64 < "$SAMPLE_IMAGE" | tr -d '\r\n')
    PAYLOAD_FILE=$(mktemp)
    cat <<EOF > "$PAYLOAD_FILE"
{
  "model": "${MODEL_NAME}",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "이 공예품/상품 이미지를 자세히 분석하여 시각적 특징, 색상, 형태, 재질을 설명하세요."
        },
        {
          "type": "image_url",
          "image_url": {
            "url": "data:${MIME_TYPE};base64,${IMAGE_B64}"
          }
        }
      ]
    }
  ],
  "temperature": 0,
  "max_tokens": 512,
  "stream": false
}
EOF
    http_result=$(curl -s -S -o "$HTTP_RESP_FILE" -w "%{http_code} %{time_total}" \
        -X POST "http://127.0.0.1:${PORT}/v1/chat/completions" \
        -H "Content-Type: application/json" \
        --max-time "$TIMEOUT_REQUEST" \
        -d @"$PAYLOAD_FILE" 2>&1 || echo "000 0")
    rm -f "$PAYLOAD_FILE"
    PAYLOAD_FILE=""
else
    # SGLang image edit route (multipart form)
    http_result=$(curl -s -S -o "$HTTP_RESP_FILE" -w "%{http_code} %{time_total}" \
        -X POST "http://127.0.0.1:${PORT}/v1/images/edits" \
        --max-time "$TIMEOUT_REQUEST" \
        -F "model=${MODEL_NAME}" \
        -F "prompt=close-up detail view of craft product, high resolution, sharp focus" \
        -F "n=1" \
        -F "size=${IMAGE_SIZE}" \
        -F "response_format=b64_json" \
        -F "num_inference_steps=4" \
        -F "image=@${SAMPLE_IMAGE};type=${MIME_TYPE}" 2>&1 || echo "000 0")
fi

http_status=$(echo "$http_result" | awk '{print $1}')
elapsed_s=$(echo "$http_result" | awk '{print $2}')

# Check server liveness
if ! server_is_alive; then
    echo "ERROR: Server process ($SERVER_PID) crashed during inference request." >&2
    exit 1
fi

# Verify response
if [[ "$http_status" != "200" ]]; then
    echo "ERROR: Request failed with HTTP status ${http_status}." >&2
    if [[ -f "$HTTP_RESP_FILE" ]]; then
        echo "Response body: $(head -c 500 "$HTTP_RESP_FILE")" >&2
    fi
    exit 1
fi

if [[ "$MODE" == "text" ]]; then
    if ! grep -q '"choices"' "$HTTP_RESP_FILE" 2>/dev/null; then
        echo "ERROR: Response JSON does not contain 'choices': $(head -c 300 "$HTTP_RESP_FILE")" >&2
        exit 1
    fi
else
    if ! grep -q '"data"' "$HTTP_RESP_FILE" 2>/dev/null; then
        echo "ERROR: Image response does not contain 'data': $(head -c 300 "$HTTP_RESP_FILE")" >&2
        exit 1
    fi
fi

echo "[INFO] Request succeeded in ${elapsed_s}s." >&2

# ------------------------------------------------------------------------------
# 6. Calculate Peak VRAM During Request Window
# ------------------------------------------------------------------------------
sleep 1
req_end_line=$(wc -l < "$CSV_FILE" 2>/dev/null || echo 0)

if (( req_start_line > req_end_line )); then
    echo "ERROR: No VRAM samples were recorded during the inference request window (lines ${req_start_line}-${req_end_line})." >&2
    exit 1
fi

peak_MiB=$(sed -n "${req_start_line},${req_end_line}p" "$CSV_FILE" 2>/dev/null | tr -d ' ' | grep -E '^[0-9]+$' | sort -n | tail -n 1 || true)

if [[ -z "$peak_MiB" || ! "$peak_MiB" =~ ^[0-9]+$ ]]; then
    echo "ERROR: Failed to extract valid peak VRAM from request window samples (lines ${req_start_line}-${req_end_line})." >&2
    exit 1
fi

if (( peak_MiB < loaded_MiB )); then
    peak_MiB="$loaded_MiB"
fi

# ------------------------------------------------------------------------------
# 7. Stop Server and Sampler, Verify VRAM Reclamation
# ------------------------------------------------------------------------------
echo "[INFO] Stopping server..." >&2
stop_server_group

if [[ -n "$SAMPLER_PID" ]] && kill -0 "$SAMPLER_PID" 2>/dev/null; then
    kill -TERM "$SAMPLER_PID" 2>/dev/null || true
    for _ in {1..3}; do
        kill -0 "$SAMPLER_PID" 2>/dev/null || break
        sleep 0.2
    done
    if kill -0 "$SAMPLER_PID" 2>/dev/null; then
        kill -KILL "$SAMPLER_PID" 2>/dev/null || true
    fi
    wait "$SAMPLER_PID" 2>/dev/null || true
    SAMPLER_PID=""
fi

# Verify VRAM returned close to baseline
sleep 2
final_MiB=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | tr -d ' ' | head -n 1 || true)
if [[ -n "$final_MiB" && "$final_MiB" =~ ^[0-9]+$ ]]; then
    echo "[INFO] Post-termination VRAM: ${final_MiB} MiB (baseline: ${baseline_MiB} MiB)" >&2
    if (( final_MiB > baseline_MiB + 512 )); then
        echo "[WARN] Post-termination VRAM (${final_MiB} MiB) did not return close to baseline (${baseline_MiB} MiB)." >&2
        echo "[WARN] Lingering processes may still hold GPU memory:" >&2
        nvidia-smi --query-compute-apps=pid,used_memory --format=csv >&2 || true
    fi
fi

# ------------------------------------------------------------------------------
# 8. Output Summary Line
# ------------------------------------------------------------------------------
echo "$MODE $baseline_MiB $loaded_MiB $peak_MiB 1 $elapsed_s"
echo "CSV: $CSV_FILE"
