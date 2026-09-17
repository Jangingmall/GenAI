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
    ProductPhoto,
    ProductPhotoSet,
)
from detail_page_ai.pipeline import DetailPagePipeline
from detail_page_ai.assets import MemoryAssetStore, StoredAsset
from detail_page_ai.persistence import SQLiteDeliveryOutbox
import hashlib


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
