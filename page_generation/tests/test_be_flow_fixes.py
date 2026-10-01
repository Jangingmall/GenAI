import base64
import hashlib
from html.parser import HTMLParser
from io import BytesIO

import pytest
from PIL import Image

from detail_page_ai.dto import (
    ApprovedDraftDto, PageBlockDto, PageBlockItemDto, ProductProfileDto, UserHintsDto,
)
from detail_page_ai.html_renderer import build_detail_page_html
from detail_page_ai.models import GenerationOptions
from detail_page_ai.pipeline import DetailPagePipeline
from detail_page_ai.prompts import (
    build_generated_usage_scene_prompt, build_usage_context_background_prompt,
)
from detail_page_ai.react_document_builder import build_react_document_from_draft
from detail_page_ai.source_photos import SourcePreservingProductPhotoGenerator
from detail_page_ai.validation import sanitize_profile_for_render
from local_detail_page_ai.clients import MlxServeImageClient, SglangImageClient
from local_detail_page_ai.runner import (
    MlxServeBackgroundGenerator, MlxServeUsageSceneGenerator,
)


def image_bytes(format="PNG"):
    output = BytesIO()
    image = Image.new("RGBA", (12, 8), (245, 240, 230, 180))
    image.save(output, format=format, lossless=True)
    return output.getvalue()


class ImageTransport:
    def post(self, url, payload, timeout):
        self.payload = payload
        return {"data": [{"b64_json": base64.b64encode(image_bytes()).decode()}]}

    def post_multipart(self, url, fields, files, timeout):
        self.file = files["image"]
        return {"data": [{"b64_json": base64.b64encode(image_bytes()).decode()}]}


@pytest.mark.parametrize("client_type", [MlxServeImageClient, SglangImageClient])
def test_webp_edit_reaches_model_as_lossless_png(client_type):
    source = image_bytes("WEBP")
    original_hash = hashlib.sha256(source).hexdigest()
    transport = ImageTransport()
    client = client_type(transport=transport)

    client.edit("Keep the exact product", source_image=source, source_mime_type="image/webp")

    if client_type is MlxServeImageClient:
        sent = base64.b64decode(transport.payload["image"])
    else:
        sent = transport.file["data"]
        assert transport.file["content_type"] == "image/png"
        assert transport.file["filename"] == "source.png"
    with Image.open(BytesIO(sent)) as decoded, Image.open(BytesIO(source)) as original:
        assert decoded.format == "PNG"
        assert decoded.size == (12, 8)
        assert decoded.convert("RGBA").tobytes() == original.convert("RGBA").tobytes()
    assert hashlib.sha256(source).hexdigest() == original_hash


def test_webp_conversion_does_not_change_photo_source_hash():
    class NoCutout:
        def extract(self, source_image, source_mime_type):
            return None

    source = image_bytes("WEBP")
    generator = SourcePreservingProductPhotoGenerator(
        extractor=NoCutout(),
        usage_scene_generator=MlxServeUsageSceneGenerator(MlxServeImageClient(transport=ImageTransport())),
        photo_roles=("hero", "lifestyle"),
    )
    result = generator.generate(source_image=source, source_mime_type="image/webp",
                                profile=ProductProfileDto.minimal("부채"), options=GenerationOptions())
    scene = next(photo for photo in result.photos if photo.photo_id == "lifestyle")
    assert scene.asset_mode == "generated_scene"
    assert scene.source_sha256 == hashlib.sha256(source).hexdigest()
    assert scene.source_sha256 != hashlib.sha256(scene.data).hexdigest()


class PageInspector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.section = None
        self.section_tags = {}
        self.swatch_styles = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "section":
            self.section = attrs.get("data-section")
            self.section_tags[self.section] = []
        if self.section:
            self.section_tags[self.section].append(tag)
        if "palette-swatch" in attrs.get("class", "").split():
            self.swatch_styles.append(attrs.get("style", ""))

    def handle_endtag(self, tag):
        if tag == "section":
            self.section = None


def profile_with_blocks(*blocks):
    return ProductProfileDto(
        product_type="부채", summary="한지 위에 매화 문양이 보입니다.", page_plan=list(blocks),
        features=[{"title": "매화 문양", "description": "분홍색 꽃잎이 보입니다.",
                   "evidence": "image-visible", "confidence": 0.9}],
    )


def walk(node):
    yield node
    for child in node.get("children", []):
        yield from walk(child)


def render_blocks(profile):
    html = build_detail_page_html(profile, image_bytes(), mime_type="image/png")
    parser = PageInspector()
    parser.feed(html)
    draft = ApprovedDraftDto.from_profile(profile)
    ast = build_react_document_from_draft(draft).model_dump(by_alias=True, exclude_none=True)
    return html, parser, ast


@pytest.mark.parametrize("color", ["#F5F0E6", "#E8A0B0", "#abc", "#abcd", "#11223344"])
def test_palette_html_and_react_use_the_supplied_safe_hex(color):
    profile = profile_with_blocks(PageBlockDto(section_id="palette", block_type="palette",
        items=[PageBlockItemDto(label="선면 색", value=color)]))
    _, parser, ast = render_blocks(profile)
    assert parser.swatch_styles == [f"background-color: {color}"]
    spans = [n for root in ast["root"] for n in walk(root) if n.get("tag") == "span"]
    colors = [n["props"].get("style", {}).get("backgroundColor") for n in spans]
    assert color in colors


@pytest.mark.parametrize("invalid", ["", "#12", "#F5F0E6;position:absolute", 'red\" onmouseover=\"alert(1)', "url(https://example.com)"])
def test_palette_rejects_css_injection_and_keeps_index_fallback(invalid):
    profile = profile_with_blocks(PageBlockDto(section_id="palette", block_type="palette",
        items=[PageBlockItemDto(label="색", value=invalid)]))
    _, parser, ast = render_blocks(profile)
    assert parser.swatch_styles == ["background-color: #8E9A9C"]
    spans = [n for root in ast["root"] for n in walk(root) if n.get("tag") == "span"]
    assert "#8E9A9C" in [n["props"].get("style", {}).get("backgroundColor") for n in spans]


def test_palette_react_preserves_all_four_items_and_index_colors():
    profile = profile_with_blocks(PageBlockDto(section_id="palette", block_type="palette",
        items=[PageBlockItemDto(label=f"색 {i}", value="색상 확인 필요") for i in range(4)]))
    _, parser, ast = render_blocks(profile)
    expected = ["#8E9A9C", "#ECEDEE", "#C6D9DC", "#414954"]
    assert parser.swatch_styles == [f"background-color: {color}" for color in expected]
    spans = [n for root in ast["root"] for n in walk(root) if n.get("tag") == "span"]
    assert [n["props"].get("style", {}).get("backgroundColor") for n in spans
            if n["props"].get("style", {}).get("backgroundColor")] == expected


def test_empty_notice_renders_care_body_without_feature_bullets():
    care = "직사광선과 습기를 피해 보관해 주세요."
    profile = profile_with_blocks(PageBlockDto(section_id="care", block_type="notice", body=care))
    html, parser, ast = render_blocks(profile)
    assert care in html
    assert "ul" not in parser.section_tags["care"]
    assert "li" not in parser.section_tags["care"]
    assert not any(n.get("tag") == "ul" for root in ast["root"] for n in walk(root))


def test_explicit_notice_items_are_preserved():
    profile = profile_with_blocks(PageBlockDto(section_id="care", block_type="notice",
        items=[PageBlockItemDto(label="보관", value="습기를 피해 주세요.")]))
    html, parser, ast = render_blocks(profile)
    assert "li" in parser.section_tags["care"]
    assert "습기를 피해 주세요." in html
    assert any(n.get("tag") == "li" for root in ast["root"] for n in walk(root))


@pytest.mark.parametrize("field", ["uncertain_information", "safety_notes"])
def test_confirmed_seller_sentences_are_removed_from_both_warning_sources(field):
    hints = UserHintsDto(product_name="매화선", making_method="한지를 겹겹이 붙였습니다.",
        care_guide="천천히 펴 주세요. 직사광선과 습기를 피해 보관해 주세요.")
    profile = profile_with_blocks(PageBlockDto(section_id="care", block_type="notice", body=hints.care_guide))
    profile = profile.model_copy(update={field: [" 천천히  펴 주세요 ", "직사광선과 습기를 피해 보관해 주세요.",
        "한지를 겹겹이 붙였습니다.", "매화선", "부채의 정확한 크기", "습기 노출 시 안전성은 확인 필요"]})
    safe = sanitize_profile_for_render(profile, user_hints=hints)
    assert getattr(safe, field) == ["부채의 정확한 크기", "습기 노출 시 안전성은 확인 필요"]
    assert safe.page_plan[0].body == hints.care_guide


def test_warnings_without_seller_confirmation_are_retained():
    profile = profile_with_blocks().model_copy(update={"safety_notes": ["천천히 펴 주세요."]})
    assert sanitize_profile_for_render(profile).safety_notes == ["천천히 펴 주세요."]


@pytest.mark.parametrize("field", ["uncertain_information", "safety_notes"])
@pytest.mark.parametrize("hint_field,seller,warning", [
    (
        "care_guide",
        "펼칠 때는 아래에서 위로 천천히 펴 주세요. 사용 후에는 접어 보관해 주세요.",
        "부채를 펼칠 때는 아래에서 위로 천천히 펴 주세요.",
    ),
    (
        "making_method",
        "한지를 겹겹이 붙였습니다. 매화를 직접 그렸습니다.",
        "이 제품은 한지를 겹겹이 붙였습니다.",
    ),
])
def test_seller_instruction_with_short_subject_prefix_is_confirmed(field, hint_field, seller, warning):
    hints = UserHintsDto(**{hint_field: seller})
    profile = profile_with_blocks().model_copy(update={field: [warning]})
    safe = sanitize_profile_for_render(profile, user_hints=hints)
    assert getattr(safe, field) == []


@pytest.mark.parametrize("field", ["uncertain_information", "safety_notes"])
@pytest.mark.parametrize("product_name,warning", [
    ("매화선", "매화선의 정확한 크기는 확인이 필요합니다."),
    ("매화선. 부채", "매화선"),
])
def test_product_name_only_matches_the_entire_warning(field, product_name, warning):
    hints = UserHintsDto(product_name=product_name)
    profile = profile_with_blocks().model_copy(update={field: [warning]})
    assert getattr(sanitize_profile_for_render(profile, user_hints=hints), field) == [warning]


@pytest.mark.parametrize("field", ["uncertain_information", "safety_notes"])
@pytest.mark.parametrize("warning", [
    "직사광선과 습기를 피해 보관해 주세요 그렇지 않으면 선면이 휘어질 수 있어 확인이 필요합니다.",
    "직사광선과 습기를 피해 보관해 주세요. 선면이 휘어질 수 있어 확인이 필요합니다.",
    "직사광선과 습기를 피해 보관해 주세요 조심하세요.",
])
def test_seller_instruction_with_added_claim_is_retained(field, warning):
    hints = UserHintsDto(care_guide="직사광선과 습기를 피해 보관해 주세요.")
    profile = profile_with_blocks().model_copy(update={field: [warning]})
    assert getattr(sanitize_profile_for_render(profile, user_hints=hints), field) == [warning]


@pytest.mark.parametrize("field", ["uncertain_information", "safety_notes"])
@pytest.mark.parametrize("prefix,removed", [
    ("전주매화합죽선을 ", True),  # Eight non-space characters including the particle.
    ("전주전통매화부채를 ", False),  # Nine characters exceed the prefix budget.
    ("확인 필요: ", False),  # A short label is not a product subject.
])
def test_seller_instruction_prefix_is_bounded_and_subject_only(field, prefix, removed):
    sentence = "펼칠 때는 아래에서 위로 천천히 펴 주세요."
    warning = prefix + sentence
    hints = UserHintsDto(care_guide=sentence)
    profile = profile_with_blocks().model_copy(update={field: [warning]})
    expected = [] if removed else [warning]
    assert getattr(sanitize_profile_for_render(profile, user_hints=hints), field) == expected


def test_draft_pipeline_filters_seller_care_warnings_and_keeps_original_hash():
    class Analyzer:
        def analyze(self, image, mime_type, user_hints=None):
            return profile_with_blocks().model_copy(update={
                "safety_notes": ["천천히 펴 주세요."], "uncertain_information": ["정확한 크기 확인 필요"]})

    source = image_bytes("WEBP")
    pipeline = DetailPagePipeline(analyzer=Analyzer(), renderer=object(), backend=object())
    result = pipeline.create_draft("job", "request", source, "image/webp", user_hints=UserHintsDto(care_guide="천천히 펴 주세요."))
    assert result.fe_draft.product.warnings == ["정확한 크기 확인 필요"]
    assert result.fe_draft.source_sha256 == hashlib.sha256(source).hexdigest()


@pytest.mark.parametrize("items", [[], [PageBlockItemDto(label="다른 전통 공예품", value="함께 구입해 보세요.")]])
def test_unbacked_related_product_recommendation_is_absent_from_html_and_react(items):
    profile = profile_with_blocks(PageBlockDto(section_id="related", block_type="recommendation",
        eyebrow="함께 보기", title="전주 전통 공예", body="전주에서 만든 다른 전통 공예품도 함께 살펴보세요.", items=items))
    html, parser, ast = render_blocks(profile)
    assert "related" not in parser.section_tags
    assert "다른 전통 공예품" not in html
    assert not any("related" in node["id"] for node in ast["root"])


def test_supported_staging_recommendation_stays_visible():
    profile = profile_with_blocks(PageBlockDto(section_id="staging", block_type="recommendation",
        title="이런 자리에서 어울립니다", body="제품의 색과 실루엣을 기준으로 제안하는 연출 아이디어입니다.",
        items=[PageBlockItemDto(label="창가", value="부드러운 자연광으로 연출해 보세요.", evidence="inferred")]))
    html, parser, ast = render_blocks(profile)
    assert "staging" in parser.section_tags
    assert "부드러운 자연광" in html
    assert any("staging" in node["id"] for node in ast["root"])


@pytest.mark.parametrize("title,body", [
    ("추천 연출", "이 작품은 거실 선반 위나 현관 벽에 두면 잘 어울립니다."),
    ("추가로 즐기는 방법", "이 제품은 여름철 장식으로도 쓸 수 있습니다."),
    ("새로운 배치", "이 상품을 창가 선반에 두어 보세요."),
    ("다른 공간", "이 제품을 현관 선반에 놓아 보세요."),
    ("각도별 연출", "다른 방향에서 이 작품을 함께 살펴보세요."),
    ("남다른 작품 활용", "자연광으로 제품의 문양을 살펴보세요."),
    ("Recommended display", "Place this product on a shelf."),
    ("Additional uses", "This product can decorate a summer room."),
])
def test_staging_recommendation_titles_do_not_remove_the_current_product(title, body):
    block = PageBlockDto(
        section_id="staging", block_type="recommendation", title=title, body=body,
        items=[PageBlockItemDto(label="선반", value="제품의 문양을 보이게 놓아 보세요.")],
    )
    profile = profile_with_blocks(block)
    assert sanitize_profile_for_render(profile).page_plan == [block]
    html, parser, ast = render_blocks(profile)
    assert "staging" in parser.section_tags
    assert title in html and body in html
    assert any("staging" in node["id"] for node in ast["root"])


@pytest.mark.parametrize("body", [
    "전주에서 만든 다른 전통 공예품도 함께 살펴보세요.",
    "관련 상품을 함께 둘러보세요.",
    "연관 제품도 구매해 보세요.",
    "유사 작품도 살펴보세요.",
    "비슷한 공예품을 함께 둘러보세요.",
    "Explore other traditional crafts.",
    "View related products.",
    "Browse similar items.",
])
def test_other_product_pitches_are_removed_even_with_staging_items(body):
    profile = profile_with_blocks(PageBlockDto(
        section_id="related", block_type="recommendation", title="함께 보기", body=body,
        items=[PageBlockItemDto(label="선반", value="제품의 문양을 보이게 놓아 보세요.")],
    ))
    assert sanitize_profile_for_render(profile).page_plan == []
    html, parser, ast = render_blocks(profile)
    assert "related" not in parser.section_tags
    assert body not in html
    assert not any("related" in node["id"] for node in ast["root"])


def test_usage_background_and_reference_edit_explicitly_exclude_unrelated_tableware():
    profile = ProductProfileDto.minimal("부채")
    for prompt in (build_usage_context_background_prompt(profile), build_generated_usage_scene_prompt(profile)):
        for prop in ("plates", "dishes", "bowls", "cups", "cutlery", "serving trays"):
            assert prop in prompt.lower()
    transport = ImageTransport()
    MlxServeBackgroundGenerator(MlxServeImageClient(transport=transport)).generate(profile=profile, role="lifestyle", width=1024, height=1024)
    for prop in ("plate", "dish", "bowl", "cup", "cutlery", "tray"):
        assert prop in transport.payload["negative_prompt"]


def test_usage_background_starts_with_empty_scene_without_ambiguous_plate_noun():
    prompt = build_usage_context_background_prompt(ProductProfileDto.minimal("부채"))
    opening = prompt.split("Hard constraints:")[0].lower()
    assert "background plate" not in prompt.lower()
    assert "empty interior background photograph" in opening
    assert opening.index("completely clear") < opening.index("visual direction:")
    assert "product remains the visual anchor" not in prompt.lower()
