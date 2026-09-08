import importlib
import json
import re
from pathlib import Path

import pytest

from detail_page_ai.dto import CraftResearchDto, PageBlockDto, ProductProfileDto
from detail_page_ai.models import ProductPhoto, ProductPhotoSet


def sample_profile() -> ProductProfileDto:
    return ProductProfileDto(
        product_type="패턴 스카프",
        display_name="컬러 패턴 스카프",
        summary="민트 그린 바탕에 새와 동물, 꽃 문양이 어우러진 패턴 스카프입니다.",
        keywords=["패턴", "컬러 포인트", "크레인", "플로럴"],
        observations={
            "colors": ["민트 그린", "레드", "오렌지", "블루"],
            "visible_motifs": ["새", "사슴 형태의 동물", "꽃", "식물"],
        },
        features=[
            {
                "title": "선명한 색감",
                "description": "민트 그린 바탕에 레드, 오렌지, 블루 포인트가 보입니다.",
                "evidence": "image-visible",
                "confidence": 0.98,
            },
            {
                "title": "섬세한 문양",
                "description": "새와 동물, 꽃과 식물이 촘촘하게 표현되어 있습니다.",
                "evidence": "image-visible",
                "confidence": 0.97,
            },
            {
                "title": "풍성한 테두리",
                "description": "레드와 오렌지, 블루가 이어지는 테두리가 보입니다.",
                "evidence": "image-visible",
                "confidence": 0.96,
            },
        ],
        copy_sections=[
            {
                "section_type": "hero",
                "title": "전통적인 패턴의 컬러 포인트",
                "description": "선명한 색감과 섬세한 문양이 시선을 끄는 패턴 스카프입니다.",
            },
        ],
        usage_scene="가방이나 옷차림에 포인트로 연출하는 장면",
        uncertain_information=["정확한 소재, 규격, 가격, 브랜드 정보"],
        safety_notes=["이미지에서 확인되지 않는 정보는 별도 확인이 필요합니다."],
    )


def test_html_renderer_injects_escaped_profile_and_data_uri():
    renderer = importlib.import_module("detail_page_ai.html_renderer")

    html = renderer.build_detail_page_html(
        sample_profile(), b"\xff\xd8\xffjpeg", mime_type="image/jpeg"
    )

    assert "컬러 패턴 스카프" in html
    assert "data:image/jpeg;base64,/9j/" in html
    assert "선명한 색감" in html
    assert "전통적인 패턴의 컬러 포인트" in html
    assert "가격, 브랜드 정보" in html
    assert "<script" not in html.lower()


@pytest.mark.parametrize("count", [1, 2, 3, 4, 5])
def test_gallery_only_renders_available_unique_images(count):
    renderer = importlib.import_module("detail_page_ai.html_renderer")
    ids = ("detail", "detail-02", "detail-03", "detail-04", "detail-05")[:count]
    photos = tuple(
        ProductPhoto(photo_id=photo_id, order=index, label=photo_id,
                     data=f"photo-{index}".encode(), mime_type="image/png",
                     source_sha256="source-hash", fidelity_status="VERIFIED", product_generated=False)
        for index, photo_id in enumerate(ids, 1)
    )
    html = renderer.build_detail_page_html(sample_profile(), b"source",
                                          photo_set=ProductPhotoSet(photos=photos))
    gallery = html.split('data-section="detail-cuts"', 1)[1].split("</section>", 1)[0]
    images = re.findall(r'<img[^>]+src="([^"]+)"', gallery)
    assert len(images) == len(set(images)) == count
    assert not re.search(r'<div class="detail-grid[^\"]*">\s*</div>', gallery)


def test_gallery_deduplicates_same_bytes_in_different_slots():
    renderer = importlib.import_module("detail_page_ai.html_renderer")
    photos = tuple(
        ProductPhoto(photo_id=photo_id, order=index, label=photo_id, data=b"same",
                     mime_type="image/png", source_sha256="source-hash", fidelity_status="VERIFIED", product_generated=False)
        for index, photo_id in enumerate(("detail", "detail-02", "detail-03"), 1)
    )
    html = renderer.build_detail_page_html(sample_profile(), b"source",
                                          photo_set=ProductPhotoSet(photos=photos))
    gallery = html.split('data-section="detail-cuts"', 1)[1].split("</section>", 1)[0]
    assert gallery.count("<img ") == 1


def test_recommendation_numbers_are_local_without_duplicate_numeric_headings():
    renderer = importlib.import_module("detail_page_ai.html_renderer")
    profile = sample_profile().model_copy(update={"page_plan": [
        PageBlockDto(section_id="intro", block_type="statement", title="소개"),
        PageBlockDto(section_id="recommend", block_type="recommendation", items=[
            {"label": "01", "value": "여유 있는 티타임"},
            {"label": "공간 & 선물", "value": "일상에 작은 포인트"},
        ]),
    ]})
    html = renderer.build_detail_page_html(profile, b"source")
    cards = html.split('class="recommendation-grid"', 1)[1].split("</section>", 1)[0]
    assert re.findall(r'<article><span>(\d+)</span>', cards) == ["01", "02"]
    assert "<h3>01</h3>" not in cards
    assert "<h3>공간 &amp; 선물</h3>" in cards
    assert "여유 있는 티타임" in cards


def test_html_renderer_uses_reference_layout_sections_and_design_tokens():
    renderer = importlib.import_module("detail_page_ai.html_renderer")

    html = renderer.build_detail_page_html(
        sample_profile(), b"\xff\xd8\xffjpeg", mime_type="image/jpeg"
    )

    assert 'class="hero"' in html
    assert 'class="feature-grid"' in html
    assert 'class="split-section' in html
    assert 'class="detail-grid detail-grid--one"' in html
    assert 'class="detail-grid detail-grid--two"' not in html
    assert "#101010" in html
    assert "#FAFBFC" in html


def test_html_renderer_applies_selected_layout_variant():
    renderer = importlib.import_module("detail_page_ai.html_renderer")

    html = renderer.build_detail_page_html(
        sample_profile().model_copy(update={"layout_id": "image-first"}),
        b"\xff\xd8\xffjpeg",
        mime_type="image/jpeg",
    )

    assert '<main class="detail-page detail-page--image-first">' in html


def test_html_renderer_follows_ai_composed_page_plan_order_and_blocks():
    renderer = importlib.import_module("detail_page_ai.html_renderer")
    profile = sample_profile().model_copy(
        update={
            "page_plan": [
                {
                    "section_id": "hero",
                    "block_type": "hero",
                    "eyebrow": "OBJECT TEA ART",
                    "title": "차잔을 넘어",
                    "body": "테이블에 남는 형상",
                    "variant": "paper",
                    "photo_id": "hero",
                },
                {
                    "section_id": "usage-scene",
                    "block_type": "usage_scene",
                    "eyebrow": "PREMIUM TEA TIME",
                    "title": "차를 내는 순간",
                    "body": "한 장면으로 정리됩니다.",
                    "variant": "dark",
                    "photo_id": "lifestyle",
                },
                {
                    "section_id": "palette",
                    "block_type": "palette",
                    "eyebrow": "PRODUCT GALLERY",
                    "title": "4가지 금속 컬러",
                    "body": "빛에 따라 달라지는 표면을 살펴봅니다.",
                    "variant": "paper",
                    "items": [
                        {
                            "label": "Gold",
                            "value": "금빛",
                            "description": "따뜻한 금속 색감",
                        }
                    ],
                },
            ]
        }
    )

    html = renderer.build_detail_page_html(
        profile, b"\xff\xd8\xffjpeg", mime_type="image/jpeg"
    )

    assert html.index('data-section="usage-scene"') < html.index('data-section="palette"')
    assert 'class="palette-section' in html
    assert "차를 내는 순간" in html
    assert 'data-section="core-value"' not in html


def test_html_renderer_uses_source_preserved_lifestyle_for_usage_block():
    renderer = importlib.import_module("detail_page_ai.html_renderer")
    profile = sample_profile().model_copy(
        update={
            "page_plan": [
                {
                    "section_id": "usage-scene",
                    "block_type": "usage_scene",
                    "eyebrow": "PREMIUM TEA TIME",
                    "title": "차를 내는 순간",
                    "body": "손끝에서 완성되는 한 장면입니다.",
                    "variant": "dark",
                    "photo_id": "lifestyle",
                }
            ]
        }
    )
    photo_set = ProductPhotoSet(
        photos=(
            ProductPhoto(
                photo_id="lifestyle",
                order=1,
                label="원본 배열",
                data=b"source-lifestyle",
                mime_type="image/png",
                source_sha256="source-hash",
                product_generated=False,
                fidelity_status="FALLBACK",
            ),
        )
    )

    html = renderer.build_detail_page_html(
        profile,
        b"\xff\xd8\xffjpeg",
        mime_type="image/jpeg",
        photo_set=photo_set,
    )

    usage = html.split('data-section="usage-scene"', 1)[1].split("</section>", 1)[0]
    assert "c291cmNlLWxpZmVzdHlsZQ==" in usage


def test_detail_page_css_defines_distinct_layout_variants():
    css = Path("web/detail_page.css").read_text(encoding="utf-8")

    assert ".detail-page--image-first" in css
    assert ".detail-page--catalog-grid" in css


def test_reference_editorial_css_supports_dark_detail_and_full_bleed_usage():
    css = Path("web/detail_page.css").read_text(encoding="utf-8")

    assert ".detail-page--adaptive .split-section.block--dark" in css
    assert ".detail-page--adaptive .usage-section.block--full-bleed" in css
    assert "linear-gradient" not in css


def test_reference_guide_tokens_are_preserved_in_adaptive_rendering():
    css = Path("web/detail_page.css").read_text(encoding="utf-8")

    assert "--cool-grey-50: #F0F0F0" in css
    assert "--jade-blue-300: #DAE6E8" in css
    assert "--yellow-500: #FFC14C" in css
    assert "--red-500: #E84610" in css
    assert ".detail-page--adaptive h1" in css
    assert "Pretendard" in css


def test_detail_page_uses_reference_guide_palette_for_adaptive_pages():
    css = Path("web/detail_page.css").read_text(encoding="utf-8")

    assert "--paper: #FAFBFC" in css
    assert "--paper-deep: #E6EEEF" in css
    assert "--espresso: #121B29" in css
    assert "--reference-display: 28px" in css
    assert "--reference-title: 17px" in css
    assert "--reference-body: 16px" in css


def test_default_editorial_plan_uses_reference_story_variants():
    renderer = importlib.import_module("detail_page_ai.html_renderer")

    html = renderer.build_detail_page_html(
        sample_profile(), b"\xff\xd8\xffjpeg", mime_type="image/jpeg"
    )

    assert 'class="split-section  block--dark"' in html
    assert 'class="usage-section block--full-bleed"' in html
    assert html.index('data-section="hero"') < html.index('data-section="detail-01"')
    assert html.index('data-section="usage-scene"') < html.index('data-section="closing"')


def test_html_renderer_marks_exportable_layout_sections_in_reading_order():
    renderer = importlib.import_module("detail_page_ai.html_renderer")

    html = renderer.build_detail_page_html(
        sample_profile(), b"\xff\xd8\xffjpeg", mime_type="image/jpeg"
    )

    section_ids = [
        "hero",
        "core-value",
        "features",
        "detail-01",
        "detail-02",
        "detail-03",
        "wide-view",
        "detail-cuts",
        "usage-scene",
        "scale-reference",
        "notice",
    ]
    positions = [html.index(f'data-section="{section_id}"') for section_id in section_ids]

    assert positions == sorted(positions)
    assert 'data-section-title="상품 소개"' in html
    assert 'data-section-title="상세 컷"' in html


def test_html_renderer_adds_craft_context_to_detail_copy_for_traditional_craft():
    renderer = importlib.import_module("detail_page_ai.html_renderer")
    profile = sample_profile().model_copy(
        update={
            "is_traditional_craft": True,
            "craft_type": "전통 패턴 공예",
            "craft_research": CraftResearchDto(
                craft_type="전통 패턴 공예",
                overview="전통 공예의 문양과 색을 살펴보는 맥락입니다.",
                characteristics=[
                    {
                        "title": "문양을 이어가는 표현",
                        "description": "반복되는 문양과 색의 조합이 특징으로 소개됩니다.",
                        "kind": "visual",
                        "source_urls": ["https://museum.example/pattern"],
                    }
                ],
                techniques=["문양 구성"],
                materials=["확인 필요"],
                sources=[
                    {
                        "title": "박물관 자료",
                        "url": "https://museum.example/pattern",
                    }
                ],
            ),
        }
    )

    html = renderer.build_detail_page_html(
        profile, b"\xff\xd8\xffjpeg", mime_type="image/jpeg"
    )

    assert 'data-section="craft-context"' in html
    assert "전통 패턴 공예" in html
    assert "문양을 이어가는 표현" in html


def test_html_renderer_adds_researched_product_context_for_description_input():
    renderer = importlib.import_module("detail_page_ai.html_renderer")
    profile = sample_profile().model_copy(
        update={
            "is_traditional_craft": False,
            "craft_type": None,
            "craft_research": CraftResearchDto(
                craft_type="가죽 지갑",
                overview="공개 자료와 입력 설명을 대조한 일반적인 제품 정보입니다.",
                characteristics=[
                    {
                        "title": "수납 구조",
                        "description": "카드와 소지품을 나누어 보관하는 구조로 소개됩니다.",
                        "kind": "visual",
                        "source_urls": ["https://example.com/wallet"],
                    }
                ],
                techniques=[],
                materials=[],
                sources=[
                    {
                        "title": "공개 제품 자료",
                        "url": "https://example.com/wallet",
                    }
                ],
            ),
        }
    )

    html = renderer.build_detail_page_html(
        profile, b"\xff\xd8\xffjpeg", mime_type="image/jpeg"
    )

    assert 'data-section-title="제품 정보"' in html
    assert "RESEARCHED PRODUCT" in html
    assert "공개 자료와 입력 설명" in html
    assert "수납 구조" in html


def test_html_renderer_uses_generated_product_photos_for_distinct_layout_roles():
    renderer = importlib.import_module("detail_page_ai.html_renderer")
    photo_set = ProductPhotoSet(
        photos=(
            ProductPhoto(
                photo_id="hero",
                order=1,
                label="Hero",
                data=b"hero-bytes",
                mime_type="image/jpeg",
                source_sha256="source-hash",
                product_generated=False,
                fidelity_status="VERIFIED",
            ),
            ProductPhoto(
                photo_id="detail",
                order=2,
                label="Detail",
                data=b"detail-bytes",
                mime_type="image/jpeg",
                source_sha256="source-hash",
                product_generated=False,
                fidelity_status="VERIFIED",
            ),
        )
    )

    html = renderer.build_detail_page_html(
        sample_profile(),
        b"\xff\xd8\xffjpeg",
        mime_type="image/jpeg",
        photo_set=photo_set,
    )

    assert "data:image/jpeg;base64,aGVyby1ieXRlcw==" in html
    assert "data:image/jpeg;base64,ZGV0YWlsLWJ5dGVz" in html


def test_html_renderer_maps_usage_packshot_scale_and_detail_roles_explicitly():
    renderer = importlib.import_module("detail_page_ai.html_renderer")
    photo_set = ProductPhotoSet(
        photos=tuple(
            ProductPhoto(
                photo_id=photo_id,
                order=order,
                label=photo_id,
                data=f"{photo_id}-bytes".encode(),
                mime_type="image/png",
                source_sha256="source-hash",
                product_generated=False,
                fidelity_status="VERIFIED",
            )
            for order, photo_id in enumerate(
                ("hero", "packshot", "detail", "lifestyle", "scale", "alternate"),
                start=1,
            )
        )
    )

    html = renderer.build_detail_page_html(
        sample_profile(),
        b"\xff\xd8\xffjpeg",
        mime_type="image/jpeg",
        photo_set=photo_set,
    )
    usage = html.split('data-section="usage-scene"', 1)[1].split("</section>", 1)[0]
    wide = html.split('data-section="wide-view"', 1)[1].split("</section>", 1)[0]
    scale = html.split('data-section="scale-reference"', 1)[1].split("</section>", 1)[0]
    gallery = html.split('data-section="detail-cuts"', 1)[1].split("</section>", 1)[0]

    assert "bGlmZXN0eWxlLWJ5dGVz" in usage
    assert "YWx0ZXJuYXRlLWJ5dGVz" not in usage
    assert "cGFja3Nob3QtYnl0ZXM=" in wide
    assert "c2NhbGUtYnl0ZXM=" in scale
    assert "ZGV0YWlsLWJ5dGVz" in gallery
    assert "YWx0ZXJuYXRlLWJ5dGVz" not in gallery


def test_html_renderer_excludes_rejected_or_generated_product_photos():
    renderer = importlib.import_module("detail_page_ai.html_renderer")
    photo_set = ProductPhotoSet(
        photos=(
            ProductPhoto(
                photo_id="lifestyle",
                order=1,
                label="unsafe",
                data=b"unsafe-generated-product",
                mime_type="image/png",
                source_sha256="source-hash",
                product_generated=True,
                fidelity_status="REJECTED",
            ),
        )
    )

    html = renderer.build_detail_page_html(
        sample_profile(),
        b"\xff\xd8\xffjpeg",
        mime_type="image/jpeg",
        photo_set=photo_set,
    )

    assert "dW5zYWZlLWdlbmVyYXRlZC1wcm9kdWN0" not in html


def test_html_renderer_includes_explicit_generated_lifestyle_scene():
    renderer = importlib.import_module("detail_page_ai.html_renderer")
    photo_set = ProductPhotoSet(
        photos=(
            ProductPhoto(
                photo_id="lifestyle",
                order=1,
                label="AI 생성 활용 장면(참고용)",
                data=b"generated-lifestyle",
                mime_type="image/png",
                source_sha256="source-hash",
                asset_mode="generated_scene",
                background_generated=True,
                product_generated=True,
                fidelity_status="GENERATED",
            ),
        )
    )

    html = renderer.build_detail_page_html(
        sample_profile(),
        b"\xff\xd8\xffjpeg",
        mime_type="image/jpeg",
        photo_set=photo_set,
    )

    assert "Z2VuZXJhdGVkLWxpZmVzdHlsZQ==" in html


def test_html_renderer_includes_explicit_generated_angle_detail():
    renderer = importlib.import_module("detail_page_ai.html_renderer")
    photo_set = ProductPhotoSet(
        photos=(
            ProductPhoto(
                photo_id="detail-03",
                order=6,
                label="AI 생성 각도 디테일(참고용)",
                data=b"generated-angle-detail",
                mime_type="image/png",
                source_sha256="source-hash",
                asset_mode="generated_view",
                background_generated=True,
                product_generated=True,
                fidelity_status="GENERATED",
            ),
        )
    )

    html = renderer.build_detail_page_html(
        sample_profile(),
        b"\xff\xd8\xffjpeg",
        mime_type="image/jpeg",
        photo_set=photo_set,
    )

    assert "Z2VuZXJhdGVkLWFuZ2xlLWRldGFpbA==" in html


def test_gallery_uses_both_generated_angle_slots_when_they_are_available():
    renderer = importlib.import_module("detail_page_ai.html_renderer")
    profile = sample_profile().model_copy(
        update={
            "page_plan": [
                PageBlockDto(
                    section_id="gallery",
                    block_type="gallery",
                    eyebrow="DETAIL",
                    title="상세 컷",
                    body="각도별 디테일",
                    variant="paper",
                    photo_ids=["detail", "detail-02", "detail-04"],
                )
            ]
        }
    )
    photos = tuple(
        ProductPhoto(
            photo_id=photo_id,
            order=order,
            label="원본 디테일",
            data=f"source-{photo_id}".encode(),
            mime_type="image/png",
            source_sha256="source-hash",
            product_generated=False,
            fidelity_status="VERIFIED",
        )
        for order, photo_id in enumerate(("detail", "detail-02", "detail-04"), start=1)
    ) + tuple(
        ProductPhoto(
            photo_id=photo_id,
            order=order,
            label="AI 생성 각도 디테일(참고용)",
            data=f"generated-{photo_id}".encode(),
            mime_type="image/png",
            asset_mode="generated_view",
            source_sha256="source-hash",
            background_generated=True,
            product_generated=True,
            fidelity_status="GENERATED",
        )
        for order, photo_id in ((4, "detail-03"), (5, "detail-05"))
    )

    html = renderer.build_detail_page_html(
        profile,
        b"\xff\xd8\xffjpeg",
        mime_type="image/jpeg",
        photo_set=ProductPhotoSet(photos=photos),
    )

    assert "Z2VuZXJhdGVkLWRldGFpbC0wMw==" in html
    assert "Z2VuZXJhdGVkLWRldGFpbC0wNQ==" in html


def test_html_renderer_excludes_photo_without_explicit_provenance():
    renderer = importlib.import_module("detail_page_ai.html_renderer")
    photo_set = ProductPhotoSet(
        photos=(
            ProductPhoto(
                photo_id="hero",
                order=1,
                label="unknown",
                data=b"unverified-photo",
                mime_type="image/png",
            ),
        )
    )

    html = renderer.build_detail_page_html(
        sample_profile(),
        b"\xff\xd8\xffjpeg",
        mime_type="image/jpeg",
        photo_set=photo_set,
    )

    assert "dW52ZXJpZmllZC1waG90bw==" not in html


def test_browser_renderer_captures_full_page_image():
    script = Path("scripts/render_detail_page.mjs")

    assert script.is_file()
    source = script.read_text(encoding="utf-8")
    assert "fullPage: true" in source
    assert "774" in source


def test_html_detail_page_renderer_captures_built_html_as_generated_image(tmp_path):
    renderer_module = importlib.import_module("detail_page_ai.html_renderer")
    calls = []

    def fake_runner(command, **kwargs):
        calls.append(command)
        Path(command[3]).write_bytes(b"captured-png")
        sections_dir = Path(command[command.index("--sections") + 1])
        sections_dir.mkdir()
        section_path = sections_dir / "01-hero.png"
        section_path.write_bytes(b"hero-png")
        (sections_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "sections": [
                        {
                            "order": 1,
                            "section_id": "hero",
                            "label": "상품 소개",
                            "file": section_path.name,
                            "width": 774,
                            "height": 526,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

    renderer = renderer_module.HtmlDetailPageRenderer(
        capture_script=tmp_path / "render_detail_page.mjs",
        command_runner=fake_runner,
    )
    result = renderer.render(
        source_image=b"\xff\xd8\xffjpeg",
        source_mime_type="image/jpeg",
        template_image=None,
        profile=sample_profile(),
        options=None,
    )

    assert result.data == b"captured-png"
    assert result.mime_type == "image/png"
    assert calls[0][0] == "node"
    assert calls[0][1].endswith("render_detail_page.mjs")
    assert "--sections" in calls[0]
    assert result.sections[0].section_id == "hero"
    assert result.sections[0].data == b"hero-png"
    assert result.sections[0].width == 774
