import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "deploy/sglang/entrypoint.sh"


def run_entrypoint(*, text_model: str, image_model: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "DRY_RUN": "1",
            "TEXT_MODEL_PATH": text_model,
            "TEXT_MODEL_REVISION": "text-sha",
            "IMAGE_MODEL_PATH": image_model,
            "IMAGE_MODEL_REVISION": "image-sha",
        }
    )
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
    (text_model / "config.json").write_text("{}", encoding="utf-8")
    (image_model / "config.json").write_text("{}", encoding="utf-8")

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
