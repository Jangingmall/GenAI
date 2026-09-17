"""Validated, serializable React-like document AST for detail pages.

The service returns a deliberately small document language instead of JSX,
React elements, HTML, or CSS strings.  Keeping the AST independent from the
product-analysis DTOs also makes it safe to validate before it crosses the
BE/FE boundary.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal, Union
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MAX_REACT_DOCUMENT_DEPTH = 20
MAX_REACT_DOCUMENT_NODES = 300

_NODE_ID_PATTERN = r"^[A-Za-z][A-Za-z0-9_-]{0,79}$"
_IMAGE_ID_PATTERN = r"^[A-Za-z][A-Za-z0-9_.:-]{0,199}$"
_VARIANT_PATTERN = r"^[A-Za-z][A-Za-z0-9_-]{0,39}$"
_HEX_COLOR_PATTERN = re.compile(
    r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$"
)
_SAFE_COLOR_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9 -]{0,30}$")


def _validate_color(value: str | None) -> str | None:
    if value is None:
        return None
    if _HEX_COLOR_PATTERN.fullmatch(value):
        return value
    if value in {"transparent", "currentColor"}:
        return value
    if _SAFE_COLOR_NAME_PATTERN.fullmatch(value):
        return value
    raise ValueError("color must be a safe hex color or a simple color token")


def _validate_safe_url(value: str) -> str:
    """Allow internal relative paths and HTTPS URLs, never executable URLs."""

    if any(ord(character) < 0x20 for character in value):
        raise ValueError("URL cannot contain control characters")
    if value.startswith("//"):
        raise ValueError("protocol-relative URLs are not allowed")
    parsed = urlparse(value)
    if parsed.scheme:
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("only HTTPS URLs are allowed for external links")
        return value
    if value.startswith(("/", "./", "../", "#")):
        return value
    raise ValueError("URL must be an internal relative path or HTTPS URL")


class ReactTextMarkDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["bold", "italic", "underline"]


class ReactTextNodeDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=_NODE_ID_PATTERN)
    type: Literal["text"] = "text"
    value: str = Field(max_length=2000)
    marks: list[ReactTextMarkDto] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def require_unique_marks(self) -> ReactTextNodeDto:
        mark_types = [mark.type for mark in self.marks]
        if len(mark_types) != len(set(mark_types)):
            raise ValueError("text marks must be unique")
        return self


class ReactCropRectDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    width: float = Field(gt=0.0, le=1.0)
    height: float = Field(gt=0.0, le=1.0)


class ReactObjectPositionDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)


class ReactEdgeValuesDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    top: float = Field(ge=0.0, le=200.0)
    right: float = Field(ge=0.0, le=200.0)
    bottom: float = Field(ge=0.0, le=200.0)
    left: float = Field(ge=0.0, le=200.0)


class ReactGradientStopDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    color: str
    position: float = Field(ge=0.0, le=1.0)

    _safe_color = field_validator("color")(_validate_color)


class ReactGradientValueDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["linear"] = "linear"
    angle: float = Field(ge=-360.0, le=360.0)
    stops: list[ReactGradientStopDto] = Field(min_length=2, max_length=8)


class ReactShadowValueDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=-1000.0, le=1000.0)
    y: float = Field(ge=-1000.0, le=1000.0)
    blur: float = Field(ge=0.0, le=100.0)
    spread: float = Field(ge=-100.0, le=100.0)
    color: str

    _safe_color = field_validator("color")(_validate_color)


class ReactLayoutPropsDto(BaseModel):
    """Structured layout values; arbitrary CSS layout strings are excluded."""

    model_config = ConfigDict(extra="forbid")

    display: Literal["stack", "flex", "grid"]
    direction: Literal["row", "column"] | None = None
    columns: Literal[1, 2, 3, 4] | None = None
    gap: float = Field(default=0.0, ge=0.0, le=200.0)
    wrap: bool = False
    align: Literal["start", "center", "end", "stretch"] = "stretch"

    @model_validator(mode="after")
    def validate_layout_shape(self) -> ReactLayoutPropsDto:
        if self.display == "stack" and (self.direction is not None or self.columns is not None):
            raise ValueError("stack layout cannot define direction or columns")
        if self.display == "flex" and self.direction is None:
            raise ValueError("flex layout requires direction")
        if self.display == "flex" and self.columns is not None:
            raise ValueError("flex layout cannot define columns")
        if self.display == "grid" and self.columns is None:
            raise ValueError("grid layout requires columns")
        if self.display == "grid" and self.direction is not None:
            raise ValueError("grid layout cannot define direction")
        if self.display == "stack" and self.wrap:
            raise ValueError("stack layout cannot wrap")
        return self


class ReactStylePropsDto(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    color: str | None = None
    background_color: str | None = Field(default=None, alias="backgroundColor")
    gradient: ReactGradientValueDto | None = None
    font_family: Literal["sans", "serif", "display"] | None = Field(
        default=None, alias="fontFamily"
    )
    font_size: float | None = Field(default=None, alias="fontSize", ge=1.0, le=200.0)
    font_weight: Literal[400, 500, 600, 700] | None = Field(default=None, alias="fontWeight")
    line_height: float | None = Field(default=None, alias="lineHeight", ge=0.5, le=4.0)
    letter_spacing: float | None = Field(
        default=None, alias="letterSpacing", ge=-10.0, le=20.0
    )
    text_align: Literal["left", "center", "right"] | None = Field(
        default=None, alias="textAlign"
    )
    opacity: float | None = Field(default=None, ge=0.0, le=1.0)
    border_color: str | None = Field(default=None, alias="borderColor")
    border_width: float | None = Field(default=None, alias="borderWidth", ge=0.0, le=40.0)
    border_radius: float | None = Field(
        default=None, alias="borderRadius", ge=0.0, le=200.0
    )
    box_shadow: ReactShadowValueDto | None = Field(default=None, alias="boxShadow")
    object_fit: Literal["cover", "contain"] | None = Field(default=None, alias="objectFit")
    object_position: ReactObjectPositionDto | None = Field(
        default=None, alias="objectPosition"
    )
    rotate: float | None = Field(default=None, ge=-180.0, le=180.0)
    padding: ReactEdgeValuesDto | None = None
    margin: ReactEdgeValuesDto | None = None

    _safe_colors = field_validator("color", "background_color", "border_color")(
        _validate_color
    )


class ReactElementPropsDto(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    variant: str | None = Field(default=None, max_length=40, pattern=_VARIANT_PATTERN)
    layout: ReactLayoutPropsDto | None = None
    style: ReactStylePropsDto | None = None
    href: str | None = Field(default=None, max_length=2048)
    target: Literal["_self", "_blank"] | None = None
    image_id: str | None = Field(default=None, alias="imageId", max_length=200)
    alt: str | None = Field(default=None, max_length=300)
    crop: ReactCropRectDto | None = None
    video_url: str | None = Field(default=None, alias="videoUrl", max_length=2048)
    scope: Literal["row", "col"] | None = None
    col_span: int | None = Field(default=None, alias="colSpan", ge=1, le=12)
    row_span: int | None = Field(default=None, alias="rowSpan", ge=1, le=12)

    @field_validator("href", "video_url")
    @classmethod
    def require_safe_url(cls, value: str | None) -> str | None:
        return _validate_safe_url(value) if value is not None else None

    @field_validator("image_id")
    @classmethod
    def require_safe_image_id(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(_IMAGE_ID_PATTERN, value):
            raise ValueError("imageId must be a safe asset reference")
        return value


AllowedTag = Literal[
    "section",
    "article",
    "div",
    "h2",
    "h3",
    "h4",
    "p",
    "span",
    "strong",
    "em",
    "ul",
    "ol",
    "li",
    "figure",
    "figcaption",
    "img",
    "video",
    "a",
    "table",
    "caption",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
]


class ReactElementNodeDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=_NODE_ID_PATTERN)
    type: Literal["element"] = "element"
    tag: AllowedTag
    props: ReactElementPropsDto = Field(default_factory=ReactElementPropsDto)
    children: list[Annotated[Union["ReactElementNodeDto", ReactTextNodeDto], Field(discriminator="type")]] = Field(
        default_factory=list, max_length=50
    )


ReactNode = Annotated[
    Union[ReactElementNodeDto, ReactTextNodeDto], Field(discriminator="type")
]


class ReactDetailPageDocumentDto(BaseModel):
    """Top-level FE contract for the restricted detail-page document."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal["2.0"] = Field(default="2.0", alias="schemaVersion")
    canvas_width: int = Field(default=774, alias="canvasWidth", ge=1, le=4096)
    root: list[ReactElementNodeDto] = Field(min_length=1, max_length=14)

    @model_validator(mode="after")
    def validate_document_tree(self) -> ReactDetailPageDocumentDto:
        seen_ids: set[str] = set()
        node_count = 0
        block_tags = {
            "section",
            "article",
            "div",
            "p",
            "ul",
            "ol",
            "figure",
            "table",
        }
        heading_tags = {"h2", "h3", "h4"}

        def walk(
            node: ReactNode,
            depth: int,
            parent_tag: str | None,
            ancestor_tags: tuple[str, ...],
        ) -> None:
            nonlocal node_count
            node_count += 1
            if node_count > MAX_REACT_DOCUMENT_NODES:
                raise ValueError(
                    f"document exceeds the {MAX_REACT_DOCUMENT_NODES}-node limit"
                )
            if depth > MAX_REACT_DOCUMENT_DEPTH:
                raise ValueError(
                    f"document exceeds the {MAX_REACT_DOCUMENT_DEPTH}-level depth limit"
                )
            if node.id in seen_ids:
                raise ValueError(f"duplicate node id: {node.id}")
            seen_ids.add(node.id)

            if isinstance(node, ReactTextNodeDto):
                return

            props = node.props
            if node.tag == "img":
                if not props.image_id:
                    raise ValueError("img requires props.imageId")
                if node.children:
                    raise ValueError("img cannot have children")
            elif props.image_id is not None:
                raise ValueError("props.imageId is only valid on img")

            if node.tag == "video" and not props.video_url:
                raise ValueError("video requires props.videoUrl")
            if node.tag != "video" and props.video_url is not None:
                raise ValueError("props.videoUrl is only valid on video")

            if node.tag == "a" and not props.href:
                raise ValueError("a requires props.href")
            if node.tag != "a" and props.href is not None:
                raise ValueError("props.href is only valid on a")
            if node.tag != "a" and props.target is not None:
                raise ValueError("props.target is only valid on a")
            if node.tag != "img" and props.alt is not None:
                raise ValueError("props.alt is only valid on img")
            if node.tag != "img" and props.crop is not None:
                raise ValueError("props.crop is only valid on img")

            child_tags = [
                child.tag
                for child in node.children
                if isinstance(child, ReactElementNodeDto)
            ]
            if node.tag in {"ul", "ol"} and any(
                not isinstance(child, ReactElementNodeDto) or child.tag != "li"
                for child in node.children
            ):
                raise ValueError(f"{node.tag} direct children must be li elements")
            if node.tag == "table" and any(
                not isinstance(child, ReactElementNodeDto)
                or child.tag not in {"caption", "thead", "tbody"}
                for child in node.children
            ):
                raise ValueError("table direct children must be caption, thead, or tbody")
            if node.tag in {"thead", "tbody"} and any(
                not isinstance(child, ReactElementNodeDto) or child.tag != "tr"
                for child in node.children
            ):
                raise ValueError("thead/tbody direct children must be tr elements")
            if node.tag == "tr" and any(
                not isinstance(child, ReactElementNodeDto)
                or child.tag not in {"th", "td"}
                for child in node.children
            ):
                raise ValueError("tr direct children must be th or td elements")
            if node.tag == "a" and "a" in ancestor_tags:
                raise ValueError("nested a elements are not allowed")
            if node.tag in heading_tags and any(
                child_tag in block_tags for child_tag in child_tags
            ):
                raise ValueError("heading elements cannot contain block elements")

            for child in node.children:
                walk(child, depth + 1, node.tag, (*ancestor_tags, node.tag))

        for root_node in self.root:
            walk(root_node, 1, None, ())
        return self


ReactElementNodeDto.model_rebuild()
ReactDetailPageDocumentDto.model_rebuild()


__all__ = [
    "AllowedTag",
    "MAX_REACT_DOCUMENT_DEPTH",
    "MAX_REACT_DOCUMENT_NODES",
    "ReactCropRectDto",
    "ReactDetailPageDocumentDto",
    "ReactEdgeValuesDto",
    "ReactElementNodeDto",
    "ReactElementPropsDto",
    "ReactGradientStopDto",
    "ReactGradientValueDto",
    "ReactLayoutPropsDto",
    "ReactNode",
    "ReactObjectPositionDto",
    "ReactShadowValueDto",
    "ReactStylePropsDto",
    "ReactTextMarkDto",
    "ReactTextNodeDto",
]
