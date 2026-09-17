from detail_page_ai.config import Settings
from pydantic import ValidationError
import pytest


def test_html_renderer_is_the_default_detail_page_generation_mode():
    settings = Settings(_env_file=None)

    assert settings.detail_page_renderer == "html"


def test_generative_final_page_renderer_is_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, DETAIL_PAGE_RENDERER="gemini")


def test_runtime_app_has_no_cloud_provider_imports():
    from pathlib import Path

    app_source = Path("src/detail_page_ai/app.py").read_text(encoding="utf-8")

    assert "Gemini" not in app_source
    assert "Bedrock" not in app_source


def test_local_analysis_and_source_safe_photos_are_the_defaults():
    settings = Settings(_env_file=None)

    assert settings.analysis_provider == "local"
    assert settings.product_photo_generation == "source"
    assert settings.local_text_model == "ddalcu/Qwen3.8-27B-MLX-Serve-4bit"
    assert settings.local_image_model == "mlx-community/flux2-klein-9b-4bit"


def test_local_models_are_the_only_service_defaults():
    settings = Settings(_env_file=None)

    assert settings.analysis_provider == "local"
    assert settings.local_text_provider == "mlx"
    assert settings.local_text_url == "http://127.0.0.1:11234"
    assert settings.local_text_model == "ddalcu/Qwen3.8-27B-MLX-Serve-4bit"
    assert settings.local_image_provider == "mlx"
    assert settings.local_image_url == "http://127.0.0.1:11234"
    assert settings.local_image_model == "mlx-community/flux2-klein-9b-4bit"
    assert settings.background_provider == "mlx"
    assert not hasattr(settings, "gemini_api_key")


def test_sglang_text_and_image_providers_are_valid_settings():
    settings = Settings(
        _env_file=None,
        LOCAL_TEXT_PROVIDER="sglang",
        LOCAL_IMAGE_PROVIDER="sglang",
        BACKGROUND_PROVIDER="sglang",
    )

    assert settings.local_text_provider == "sglang"
    assert settings.local_image_provider == "sglang"
    assert settings.background_provider == "sglang"


def test_cloud_analysis_provider_is_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ANALYSIS_PROVIDER="gemini")


def test_source_safe_local_storage_is_the_default():
    settings = Settings(_env_file=None)

    assert settings.asset_store_dir == ".local/detail-page-ai/assets"
    assert settings.sqlite_path == ".local/detail-page-ai/state.sqlite3"
    assert settings.response_asset_mode == "base64"
    assert settings.craft_confidence_threshold == 0.65
    assert settings.product_photo_shots == "hero,packshot,detail,lifestyle"
    assert settings.prompt_version == "local-mlx-qwen-flux-v1"
    assert settings.max_generated_photos == 5


def test_max_generated_photos_accepts_zero_and_uses_the_new_environment_alias():
    settings = Settings(_env_file=None, MAX_GENERATED_PHOTOS=0)

    assert settings.max_generated_photos == 0


@pytest.mark.parametrize("value", [-1, 13])
def test_max_generated_photos_rejects_values_outside_zero_to_twelve(value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, MAX_GENERATED_PHOTOS=value)
