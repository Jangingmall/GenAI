from pathlib import Path


def _parse_env(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key] = value
    return values


def test_env_example_contains_placeholders_not_credentials():
    values = _parse_env(Path(".env.example"))

    assert values["ANALYSIS_PROVIDER"] == "local"
    assert values["LOCAL_TEXT_MODEL"] == "ddalcu/Qwen3.8-27B-MLX-Serve-4bit"
    assert values["LOCAL_IMAGE_MODEL"] == "mlx-community/flux2-klein-9b-4bit"
    assert "AWS_ACCESS_KEY_ID" not in values
    assert "GEMINI_API_KEY" not in values


def test_local_env_example_has_no_gemini_or_cloud_credentials():
    local_env = Path("local.env.example").read_text(encoding="utf-8")

    assert "GEMINI" not in local_env
    assert "AWS_ACCESS_KEY_ID" not in local_env
    assert "AWS_SECRET_ACCESS_KEY" not in local_env


def test_sensitive_and_generated_local_files_are_ignored():
    ignored = set(Path(".gitignore").read_text(encoding="utf-8").splitlines())

    assert ".env" in ignored
    assert ".env.local" in ignored
    assert ".local/" in ignored
    assert "generated/" in ignored
