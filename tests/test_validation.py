import pytest
from io import BytesIO
from PIL import Image

from detail_page_ai.dto import PageBlockDto, ProductProfileDto
from detail_page_ai.validation import (
    ensure_editorial_page_plan,
    InvalidImageError,
    ProfileValidationError,
    validate_product_profile,
    validate_source_image,
)


def test_invalid_image_is_rejected():
    with pytest.raises(InvalidImageError):
        validate_source_image(b"not-an-image", "image/png")


def test_valid_png_is_accepted():
    validate_source_image(b"\x89PNG\r\n\x1a\nimage", "image/png")


def test_production_image_validation_can_require_actual_decodability():
    with pytest.raises(InvalidImageError):
        validate_source_image(
            b"\x89PNG\r\n\x1a\nimage", "image/png", require_decodable=True
        )

    output = BytesIO()
    Image.new("RGB", (2, 2), "white").save(output, format="PNG")
    validate_source_image(
        output.getvalue(), "image/png", require_decodable=True
    )


def test_profile_rejects_unbounded_long_copy():
    profile = ProductProfileDto.minimal("desk lamp").model_copy(
        update={"summary": "x" * 501}
    )

    with pytest.raises(ProfileValidationError):
        validate_product_profile(profile)


def test_editorial_plan_fills_missing_recommendation_without_replacing_ai_order():
    profile = ProductProfileDto.minimal("금속 차기 세트").model_copy(
        update={
            "display_name": "금속 차기 세트",
            "page_plan": [
                PageBlockDto(
                    section_id="hero",
                    block_type="hero",
                    title="차 한 잔의 풍경",
                    photo_id="hero",
                ),
                PageBlockDto(
                    section_id="texture",
                    block_type="detail_split",
                    title="표면의 결",
                    photo_id="detail",
                ),
                PageBlockDto(
                    section_id="scene",
                    block_type="usage_scene",
                    title="차를 내는 시간",
                    photo_id="lifestyle",
                ),
                PageBlockDto(
                    section_id="info",
                    block_type="info_table",
                    title="제품 정보",
                ),
                PageBlockDto(
                    section_id="closing",
                    block_type="closing",
                    title="오래 남는 인상",
                ),
            ],
        }
    )

    normalized = ensure_editorial_page_plan(profile)
    block_types = [block.block_type for block in normalized.page_plan]

    assert block_types.index("hero") < block_types.index("detail_split")
    assert block_types.index("detail_split") < block_types.index("usage_scene")
    assert block_types.index("recommendation") < block_types.index("info_table")
    assert block_types[-1] == "closing"
    assert normalized.page_plan[block_types.index("detail_split")].variant == "dark"
    assert normalized.page_plan[block_types.index("usage_scene")].variant == "full-bleed"
    assert normalized.page_plan[block_types.index("usage_scene")].photo_id == "lifestyle"


def test_editorial_plan_does_not_modify_profiles_without_ai_page_plan():
    profile = ProductProfileDto.minimal("보관함")

    assert ensure_editorial_page_plan(profile) == profile


def test_editorial_plan_keeps_palette_and_adds_missing_product_gallery():
    profile = ProductProfileDto.minimal("유리 오브제").model_copy(
        update={
            "page_plan": [
                PageBlockDto(
                    section_id="hero",
                    block_type="hero",
                    title="유리 오브제",
                    photo_id="hero",
                ),
                PageBlockDto(
                    section_id="scene",
                    block_type="usage_scene",
                    title="공간 속 연출",
                    photo_id="lifestyle",
                ),
                PageBlockDto(
                    section_id="palette",
                    block_type="palette",
                    title="흑백 색감",
                ),
                PageBlockDto(
                    section_id="closing",
                    block_type="closing",
                    title="오래 남는 인상",
                ),
            ],
        }
    )

    normalized = ensure_editorial_page_plan(profile)
    block_types = [block.block_type for block in normalized.page_plan]

    assert block_types.count("gallery") == 1
    assert block_types.count("palette") == 1
    assert block_types.index("usage_scene") < block_types.index("gallery")
    assert block_types.index("gallery") < block_types.index("palette")
