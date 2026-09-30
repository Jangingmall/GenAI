import os
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "deploy/sglang/entrypoint.sh"


def run_entrypoint(
    *,
    text_model: str,
    image_model: str,
    text_max_running_requests: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("TEXT_MAX_RUNNING_REQUESTS", None)
    env.update(
        {
            "DRY_RUN": "1",
            "TEXT_MODEL_PATH": text_model,
            "TEXT_MODEL_REVISION": "text-sha",
            "IMAGE_MODEL_PATH": image_model,
            "IMAGE_MODEL_REVISION": "image-sha",
        }
    )
    if text_max_running_requests is not None:
        env["TEXT_MAX_RUNNING_REQUESTS"] = text_max_running_requests
    return subprocess.run(
        ["bash", str(ENTRYPOINT)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def command_lines(result: subprocess.CompletedProcess[str]) -> tuple[str, str]:
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("TEXT:")
    assert lines[1].startswith("IMAGE:")
    return lines[0], lines[1]


def test_huggingface_paths_keep_revisions() -> None:
    result = run_entrypoint(
        text_model="cyankiwi/Qwen3.8-27B-AWQ-INT4",
        image_model="circulus/FLUX.2-klein-9B-bnb-4bit",
    )

    text_line, image_line = command_lines(result)
    assert "--revision text-sha" in text_line
    assert "--revision image-sha" in image_line
    assert "HF_HUB_OFFLINE=1" not in result.stdout


def test_local_paths_omit_revisions_and_enable_hub_offline(tmp_path: Path) -> None:
    text_model = tmp_path / "qwen"
    image_model = tmp_path / "flux"
    text_model.mkdir()
    image_model.mkdir()
    # 텍스트·비전은 transformers 규약(config.json), 이미지 확산은 diffusers
    # 규약(model_index.json)이다. 배포 모델 circulus/FLUX.2-klein-9B-bnb-4bit 의
    # 루트에는 config.json 이 없다.
    (text_model / "config.json").write_text("{}", encoding="utf-8")
    (image_model / "model_index.json").write_text("{}", encoding="utf-8")

    result = run_entrypoint(
        text_model=str(text_model),
        image_model=str(image_model),
    )

    text_line, image_line = command_lines(result)
    assert "HF_HUB_OFFLINE=1" in text_line
    assert "HF_HUB_OFFLINE=1" in image_line
    assert "--revision" not in text_line
    assert "--revision" not in image_line


def test_text_local_and_image_huggingface_modes_are_independent(tmp_path: Path) -> None:
    text_model = tmp_path / "qwen"
    text_model.mkdir()
    (text_model / "config.json").write_text("{}", encoding="utf-8")

    result = run_entrypoint(
        text_model=str(text_model),
        image_model="circulus/FLUX.2-klein-9B-bnb-4bit",
    )

    text_line, image_line = command_lines(result)
    assert "HF_HUB_OFFLINE=1" in text_line
    assert "--revision" not in text_line
    assert "HF_HUB_OFFLINE=1" not in image_line
    assert "--revision image-sha" in image_line


def test_local_model_without_config_fails_before_startup(tmp_path: Path) -> None:
    text_model = tmp_path / "qwen"
    text_model.mkdir()

    result = run_entrypoint(
        text_model=str(text_model),
        image_model="circulus/FLUX.2-klein-9B-bnb-4bit",
    )

    assert result.returncode != 0
    assert f"TEXT_MODEL_PATH={text_model}" in result.stderr
    assert "config.json" in result.stderr
    assert "S3" in result.stderr


def test_local_diffusion_model_is_checked_with_model_index(tmp_path: Path) -> None:
    """확산 모델은 config.json 이 아니라 model_index.json 으로 판정한다."""
    text_model = tmp_path / "qwen"
    image_model = tmp_path / "flux"
    text_model.mkdir()
    image_model.mkdir()
    (text_model / "config.json").write_text("{}", encoding="utf-8")
    # config.json 만 있고 model_index.json 이 없으면 불완전한 확산 모델이다.
    (image_model / "config.json").write_text("{}", encoding="utf-8")

    result = run_entrypoint(
        text_model=str(text_model),
        image_model=str(image_model),
    )

    assert result.returncode != 0
    assert f"IMAGE_MODEL_PATH={image_model}" in result.stderr
    assert "model_index.json" in result.stderr


def test_dry_run_adds_max_running_requests_when_configured() -> None:
    result = run_entrypoint(
        text_model="cyankiwi/Qwen3.8-27B-AWQ-INT4",
        image_model="circulus/FLUX.2-klein-9B-bnb-4bit",
        text_max_running_requests="3",
    )

    text_line, _ = command_lines(result)
    assert "--max-running-requests 3" in text_line


def test_dry_run_omits_max_running_requests_when_unconfigured() -> None:
    result = run_entrypoint(
        text_model="cyankiwi/Qwen3.8-27B-AWQ-INT4",
        image_model="circulus/FLUX.2-klein-9B-bnb-4bit",
    )

    text_line, _ = command_lines(result)
    assert "--max-running-requests" not in text_line


def _write_executable(path: Path, contents: str) -> None:
    path.write_text(contents, encoding="utf-8")
    path.chmod(0o755)


def _run_fake_runtime(
    tmp_path: Path, *, text_fails_before_ready: bool = False
) -> tuple[int, list[str], str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    events_file = tmp_path / "events.log"
    text_ready_file = tmp_path / "text-ready"
    image_ready_file = tmp_path / "image-ready"

    _write_executable(
        bin_dir / "sglang-python",
        """#!/usr/bin/env bash
set -eu
if [[ "${1:-}" == "-c" ]]; then
    if [[ "${3:-}" == "30000" ]]; then
        printf 'probe-text\\n' >> "$EVENTS_FILE"
        [[ -f "$TEXT_READY_FILE" ]]
    elif [[ "${3:-}" == "30001" ]]; then
        printf 'probe-image\\n' >> "$EVENTS_FILE"
        [[ -f "$IMAGE_READY_FILE" ]]
    else
        exit 2
    fi
    exit 0
fi
if [[ "${1:-}" == "-m" ]]; then
    printf 'text-start\\n' >> "$EVENTS_FILE"
    if [[ "${FAIL_TEXT:-0}" == "1" ]]; then
        exit 7
    fi
    (
        sleep 0.1
        touch "$TEXT_READY_FILE"
        printf 'text-ready\\n' >> "$EVENTS_FILE"
    ) &
    trap 'exit 0' TERM INT
    while :; do sleep 0.05; done
fi
exit 2
""",
    )
    _write_executable(
        bin_dir / "sglang",
        """#!/usr/bin/env bash
set -eu
printf 'image-start\\n' >> "$EVENTS_FILE"
(
    sleep 0.1
    touch "$IMAGE_READY_FILE"
    printf 'image-ready\\n' >> "$EVENTS_FILE"
) &
trap 'exit 0' TERM INT
while :; do sleep 0.05; done
""",
    )
    _write_executable(
        bin_dir / "serve-ai",
        """#!/usr/bin/env bash
set -eu
printf 'api-start\\n' >> "$EVENTS_FILE"
trap 'exit 0' TERM INT
while :; do sleep 0.05; done
""",
    )
    _write_executable(
        bin_dir / "nvidia-smi",
        """#!/usr/bin/env bash
printf 'vram\\n' >> "$EVENTS_FILE"
printf '123 MiB, 456 MiB\\n'
""",
    )

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "EVENTS_FILE": str(events_file),
            "TEXT_READY_FILE": str(text_ready_file),
            "IMAGE_READY_FILE": str(image_ready_file),
            "TEXT_READY_TIMEOUT": "5",
            "TEXT_MODEL_PATH": "text-model",
            "TEXT_MODEL_REVISION": "text-sha",
            "IMAGE_MODEL_PATH": "image-model",
            "IMAGE_MODEL_REVISION": "image-sha",
            "ASSET_STORE_DIR": str(tmp_path / "assets"),
            "U2NET_HOME": str(tmp_path / "u2net"),
            "HF_HOME": str(tmp_path / "hf"),
            "HF_HUB_CACHE": str(tmp_path / "hf-hub"),
            "HF_DATASETS_CACHE": str(tmp_path / "hf-datasets"),
            "TRANSFORMERS_CACHE": str(tmp_path / "transformers"),
            "XDG_CACHE_HOME": str(tmp_path / "xdg"),
            "TORCH_HOME": str(tmp_path / "torch"),
            "SGLANG_CACHE_DIR": str(tmp_path / "sglang-cache"),
            "FLASHINFER_CACHE_DIR": str(tmp_path / "flashinfer"),
            "TRITON_CACHE_DIR": str(tmp_path / "triton"),
            "TORCHINDUCTOR_CACHE_DIR": str(tmp_path / "torchinductor"),
            "CUDA_CACHE_PATH": str(tmp_path / "cuda"),
            "SQLITE_PATH": str(tmp_path / "state.sqlite3"),
        }
    )
    if text_fails_before_ready:
        env["FAIL_TEXT"] = "1"

    process = subprocess.Popen(
        ["bash", str(ENTRYPOINT)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        events = events_file.read_text(encoding="utf-8").splitlines() if events_file.exists() else []
        if events.count("vram") >= 2 or text_fails_before_ready:
            break
        time.sleep(0.02)

    if process.poll() is None and not text_fails_before_ready:
        process.terminate()
    try:
        stdout, stderr = process.communicate(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
    events = events_file.read_text(encoding="utf-8").splitlines() if events_file.exists() else []
    return process.returncode, events, stderr


def test_api_starts_before_image_and_image_waits_for_text(tmp_path: Path) -> None:
    returncode, events, stderr = _run_fake_runtime(tmp_path)

    assert returncode == 0, stderr
    assert events.index("api-start") < events.index("image-start")
    assert events.index("text-ready") < events.index("image-start")
    assert "VRAM text-ready: 123 MiB, 456 MiB" in stderr
    assert "VRAM image-ready: 123 MiB, 456 MiB" in stderr


def test_text_failure_before_ready_does_not_start_image(tmp_path: Path) -> None:
    returncode, events, stderr = _run_fake_runtime(
        tmp_path, text_fails_before_ready=True
    )

    assert returncode != 0
    assert "api-start" in events
    assert "text-start" in events
    assert "image-start" not in events
    assert "text server" in stderr


def test_default_text_context_fits_the_analysis_request() -> None:
    # Stage 2026-09-30: the analysis request (prompt + JSON schema + one 1280px
    # photo) was 9307 input tokens, plus up to 4096 output tokens, and SGLang
    # rejected it at 8192. The image ENV and the entrypoint default must agree.
    result = run_entrypoint(
        text_model="cyankiwi/Qwen3.8-27B-AWQ-INT4",
        image_model="circulus/FLUX.2-klein-9B-bnb-4bit",
    )

    text_line, _ = command_lines(result)
    assert "--context-length 16384" in text_line
    dockerfile = (ROOT / "deploy/sglang/Dockerfile").read_text()
    assert "TEXT_CONTEXT_LENGTH=16384" in dockerfile
