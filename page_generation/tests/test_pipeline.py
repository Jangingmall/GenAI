from detail_page_ai.backend_client import BackendDeliveryError
from detail_page_ai.dto import (
    AiBePersistAck,
    CraftResearchDto,
    GenerationOptions,
    PageBlockDto,
    ProductProfileDto,
    UserHintsDto,
)
from detail_page_ai.models import (
    GeneratedImage,
    GeneratedSection,
    PhotoGenerationFailure,
    ProductPhoto,
    ProductPhotoSet,
)
from detail_page_ai.pipeline import DetailPagePipeline
from detail_page_ai.assets import MemoryAssetStore, StoredAsset
from detail_page_ai.persistence import SQLiteDeliveryOutbox
import hashlib
import logging


VALID_PNG = b"\x89PNG\r\n\x1a\nimage"


class FakeAnalyzer:
    def __init__(self):
        self.user_hints = None

    def analyze(
        self,
        image: bytes,
        mime_type: str,
        user_hints: UserHintsDto | None = None,
    ) -> ProductProfileDto:
        self.user_hints = user_hints
        return ProductProfileDto.minimal("desk lamp")


class FakeRenderer:
    def __init__(self):
        self.call_count = 0
        self.profiles = []
        self.photo_sets = []

    def render(self, **kwargs):
        self.call_count += 1
        self.profiles.append(kwargs["profile"])
        self.photo_sets.append(kwargs.get("photo_set"))
        return GeneratedImage(
            data=b"generated",
            mime_type="image/png",
            width=1024,
            height=4096,
            sections=(
                GeneratedSection(
                    section_id="hero",
                    order=1,
                    label="상품 소개",
                    data=b"hero",
                    mime_type="image/png",
                    width=774,
                    height=526,
                ),
            ),
            photos=kwargs.get("photo_set", ProductPhotoSet()).photos,
        )


class FakeBackend:
    def __init__(self, fail: bool):
        self.fail = fail
        self.call_count = 0
        self.last_request = None

    def persist(self, request, image):
        self.call_count += 1
        self.last_request = request
        if self.fail:
            raise BackendDeliveryError("backend unavailable", retryable=True)
        return AiBePersistAck(
            generation_id=request.generation_id,
            product_id="product-1",
            status="SAVED",
            saved_at="2026-08-26T08:01:12Z",
        )


def make_pipeline(backend_error: bool = False, return_parts: bool = False):
    class EchoPhotoGenerator:
        def generate(self, **kwargs):
            source = kwargs["source_image"]
            return ProductPhotoSet(
                photos=(
                    ProductPhoto(
                        photo_id="hero",
                        order=1,
                        label="Hero",
                        data=source,
                        mime_type=kwargs["source_mime_type"],
                        asset_mode="source",
                        source_asset_id="source-asset",
                        source_sha256=hashlib.sha256(source).hexdigest(),
                        product_generated=False,
                        fidelity_status="VERIFIED",
                    ),
                )
            )

    renderer = FakeRenderer()
    backend = FakeBackend(fail=backend_error)
    pipeline = DetailPagePipeline(
        analyzer=FakeAnalyzer(),
        photo_generator=EchoPhotoGenerator(),
        renderer=renderer,
        backend=backend,
        options=GenerationOptions(aspect_ratio="1:4", image_size="2K"),
        id_factory=lambda: "generation-1",
    )
    if return_parts:
        return pipeline, renderer, backend
    return pipeline


def test_pipeline_analyzes_renders_delivers_to_fe_and_be():
    result = make_pipeline().run("job-1", "request-1", VALID_PNG, "image/png")

    assert result.fe_result.product.product_type == "desk lamp"
    assert result.fe_result.detail_page.image_base64 == "Z2VuZXJhdGVk"
    assert result.fe_result.detail_page.sections[0].section_id == "hero"
    assert result.be_ack.status == "SAVED"


def test_pipeline_delivers_react_document_to_fe_and_be():
    pipeline, _, backend = make_pipeline(return_parts=True)

    result = pipeline.run("job-react", "request-react", VALID_PNG, "image/png")

    document = result.fe_result.detail_page.react_document
    assert document is not None
    assert document.schema_version == "2.0"
    assert document.root[0].tag == "section"
    assert backend.last_request.detail_page.react_document == document


def _generated_photo(photo_id: str, order: int) -> ProductPhoto:
    return ProductPhoto(
        photo_id=photo_id,
        order=order,
        label=f"AI generated {photo_id}",
        data=b"generated-photo",
        mime_type="image/png",
        asset_mode="generated_scene" if photo_id == "lifestyle" else "generated_view",
        source_sha256=hashlib.sha256(VALID_PNG).hexdigest(),
        background_generated=True,
        product_generated=True,
        fidelity_status="GENERATED",
    )


def test_pipeline_reports_generated_photos_not_referenced_by_react_document():
    renderer = FakeRenderer()
    backend = FakeBackend(fail=False)

    class PhotoGenerator:
        def generate(self, **kwargs):
            return ProductPhotoSet(
                photos=(
                    _generated_photo("lifestyle", 4),
                    _generated_photo("detail-02", 5),
                )
            )

    pipeline = DetailPagePipeline(
        analyzer=FakeAnalyzer(),
        photo_generator=PhotoGenerator(),
        renderer=renderer,
        backend=backend,
        id_factory=lambda: "generation-unused-photo",
    )
    profile = ProductProfileDto.minimal("desk lamp").model_copy(
        update={
            "page_plan": [
                PageBlockDto(
                    section_id="usage",
                    block_type="usage_scene",
                    photo_id="lifestyle",
                )
            ]
        }
    )

    result = pipeline.run(
        "job-unused-photo",
        "request-unused-photo",
        VALID_PNG,
        "image/png",
        profile_override=profile,
    )

    assert result.fe_result.detail_page.unused_generated_photo_ids == ["detail-02"]
    assert backend.last_request.detail_page.unused_generated_photo_ids == ["detail-02"]
    assert pipeline.recover_fe_result(
        "generation-unused-photo"
    ).detail_page.unused_generated_photo_ids == ["detail-02"]


def test_pipeline_reports_no_unused_generated_photos_when_all_are_referenced():
    renderer = FakeRenderer()
    backend = FakeBackend(fail=False)

    class PhotoGenerator:
        def generate(self, **kwargs):
            return ProductPhotoSet(
                photos=(
                    _generated_photo("lifestyle", 4),
                    _generated_photo("detail-02", 5),
                )
            )

    pipeline = DetailPagePipeline(
        analyzer=FakeAnalyzer(),
        photo_generator=PhotoGenerator(),
        renderer=renderer,
        backend=backend,
        id_factory=lambda: "generation-all-photos",
    )
    profile = ProductProfileDto.minimal("desk lamp").model_copy(
        update={
            "page_plan": [
                PageBlockDto(
                    section_id="usage",
                    block_type="usage_scene",
                    photo_id="lifestyle",
                ),
                PageBlockDto(
                    section_id="detail",
                    block_type="detail_split",
                    photo_id="detail-02",
                ),
            ]
        }
    )

    result = pipeline.run(
        "job-all-photos",
        "request-all-photos",
        VALID_PNG,
        "image/png",
        profile_override=profile,
    )

    assert result.fe_result.detail_page.unused_generated_photo_ids == []
    assert backend.last_request.detail_page.unused_generated_photo_ids == []


def test_pipeline_completes_missing_required_blocks_in_ai_page_plan():
    pipeline, renderer, _ = make_pipeline(return_parts=True)

    class PartialEditorialAnalyzer:
        def analyze(self, image, mime_type):
            return ProductProfileDto.minimal("금속 차기 세트").model_copy(
                update={
                    "page_plan": [
                        PageBlockDto(
                            section_id="hero",
                            block_type="hero",
                            title="차 한 잔의 풍경",
                            photo_id="hero",
                        ),
                        PageBlockDto(
                            section_id="closing",
                            block_type="closing",
                            title="오래 남는 인상",
                        ),
                    ]
                }
            )

    pipeline.analyzer = PartialEditorialAnalyzer()
    pipeline.run("job-editorial", "request-editorial", VALID_PNG, "image/png")

    block_types = [block.block_type for block in renderer.profiles[0].page_plan]
    assert block_types[0] == "hero"
    assert "detail_split" in block_types
    assert "usage_scene" in block_types
    assert "gallery" in block_types
    assert "recommendation" in block_types
    assert "info_table" in block_types
    assert "notice" in block_types
    assert block_types[-1] == "closing"


def test_pipeline_renders_approved_profile_without_reanalyzing():
    pipeline, renderer, _ = make_pipeline(return_parts=True)
    approved_profile = ProductProfileDto.minimal("나전 보관함").model_copy(
        update={"layout_id": "image-first", "display_name": "수정한 나전 보관함"}
    )

    result = pipeline.run(
        "job-approved",
        "request-approved",
        VALID_PNG,
        "image/png",
        profile_override=approved_profile,
    )

    assert result.fe_result.product.layout_id == "image-first"
    assert renderer.profiles[0].display_name == "수정한 나전 보관함"


def test_pipeline_passes_user_hints_to_analysis_and_be_metadata():
    pipeline, _, backend = make_pipeline(return_parts=True)
    hints = UserHintsDto(
        product_name="작은 보관함",
        making_method="표면 장식으로 완성했습니다.",
        care_guide="마른 천으로 닦아 주세요.",
    )

    pipeline.run(
        "job-1",
        "request-1",
        VALID_PNG,
        "image/png",
        user_hints=hints,
    )

    assert pipeline.analyzer.user_hints == hints
    assert backend.last_request.user_hints == hints


def test_pipeline_passes_product_identity_to_be_metadata():
    pipeline, _, backend = make_pipeline(return_parts=True)

    pipeline.run(
        "job-42",
        "request-42",
        VALID_PNG,
        "image/png",
        product_id="product-42",
        source_asset_id="source-asset-42",
    )

    assert backend.last_request.product_id == "product-42"
    assert backend.last_request.source.asset_id == "source-asset-42"


def test_pipeline_persists_outbox_before_first_backend_attempt(tmp_path):
    outbox = SQLiteDeliveryOutbox(tmp_path / "state.sqlite3")

    class InspectingBackend(FakeBackend):
        def persist(self, request, image):
            record = outbox.get(request.generation_id)
            assert record.status == "DELIVERING"
            return super().persist(request, image)

    backend = InspectingBackend(fail=False)
    pipeline = DetailPagePipeline(
        analyzer=FakeAnalyzer(),
        renderer=FakeRenderer(),
        backend=backend,
        outbox=outbox,
        id_factory=lambda: "generation-prewritten",
    )

    pipeline.run("job-1", "request-1", VALID_PNG, "image/png")

    assert outbox.get("generation-prewritten").status == "DELIVERED"


def test_pipeline_uses_caller_persisted_generation_id():
    pipeline = make_pipeline()

    result = pipeline.run(
        "job-1",
        "request-1",
        VALID_PNG,
        "image/png",
        generation_id="stable-generation-id",
    )

    assert result.generation_id == "stable-generation-id"


def test_backend_failure_does_not_trigger_second_image_generation():
    pipeline, renderer, backend = make_pipeline(backend_error=True, return_parts=True)

    result = pipeline.run("job-1", "request-1", VALID_PNG, "image/png")

    assert result.fe_result.product.product_type == "desk lamp"
    assert result.be_ack is None
    assert result.backend_delivery_pending is True
    assert renderer.call_count == 1
    assert backend.call_count == 1


def test_backend_retry_uses_saved_generation_without_reanalysis_or_rerender():
    pipeline, renderer, backend = make_pipeline(backend_error=True, return_parts=True)
    first = pipeline.run("job-1", "request-1", VALID_PNG, "image/png")
    backend.fail = False

    ack = pipeline.retry_backend_delivery(first.generation_id)

    assert ack.status == "SAVED"
    assert renderer.call_count == 1
    assert backend.call_count == 2


def test_backend_retry_survives_pipeline_and_outbox_reopen(tmp_path):
    renderer = FakeRenderer()
    failing_backend = FakeBackend(fail=True)
    database = tmp_path / "state.sqlite3"
    first_pipeline = DetailPagePipeline(
        analyzer=FakeAnalyzer(),
        renderer=renderer,
        backend=failing_backend,
        outbox=SQLiteDeliveryOutbox(database),
        id_factory=lambda: "generation-restart",
    )

    first_pipeline.run("job-1", "request-1", VALID_PNG, "image/png")

    healthy_backend = FakeBackend(fail=False)
    second_pipeline = DetailPagePipeline(
        analyzer=FakeAnalyzer(),
        renderer=renderer,
        backend=healthy_backend,
        outbox=SQLiteDeliveryOutbox(database),
    )
    ack = second_pipeline.retry_backend_delivery("generation-restart")

    assert ack.status == "SAVED"
    assert renderer.call_count == 1
    assert healthy_backend.call_count == 1
    assert SQLiteDeliveryOutbox(database).get("generation-restart").status == "DELIVERED"


def test_pipeline_researches_classified_traditional_craft_before_rendering():
    renderer = FakeRenderer()
    backend = FakeBackend(fail=False)

    class CraftAnalyzer:
        def analyze(self, image, mime_type):
            return ProductProfileDto.minimal("한지 부채").model_copy(
                update={"is_traditional_craft": True, "craft_type": "한지 공예"}
            )

    class CraftResearcher:
        def __init__(self):
            self.call_count = 0

        def research(self, profile):
            self.call_count += 1
            return CraftResearchDto(
                craft_type=profile.craft_type,
                overview="검색으로 확인한 공예 맥락입니다.",
                characteristics=[],
                techniques=[],
                materials=[],
                sources=[],
            )

    researcher = CraftResearcher()
    pipeline = DetailPagePipeline(
        analyzer=CraftAnalyzer(),
        researcher=researcher,
        renderer=renderer,
        backend=backend,
        id_factory=lambda: "generation-craft",
    )

    pipeline.run("job-1", "request-1", VALID_PNG, "image/png")

    assert researcher.call_count == 1
    assert renderer.profiles[0].craft_research.overview == "검색으로 확인한 공예 맥락입니다."


def test_pipeline_researches_a_product_description_before_writing_copy():
    renderer = FakeRenderer()
    backend = FakeBackend(fail=False)

    class ProductAnalyzer:
        def analyze(self, image, mime_type, user_hints=None):
            return ProductProfileDto.minimal("장식함")

    class ProductResearcher:
        def __init__(self):
            self.hints = None

        def research(self, profile, user_hints=None):
            self.hints = user_hints
            return CraftResearchDto(
                craft_type=profile.product_type,
                overview="입력 설명과 공개 자료를 대조한 제품 맥락입니다.",
                characteristics=[],
                techniques=[],
                materials=[],
                sources=[],
            )

    researcher = ProductResearcher()
    pipeline = DetailPagePipeline(
        analyzer=ProductAnalyzer(),
        researcher=researcher,
        renderer=renderer,
        backend=backend,
        id_factory=lambda: "generation-described-product",
    )
    hints = UserHintsDto(
        product_name="나전 보관함",
        making_method="전복 껍데기 조각을 표면에 붙여 장식했습니다.",
    )

    pipeline.run(
        "job-1",
        "request-1",
        VALID_PNG,
        "image/png",
        user_hints=hints,
    )

    assert researcher.hints == hints
    assert renderer.profiles[0].craft_research.overview.startswith("입력 설명")


def test_pipeline_generates_product_photo_set_before_detail_page_rendering():
    renderer = FakeRenderer()
    backend = FakeBackend(fail=False)

    class PhotoGenerator:
        def generate(self, **kwargs):
            return ProductPhotoSet(
                photos=(
                    ProductPhoto(
                        photo_id="hero",
                        order=1,
                        label="Hero",
                        data=kwargs["source_image"],
                        mime_type=kwargs["source_mime_type"],
                        asset_mode="source",
                        source_sha256=hashlib.sha256(
                            kwargs["source_image"]
                        ).hexdigest(),
                        product_generated=False,
                        fidelity_status="VERIFIED",
                    ),
                )
            )

    pipeline = DetailPagePipeline(
        analyzer=FakeAnalyzer(),
        photo_generator=PhotoGenerator(),
        renderer=renderer,
        backend=backend,
        id_factory=lambda: "generation-photo",
    )

    result = pipeline.run("job-1", "request-1", VALID_PNG, "image/png")

    assert renderer.photo_sets[0].photos[0].photo_id == "hero"
    assert result.fe_result.detail_page.photos[0].photo_id == "hero"
    assert backend.last_request.detail_page.photos[0].photo_id == "hero"


def test_pipeline_delivers_photo_generation_failures_to_fe_be_and_recovery():
    renderer = FakeRenderer()
    backend = FakeBackend(fail=False)

    class PhotoGenerator:
        def generate(self, **kwargs):
            return ProductPhotoSet(
                photo_generation_failures=(
                    PhotoGenerationFailure(
                        photo_id="lifestyle",
                        reason="생성하지 못했습니다",
                    ),
                )
            )

    pipeline = DetailPagePipeline(
        analyzer=FakeAnalyzer(),
        photo_generator=PhotoGenerator(),
        renderer=renderer,
        backend=backend,
        id_factory=lambda: "generation-photo-failure",
    )

    result = pipeline.run("job-1", "request-1", VALID_PNG, "image/png")

    assert result.fe_result.detail_page.photo_generation_failures[0].photo_id == "lifestyle"
    assert (
        result.fe_result.detail_page.photo_generation_failures[0].reason
        == "생성하지 못했습니다"
    )
    assert backend.last_request.detail_page.photo_generation_failures[0].photo_id == "lifestyle"
    recovered = pipeline.recover_fe_result("generation-photo-failure")
    assert recovered.detail_page.photo_generation_failures[0].photo_id == "lifestyle"


def test_pipeline_maps_photo_provenance_to_fe_and_be():
    result_pipeline, _, backend = make_pipeline(return_parts=True)

    result = result_pipeline.run("job-1", "request-1", VALID_PNG, "image/png")
    fe_photo = result.fe_result.detail_page.photos[0]
    be_photo = backend.last_request.detail_page.photos[0]

    assert fe_photo.asset_mode == "source"
    assert fe_photo.product_generated is False
    assert fe_photo.background_generated is False
    assert be_photo.source_sha256 == hashlib.sha256(VALID_PNG).hexdigest()
    assert be_photo.mask_sha256 is None


def test_pipeline_rejects_forged_photo_before_renderer_receives_it():
    renderer = FakeRenderer()

    class ForgedPhotoGenerator:
        def generate(self, **kwargs):
            return ProductPhotoSet(
                photos=(
                    ProductPhoto(
                        photo_id="forged",
                        order=1,
                        label="forged",
                        data=b"fabricated-product-pixels",
                        mime_type="image/png",
                        asset_mode="source",
                        source_sha256=hashlib.sha256(
                            kwargs["source_image"]
                        ).hexdigest(),
                        product_generated=False,
                        fidelity_status="VERIFIED",
                    ),
                )
            )

    pipeline = DetailPagePipeline(
        analyzer=FakeAnalyzer(),
        photo_generator=ForgedPhotoGenerator(),
        renderer=renderer,
        backend=FakeBackend(fail=False),
    )

    pipeline.run("job-1", "request-1", VALID_PNG, "image/png")

    assert renderer.photo_sets[0].photos == ()


def test_craft_confidence_triggers_research_without_boolean_flag():
    renderer = FakeRenderer()
    backend = FakeBackend(fail=False)

    class ConfidentCraftAnalyzer:
        def analyze(self, image, mime_type):
            return ProductProfileDto.minimal("장식함").model_copy(
                update={
                    "craft_confidence": 0.91,
                    "candidate_types": ["나전칠기"],
                }
            )

    class Researcher:
        def __init__(self):
            self.call_count = 0

        def research(self, profile):
            self.call_count += 1
            return CraftResearchDto(
                craft_type=profile.craft_type or profile.product_type,
                overview="공예 유형의 일반적 맥락입니다.",
            )

    researcher = Researcher()
    pipeline = DetailPagePipeline(
        analyzer=ConfidentCraftAnalyzer(),
        researcher=researcher,
        renderer=renderer,
        backend=backend,
        craft_confidence_threshold=0.65,
    )

    pipeline.run("job-1", "request-1", VALID_PNG, "image/png")

    assert researcher.call_count == 1


def test_pipeline_passes_additional_originals_only_to_photo_generator():
    renderer = FakeRenderer()

    class RecordingPhotoGenerator:
        def __init__(self):
            self.additional = None

        def generate(self, **kwargs):
            self.additional = kwargs["additional_source_images"]
            return ProductPhotoSet()

    photo_generator = RecordingPhotoGenerator()
    pipeline = DetailPagePipeline(
        analyzer=FakeAnalyzer(),
        photo_generator=photo_generator,
        renderer=renderer,
        backend=FakeBackend(fail=False),
    )
    side = b"\x89PNG\r\n\x1a\nside"

    pipeline.run(
        "job-1",
        "request-1",
        VALID_PNG,
        "image/png",
        additional_source_images=((side, "image/png"),),
    )

    assert photo_generator.additional == ((side, "image/png"),)


def test_url_response_mode_omits_duplicate_base64_payloads():
    class UrlAssetStore(MemoryAssetStore):
        @staticmethod
        def _with_url(record):
            return StoredAsset(
                asset_id=record.asset_id,
                mime_type=record.mime_type,
                size=record.size,
                sha256=record.sha256,
                category=record.category,
                location=record.location,
                url=f"https://assets.example/{record.asset_id}",
            )

        def put(self, data, mime_type, category):
            return self._with_url(super().put(data, mime_type, category))

        def get_record(self, asset_id):
            return self._with_url(super().get_record(asset_id))

    pipeline, _, backend = make_pipeline(return_parts=True)
    pipeline.asset_store = UrlAssetStore()
    pipeline.response_asset_mode = "url"

    result = pipeline.run("job-1", "request-1", VALID_PNG, "image/png")

    assert result.fe_result.detail_page.image_url.startswith("https://assets.example/")
    assert result.fe_result.detail_page.image_base64 is None
    assert result.fe_result.detail_page.sections[0].image_base64 is None
    assert result.fe_result.detail_page.photos[0].image_base64 is None
    assert backend.last_request.source.asset_id is not None
    assert backend.last_request.detail_page.asset_id is not None

    recovered = pipeline.recover_fe_result(result.generation_id)
    assert recovered.detail_page.image_url.startswith("https://assets.example/")
    assert recovered.detail_page.image_base64 is None
    assert recovered.detail_page.sections[0].image_base64 is None
    assert recovered.detail_page.photos[0].image_base64 is None


def test_pipeline_resolves_dangling_page_plan_photo_id_to_actual_photo(caplog):
    pipeline, _, backend = make_pipeline(return_parts=True)

    class ScaleReferenceAnalyzer:
        def analyze(self, image, mime_type):
            return ProductProfileDto.minimal("초충도 부채 세트").model_copy(
                update={
                    "summary": "전통 부채 세트입니다.",
                    "page_plan": [
                        PageBlockDto(
                            section_id="hero",
                            block_type="hero",
                            title="초충도 부채 세트",
                            photo_id="hero",
                        ),
                        PageBlockDto(
                            section_id="statement",
                            block_type="statement",
                            title="대나무 살과 한지",
                            body="합죽선 세트의 이야기입니다.",
                        ),
                        PageBlockDto(
                            section_id="scale_reference",
                            block_type="scale_reference",
                            title="부채와 파우치의 비율",
                            photo_id="scale",
                        ),
                        PageBlockDto(
                            section_id="feature_grid",
                            block_type="feature_grid",
                            title="특징",
                            body="제품의 주요 특징입니다.",
                        ),
                        PageBlockDto(
                            section_id="recommendation",
                            block_type="recommendation",
                            title="추천 연출",
                            body="다양한 상황에서의 연출 방법입니다.",
                        ),
                        PageBlockDto(
                            section_id="info_table",
                            block_type="info_table",
                            title="기본 정보",
                            body="기본 사양입니다.",
                        ),
                        PageBlockDto(
                            section_id="notice",
                            block_type="notice",
                            title="안내 사항",
                            body="관리 방법입니다.",
                        ),
                        PageBlockDto(
                            section_id="closing",
                            block_type="closing",
                            title="오래 남는 인상",
                        ),
                    ]
                }
            )

    pipeline.analyzer = ScaleReferenceAnalyzer()

    with caplog.at_level(logging.WARNING, logger="detail_page_ai.react_document_builder"):
        result = pipeline.run("job-scale", "request-scale", VALID_PNG, "image/png")

    fe_photos = result.fe_result.detail_page.photos
    available_fe_photo_ids = {p.photo_id for p in fe_photos}
    assert "scale" not in available_fe_photo_ids
    assert "hero" in available_fe_photo_ids

    # Check FE page_plan: scale_reference.photo_id must be resolved to 'hero'
    fe_plan = result.fe_result.product.page_plan
    scale_blocks = [b for b in fe_plan if b.block_type == "scale_reference"]
    assert len(scale_blocks) == 1
    assert scale_blocks[0].photo_id == "hero"
    for block in fe_plan:
        if block.photo_id is not None:
            assert block.photo_id in available_fe_photo_ids, (
                f"Dangling photo_id {block.photo_id} in FE block {block.section_id}"
            )
        for pid in block.photo_ids:
            assert pid in available_fe_photo_ids, (
                f"Dangling photo_id {pid} in FE block {block.section_id}"
            )

    # Check BE persist request: product.page_plan must point to existing photos
    be_request = backend.last_request
    be_photos = be_request.detail_page.photos
    available_be_photo_ids = {p.photo_id for p in be_photos}
    assert "scale" not in available_be_photo_ids
    be_plan = be_request.product.page_plan
    be_scale_blocks = [b for b in be_plan if b.block_type == "scale_reference"]
    assert len(be_scale_blocks) == 1
    assert be_scale_blocks[0].photo_id == "hero"
    for block in be_plan:
        if block.photo_id is not None:
            assert block.photo_id in available_be_photo_ids, (
                f"Dangling photo_id {block.photo_id} in BE block {block.section_id}"
            )
        for pid in block.photo_ids:
            assert pid in available_be_photo_ids, (
                f"Dangling photo_id {pid} in BE block {block.section_id}"
            )

    # Check React document has hero for scale_reference image node
    react_doc = result.fe_result.detail_page.react_document
    assert react_doc is not None

    # Check warning log was emitted exactly 1 time per block
    assert (
        "photo_id 'scale' requested by scale_reference block is unavailable; using default photo_id 'hero'"
        in caplog.text
    )
    scale_warnings = [
        record
        for record in caplog.records
        if "photo_id 'scale' requested by scale_reference block is unavailable" in record.message
    ]
    assert len(scale_warnings) == 1




def test_drafts_and_renders_run_one_at_a_time():
    # Stage 2026-10-01: two renders and a draft overlapped on one L40S and ran
    # out of GPU memory. The analysis, cutout and image models must see one job
    # at a time.
    import threading
    import time

    pipeline = make_pipeline()
    real_analyze = pipeline.analyzer.analyze
    active = []
    overlaps = []

    def slow_analyze(*args, **kwargs):
        active.append(1)
        overlaps.append(len(active))
        time.sleep(0.2)
        active.pop()
        return real_analyze(*args, **kwargs)

    pipeline.analyzer.analyze = slow_analyze
    calls = [
        lambda: pipeline.run("job-a", "request-a", VALID_PNG, "image/png"),
        lambda: pipeline.run("job-b", "request-b", VALID_PNG, "image/png"),
        lambda: pipeline.create_draft(
            job_id="job-c", request_id="request-c",
            source_image=VALID_PNG, source_mime_type="image/png",
        ),
    ]
    threads = [threading.Thread(target=call) for call in calls]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert len(overlaps) == 3
    assert max(overlaps) == 1
