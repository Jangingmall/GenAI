"""Build the validated React document from the service's approved draft."""

from __future__ import annotations

import re

from .dto import (
    ApprovedDraftDto,
    PageBlockDto,
    PageBlockItemDto,
)
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

_CARD_COLORS = {
    "paper": ("#E6EEEF", "#222222"),
    "light": ("#EEF3F4", "#222222"),
    "sand": ("#F0F0F0", "#222222"),
    "dark": ("#414954", "#FFFFFF"),
    "image-left": ("#EEF3F4", "#222222"),
    "image-right": ("#EEF3F4", "#222222"),
    "full-bleed": ("#E6EEEF", "#222222"),
    "compact": ("#F0F0F0", "#222222"),
}


def _slug(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-_")
    return normalized[:42]


def _node_id(block_id: str, suffix: str) -> str:
    return f"{block_id}-{suffix}"[:80]


def _edges(value: float) -> dict[str, float]:
    return {"top": value, "right": value, "bottom": value, "left": value}


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


def _typography_style(
    *,
    font_size: float,
    font_weight: int,
    line_height: float,
    color: str | None = None,
) -> ReactStylePropsDto:
    return ReactStylePropsDto(
        color=color,
        font_family="sans",
        font_size=font_size,
        font_weight=font_weight,
        line_height=line_height,
        margin=_edges(0),
    )


def _eyebrow_style() -> ReactStylePropsDto:
    return _typography_style(font_size=13, font_weight=500, line_height=1.5)


def _heading_style(*, hero: bool = False) -> ReactStylePropsDto:
    return _typography_style(
        font_size=40 if hero else 30,
        font_weight=700,
        line_height=1.25 if hero else 1.35,
    )


def _body_style() -> ReactStylePropsDto:
    return _typography_style(font_size=16, font_weight=400, line_height=1.7)


def _card_title_style() -> ReactStylePropsDto:
    return _typography_style(font_size=19, font_weight=600, line_height=1.4)


def _text_element(
    *,
    block_id: str,
    suffix: str,
    tag: str,
    value: str,
    style: ReactStylePropsDto,
) -> ReactElementNodeDto | None:
    text = _text(_node_id(block_id, f"{suffix}-text"), value)
    if text is None:
        return None
    return _element(
        block_id=block_id,
        suffix=suffix,
        tag=tag,
        props=ReactElementPropsDto(style=style),
        children=[text],
    )


def _copy_group(
    *, block_id: str, block: PageBlockDto, title: str, body: str
) -> ReactElementNodeDto:
    children: list[ReactElementNodeDto | ReactTextNodeDto] = []
    eyebrow = _text_element(
        block_id=block_id,
        suffix="eyebrow",
        tag="span",
        value=block.eyebrow,
        style=_eyebrow_style(),
    )
    if eyebrow:
        children.append(eyebrow)
    title_node = _text_element(
        block_id=block_id,
        suffix="title",
        tag="h2",
        value=title,
        style=_heading_style(hero=block.block_type == "hero"),
    )
    if title_node:
        children.append(title_node)
    body_node = _text_element(
        block_id=block_id,
        suffix="body",
        tag="p",
        value=body,
        style=_body_style(),
    )
    if body_node:
        children.append(body_node)
    return _element(
        block_id=block_id,
        suffix="copy",
        tag="div",
        props=ReactElementPropsDto(
            layout=ReactLayoutPropsDto(display="stack", gap=16, align="stretch"),
            style=ReactStylePropsDto(margin=_edges(0)),
        ),
        children=children,
    )


def _layout_for_block(block_type: str) -> ReactLayoutPropsDto:
    if block_type == "detail_split":
        return ReactLayoutPropsDto(
            display="flex", direction="row", gap=24, align="center"
        )
    return ReactLayoutPropsDto(display="stack", gap=24, align="stretch")


def _section_style(variant: str) -> ReactStylePropsDto:
    background_color, color = _VARIANT_COLORS.get(
        variant, _VARIANT_COLORS["paper"]
    )
    return ReactStylePropsDto(
        background_color=background_color,
        color=color,
        padding=_edges(40),
        margin=_edges(0),
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
    limit = 5 if block.block_type == "gallery" else 1
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
                    margin=_edges(0),
                ),
            ),
        )
        figures.append(
            _element(
                block_id=block_id,
                suffix=f"figure-{index:02d}",
                tag="figure",
                props=ReactElementPropsDto(
                    style=ReactStylePropsDto(margin=_edges(0))
                ),
                children=[image],
            )
        )
    return figures


def _media_group(
    *, block_id: str, block: PageBlockDto, product_name: str
) -> ReactElementNodeDto | None:
    figures = _image_figures(block_id=block_id, block=block, product_name=product_name)
    if not figures:
        return None

    if block.block_type == "gallery":
        rows: list[ReactElementNodeDto] = []
        for row_index, (columns, row_figures) in enumerate(
            ((3, figures[:3]), (2, figures[3:5])), start=1
        ):
            if not row_figures:
                continue
            rows.append(
                _element(
                    block_id=block_id,
                    suffix=f"gallery-row-{row_index:02d}",
                    tag="div",
                    props=ReactElementPropsDto(
                        layout=ReactLayoutPropsDto(
                            display="grid", columns=columns, gap=16, align="stretch"
                        ),
                        style=ReactStylePropsDto(margin=_edges(0)),
                    ),
                    children=row_figures,
                )
            )
        media_children = rows
    else:
        media_children = figures
    return _element(
        block_id=block_id,
        suffix="media",
        tag="div",
        props=ReactElementPropsDto(
            layout=ReactLayoutPropsDto(display="stack", gap=16, align="stretch"),
            style=ReactStylePropsDto(margin=_edges(0)),
        ),
        children=media_children,
    )


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
                    props=ReactElementPropsDto(style=_card_title_style()),
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
                    props=ReactElementPropsDto(style=_body_style()),
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
                        props=ReactElementPropsDto(style=_body_style()),
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
    return _element(
        block_id=block_id,
        suffix="items",
        tag="ul",
        props=ReactElementPropsDto(
            layout=ReactLayoutPropsDto(display="stack", gap=12, align="stretch"),
            style=ReactStylePropsDto(margin=_edges(0)),
        ),
        children=children,
    )


def _card_style(variant: str) -> ReactStylePropsDto:
    background_color, color = _CARD_COLORS.get(variant, _CARD_COLORS["paper"])
    return ReactStylePropsDto(
        background_color=background_color,
        color=color,
        padding=_edges(20),
        border_radius=12,
        margin=_edges(0),
    )


def _card_items(
    *, block_id: str, block: PageBlockDto
) -> ReactElementNodeDto | None:
    cards: list[ReactElementNodeDto] = []
    for index, item in enumerate(block.items[:3], start=1):
        title = _text_element(
            block_id=block_id,
            suffix=f"card-{index:02d}-title",
            tag="h3",
            value=item.label,
            style=_card_title_style(),
        )
        description = _text_element(
            block_id=block_id,
            suffix=f"card-{index:02d}-body",
            tag="p",
            value=_item_value(item),
            style=_body_style(),
        )
        children = [node for node in (title, description) if node is not None]
        if not children:
            continue
        cards.append(
            _element(
                block_id=block_id,
                suffix=f"card-{index:02d}",
                tag="article",
                props=ReactElementPropsDto(
                    layout=ReactLayoutPropsDto(
                        display="stack", gap=12, align="stretch"
                    ),
                    style=_card_style(block.variant),
                ),
                children=children,
            )
        )
    if not cards:
        return None
    return _element(
        block_id=block_id,
        suffix="cards",
        tag="div",
        props=ReactElementPropsDto(
            layout=ReactLayoutPropsDto(
                display="grid", columns=3, gap=16, align="stretch"
            ),
            style=ReactStylePropsDto(margin=_edges(0)),
        ),
        children=cards,
    )


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
                    props=ReactElementPropsDto(
                        scope="row",
                        style=_typography_style(
                            font_size=16, font_weight=600, line_height=1.5
                        ),
                    ),
                    children=[label],
                )
            )
        if value:
            cells.append(
                _element(
                    block_id=block_id,
                    suffix=f"row-{index:02d}-value",
                    tag="td",
                    props=ReactElementPropsDto(style=_body_style()),
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
            props=ReactElementPropsDto(style=_eyebrow_style()),
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
        props=ReactElementPropsDto(
            layout=ReactLayoutPropsDto(display="stack", gap=12, align="stretch"),
            style=ReactStylePropsDto(margin=_edges(0)),
        ),
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

    copy_group = _copy_group(block_id=block_id, block=block, title=title, body=body)
    children: list[ReactElementNodeDto | ReactTextNodeDto] = [copy_group]

    if block.block_type == "info_table":
        table = _info_table(block_id=block_id, title=title, items=block.items)
        if table:
            children.append(table)
    elif block.block_type in {"feature_grid", "recommendation"}:
        cards = _card_items(block_id=block_id, block=block)
        if cards:
            children.append(cards)
    elif block.block_type == "notice":
        item_list = _list_items(block_id=block_id, items=block.items)
        if item_list:
            children.append(item_list)

    if block.block_type in _IMAGE_BLOCK_TYPES:
        media_group = _media_group(
            block_id=block_id, block=block, product_name=product_name
        )
        if media_group:
            if block.block_type == "detail_split":
                children = [copy_group, media_group]
            else:
                children.append(media_group)

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
