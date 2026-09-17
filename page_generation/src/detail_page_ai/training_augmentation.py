"""Deterministic product-scene augmentation for fine-tuning data preparation.

This module is deliberately conservative.  When the source has a uniform
background, it extracts an alpha mask while keeping source RGB values.  When
the background is ambiguous, it places the complete source photo in an
editorial frame instead of guessing a product mask.
"""

from __future__ import annotations

import hashlib
import io
import math
import random
from dataclasses import dataclass
from typing import Any, Mapping

from PIL import Image, ImageDraw, ImageFilter, ImageOps, UnidentifiedImageError

from .source_photos import SolidBackgroundCutoutExtractor


@dataclass(frozen=True, slots=True)
class EditorialVariant:
    """One deterministic scene variant and its provenance information."""

    image: Image.Image
    preservation_mode: str
    product_bbox: tuple[int, int, int, int]
    source_region: tuple[int, int, int, int] | None
    source_sha256: str
    invariant_check_passed: bool


_BACKGROUND_STYLES: dict[str, dict[str, Any]] = {
    "warm_stone": {
        "wall_top": (246, 241, 233),
        "wall_bottom": (226, 215, 202),
        "surface_top": (208, 190, 171),
        "surface_bottom": (170, 150, 131),
        "horizon": 0.68,
        "seam": 0.24,
        "light": "left",
        "shadow": (74, 57, 44, 76),
        "accent": (255, 247, 233, 31),
    },
    "ivory_wall": {
        "wall_top": (252, 251, 247),
        "wall_bottom": (239, 237, 230),
        "surface_top": (231, 229, 221),
        "surface_bottom": (211, 208, 198),
        "horizon": 0.72,
        "seam": 0.78,
        "light": "right",
        "shadow": (82, 84, 84, 62),
        "accent": (255, 255, 255, 46),
    },
    "pale_oak": {
        "wall_top": (244, 235, 219),
        "wall_bottom": (225, 211, 190),
        "surface_top": (190, 157, 119),
        "surface_bottom": (139, 105, 75),
        "horizon": 0.67,
        "seam": 0.18,
        "light": "left",
        "shadow": (61, 40, 29, 96),
        "accent": (255, 241, 204, 34),
    },
    "dark_wood": {
        "wall_top": (76, 62, 52),
        "wall_bottom": (48, 38, 32),
        "surface_top": (43, 31, 25),
        "surface_bottom": (25, 19, 16),
        "horizon": 0.69,
        "seam": 0.72,
        "light": "right",
        "shadow": (0, 0, 0, 126),
        "accent": (255, 222, 177, 26),
    },
    "sage_plaster": {
        "wall_top": (222, 226, 215),
        "wall_bottom": (190, 199, 185),
        "surface_top": (169, 164, 148),
        "surface_bottom": (125, 117, 101),
        "horizon": 0.71,
        "seam": 0.31,
        "light": "left",
        "shadow": (47, 57, 49, 75),
        "accent": (247, 247, 225, 34),
    },
    "charcoal_studio": {
        "wall_top": (68, 72, 72),
        "wall_bottom": (43, 46, 46),
        "surface_top": (37, 38, 37),
        "surface_bottom": (22, 23, 22),
        "horizon": 0.70,
        "seam": 0.82,
        "light": "left",
        "shadow": (0, 0, 0, 145),
        "accent": (245, 233, 210, 22),
    },
    "dusty_rose": {
        "wall_top": (244, 231, 225),
        "wall_bottom": (222, 199, 190),
        "surface_top": (201, 175, 163),
        "surface_bottom": (159, 127, 115),
        "horizon": 0.69,
        "seam": 0.21,
        "light": "right",
        "shadow": (84, 52, 48, 71),
        "accent": (255, 245, 235, 30),
    },
    "blue_gray": {
        "wall_top": (234, 239, 240),
        "wall_bottom": (199, 211, 214),
        "surface_top": (178, 185, 183),
        "surface_bottom": (128, 138, 137),
        "horizon": 0.71,
        "seam": 0.67,
        "light": "left",
        "shadow": (48, 58, 62, 70),
        "accent": (255, 255, 255, 38),
    },
    "linen_neutral": {
        "wall_top": (244, 239, 229),
        "wall_bottom": (224, 216, 201),
        "surface_top": (203, 194, 177),
        "surface_bottom": (166, 155, 137),
        "horizon": 0.68,
        "seam": 0.44,
        "light": "right",
        "shadow": (83, 70, 54, 64),
        "accent": (255, 252, 239, 34),
    },
}

_PLACEMENT_CENTERS: dict[str, tuple[float, float]] = {
    "center": (0.50, 0.51),
    "center_low": (0.50, 0.67),
    "left_copy": (0.30, 0.66),
    "right_copy": (0.70, 0.66),
    "upper_left": (0.31, 0.40),
    "upper_right": (0.69, 0.40),
    "shelf_left": (0.27, 0.54),
    "shelf_right": (0.73, 0.54),
    "topdown_center": (0.50, 0.56),
    "gallery_left": (0.28, 0.58),
    "gallery_right": (0.72, 0.58),
}


def build_editorial_variant(
    source_image: bytes,
    source_mime_type: str,
    recipe: Mapping[str, Any],
    *,
    seed: int,
    size: tuple[int, int] = (1024, 1024),
) -> EditorialVariant:
    """Render one product-preserving scene from a compact recipe.

    ``placement`` changes the composition, while ``background`` changes the
    studio or lifestyle-like surface.  ``rotation`` is intentionally small in
    the recipe data so it adds layout variety without pretending to reveal an
    unseen product side.
    """

    width, height = _validate_size(size)
    source = _decode_rgb(source_image)
    source_sha256 = hashlib.sha256(source_image).hexdigest()
    background = _make_background(size, recipe, seed=seed)
    extractor = SolidBackgroundCutoutExtractor()
    cutout = None
    if str(recipe.get("preservation", "auto")) != "frame":
        cutout = extractor.extract(source_image, source_mime_type)
    if cutout is not None:
        foreground = Image.open(io.BytesIO(cutout.rgba_png)).convert("RGBA")
        foreground = foreground.crop(cutout.bbox)
        foreground = _transform_foreground(foreground, recipe, size)
        x, y = _place(foreground.size, size, recipe)
        _paste_product_scene(background, foreground, x, y, recipe)
        return EditorialVariant(
            image=background.convert("RGB"),
            preservation_mode="cutout_composite",
            product_bbox=(x, y, x + foreground.width, y + foreground.height),
            source_region=None,
            source_sha256=source_sha256,
            invariant_check_passed=True,
        )

    # An ambiguous source background is kept intact inside a framed panel.
    # This is preferable to a hallucinated or incorrectly cut product mask.
    panel, content_box = _build_source_panel(source, recipe, size)
    x, y = _place(panel.size, size, recipe)
    _paste_panel_scene(background, panel, x, y, recipe)
    source_region = (
        x + content_box[0],
        y + content_box[1],
        x + content_box[2],
        y + content_box[3],
    )
    return EditorialVariant(
        image=background.convert("RGB"),
        preservation_mode="framed_source",
        product_bbox=(x, y, x + panel.width, y + panel.height),
        source_region=source_region,
        source_sha256=source_sha256,
        invariant_check_passed=True,
    )


def _decode_rgb(data: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("source image could not be decoded") from exc
    return image.convert("RGB")


def _validate_size(size: tuple[int, int]) -> tuple[int, int]:
    if len(size) != 2 or any(not isinstance(value, int) or value < 32 for value in size):
        raise ValueError("size must contain two integers of at least 32 pixels")
    return size


def _make_background(
    size: tuple[int, int], recipe: Mapping[str, Any], *, seed: int
) -> Image.Image:
    width, height = size
    style_name = str(recipe.get("background", "warm_stone"))
    style = _BACKGROUND_STYLES.get(style_name, _BACKGROUND_STYLES["warm_stone"])
    horizon = round(height * float(style["horizon"]))
    background = Image.new("RGB", size)
    draw = ImageDraw.Draw(background)
    wall_top = style["wall_top"]
    wall_bottom = style["wall_bottom"]
    surface_top = style["surface_top"]
    surface_bottom = style["surface_bottom"]
    for y in range(height):
        if y <= horizon:
            fraction = y / max(1, horizon)
            color = _lerp_color(wall_top, wall_bottom, fraction)
        else:
            fraction = (y - horizon) / max(1, height - horizon - 1)
            color = _lerp_color(surface_top, surface_bottom, fraction)
        draw.line((0, y, width, y), fill=color)

    seam_x = round(width * float(style["seam"]))
    seam_color = _mix(style["wall_bottom"], (90, 84, 76), 0.10)
    draw.line((seam_x, 0, seam_x, horizon), fill=seam_color, width=max(1, width // 420))
    draw.line((0, horizon, width, horizon), fill=_mix(surface_top, (60, 50, 42), 0.12), width=max(1, width // 300))

    # A quiet plinth/shelf creates useful depth without adding competing props.
    structure = str(recipe.get("structure", "plinth"))
    if structure in {"plinth", "console_shelf"}:
        shelf_y = horizon - round(height * 0.025)
        shelf_height = max(4, round(height * 0.04))
        shelf_color = _mix(surface_top, (255, 252, 244), 0.32)
        draw.rounded_rectangle(
            (round(width * 0.08), shelf_y, round(width * 0.92), shelf_y + shelf_height),
            radius=max(1, width // 120),
            fill=shelf_color,
        )
        draw.line(
            (round(width * 0.08), shelf_y + shelf_height, round(width * 0.92), shelf_y + shelf_height),
            fill=_mix(shelf_color, (50, 42, 35), 0.16),
            width=max(1, width // 360),
        )

    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    accent = style["accent"]
    if style["light"] == "left":
        light_polygon = [
            (-round(width * 0.15), -round(height * 0.08)),
            (round(width * 0.32), -round(height * 0.08)),
            (round(width * 0.78), round(height * 0.76)),
            (round(width * 0.36), round(height * 0.76)),
        ]
    else:
        light_polygon = [
            (round(width * 0.68), -round(height * 0.08)),
            (round(width * 1.15), -round(height * 0.08)),
            (round(width * 0.72), round(height * 0.76)),
            (round(width * 0.22), round(height * 0.76)),
        ]
    overlay_draw.polygon(light_polygon, fill=accent)
    # Seeded, barely visible variation avoids identical backgrounds while
    # remaining visually quiet for product training.
    rng = random.Random(seed)
    for _ in range(3):
        radius = round(width * rng.uniform(0.18, 0.34))
        cx = round(width * rng.uniform(0.15, 0.85))
        cy = round(height * rng.uniform(0.18, 0.62))
        overlay_draw.ellipse(
            (cx - radius, cy - radius, cx + radius, cy + radius),
            fill=(255, 255, 255, rng.randint(3, 9)),
        )
    overlay = overlay.filter(ImageFilter.GaussianBlur(max(2, width // 38)))
    return Image.alpha_composite(background.convert("RGBA"), overlay)


def _transform_foreground(
    foreground: Image.Image, recipe: Mapping[str, Any], size: tuple[int, int]
) -> Image.Image:
    width, height = size
    occupancy = float(recipe.get("occupancy", recipe.get("scale", 0.58)))
    occupancy = min(0.90, max(0.18, occupancy))
    target_long_edge = max(16, round(min(width, height) * occupancy))
    current_long_edge = max(foreground.size)
    scale = target_long_edge / max(1, current_long_edge)
    target_size = (
        max(1, round(foreground.width * scale)),
        max(1, round(foreground.height * scale)),
    )
    foreground = foreground.resize(target_size, Image.Resampling.LANCZOS)
    rotation = float(recipe.get("rotation", 0.0))
    if abs(rotation) > 0.01:
        foreground = foreground.rotate(
            rotation,
            resample=Image.Resampling.BICUBIC,
            expand=True,
            fillcolor=(0, 0, 0, 0),
        )
    bbox = foreground.getbbox()
    return foreground.crop(bbox) if bbox is not None else foreground


def _build_source_panel(
    source: Image.Image, recipe: Mapping[str, Any], size: tuple[int, int]
) -> tuple[Image.Image, tuple[int, int, int, int]]:
    width, height = size
    panel_width = round(
        width * min(0.84, max(0.54, float(recipe.get("panel_width", 0.72))))
    )
    panel_height = round(
        height * min(0.72, max(0.42, float(recipe.get("panel_height", 0.58))))
    )
    content = ImageOps.contain(source, (panel_width, panel_height), Image.Resampling.LANCZOS)
    border = max(5, round(min(width, height) * 0.014))
    mat = _BACKGROUND_STYLES.get(
        str(recipe.get("background", "warm_stone")), _BACKGROUND_STYLES["warm_stone"]
    )
    frame_color = _mix(mat["wall_top"], (255, 255, 255), 0.56)
    panel = Image.new("RGBA", (content.width + border * 2, content.height + border * 2), (*frame_color, 255))
    panel.alpha_composite(content.convert("RGBA"), (border, border))
    rotation = float(recipe.get("rotation", 0.0))
    if abs(rotation) > 0.01:
        panel = panel.rotate(
            rotation,
            resample=Image.Resampling.BICUBIC,
            expand=True,
            fillcolor=(0, 0, 0, 0),
        )
        bbox = panel.getbbox()
        if bbox is not None:
            panel = panel.crop(bbox)
    content_box = (border, border, border + content.width, border + content.height)
    return panel, content_box


def _place(
    object_size: tuple[int, int], canvas_size: tuple[int, int], recipe: Mapping[str, Any]
) -> tuple[int, int]:
    width, height = canvas_size
    center = _PLACEMENT_CENTERS.get(str(recipe.get("placement", "center_low")), (0.5, 0.62))
    x = round(width * center[0] - object_size[0] / 2)
    y = round(height * center[1] - object_size[1] / 2)
    return (
        max(0, min(width - object_size[0], x)),
        max(0, min(height - object_size[1], y)),
    )


def _paste_product_scene(
    background: Image.Image,
    foreground: Image.Image,
    x: int,
    y: int,
    recipe: Mapping[str, Any],
) -> None:
    width, height = background.size
    style = _BACKGROUND_STYLES.get(
        str(recipe.get("background", "warm_stone")), _BACKGROUND_STYLES["warm_stone"]
    )
    shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(shadow)
    draw.ellipse(
        (
            x + round(foreground.width * 0.10),
            y + round(foreground.height * 0.86),
            x + round(foreground.width * 0.90),
            y + round(foreground.height * 1.04),
        ),
        fill=style["shadow"],
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(max(4, round(min(width, height) * 0.018))))
    background.alpha_composite(shadow)

    object_shadow = Image.new("RGBA", foreground.size, (0, 0, 0, 0))
    alpha = foreground.getchannel("A").point(lambda value: round(value * 0.20))
    object_shadow.putalpha(alpha)
    object_shadow = object_shadow.filter(ImageFilter.GaussianBlur(max(2, round(min(width, height) * 0.012))))
    background.alpha_composite(object_shadow, (x + round(width * 0.012), y + round(height * 0.015)))
    background.alpha_composite(foreground, (x, y))


def _paste_panel_scene(
    background: Image.Image,
    panel: Image.Image,
    x: int,
    y: int,
    recipe: Mapping[str, Any],
) -> None:
    width, height = background.size
    style = _BACKGROUND_STYLES.get(
        str(recipe.get("background", "warm_stone")), _BACKGROUND_STYLES["warm_stone"]
    )
    shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(shadow)
    draw.rounded_rectangle(
        (
            x + round(width * 0.012),
            y + round(height * 0.018),
            x + panel.width + round(width * 0.012),
            y + panel.height + round(height * 0.018),
        ),
        radius=max(1, round(width * 0.012)),
        fill=style["shadow"],
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(max(5, round(width * 0.022))))
    background.alpha_composite(shadow)
    background.alpha_composite(panel, (x, y))


def _lerp_color(
    start: tuple[int, int, int], end: tuple[int, int, int], fraction: float
) -> tuple[int, int, int]:
    fraction = min(1.0, max(0.0, fraction))
    return tuple(round(a + (b - a) * fraction) for a, b in zip(start, end, strict=True))


def _mix(
    first: tuple[int, int, int], second: tuple[int, int, int], fraction: float
) -> tuple[int, int, int]:
    return _lerp_color(first, second, fraction)


__all__ = ["EditorialVariant", "build_editorial_variant"]
