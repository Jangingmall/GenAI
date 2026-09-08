from detail_page_ai.dto import ProductProfileDto
from detail_page_ai.html_renderer import build_detail_page_html


def test_non_image_evidence_is_not_rendered_as_product_selling_copy():
    profile = ProductProfileDto.model_validate(
        {
            **ProductProfileDto.minimal("장식함").model_dump(),
            **{
            "features": [
                {
                    "title": "이미지에 보이는 문양",
                    "description": "표면의 반복 무늬가 확인됩니다.",
                    "evidence": "image-visible",
                },
                {
                    "title": "확정할 수 없는 소재",
                    "description": "최고급 자개로 제작되었다고 단정합니다.",
                    "evidence": "inferred",
                },
            ],
            "copy_sections": [
                {
                    "section_type": "hero",
                    "title": "이미지에 보이는 문양",
                    "description": "표면의 반복 무늬가 확인됩니다.",
                    "evidence": "image-visible",
                },
                {
                    "section_type": "benefit",
                    "title": "확정할 수 없는 소재",
                    "description": "최고급 자개로 제작되었다고 단정합니다.",
                    "evidence": "inferred",
                },
            ],
            },
        }
    )

    html = build_detail_page_html(
        profile, b"\x89PNG\r\n\x1a\nimage", mime_type="image/png"
    )

    assert "이미지에 보이는 문양" in html
    assert "<h3>확정할 수 없는 소재</h3>" not in html
    assert "최고급 자개로 제작되었다고 단정합니다." not in html
    assert "검증되지 않은 AI 추정 문구 제외" in html
