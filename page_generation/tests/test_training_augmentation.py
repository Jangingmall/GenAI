from pathlib import Path

from PIL import Image, ImageDraw

from detail_page_ai.training_augmentation import build_editorial_variant


def _save_source(path: Path, *, uniform_background: bool) -> None:
    image = Image.new("RGB", (64, 48), "white")
    if not uniform_background:
        draw = ImageDraw.Draw(image)
        for x in range(image.width):
            draw.line((x, 0, x, image.height), fill=(220 - x, 220, 220))
    draw = ImageDraw.Draw(image)
    draw.rectangle((18, 12, 46, 36), fill=(35, 80, 120))
    image.save(path)


def test_editorial_variant_composites_a_cutout_on_a_new_scene(tmp_path: Path):
    source = tmp_path / "source.png"
    _save_source(source, uniform_background=True)

    result = build_editorial_variant(
        source.read_bytes(),
        "image/png",
        {"background": "warm_stone", "placement": "left_copy", "scale": 0.8},
        seed=7,
        size=(128, 128),
    )

    assert result.image.mode == "RGB"
    assert result.image.size == (128, 128)
    assert result.preservation_mode == "cutout_composite"
    assert result.product_bbox[2] > result.product_bbox[0]
    assert result.product_bbox[3] > result.product_bbox[1]


def test_editorial_variant_frames_a_nonuniform_source_instead_of_guessing_a_mask(tmp_path: Path):
    source = tmp_path / "source.png"
    _save_source(source, uniform_background=False)

    result = build_editorial_variant(
        source.read_bytes(),
        "image/png",
        {"background": "ivory_wall", "placement": "right_copy"},
        seed=11,
        size=(160, 120),
    )

    assert result.image.size == (160, 120)
    assert result.preservation_mode == "framed_source"
    assert result.source_region is not None
    assert result.source_region[2] > result.source_region[0]
    assert result.source_region[3] > result.source_region[1]


def test_editorial_variant_can_force_a_full_source_frame_for_ambiguous_products(tmp_path: Path):
    source = tmp_path / "source.png"
    _save_source(source, uniform_background=True)

    result = build_editorial_variant(
        source.read_bytes(),
        "image/png",
        {"background": "warm_stone", "placement": "center", "preservation": "frame"},
        seed=13,
        size=(128, 128),
    )

    assert result.preservation_mode == "framed_source"
    assert result.source_region is not None


def test_editorial_recipe_changes_composition_but_keeps_the_same_canvas(tmp_path: Path):
    source = tmp_path / "source.png"
    _save_source(source, uniform_background=True)
    data = source.read_bytes()

    left = build_editorial_variant(
        data,
        "image/png",
        {"background": "warm_stone", "placement": "left_copy", "scale": 0.8},
        seed=3,
        size=(128, 128),
    )
    right = build_editorial_variant(
        data,
        "image/png",
        {"background": "warm_stone", "placement": "right_copy", "scale": 0.8},
        seed=3,
        size=(128, 128),
    )

    assert left.image.size == right.image.size == (128, 128)
    assert left.image.tobytes() != right.image.tobytes()
