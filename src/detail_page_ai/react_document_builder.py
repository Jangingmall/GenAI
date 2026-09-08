"""Build the validated React document from the service's approved draft."""

from __future__ import annotations

import re

from .dto import ApprovedDraftDto, PageBlockDto, PageBlockItemDto
from .react_document import (
    ReactDetailPageDocumentDto,
    ReactElementNodeDto,
    ReactElementPropsDto,
    ReactLayoutPropsDto,
    ReactStylePropsDto,
    ReactTextNodeDto,
)


_DEFAULT_PHOTO_BY_BLOCK = {
    "hero": "hero",
    "detail_split": "detail",
    "wide_image": "hero",
    "usage_scene": "lifestyle",
    "scale_reference": "hero",
    "palette": "detail",
}

_IMAGE_BLOCK_TYPES = set(_DEFAULT_PHOTO_BY_BLOCK) | {"gallery"}
_ITEM_BLOCK_TYPES = {"feature_grid", "recommendation", "notice"}

_VARIANT_COLORS = {
    "paper": ("#F6F2EC", "#222222"),
    "light": ("#F7F7F5", "#222222"),
    "sand": ("#EEE5D8", "#222222"),
    "dark": ("#242424", "#F7F4EE"),
    "image-left": ("#F7F7F5", "#222222"),
    "image-right": ("#F7F7F5", "#222222"),
    "full-bleed": ("#E8E5DF", "#222222"),
    "compact": ("#FAFAF8", "#222222"),
}


def _slug(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-_")
    return normalized[:42]


def _node_id(block_id: str, suffix: str) -> str:
    return f"{block_id}-{suffix}"[:80]


def _text(node_id: str, value: str) -> ReactTextNodeDto | None:
    value = value.strip()
    return ReactTextNodeDto(id=node_id, value=value) if value else None


def _element(
    *,
    block_id: str,
    suffix: str,
    tag: str,
    children: list[ReactElementNodeDto | ReactTextNodeDto] | None = None,
    props: ReactElementPropsDto | None = None,
) -> ReactElementNodeDto:
    return ReactElementNodeDto(
        id=_node_id(block_id, suffix),
        tag=tag,
        props=props or ReactElementPropsDto(),
        children=children or [],
    )


def _layout_for_block(block_type: str) -> ReactLayoutPropsDto:
    if block_type == "detail_split":
        return ReactLayoutPropsDto(
            display="flex", direction="row", gap=24, align="center"
        )
    if block_type in {"feature_grid", "recommendation"}:
        return ReactLayoutPropsDto(display="grid", columns=3, gap=24)
    return ReactLayoutPropsDto(display="stack", gap=16, align="stretch")


def _section_style(variant: str) -> ReactStylePropsDto:
    background_color, color = _VARIANT_COLORS.get(
        variant, _VARIANT_COLORS["paper"]
    )
    return ReactStylePropsDto(
        background_color=background_color,
        color=color,
        padding={"top": 48, "right": 32, "bottom": 48, "left": 32},
    )


def _photo_ids(block: PageBlockDto) -> list[str]:
    candidates = [*( [block.photo_id] if block.photo_id else []), *block.photo_ids]
    if not candidates:
        default_photo_id = _DEFAULT_PHOTO_BY_BLOCK.get(block.block_type)
        if default_photo_id:
            candidates = [default_photo_id]
    deduplicated: list[str] = []
    for photo_id in candidates:
        if photo_id and photo_id not in deduplicated:
            deduplicated.append(photo_id)
    limit = 4 if block.block_type == "gallery" else 1
    return deduplicated[:limit]


def _image_figures(
    *, block_id: str, block: PageBlockDto, product_name: str
) -> list[ReactElementNodeDto]:
    figures: list[ReactElementNodeDto] = []
    for index, photo_id in enumerate(_photo_ids(block), start=1):
        alt_label = block.title or block.block_type.replace("_", " ")
        image = _element(
            block_id=block_id,
            suffix=f"image-{index:02d}",
            tag="img",
            props=ReactElementPropsDto(
                image_id=photo_id,
                alt=f"{product_name} {alt_label}"[:300],
                style=ReactStylePropsDto(
                    object_fit="cover"
                    if block.block_type in {"wide_image", "usage_scene"}
                    else "contain",
                    object_position={"x": 0.5, "y": 0.5},
                ),
            ),
        )
        figures.append(
            _element(
                block_id=block_id,
                suffix=f"figure-{index:02d}",
                tag="figure",
                children=[image],
            )
        )
    return figures


def _item_value(item: PageBlockItemDto) -> str:
    return item.value.strip() or item.description.strip()


def _list_items(
    *, block_id: str, items: list[PageBlockItemDto]
) -> ReactElementNodeDto | None:
    children: list[ReactElementNodeDto] = []
    for index, item in enumerate(items[:3], start=1):
        item_children: list[ReactElementNodeDto | ReactTextNodeDto] = []
        label = _text(_node_id(block_id, f"item-{index:02d}-label-text"), item.label)
        if label:
            item_children.append(
                _element(
                    block_id=block_id,
                    suffix=f"item-{index:02d}-label",
                    tag="strong",
                    children=[label],
                )
            )
        value = _item_value(item)
        value_node = _text(_node_id(block_id, f"item-{index:02d}-value-text"), value)
        if value_node:
            item_children.append(
                _element(
                    block_id=block_id,
                    suffix=f"item-{index:02d}-value",
                    tag="span",
                    children=[value_node],
                )
            )
        if item.description.strip() and item.value.strip():
            description = _text(
                _node_id(block_id, f"item-{index:02d}-description-text"),
                item.description,
            )
            if description:
                item_children.append(
                    _element(
                        block_id=block_id,
                        suffix=f"item-{index:02d}-description",
                        tag="span",
                        children=[description],
                    )
                )
        if item_children:
            children.append(
                _element(
                    block_id=block_id,
                    suffix=f"item-{index:02d}",
                    tag="li",
                    children=item_children,
                )
            )
    if not children:
        return None
    return _element(block_id=block_id, suffix="items", tag="ul", children=children)


def _info_table(
    *, block_id: str, title: str, items: list[PageBlockItemDto]
) -> ReactElementNodeDto | None:
    rows: list[ReactElementNodeDto] = []
    for index, item in enumerate(items[:6], start=1):
        label = _text(_node_id(block_id, f"row-{index:02d}-label-text"), item.label)
        value = _text(_node_id(block_id, f"row-{index:02d}-value-text"), _item_value(item))
        if not label and not value:
            continue
        cells: list[ReactElementNodeDto] = []
        if label:
            cells.append(
                _element(
                    block_id=block_id,
                    suffix=f"row-{index:02d}-label",
                    tag="th",
                    props=ReactElementPropsDto(scope="row"),
                    children=[label],
                )
            )
        if value:
            cells.append(
                _element(
                    block_id=block_id,
                    suffix=f"row-{index:02d}-value",
                    tag="td",
                    children=[value],
                )
            )
        rows.append(
            _element(
                block_id=block_id,
                suffix=f"row-{index:02d}",
                tag="tr",
                children=cells,
            )
        )
    if not rows:
        return None
    caption = _text(_node_id(block_id, "table-caption-text"), title)
    caption_node = (
        _element(
            block_id=block_id,
            suffix="table-caption",
            tag="caption",
            children=[caption],
        )
        if caption
        else None
    )
    body = _element(
        block_id=block_id,
        suffix="table-body",
        tag="tbody",
        children=rows,
    )
    return _element(
        block_id=block_id,
        suffix="table",
        tag="table",
        children=[node for node in (caption_node, body) if node is not None],
    )


def _fallback_blocks(draft: ApprovedDraftDto) -> list[PageBlockDto]:
    return [
        PageBlockDto(
            section_id="hero",
            block_type="hero",
            eyebrow="OBJECT DETAIL",
            title=draft.hero_headline,
            body=draft.hero_description,
            photo_id="hero",
        ),
        PageBlockDto(
            section_id="story",
            block_type="statement",
            eyebrow="OBJECT STORY",
            title=draft.product_name,
            body=draft.summary,
        ),
        PageBlockDto(
            section_id="closing",
            block_type="closing",
            eyebrow="CRAFTSMANSHIP",
            title="공간에 오래 남는 인상",
            body=draft.summary,
        ),
    ]


def _build_block(
    *, block: PageBlockDto, index: int, product_name: str, draft: ApprovedDraftDto
) -> ReactElementNodeDto:
    slug = _slug(block.section_id) or "section"
    block_id = f"section-{index:02d}-{slug}"[:70]
    title = block.title.strip() or product_name
    body = block.body.strip()
    if block.block_type == "hero":
        title = draft.hero_headline
        body = draft.hero_description

    children: list[ReactElementNodeDto | ReactTextNodeDto] = []
    eyebrow = _text(_node_id(block_id, "eyebrow-text"), block.eyebrow)
    if eyebrow:
        children.append(
            _element(
                block_id=block_id,
                suffix="eyebrow",
                tag="span",
                children=[eyebrow],
            )
        )
    title_node = _text(_node_id(block_id, "title-text"), title)
    if title_node:
        children.append(
            _element(
                block_id=block_id,
                suffix="title",
                tag="h2",
                children=[title_node],
            )
        )
    body_node = _text(_node_id(block_id, "body-text"), body)
    if body_node:
        children.append(
            _element(
                block_id=block_id,
                suffix="body",
                tag="p",
                children=[body_node],
            )
        )

    if block.block_type == "info_table":
        table = _info_table(block_id=block_id, title=title, items=block.items)
        if table:
            children.append(table)
    elif block.block_type in _ITEM_BLOCK_TYPES:
        item_list = _list_items(block_id=block_id, items=block.items)
        if item_list:
            children.append(item_list)

    if block.block_type in _IMAGE_BLOCK_TYPES:
        children.extend(_image_figures(block_id=block_id, block=block, product_name=product_name))

    return _element(
        block_id=block_id,
        suffix="root",
        tag="section",
        props=ReactElementPropsDto(
            variant=block.variant,
            layout=_layout_for_block(block.block_type),
            style=_section_style(block.variant),
        ),
        children=children,
    )


def build_react_document_from_draft(
    draft: ApprovedDraftDto,
) -> ReactDetailPageDocumentDto:
    """Convert a validated approved draft into the FE's restricted JSON AST.

    The model never writes this AST directly.  It is assembled from the
    already validated page-plan DTO, so unknown tags, raw HTML, executable
    props, and unverified image URLs cannot leak into the response.
    """

    blocks = draft.page_plan or _fallback_blocks(draft)
    root = [
        _build_block(
            block=block,
            index=index,
            product_name=draft.product_name,
            draft=draft,
        )
        for index, block in enumerate(blocks[:14], start=1)
    ]
    return ReactDetailPageDocumentDto(root=root)


__all__ = ["build_react_document_from_draft"]
