import base64
import html
import json
import struct
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

from .dto import PageBlockDto, PageBlockItemDto, ProductProfileDto
from .models import GeneratedImage, GeneratedSection, ProductPhotoSet
from .validation import sanitize_profile_for_render


class HtmlTemplateError(RuntimeError):
    """Raised when the HTML detail-page template cannot be rendered."""


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WEB_DIR = PROJECT_ROOT / "web"


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _image_data_uri(image: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(image).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _image_tag(image_uri: str, *, alt: str, class_name: str) -> str:
    return (
        f'<img class="{_escape(class_name)}" src="{_escape(image_uri)}" '
        f'alt="{_escape(alt)}" loading="eager">'
    )


def _feature_cards(profile: ProductProfileDto) -> str:
    cards = []
    for index, feature in enumerate(profile.features[:3]):
        accent = ("jade", "red", "yellow")[index % 3]
        cards.append(
            """<article class="feature-card">
  <span class="feature-card__accent feature-card__accent--{accent}"></span>
  <h3>{title}</h3>
  <p>{description}</p>
</article>""".format(
                accent=accent,
                title=_escape(feature.title),
                description=_escape(feature.description),
            )
        )
    return "\n".join(cards)


def _split_sections(profile: ProductProfileDto, image_uris: tuple[str, ...]) -> str:
    sections = []
    for index, feature in enumerate(profile.features[:3]):
        side = "split-section--reverse" if index % 2 else ""
        position = ("center top", "center center", "center bottom")[index % 3]
        research_note = ""
        if profile.craft_research and index < len(profile.craft_research.characteristics):
            characteristic = profile.craft_research.characteristics[index]
            context_label = "전통 맥락" if profile.is_traditional_craft else "확인된 자료"
            research_note = (
                f'<p class="split-section__research-note"><strong>{context_label}</strong> '
                f"{_escape(characteristic.description)}</p>"
            )
        image_uri = image_uris[index % len(image_uris)]
        sections.append(
            """<section class="split-section {side}" data-section="detail-{number:02d}" data-section-title="{title}">
  <div class="split-section__media split-section__media--{position}">
    {image}
  </div>
  <div class="split-section__copy">
    <span class="eyebrow">DETAIL {number:02d}</span>
    <h2>{title}</h2>
    <p>{description}</p>
    {research_note}
  </div>
</section>""".format(
                side=side,
                position=position.replace(" ", "-"),
                image=_image_tag(
                    image_uri,
                    alt=f"{feature.title} 상세 이미지",
                    class_name="product-image product-image--split",
                ),
                number=index + 1,
                title=_escape(feature.title),
                description=_escape(feature.description),
                research_note=research_note,
            )
        )
    return "\n".join(sections)


def _gallery(image_uris: tuple[str, ...], product_name: str) -> tuple[str, str]:
    # Do not manufacture extra views by cycling through the available photos.
    unique_uris = tuple(dict.fromkeys(image_uris))[:5]
    first_count = 2 if len(unique_uris) == 4 else min(3, len(unique_uris))
    images = [
        _image_tag(
            uri,
            alt=f"{product_name} 디테일 이미지 {index + 1}",
            class_name=f"product-image crop-{index}",
        )
        for index, uri in enumerate(unique_uris)
    ]
    return "\n".join(images[:first_count]), "\n".join(images[first_count:])


def _gallery_row(images: str) -> str:
    count = images.count("<img ")
    if not count:
        return ""
    columns = ("one", "two", "three")[count - 1]
    return f'<div class="detail-grid detail-grid--{columns}">{images}</div>'


def _default_page_plan(profile: ProductProfileDto) -> tuple[PageBlockDto, ...]:
    """Build a safe editorial plan for old profiles without an AI page plan."""
    product_name = profile.display_name or profile.product_type
    hero_copy = next(
        (section for section in profile.copy_sections if section.section_type == "hero"),
        None,
    )
    features = profile.features[:3]
    feature_items = [
        PageBlockItemDto(
            label=feature.title,
            value=feature.description,
            description=feature.description,
            evidence=feature.evidence,
        )
        for feature in features
    ]
    colors = profile.observations.get("colors", [])
    color_items = [
        PageBlockItemDto(label=str(color), value=str(color), description="이미지에서 보이는 색감")
        for color in colors[:4]
        if str(color).strip()
    ]
    visible_components = profile.observations.get("visible_components", [])
    component_text = (
        ", ".join(str(item) for item in visible_components[:6])
        if isinstance(visible_components, list) and visible_components
        else "이미지에서 확인되는 구성"
    )
    plan: list[PageBlockDto] = [
        PageBlockDto(
            section_id="hero",
            block_type="hero",
            eyebrow="OBJECT DETAIL",
            title=hero_copy.title if hero_copy else product_name,
            body=hero_copy.description if hero_copy else profile.summary,
            variant="paper",
            photo_id="hero",
        ),
        PageBlockDto(
            section_id="core-value",
            block_type="statement",
            eyebrow="CORE VALUE",
            title=hero_copy.title if hero_copy else "이미지에서 발견한 제품의 특징",
            body=hero_copy.description if hero_copy else profile.summary,
            variant="paper",
        ),
        PageBlockDto(
            section_id="features",
            block_type="feature_grid",
            eyebrow="VISIBLE DETAILS",
            title="가까이 볼수록 선명해지는 디테일",
            body="원본 이미지에서 확인되는 요소를 중심으로 구성했습니다.",
            variant="paper",
            items=feature_items,
        ),
    ]
    for index, feature in enumerate(features):
        plan.append(
            PageBlockDto(
                section_id=f"detail-{index + 1:02d}",
                block_type="detail_split",
                eyebrow=f"DETAIL {index + 1:02d}",
                title=feature.title,
                body=feature.description,
                variant=(
                    "dark"
                    if index == 0
                    else ("image-left" if index % 2 == 0 else "image-right")
                ),
                photo_id="detail" if index == 0 else f"detail-{index + 1:02d}",
            )
        )
    plan.extend(
        [
            PageBlockDto(
                section_id="wide-view",
                block_type="wide_image",
                eyebrow="WIDE VIEW",
                title="전체 인상을 한눈에",
                body="제품의 형태와 배열을 원본 그대로 살펴봅니다.",
                variant="light",
                photo_id="packshot",
            ),
            PageBlockDto(
                section_id="detail-cuts",
                block_type="gallery",
                eyebrow="PRODUCT GALLERY",
                title="색과 형태의 작은 차이",
                body="서로 다른 디테일을 가까이에서 비교해 보세요.",
                variant="paper",
                photo_ids=["detail", "detail-02", "detail-03", "detail-04", "detail-05"],
            ),
            PageBlockDto(
                section_id="usage-scene",
                block_type="usage_scene",
                eyebrow="EVERYDAY SCENE",
                title="일상에 더하는 하나의 포인트",
                body=profile.usage_scene or "제품이 놓이는 장면을 이미지 기반으로 제안합니다.",
                variant="full-bleed",
                photo_id="lifestyle",
            ),
        ]
    )
    if color_items:
        plan.append(
            PageBlockDto(
                section_id="palette",
                block_type="palette",
                eyebrow="COLOR & SURFACE",
                title="이미지에서 읽어낸 색의 결",
                body="빛에 따라 달라지는 표면 인상을 정리했습니다.",
                variant="paper",
                photo_id="packshot",
                items=color_items,
            )
        )
    plan.extend(
        [
            PageBlockDto(
                section_id="scale-reference",
                block_type="scale_reference",
                eyebrow="OBJECT ARRANGEMENT",
                title="공간 속에서 살펴보는 균형",
                body="실제 크기와 용도는 별도 확인이 필요하며, 여기서는 이미지 속 배열을 보여 줍니다.",
                variant="light",
                photo_id="scale",
                items=[PageBlockItemDto(label="구성", value=component_text)],
            ),
            PageBlockDto(
                section_id="notice",
                block_type="notice",
                eyebrow="IMAGE-BASED NOTE",
                title="이미지에서 확인되는 정보만 담았습니다.",
                body="확인되지 않은 정보는 상품 등록 전에 보완해 주세요.",
                variant="dark",
                items=[
                    PageBlockItemDto(label="확인 필요", value=item)
                    for item in [*profile.uncertain_information, *profile.safety_notes][:6]
                ],
            ),
            PageBlockDto(
                section_id="closing",
                block_type="closing",
                eyebrow="OBJECT STORY",
                title="테이블 위에 남는 인상",
                body="이미지에서 확인되는 형태와 표면의 특징을 중심으로 정리했습니다.",
                variant="paper",
            ),
        ]
    )
    return tuple(plan)


def _page_plan(profile: ProductProfileDto) -> tuple[PageBlockDto, ...]:
    return (
        tuple(PageBlockDto.model_validate(block) for block in profile.page_plan)
        if profile.page_plan
        else _default_page_plan(profile)
    )


def _block_image(
    block: PageBlockDto,
    photo_uris: dict[str, str],
    fallback_uri: str,
    *,
    fallback_photo_id: str,
) -> str:
    photo_id = block.photo_id or fallback_photo_id
    return photo_uris.get(photo_id, photo_uris.get(fallback_photo_id, fallback_uri))


def _block_items(block: PageBlockDto, profile: ProductProfileDto) -> tuple[PageBlockItemDto, ...]:
    if block.items:
        return tuple(block.items)
    return tuple(
        PageBlockItemDto(
            label=feature.title,
            value=feature.description,
            description=feature.description,
            evidence=feature.evidence,
        )
        for feature in profile.features[:3]
    )


def _render_page_block(
    block: PageBlockDto,
    *,
    index: int,
    profile: ProductProfileDto,
    photo_uris: dict[str, str],
    fallback_uri: str,
    product_name: str,
) -> str:
    block_type = block.block_type
    variant = f" block--{_escape(block.variant)}" if block.variant else ""
    eyebrow = _escape(block.eyebrow or block_type.replace("_", " ").upper())
    title = _escape(block.title or product_name)
    body = _escape(block.body)
    section_id = _escape(block.section_id)
    items = _block_items(block, profile)

    if block_type == "hero":
        image = _block_image(block, photo_uris, fallback_uri, fallback_photo_id="hero")
        hero_variant = variant if block.variant != "paper" else ""
        return f'''<section class="hero{hero_variant}" data-section="{section_id}" data-section-title="상품 소개">
  <div class="hero__copy"><span class="eyebrow">{eyebrow}</span><h1>{title}</h1><p>{body}</p></div>
  <div class="hero__media">{_image_tag(image, alt=f"{product_name} 대표 이미지", class_name="product-image product-image--hero")}</div>
</section>'''
    if block_type == "statement":
        return f'''<section class="intro-band{variant}" data-section="{section_id}" data-section-title="핵심 메시지">
  <span class="section-number">{index:02d}</span><div><span class="eyebrow">{eyebrow}</span><h2>{title}</h2></div><p>{body}</p>
</section>'''
    if block_type == "feature_grid":
        grid_variant = variant if block.variant != "paper" else ""
        cards = "\n".join(
            f'''<article class="feature-card"><span class="feature-card__accent feature-card__accent--{("jade", "red", "yellow")[item_index % 3]}"></span><h3>{_escape(item.label)}</h3><p>{_escape(item.value or item.description)}</p></article>'''
            for item_index, item in enumerate(items)
        )
        return f'''<section class="feature-grid{grid_variant}" data-section="{section_id}" data-section-title="제품 특징">
  <div class="section-heading section-heading--compact"><span class="eyebrow">{eyebrow}</span><h2>{title}</h2><p>{body}</p></div>{cards}
</section>'''
    if block_type == "detail_split":
        image = _block_image(block, photo_uris, fallback_uri, fallback_photo_id="detail")
        side = "split-section--reverse" if block.variant == "image-right" else ""
        return f'''<section class="split-section {side}{variant}" data-section="{section_id}" data-section-title="{title}">
  <div class="split-section__media">{_image_tag(image, alt=f"{product_name} {title} 상세 이미지", class_name="product-image product-image--split")}</div>
  <div class="split-section__copy"><span class="eyebrow">{eyebrow}</span><h2>{title}</h2><p>{body}</p></div>
</section>'''
    if block_type == "wide_image":
        image = _block_image(block, photo_uris, fallback_uri, fallback_photo_id="packshot")
        return f'''<section class="wide-section{variant}" data-section="{section_id}" data-section-title="와이드 뷰">
  <div class="section-heading section-heading--compact"><span class="eyebrow">{eyebrow}</span><h2>{title}</h2><p>{body}</p></div><div class="wide-section__media">{_image_tag(image, alt=f"{product_name} 전체 이미지", class_name="product-image product-image--wide")}</div>
</section>'''
    if block_type == "gallery":
        detail_slots = ("detail", "detail-02", "detail-03", "detail-04", "detail-05")
        if any(
            photo_id in photo_uris
            for photo_id in ("detail-02", "detail-03", "detail-04", "detail-05")
        ):
            requested = [photo_id for photo_id in detail_slots if photo_id in photo_uris]
        else:
            requested = block.photo_ids or list(detail_slots)
        gallery_uris = tuple(photo_uris[photo_id] for photo_id in requested if photo_id in photo_uris)
        if not gallery_uris:
            gallery_uris = (photo_uris.get("detail", fallback_uri),)
        three, two = _gallery(gallery_uris, product_name)
        return f'''<section class="gallery-section{variant}" data-section="{section_id}" data-section-title="상세 컷">
  <div class="section-heading section-heading--compact"><span class="eyebrow">{eyebrow}</span><h2>{title}</h2><p>{body}</p></div>{_gallery_row(three)}{_gallery_row(two)}
</section>'''
    if block_type == "usage_scene":
        image = _block_image(block, photo_uris, fallback_uri, fallback_photo_id="lifestyle")
        return f'''<section class="usage-section{variant}" data-section="{section_id}" data-section-title="활용 장면">
  <div class="usage-section__copy"><span class="eyebrow">{eyebrow}</span><h2>{title}</h2><p>{body}</p></div><div class="usage-section__media">{_image_tag(image, alt=f"{product_name} 활용 이미지", class_name="product-image product-image--usage")}</div>
</section>'''
    if block_type == "scale_reference":
        image = _block_image(block, photo_uris, fallback_uri, fallback_photo_id="scale")
        return f'''<section class="scale-section{variant}" data-section="{section_id}" data-section-title="크기 참고">
  <div class="section-heading section-heading--compact"><span class="eyebrow">{eyebrow}</span><h2>{title}</h2><p>{body}</p></div><div class="scale-section__media">{_image_tag(image, alt=f"{product_name} 크기 참고 이미지", class_name="product-image product-image--scale")}</div>
</section>'''
    if block_type == "palette":
        image = _block_image(block, photo_uris, fallback_uri, fallback_photo_id="packshot")
        palette_items = "\n".join(
            f'''<li><span class="palette-swatch palette-swatch--{item_index % 4}"></span><strong>{_escape(item.label)}</strong><span>{_escape(item.value or item.description)}</span></li>'''
            for item_index, item in enumerate(items)
        )
        return f'''<section class="palette-section{variant}" data-section="{section_id}" data-section-title="색과 표면">
  <div class="palette-section__copy"><span class="eyebrow">{eyebrow}</span><h2>{title}</h2><p>{body}</p><ul>{palette_items}</ul></div><div class="palette-section__media">{_image_tag(image, alt=f"{product_name} 색상과 표면", class_name="product-image product-image--palette")}</div>
</section>'''
    if block_type == "recommendation":
        cards = []
        for item_index, item in enumerate(items[:3], start=1):
            # A numeric label is already represented by the local card number.
            heading = "" if item.label.strip().rstrip(".)").isdigit() else f"<h3>{_escape(item.label)}</h3>"
            cards.append(f'<article><span>{item_index:02d}</span>{heading}<p>{_escape(item.value or item.description)}</p></article>')
        cards = "\n".join(cards)
        return f'''<section class="recommendation-section{variant}" data-section="{section_id}" data-section-title="추천 연출">
  <div class="section-heading section-heading--compact"><span class="eyebrow">{eyebrow}</span><h2>{title}</h2><p>{body}</p></div><div class="recommendation-grid">{cards}</div>
</section>'''
    if block_type == "info_table":
        rows = "\n".join(
            f"<tr><th>{_escape(item.label)}</th><td>{_escape(item.value or item.description)}</td></tr>"
            for item in items
        )
        return f'''<section class="info-section{variant}" data-section="{section_id}" data-section-title="기본 정보">
  <div class="section-heading section-heading--compact"><span class="eyebrow">{eyebrow}</span><h2>{title}</h2><p>{body}</p></div><table><tbody>{rows}</tbody></table>
</section>'''
    if block_type == "notice":
        notices = "\n".join(
            f"<li>{_escape(item.value or item.description or item.label)}</li>" for item in items
        )
        return f'''<section class="notice-section{variant}" data-section="{section_id}" data-section-title="안내">
  <span class="eyebrow">{eyebrow}</span><h2>{title}</h2><p>{body}</p><ul>{notices}</ul>
</section>'''
    if block_type == "closing":
        return f'''<section class="closing-section{variant}" data-section="{section_id}" data-section-title="마무리">
  <span class="eyebrow">{eyebrow}</span><h2>{title}</h2><p>{body}</p>
</section>'''
    return ""


def _dynamic_sections(
    profile: ProductProfileDto,
    *,
    photo_uris: dict[str, str],
    fallback_uri: str,
    product_name: str,
) -> str:
    return "\n".join(
        _render_page_block(
            block,
            index=index + 1,
            profile=profile,
            photo_uris=photo_uris,
            fallback_uri=fallback_uri,
            product_name=product_name,
        )
        for index, block in enumerate(_page_plan(profile))
    )


def _keywords(profile: ProductProfileDto) -> str:
    return "\n".join(
        f'<span class="keyword">#{_escape(keyword)}</span>'
        for keyword in profile.keywords[:6]
    )


def _notice_items(profile: ProductProfileDto) -> str:
    items = [*profile.uncertain_information, *profile.safety_notes]
    return "\n".join(f"<li>{_escape(item)}</li>" for item in items[:6])


def _craft_context(profile: ProductProfileDto) -> str:
    research = profile.craft_research
    if research is None:
        return ""
    characteristics = "\n".join(
        f"<li><strong>{_escape(item.title)}</strong> {_escape(item.description)}</li>"
        for item in research.characteristics[:3]
    )
    region = f" · {_escape(research.region)}" if research.region else ""
    eyebrow = "TRADITIONAL CRAFT" if profile.is_traditional_craft else "RESEARCHED PRODUCT"
    heading = (
        f"{_escape(research.craft_type)}의 특징을 참고한 디테일"
        if profile.is_traditional_craft
        else f"{_escape(research.craft_type)}를 이해하는 정보"
    )
    section_title = "공예품 특징" if profile.is_traditional_craft else "제품 정보"
    return f"""<section class="craft-context" data-section="craft-context" data-section-title="{section_title}">
  <div class="craft-context__copy">
    <span class="eyebrow">{eyebrow}{region}</span>
    <h2>{heading}</h2>
    <p>{_escape(research.overview)}</p>
    <ul>{characteristics}</ul>
  </div>
</section>"""


def build_detail_page_html(
    profile: ProductProfileDto,
    source_image: bytes,
    *,
    mime_type: str = "image/jpeg",
    photo_set: ProductPhotoSet | None = None,
    template_path: str | Path | None = None,
    css_path: str | Path | None = None,
) -> str:
    """Build a self-contained HTML detail page from an AI product profile."""
    if not source_image:
        raise ValueError("source_image must not be empty")
    if not mime_type.startswith("image/"):
        raise ValueError("mime_type must be an image MIME type")

    profile = sanitize_profile_for_render(profile)
    resolved_template = Path(template_path or DEFAULT_WEB_DIR / "detail_page.html")
    resolved_css = Path(css_path or DEFAULT_WEB_DIR / "detail_page.css")
    try:
        template = resolved_template.read_text(encoding="utf-8")
        css = resolved_css.read_text(encoding="utf-8")
    except OSError as exc:
        raise HtmlTemplateError("Detail-page HTML/CSS template could not be read") from exc

    source_image_uri = _image_data_uri(source_image, mime_type)
    photos = photo_set.photos if photo_set else ()
    photo_uris = {
        photo.photo_id: _image_data_uri(photo.data, photo.mime_type)
        for photo in photos
        if photo.fidelity_status in {"VERIFIED", "FALLBACK", "GENERATED"}
        and (
            not photo.product_generated
            or (photo.photo_id == "lifestyle" and photo.asset_mode == "generated_scene")
            or (
                photo.photo_id in {"detail-02", "detail-03", "detail-04", "detail-05"}
                and photo.asset_mode == "generated_view"
            )
        )
        and photo.source_sha256
    }
    hero_uri = photo_uris.get("hero", source_image_uri)
    packshot_uri = photo_uris.get("packshot", source_image_uri)
    lifestyle_uri = photo_uris.get("lifestyle", source_image_uri)
    scale_uri = photo_uris.get("scale", source_image_uri)
    detail_uri = photo_uris.get("detail", source_image_uri)
    detail_uris = tuple(
        uri
        for photo in sorted(
            (photo for photo in photos
             if photo.photo_id == "detail" or photo.photo_id.startswith("detail-")),
            key=lambda item: item.order,
        )
        for uri in (photo_uris.get(photo.photo_id),)
        if uri
    ) or (detail_uri,)
    split_uris = detail_uris
    product_name = profile.display_name or profile.product_type
    hero_copy = next(
        (section for section in profile.copy_sections if section.section_type == "hero"),
        None,
    )
    three_gallery, two_gallery = _gallery(detail_uris, product_name)
    layout_class = "adaptive" if profile.page_plan else profile.layout_id
    values = {
        "{{PAGE_CSS}}": css,
        "{{LAYOUT_CLASS}}": f"detail-page--{layout_class}",
        "{{DYNAMIC_SECTIONS}}": _dynamic_sections(
            profile,
            photo_uris=photo_uris,
            fallback_uri=source_image_uri,
            product_name=product_name,
        ),
        "{{PRODUCT_TYPE}}": _escape(profile.product_type),
        "{{PRODUCT_NAME}}": _escape(product_name),
        "{{SUMMARY}}": _escape(profile.summary),
        "{{HERO_HEADLINE}}": _escape(
            hero_copy.title if hero_copy else "이미지에서 발견한 제품의 특징"
        ),
        "{{HERO_DESCRIPTION}}": _escape(
            hero_copy.description if hero_copy else profile.summary
        ),
        "{{KEYWORDS}}": _keywords(profile),
        "{{HERO_IMAGE}}": _image_tag(
            hero_uri, alt=f"{product_name} 대표 이미지", class_name="product-image product-image--hero"
        ),
        "{{USAGE_IMAGE}}": _image_tag(
            lifestyle_uri,
            alt=f"{product_name} 활용 이미지",
            class_name="product-image product-image--usage",
        ),
        "{{SCALE_IMAGE}}": _image_tag(
            scale_uri,
            alt=f"{product_name} 크기 참고 이미지",
            class_name="product-image product-image--scale",
        ),
        "{{FEATURE_CARDS}}": _feature_cards(profile),
        "{{CRAFT_CONTEXT}}": _craft_context(profile),
        "{{SPLIT_SECTIONS}}": _split_sections(profile, split_uris),
        "{{WIDE_IMAGE}}": _image_tag(
            packshot_uri,
            alt=f"{product_name} 전체 팩샷 이미지",
            class_name="product-image product-image--wide",
        ),
        "{{THREE_GALLERY}}": three_gallery,
        "{{TWO_GALLERY}}": two_gallery,
        "{{USAGE_SCENE}}": _escape(profile.usage_scene or "이미지에서 확인되는 제품의 형태와 패턴을 중심으로 연출합니다."),
        "{{NOTICE_ITEMS}}": _notice_items(profile),
    }
    for token, value in values.items():
        template = template.replace(token, value)

    if "{{" in template or "}}" in template:
        raise HtmlTemplateError("Detail-page HTML template has unresolved placeholders")
    return template


def _png_dimensions(data: bytes) -> tuple[int | None, int | None]:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    return None, None


def _load_section_assets(sections_dir: Path) -> tuple[GeneratedSection, ...]:
    manifest_path = sections_dir / "manifest.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HtmlTemplateError("HTML section capture manifest could not be read") from exc

    raw_sections = payload.get("sections") if isinstance(payload, dict) else None
    if not isinstance(raw_sections, list):
        raise HtmlTemplateError("HTML section capture manifest has no sections")

    sections = []
    for raw_section in raw_sections:
        if not isinstance(raw_section, dict):
            raise HtmlTemplateError("HTML section capture manifest contains an invalid section")
        filename = raw_section.get("file")
        if not isinstance(filename, str) or not filename or Path(filename).name != filename:
            raise HtmlTemplateError("HTML section capture manifest contains an unsafe filename")
        section_path = sections_dir / filename
        try:
            section_data = section_path.read_bytes()
        except OSError as exc:
            raise HtmlTemplateError("HTML section image could not be read") from exc
        if not section_data:
            raise HtmlTemplateError("HTML section image is empty")
        sections.append(
            GeneratedSection(
                section_id=str(raw_section.get("section_id") or "section"),
                order=int(raw_section.get("order") or len(sections) + 1),
                label=str(raw_section.get("label") or raw_section.get("section_id") or "section"),
                data=section_data,
                mime_type="image/png",
                width=raw_section.get("width"),
                height=raw_section.get("height"),
            )
        )
    return tuple(sorted(sections, key=lambda section: section.order))


class HtmlDetailPageRenderer:
    """Render a DTO-backed HTML page as a full PNG and ordered section PNGs."""

    def __init__(
        self,
        *,
        capture_script: str | Path | None = None,
        node_binary: str = "node",
        command_runner: Callable[..., Any] | None = None,
    ):
        self.capture_script = Path(
            capture_script or PROJECT_ROOT / "scripts" / "runtime" / "render_detail_page.mjs"
        )
        self.node_binary = node_binary
        self.command_runner = command_runner or subprocess.run

    def render(
        self,
        source_image: bytes,
        source_mime_type: str,
        template_image: bytes | None,
        profile: ProductProfileDto,
        options: Any = None,
        photo_set: ProductPhotoSet | None = None,
    ) -> GeneratedImage:
        del template_image
        page_html = build_detail_page_html(
            profile,
            source_image,
            mime_type=source_mime_type,
            photo_set=photo_set,
        )
        with tempfile.TemporaryDirectory(prefix="detail-page-render-") as temp_dir:
            temp_root = Path(temp_dir)
            html_path = temp_root / "detail-page.html"
            output_path = temp_root / "detail-page.png"
            sections_dir = temp_root / "sections"
            html_path.write_text(page_html, encoding="utf-8")
            self.command_runner(
                [
                    self.node_binary,
                    str(self.capture_script),
                    str(html_path),
                    str(output_path),
                    "--sections",
                    str(sections_dir),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            data = output_path.read_bytes()
            sections = _load_section_assets(sections_dir)

        if not data:
            raise HtmlTemplateError("HTML detail-page capture returned no image")
        width, height = _png_dimensions(data)
        return GeneratedImage(
            data=data,
            mime_type="image/png",
            width=width,
            height=height,
            sections=sections,
            photos=photo_set.photos if photo_set else (),
        )
