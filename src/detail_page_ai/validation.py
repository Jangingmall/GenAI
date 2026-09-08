from .dto import PageBlockDto, PageBlockItemDto, ProductProfileDto


SUPPORTED_MIME_TYPES = {"image/png", "image/jpeg", "image/webp"}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8\xff"
WEBP_SIGNATURE = b"RIFF"


class ValidationError(ValueError):
    """Base class for input and AI-output validation failures."""


class InvalidImageError(ValidationError):
    pass


class ProfileValidationError(ValidationError):
    pass


def validate_source_image(
    data: bytes,
    mime_type: str,
    *,
    max_bytes: int = 10 * 1024 * 1024,
    require_decodable: bool = False,
) -> None:
    if mime_type not in SUPPORTED_MIME_TYPES:
        raise InvalidImageError(f"Unsupported image MIME type: {mime_type}")
    if not data:
        raise InvalidImageError("Image is empty")
    if len(data) > max_bytes:
        raise InvalidImageError("Image exceeds the maximum allowed size")

    signature_matches = (
        (mime_type == "image/png" and data.startswith(PNG_SIGNATURE))
        or (mime_type == "image/jpeg" and data.startswith(JPEG_SIGNATURE))
        or (
            mime_type == "image/webp"
            and len(data) >= 12
            and data.startswith(WEBP_SIGNATURE)
            and data[8:12] == b"WEBP"
        )
    )
    if not signature_matches:
        raise InvalidImageError("Image bytes do not match the declared MIME type")
    if require_decodable:
        try:
            from io import BytesIO
            from PIL import Image

            with Image.open(BytesIO(data)) as image:
                image.verify()
        except Exception as exc:
            raise InvalidImageError("Image bytes could not be decoded") from exc


def validate_product_profile(profile: ProductProfileDto) -> None:
    if not profile.product_type.strip():
        raise ProfileValidationError("product_type must not be empty")
    if not profile.summary.strip():
        raise ProfileValidationError("summary must not be empty")
    if len(profile.summary) > 500:
        raise ProfileValidationError("summary must be at most 500 characters")
    if len(profile.features) > 5:
        raise ProfileValidationError("features must contain at most 5 items")
    if len(profile.copy_sections) > 8:
        raise ProfileValidationError("copy_sections must contain at most 8 items")
    for feature in profile.features:
        if not 0 <= feature.confidence <= 1:
            raise ProfileValidationError("feature confidence must be between 0 and 1")


def ensure_editorial_page_plan(profile: ProductProfileDto) -> ProductProfileDto:
    """Fill required editorial beats that an image model may omit.

    The AI-authored copy and relative order remain authoritative. This function only
    moves the hero/closing to their required edges, applies the fidelity-sensitive
    image variants, and inserts missing reference-inspired blocks.
    """
    if not profile.page_plan:
        return profile

    product_name = profile.display_name or profile.product_type
    original = list(profile.page_plan)
    hero = next((block for block in original if block.block_type == "hero"), None)
    closing = next((block for block in original if block.block_type == "closing"), None)
    middle = [
        block
        for block in original
        if block.block_type not in {"hero", "closing"}
    ]

    hero = (hero or PageBlockDto(
        section_id="hero",
        block_type="hero",
        eyebrow="OBJECT DETAIL",
        title=product_name,
        body=profile.summary,
        photo_id="hero",
    )).model_copy(update={"variant": "paper", "photo_id": "hero"})
    closing = (closing or PageBlockDto(
        section_id="closing",
        block_type="closing",
        eyebrow="CRAFTSMANSHIP",
        title="공간에 오래 남는 인상",
        body=profile.summary,
    )).model_copy(update={"variant": "paper"})

    def first_index(*block_types: str) -> int:
        return next(
            (
                index
                for index, block in enumerate(middle)
                if block.block_type in block_types
            ),
            len(middle),
        )

    detail_index = first_index("detail_split")
    if detail_index == len(middle):
        middle.insert(
            min(first_index("usage_scene", "gallery", "palette", "info_table"), len(middle)),
            PageBlockDto(
                section_id="surface-detail",
                block_type="detail_split",
                eyebrow="SURFACE DETAIL",
                title="가까이에서 본 표면과 형태",
                body=profile.summary,
                variant="dark",
                photo_id="detail",
            ),
        )
    else:
        middle[detail_index] = middle[detail_index].model_copy(
            update={
                "variant": "dark",
                "photo_id": middle[detail_index].photo_id or "detail",
            }
        )

    usage_index = first_index("usage_scene")
    if usage_index == len(middle):
        detail_index = first_index("detail_split")
        middle.insert(
            detail_index + 1,
            PageBlockDto(
                section_id="usage-scene",
                block_type="usage_scene",
                eyebrow="EVERYDAY SCENE",
                title="일상에 놓인 공예의 풍경",
                body=profile.usage_scene or "제품이 자연스럽게 놓이는 장면을 제안합니다.",
                variant="full-bleed",
                photo_id="lifestyle",
            ),
        )
    else:
        middle[usage_index] = middle[usage_index].model_copy(
            update={"variant": "full-bleed", "photo_id": "lifestyle"}
        )

    # A palette explains color/surface; it is not a substitute for the product
    # gallery. Keep both blocks when the model returns only one of them.
    if not any(block.block_type == "gallery" for block in middle):
        usage_index = first_index("usage_scene")
        middle.insert(
            usage_index + 1,
            PageBlockDto(
                section_id="product-gallery",
                block_type="gallery",
                eyebrow="PRODUCT GALLERY",
                title="색과 형태를 가까이에서",
                body="원본 이미지에서 확인되는 서로 다른 표면과 구성을 살펴보세요.",
                variant="paper",
                photo_ids=["detail", "detail-02", "detail-03", "detail-04"],
            ),
        )

    if not any(block.block_type == "recommendation" for block in middle):
        middle.insert(
            first_index("info_table", "notice"),
            PageBlockDto(
                section_id="recommended-scenes",
                block_type="recommendation",
                eyebrow="RECOMMENDED SCENES",
                title="이런 자리에서 더 잘 어울립니다.",
                body="제품의 색과 실루엣을 기준으로 제안하는 연출 아이디어입니다.",
                variant="paper",
                items=[
                    PageBlockItemDto(
                        label="01",
                        value="여백 있는 테이블",
                        description="주변 소품을 덜어 형태가 돋보이게 연출해 보세요.",
                        evidence="inferred",
                    ),
                    PageBlockItemDto(
                        label="02",
                        value="부드러운 자연광",
                        description="측면의 은은한 빛으로 표면의 결을 살려 보세요.",
                        evidence="inferred",
                    ),
                    PageBlockItemDto(
                        label="03",
                        value="차분한 배경색",
                        description="크림·베이지 계열 배경으로 제품에 시선을 모아 보세요.",
                        evidence="inferred",
                    ),
                ],
            ),
        )

    if not any(block.block_type == "info_table" for block in middle):
        components = profile.observations.get("visible_components", [])
        colors = profile.observations.get("colors", [])
        middle.insert(
            first_index("notice"),
            PageBlockDto(
                section_id="product-info",
                block_type="info_table",
                eyebrow="SPECIFICATIONS",
                title="주문 전 확인할 기본 정보",
                body="이미지에서 확인되는 범위만 정리했습니다.",
                variant="light",
                items=[
                    PageBlockItemDto(
                        label="구성",
                        value=(
                            ", ".join(str(value) for value in components[:6])
                            if isinstance(components, list) and components
                            else "확인 필요"
                        ),
                    ),
                    PageBlockItemDto(
                        label="색상",
                        value=(
                            ", ".join(str(value) for value in colors[:4])
                            if isinstance(colors, list) and colors
                            else "확인 필요"
                        ),
                    ),
                    PageBlockItemDto(label="소재·크기", value="확인 필요", evidence="unknown"),
                ],
            ),
        )

    notice_index = first_index("notice")
    if notice_index == len(middle):
        middle.append(
            PageBlockDto(
                section_id="care-notice",
                block_type="notice",
                eyebrow="CARE NOTE",
                title="구매 전 확인해 주세요.",
                body="관리법과 정확한 사양은 장인의 입력 내용으로 최종 확인해 주세요.",
                variant="dark",
            )
        )
    else:
        middle[notice_index] = middle[notice_index].model_copy(update={"variant": "dark"})

    if len(middle) < 7 and not any(block.block_type == "statement" for block in middle):
        middle.insert(
            0,
            PageBlockDto(
                section_id="editorial-statement",
                block_type="statement",
                eyebrow="OBJECT STORY",
                title="형태와 표면이 만드는 조화",
                body=profile.summary,
                variant="paper",
            ),
        )

    plan = [hero, *middle, closing]
    if len(plan) > 14:
        optional_types = {"wide_image", "scale_reference", "statement"}
        while len(plan) > 14:
            removable = next(
                (
                    index
                    for index in range(len(plan) - 2, 0, -1)
                    if plan[index].block_type in optional_types
                ),
                None,
            )
            if removable is None:
                break
            plan.pop(removable)
    return profile.model_copy(update={"page_plan": plan[:13] + [closing] if len(plan) > 14 else plan})


def sanitize_profile_for_render(profile: ProductProfileDto) -> ProductProfileDto:
    """Keep uncertain model claims out of customer-facing selling copy."""
    safe_features = [
        feature for feature in profile.features if feature.evidence == "image-visible"
    ]
    safe_copy_sections = [
        section
        for section in profile.copy_sections
        if section.evidence == "image-visible"
    ]
    rejected = [
        f"검증되지 않은 AI 추정 문구 제외: {item.title}"
        for item in [*profile.features, *profile.copy_sections]
        if getattr(item, "evidence", "image-visible") != "image-visible"
    ]
    warnings = list(dict.fromkeys([*profile.uncertain_information, *rejected]))
    return profile.model_copy(
        update={
            "features": safe_features,
            "copy_sections": safe_copy_sections,
            "uncertain_information": warnings[:12],
        }
    )
