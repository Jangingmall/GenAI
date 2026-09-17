import json
from pathlib import Path

from detail_page_ai.dto import AiFeStatusResponse


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = ROOT / "tests/fixtures/images-2"
GENERATED_SAMPLE_ROOT = Path("/generated/samples/images-2")


def _fixture_path(image_url: str) -> Path:
    """Resolve a generated response URL to the tracked sample fixture."""
    return SAMPLE_DIR / Path(image_url).relative_to(GENERATED_SAMPLE_ROOT)


def test_images2_sample_contains_a_valid_fe_response_and_rendered_assets():
    response_path = SAMPLE_DIR / "ai-fe-response.json"
    response = AiFeStatusResponse.model_validate_json(response_path.read_text(encoding="utf-8"))

    assert response.status == "COMPLETED"
    assert response.progress == 100
    assert response.result is not None
    assert response.result.product.display_name == "메탈 티웨어 오브제 세트"
    assert response.result.detail_page.image_url == "/generated/samples/images-2/detail_page.png"
    assert response.result.detail_page.image_base64 is None
    assert response.result.detail_page.mime_type == "image/png"
    assert len(response.result.detail_page.sections) == 11
    assert len(response.result.detail_page.photos) == 4

    for section in response.result.detail_page.sections:
        assert section.image_url is not None
        assert _fixture_path(section.image_url).is_file()

    for photo in response.result.detail_page.photos:
        assert photo.image_url is not None
        assert photo.product_generated is False
        assert _fixture_path(photo.image_url).is_file()

    assert (ROOT / "assets/samples/images-2.jpeg").is_file()
    assert (SAMPLE_DIR / "product-profile.json").is_file()
    assert json.loads(response_path.read_text(encoding="utf-8"))["result"]["detail_page"]["sections"]
