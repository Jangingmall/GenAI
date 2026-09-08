import hashlib
import io
from dataclasses import replace

from PIL import Image

from detail_page_ai.assets import MemoryAssetStore
from detail_page_ai.dto import GenerationOptions, ProductProfileDto
from detail_page_ai.models import ProductPhoto
from detail_page_ai import source_photos


def _png(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _source_fixture() -> bytes:
    image = Image.new("RGB", (80, 80), "white")
    for y in range(15, 65):
        for x in range(20, 60):
            image.putpixel(
                (x, y),
                ((x * 3) % 180, 30 + (y * 2) % 170, 40 + ((x + y) * 2) % 160),
            )
    return _png(image)


def _complex_background_fixture() -> bytes:
    image = Image.new("RGB", (40, 40), "white")
    image.putpixel((0, 0), (255, 0, 0))
    image.putpixel((39, 0), (0, 255, 0))
    image.putpixel((0, 39), (0, 0, 255))
    image.putpixel((39, 39), (0, 0, 0))
    return _png(image)


def _profile() -> ProductProfileDto:
    return ProductProfileDto.minimal("장식함")


def _generator(**kwargs):
    return source_photos.SourcePreservingProductPhotoGenerator(
        asset_store=MemoryAssetStore(),
        canvas_size=(320, 320),
        **kwargs,
    )


def test_mask_failure_still_edits_original_for_scene_and_four_detail_views():
    source = _complex_background_fixture()

    class NoMask:
        def extract(self, image, mime_type):
            return None

    class Editor:
        def __init__(self):
            self.calls = []

        def generate(self, **kwargs):
            self.calls.append(kwargs)
            return _png(Image.new("RGB", (32, 32), "blue"))

    editor = Editor()
    photos = _generator(
        extractor=NoMask(), usage_scene_generator=editor,
        detail_view_generator=editor,
    ).generate(source_image=source, source_mime_type="image/png",
               profile=_profile(), options=GenerationOptions()).photos
    assert [call["role"] for call in editor.calls] == [
        "lifestyle", "detail-02", "detail-03", "detail-04", "detail-05"
    ]
    assert all(call["source_image"] == source for call in editor.calls)
    assert sum(photo.fidelity_status == "GENERATED" for photo in photos) == 5
    assert next(photo for photo in photos if photo.photo_id == "hero").data == source


def test_cutout_rgb_channels_are_copied_from_source_pixels():
    source = _source_fixture()
    cutout = source_photos.SolidBackgroundCutoutExtractor().extract(source, "image/png")

    assert cutout is not None
    source_rgb = Image.open(io.BytesIO(source)).convert("RGB")
    cutout_rgba = Image.open(io.BytesIO(cutout.rgba_png)).convert("RGBA")
    mask = Image.open(io.BytesIO(cutout.mask_png)).convert("L")
    for y in range(source_rgb.height):
        for x in range(source_rgb.width):
            if mask.getpixel((x, y)):
                assert cutout_rgba.getpixel((x, y))[:3] == source_rgb.getpixel((x, y))


def test_cutout_suppresses_low_contrast_shadow_connected_to_frame_edge():
    image = Image.new("RGB", (80, 80), "#e6e6e6")
    for y in range(20, 60):
        for x in range(20, 60):
            image.putpixel((x, y), (35, 30, 25))
    for y in range(48, 58):
        for x in range(0, 20):
            image.putpixel((x, y), (175, 175, 175))

    cutout = source_photos.SolidBackgroundCutoutExtractor().extract(_png(image), "image/png")

    assert cutout is not None
    mask = Image.open(io.BytesIO(cutout.mask_png)).convert("L")
    assert mask.getpixel((5, 52)) == 0
    assert mask.getpixel((40, 40)) == 255


def test_cutout_softens_light_boundary_halo_while_preserving_inner_source_rgb():
    image = Image.new("RGB", (80, 80), "white")
    for y in range(15, 65):
        image.putpixel((19, y), (220, 220, 220))
        for x in range(20, 60):
            image.putpixel((x, y), (35, 30, 25))

    cutout = source_photos.SolidBackgroundCutoutExtractor().extract(_png(image), "image/png")

    assert cutout is not None
    source_rgb = Image.open(io.BytesIO(_png(image))).convert("RGB")
    cutout_rgba = Image.open(io.BytesIO(cutout.rgba_png)).convert("RGBA")
    mask = Image.open(io.BytesIO(cutout.mask_png)).convert("L")
    assert mask.getpixel((19, 40)) < 255
    assert mask.getpixel((40, 40)) == 255
    assert cutout_rgba.getpixel((40, 40))[:3] == source_rgb.getpixel((40, 40))


def test_complex_background_returns_safe_source_fallback():
    source = _complex_background_fixture()

    photos = _generator().generate(
        source_image=source,
        source_mime_type="image/png",
        profile=_profile(),
        options=GenerationOptions(),
    )

    assert {photo.fidelity_status for photo in photos.photos} == {"FALLBACK"}
    assert {photo.asset_mode for photo in photos.photos} == {"source"}
    assert all(photo.data == source for photo in photos.photos)


def test_background_generator_never_receives_source_bytes():
    class RecordingBackgroundGenerator:
        def __init__(self):
            self.calls = []

        def generate(self, **kwargs):
            self.calls.append(kwargs)
            return _png(Image.new("RGB", (320, 320), "#d8d1c5"))

    background = RecordingBackgroundGenerator()
    source = _source_fixture()

    _generator(background_generator=background).generate(
        source_image=source,
        source_mime_type="image/png",
        profile=_profile(),
        options=GenerationOptions(),
    )

    assert [call["role"] for call in background.calls] == ["lifestyle"]
    assert all("source_image" not in call for call in background.calls)
    assert all(source not in call.values() for call in background.calls)


def test_single_input_never_creates_alternate_and_default_roles_are_explicit():
    photos = _generator().generate(
        source_image=_source_fixture(),
        source_mime_type="image/png",
        profile=_profile(),
        options=GenerationOptions(),
    )

    assert [photo.photo_id for photo in photos.photos[:4]] == [
        "hero",
        "packshot",
        "detail",
        "lifestyle",
    ]
    assert len([photo for photo in photos.photos if photo.photo_id.startswith("detail")]) >= 3


def test_lifestyle_product_is_placed_on_lower_surface_with_contact_shadow():
    class GeneratedBackground:
        def generate(self, **kwargs):
            return _png(Image.new("RGB", (320, 320), "#d8d1c5"))

    photos = _generator(
        background_generator=GeneratedBackground()
    ).generate(
        source_image=_source_fixture(),
        source_mime_type="image/png",
        profile=_profile(),
        options=GenerationOptions(),
    )

    lifestyle = next(photo for photo in photos.photos if photo.photo_id == "lifestyle")
    assert lifestyle.transform.y > 320 // 4
    assert lifestyle.background_generated is True
    assert lifestyle.fidelity_status == "VERIFIED"


def test_lifestyle_product_is_smaller_than_the_catalog_hero_for_natural_scale():
    class GeneratedBackground:
        def generate(self, **kwargs):
            return _png(Image.new("RGB", (320, 320), "#d8d1c5"))

    photos = _generator(
        background_generator=GeneratedBackground()
    ).generate(
        source_image=_source_fixture(),
        source_mime_type="image/png",
        profile=_profile(),
        options=GenerationOptions(),
    )

    hero = next(photo for photo in photos.photos if photo.photo_id == "hero")
    lifestyle = next(photo for photo in photos.photos if photo.photo_id == "lifestyle")
    assert lifestyle.transform.scale < hero.transform.scale * 0.75


def test_multi_item_catalog_profile_preserves_pixels_without_usage_scene_generator():
    class GeneratedBackground:
        def generate(self, **kwargs):
            assert kwargs["role"] == "lifestyle"
            return _png(Image.new("RGB", (320, 320), "#443b35"))

    source = _source_fixture()
    profile = ProductProfileDto.minimal("금속 공예 세트").model_copy(
        update={
            "display_name": "다양한 금속 소재의 병과 잔 세트",
            "layout_id": "catalog-grid",
            "keywords": ["세트", "병", "잔"],
        }
    )

    photos = _generator(
        background_generator=GeneratedBackground()
    ).generate(
        source_image=source,
        source_mime_type="image/png",
        profile=profile,
        options=GenerationOptions(),
    )

    lifestyle = next(photo for photo in photos.photos if photo.photo_id == "lifestyle")
    assert lifestyle.data != source
    assert lifestyle.asset_mode == "source_composite"
    assert lifestyle.product_generated is False
    assert lifestyle.background_generated is True
    assert lifestyle.fidelity_status == "VERIFIED"


def test_multi_item_set_preserves_original_frame_for_hero_and_packshot_only():
    class GeneratedBackground:
        def generate(self, **kwargs):
            return _png(Image.new("RGB", (320, 320), "#443b35"))

    source = _source_fixture()
    profile = ProductProfileDto.minimal("금속 공예 세트").model_copy(
        update={
            "observations": {"visible_components": ["병", "주전자", "잔"]},
        }
    )

    photos = _generator(
        background_generator=GeneratedBackground()
    ).generate(
        source_image=source,
        source_mime_type="image/png",
        profile=profile,
        options=GenerationOptions(),
    )

    for photo_id in ("hero", "packshot"):
        photo = next(photo for photo in photos.photos if photo.photo_id == photo_id)
        assert photo.data == source
        assert photo.asset_mode == "source"
        assert photo.fidelity_status == "FALLBACK"

    lifestyle = next(photo for photo in photos.photos if photo.photo_id == "lifestyle")
    assert lifestyle.asset_mode == "source_composite"
    assert lifestyle.product_generated is False
    assert lifestyle.fidelity_status == "VERIFIED"


def test_multi_item_set_uses_prompt_only_usage_scene_with_source_reference():
    source = _source_fixture()

    generated_scene = _png(Image.new("RGB", (320, 320), "#cbb8a2"))

    class UsageSceneGenerator:
        def __init__(self):
            self.calls = []

        def generate(self, **kwargs):
            self.calls.append(kwargs)
            return generated_scene

    usage_scene = UsageSceneGenerator()

    profile = ProductProfileDto.minimal("금속 공예 세트").model_copy(
        update={
            "observations": {"visible_components": ["병", "주전자", "잔"]},
        }
    )

    photos = _generator(
        usage_scene_generator=usage_scene,
    ).generate(
        source_image=source,
        source_mime_type="image/png",
        profile=profile,
        options=GenerationOptions(),
    )

    hero = next(photo for photo in photos.photos if photo.photo_id == "hero")
    packshot = next(photo for photo in photos.photos if photo.photo_id == "packshot")
    lifestyle = next(photo for photo in photos.photos if photo.photo_id == "lifestyle")

    assert len(usage_scene.calls) == 1
    assert usage_scene.calls[0]["role"] == "lifestyle"
    assert hero.data == source
    assert packshot.data == source
    assert lifestyle.data == generated_scene
    assert lifestyle.asset_mode == "generated_scene"
    assert lifestyle.product_generated is True
    assert lifestyle.background_generated is True
    assert lifestyle.fidelity_status == "GENERATED"
    assert lifestyle.source_sha256 == hashlib.sha256(source).hexdigest()


def test_generated_scene_is_allowed_only_for_lifestyle_with_source_traceability():
    source = _source_fixture()
    scene = ProductPhoto(
        photo_id="lifestyle",
        order=4,
        label="AI 생성 활용 장면",
        data=_png(Image.new("RGB", (320, 320), "#cbb8a2")),
        mime_type="image/png",
        asset_mode="generated_scene",
        source_asset_id="source-asset",
        source_sha256=hashlib.sha256(source).hexdigest(),
        background_generated=True,
        product_generated=True,
        fidelity_status="GENERATED",
    )
    validator = source_photos.ProductFidelityValidator()
    sources = ((source, "image/png"),)

    assert validator.validate(scene, source_images=sources) == "GENERATED"
    assert (
        validator.validate(
            replace(scene, photo_id="hero"),
            source_images=sources,
        )
        == "REJECTED"
    )
    assert (
        validator.validate(
            replace(scene, source_sha256=None),
            source_images=sources,
        )
        == "REJECTED"
    )


def test_multi_item_observations_use_source_composite_instead_of_product_regeneration():
    class GeneratedBackground:
        def generate(self, **kwargs):
            return _png(Image.new("RGB", (320, 320), "#443b35"))

    source = _source_fixture()
    profile = ProductProfileDto.minimal("장식용 금속 제품").model_copy(
        update={
            "layout_id": "catalog-grid",
            "observations": {
                "visible_components": ["병", "주전자", "잔", "받침"],
            },
        }
    )

    photos = _generator(
        background_generator=GeneratedBackground()
    ).generate(
        source_image=source,
        source_mime_type="image/png",
        profile=profile,
        options=GenerationOptions(),
    )

    lifestyle = next(photo for photo in photos.photos if photo.photo_id == "lifestyle")
    assert lifestyle.asset_mode == "source_composite"
    assert lifestyle.product_generated is False
    assert lifestyle.fidelity_status == "VERIFIED"


def test_multi_item_set_is_protected_even_when_ai_style_hint_is_not_catalog_grid():
    class GeneratedBackground:
        def generate(self, **kwargs):
            return _png(Image.new("RGB", (320, 320), "#443b35"))

    source = _source_fixture()
    profile = ProductProfileDto.minimal("금속 공예 세트").model_copy(
        update={
            "layout_id": "editorial-split",
            "display_name": "다양한 금속 소재의 병과 잔 세트",
        }
    )

    photos = _generator(
        background_generator=GeneratedBackground()
    ).generate(
        source_image=source,
        source_mime_type="image/png",
        profile=profile,
        options=GenerationOptions(),
    )

    lifestyle = next(photo for photo in photos.photos if photo.photo_id == "lifestyle")
    assert lifestyle.asset_mode == "source_composite"
    assert lifestyle.product_generated is False
    assert lifestyle.fidelity_status == "VERIFIED"


def test_single_product_usage_context_uses_a_generated_background_with_exact_source_pixels():
    class UsageContextBackgroundGenerator:
        def generate(self, **kwargs):
            assert kwargs["role"] == "lifestyle"
            return _png(Image.new("RGB", (320, 320), "#d8c7b8"))

    photos = _generator(
        background_generator=UsageContextBackgroundGenerator()
    ).generate(
        source_image=_source_fixture(),
        source_mime_type="image/png",
        profile=ProductProfileDto.minimal("금속 주전자"),
        options=GenerationOptions(),
    )

    lifestyle = next(photo for photo in photos.photos if photo.photo_id == "lifestyle")
    assert lifestyle.asset_mode == "source_composite"
    assert lifestyle.product_generated is False
    assert lifestyle.background_generated is True
    assert lifestyle.source_sha256 == hashlib.sha256(_source_fixture()).hexdigest()
    assert lifestyle.fidelity_status == "VERIFIED"


def test_additional_original_is_the_only_source_of_alternate():
    primary = _source_fixture()
    side = _png(Image.new("RGB", (55, 40), "#816f55"))

    photos = _generator().generate(
        source_image=primary,
        source_mime_type="image/png",
        profile=_profile(),
        options=GenerationOptions(),
        additional_source_images=((side, "image/png"),),
    )
    alternate = next(photo for photo in photos.photos if photo.photo_id == "alternate")

    assert alternate.data == side
    assert alternate.source_sha256 == hashlib.sha256(side).hexdigest()
    assert alternate.product_generated is False
    assert alternate.asset_mode == "source"


def test_four_or_more_sources_skip_variation_generation_and_fill_layout_roles():
    primary = _source_fixture()
    additional = tuple(
        (_png(Image.new("RGB", (80 + index, 80), (80 + index, 90, 100))), "image/png")
        for index in range(1, 4)
    )

    class FailingBackgroundGenerator:
        def generate(self, **kwargs):
            raise AssertionError("background generation must be skipped")

    photos = _generator(
        background_generator=FailingBackgroundGenerator(),
        source_photo_variation_threshold=4,
    ).generate(
        source_image=primary,
        source_mime_type="image/png",
        profile=_profile(),
        options=GenerationOptions(),
        additional_source_images=additional,
    )

    assert [photo.photo_id for photo in photos.photos] == [
        "hero",
        "packshot",
        "detail",
        "lifestyle",
    ]
    assert [photo.data for photo in photos.photos] == [primary, *[data for data, _ in additional]]
    assert all(photo.asset_mode == "source" for photo in photos.photos)
    assert all(photo.fidelity_status == "VERIFIED" for photo in photos.photos)


def test_fewer_sources_keep_one_source_detail_and_generate_three_detail_jobs():
    generated = {
        "detail-02": _png(Image.new("RGB", (320, 320), "#b5a28c")),
        "detail-03": _png(Image.new("RGB", (320, 320), "#8c7965")),
        "detail-04": _png(Image.new("RGB", (320, 320), "#746b61")),
        "detail-05": _png(Image.new("RGB", (320, 320), "#5e6470")),
    }

    class RecordingDetailViewGenerator:
        def __init__(self):
            self.roles = []

        def generate(self, **kwargs):
            self.roles.append(kwargs["role"])
            return generated[kwargs["role"]]

    detail_generator = RecordingDetailViewGenerator()
    source = _source_fixture()
    photos = _generator(detail_view_generator=detail_generator).generate(
        source_image=source,
        source_mime_type="image/png",
        profile=_profile(),
        options=GenerationOptions(),
    )
    by_id = {photo.photo_id: photo for photo in photos.photos}

    assert detail_generator.roles == ["detail-02", "detail-03", "detail-04", "detail-05"]
    assert all(by_id[role].data == generated[role] for role in generated)
    assert all(by_id[role].asset_mode == "generated_view" for role in generated)
    assert all(by_id[role].fidelity_status == "GENERATED" for role in generated)
    assert all(
        by_id[role].source_sha256 == hashlib.sha256(source).hexdigest()
        for role in generated
    )
    assert by_id["detail"].asset_mode == "source_crop"
    assert by_id["detail"].fidelity_status == "VERIFIED"


def test_failed_detail_generation_falls_back_to_verified_source_crops():
    class FailingDetailViewGenerator:
        def generate(self, **kwargs):
            raise RuntimeError("image model unavailable")

    photos = _generator(detail_view_generator=FailingDetailViewGenerator()).generate(
        source_image=_source_fixture(),
        source_mime_type="image/png",
        profile=_profile(),
        options=GenerationOptions(),
    )
    by_id = {photo.photo_id: photo for photo in photos.photos}

    assert all(by_id[role].asset_mode == "source_crop" for role in ("detail-02", "detail-03", "detail-04", "detail-05"))
    assert all(by_id[role].fidelity_status == "VERIFIED" for role in ("detail-02", "detail-03", "detail-04", "detail-05"))


def test_four_sources_skip_all_generated_detail_jobs():
    class FailingDetailViewGenerator:
        def generate(self, **kwargs):
            raise AssertionError("generated detail jobs must be skipped")

    primary = _source_fixture()
    additional = tuple(
        (_png(Image.new("RGB", (80 + index, 80), (80 + index, 90, 100))), "image/png")
        for index in range(1, 4)
    )

    photos = _generator(detail_view_generator=FailingDetailViewGenerator()).generate(
        source_image=primary,
        source_mime_type="image/png",
        profile=_profile(),
        options=GenerationOptions(),
        additional_source_images=additional,
    )

    assert all(photo.asset_mode == "source" for photo in photos.photos)


def test_fewer_than_threshold_keeps_source_preserving_variation_path():
    primary = _source_fixture()
    side = _png(Image.new("RGB", (55, 40), "#816f55"))
    calls = []

    class RecordingBackgroundGenerator:
        def generate(self, **kwargs):
            calls.append(kwargs["role"])
            return _png(Image.new("RGB", (320, 320), "#d8d1c5"))

    photos = _generator(
        background_generator=RecordingBackgroundGenerator(),
        source_photo_variation_threshold=4,
    ).generate(
        source_image=primary,
        source_mime_type="image/png",
        profile=_profile(),
        options=GenerationOptions(),
        additional_source_images=((side, "image/png"),),
    )

    assert [photo.photo_id for photo in photos.photos[:4]] == [
        "hero",
        "packshot",
        "detail",
        "lifestyle",
    ]
    assert "lifestyle" in calls
    assert any(photo.photo_id == "alternate" for photo in photos.photos)


def test_composition_is_deterministic_and_detail_crop_stays_in_source_bounds():
    source = _source_fixture()
    generator = _generator()

    first = generator.generate(
        source_image=source,
        source_mime_type="image/png",
        profile=_profile(),
        options=GenerationOptions(),
    )
    second = generator.generate(
        source_image=source,
        source_mime_type="image/png",
        profile=_profile(),
        options=GenerationOptions(),
    )
    detail = next(photo for photo in first.photos if photo.photo_id == "detail")

    assert [hashlib.sha256(item.data).hexdigest() for item in first.photos] == [
        hashlib.sha256(item.data).hexdigest() for item in second.photos
    ]
    left, top, right, bottom = detail.transform.crop
    assert 0 <= left < right <= 80
    assert 0 <= top < bottom <= 80
    assert detail.asset_mode == "source_crop"


def test_detail_crops_are_distinct_source_regions_for_gallery_slots():
    generated = _generator().generate(
        source_image=_source_fixture(),
        source_mime_type="image/png",
        profile=_profile(),
        options=GenerationOptions(),
    )

    details = [photo for photo in generated.photos if photo.photo_id.startswith("detail")]

    assert len(details) >= 3
    assert len({photo.transform.crop for photo in details}) == len(details)
    assert len({photo.data for photo in details}) == len(details)


def test_fidelity_validator_rejects_generated_product_pixels():
    unsafe = ProductPhoto(
        photo_id="unsafe",
        order=1,
        label="unsafe",
        data=b"generated",
        mime_type="image/png",
        source_sha256="source-hash",
        product_generated=True,
    )

    assert source_photos.ProductFidelityValidator().validate(unsafe) == "REJECTED"


def test_fidelity_validator_rejects_forged_source_hash_and_composite_pixels():
    source = _source_fixture()
    generator = _generator()
    generated = generator.generate(
        source_image=source,
        source_mime_type="image/png",
        profile=_profile(),
        options=GenerationOptions(),
    )
    hero = next(photo for photo in generated.photos if photo.photo_id == "hero")
    validator = source_photos.ProductFidelityValidator()
    sources = ((source, "image/png"),)

    assert validator.validate(hero, source_images=sources) == "VERIFIED"
    assert (
        validator.validate(
            replace(hero, source_sha256="0" * 64), source_images=sources
        )
        == "REJECTED"
    )
    assert (
        validator.validate(
            replace(
                hero,
                data=_png(Image.new("RGB", (320, 320), "black")),
            ),
            source_images=sources,
        )
        == "REJECTED"
    )
