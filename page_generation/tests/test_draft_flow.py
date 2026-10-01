from io import BytesIO

from PIL import Image

from detail_page_ai.dto import (
    ApprovedDraftDto,
    GenerationOptions,
    ProductProfileDto,
    UserHintsDto,
)
from detail_page_ai.models import ProductPhotoSet
from detail_page_ai.pipeline import DetailPagePipeline, DraftPipelineResult
from detail_page_ai.persistence import MemoryJobRepository
from detail_page_ai.service import (
    DetailPageJobService,
    DraftVersionConflictError,
    IdempotencyConflictError,
)


def valid_png() -> bytes:
    image = Image.new("RGB", (16, 16), (238, 236, 232))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class FakeAnalyzer:
    def analyze(self, image, mime_type, user_hints=None):
        return ProductProfileDto(
            product_type="나전 보관함",
            display_name="나전 보관함",
            is_traditional_craft=True,
            craft_type="나전칠기",
            summary="어두운 바탕에 자개 문양이 장식된 보관함입니다.",
            features=[],
            copy_sections=[],
            usage_scene="소중한 물건을 정돈해 보관하는 장면",
        )


class MustNotRunRenderer:
    def render(self, **kwargs):
        raise AssertionError("최종 PNG 렌더러는 초안 생성 단계에서 호출되면 안 됩니다")


class MustNotRunPhotoGenerator:
    def generate(self, **kwargs):
        raise AssertionError("제품 사진 생성기는 승인 전 호출되면 안 됩니다")


def test_create_draft_only_analyzes_and_returns_structured_editable_json():
    pipeline = DetailPagePipeline(
        analyzer=FakeAnalyzer(),
        photo_generator=MustNotRunPhotoGenerator(),
        renderer=MustNotRunRenderer(),
        backend=object(),
        options=GenerationOptions(),
        id_factory=lambda: "generation-draft-1",
    )

    result = pipeline.create_draft(
        job_id="job-draft-1",
        request_id="request-draft-1",
        source_image=valid_png(),
        source_mime_type="image/png",
    )

    assert isinstance(result, DraftPipelineResult)
    assert result.generation_id == "generation-draft-1"
    assert result.profile.display_name == "나전 보관함"
    assert result.approved_draft.product_name == "나전 보관함"
    assert "html" not in result.fe_draft.model_dump()
    assert result.fe_draft.draft.product_name == "나전 보관함"
    assert result.fe_draft.preview.source_sha256
    assert result.fe_draft.photo_generation_failures == []
    assert result.fe_draft.unused_generated_photo_ids == []
    assert result.preview_photo_set == ProductPhotoSet()


def test_approved_draft_merge_preserves_research_and_safety_context():
    original = FakeAnalyzer().analyze(valid_png(), "image/png")
    original = original.model_copy(
        update={
            "uncertain_information": ["규격은 별도 확인 필요"],
            "safety_notes": ["이미지에 없는 성능은 단정하지 않음"],
        }
    )
    draft = ApprovedDraftDto(
        product_name="장인이 다듬은 나전 보관함",
        product_type="나전 보관함",
        summary="수정된 요약",
        hero_headline="시간을 담는 보관함",
        hero_description="수정된 소개 문구",
    )

    merged = draft.to_profile(original)

    assert merged.display_name == "장인이 다듬은 나전 보관함"
    assert merged.summary == "수정된 요약"
    assert merged.is_traditional_craft is True
    assert merged.craft_research == original.craft_research
    assert merged.uncertain_information == original.uncertain_information
    assert merged.safety_notes == original.safety_notes


class ControlledExecutor:
    def __init__(self):
        self.jobs = []

    def submit(self, function, *args, **kwargs):
        self.jobs.append((function, args, kwargs))

    def run_all(self):
        jobs, self.jobs = self.jobs, []
        for function, args, kwargs in jobs:
            function(*args, **kwargs)


class FinalRenderer:
    def __init__(self):
        self.calls = 0

    def render(self, **kwargs):
        from detail_page_ai.models import GeneratedImage

        self.calls += 1
        return GeneratedImage(data=valid_png(), mime_type="image/png")


class FinalBackend:
    def persist(self, request, image):
        from datetime import datetime, timezone
        from detail_page_ai.dto import AiBePersistAck

        return AiBePersistAck(
            generation_id=request.generation_id,
            product_id=request.product_id,
            status="SAVED",
            saved_at=datetime.now(timezone.utc),
        )


def test_service_exposes_draft_ready_and_approval_is_the_only_final_render():
    executor = ControlledExecutor()
    renderer = FinalRenderer()
    pipeline = DetailPagePipeline(
        analyzer=FakeAnalyzer(),
        renderer=renderer,
        backend=FinalBackend(),
        id_factory=lambda: "analysis-generation",
    )
    service = DetailPageJobService(
        pipeline=pipeline,
        executor=executor,
        repository=MemoryJobRepository(),
    )

    accepted = service.submit(
        valid_png(), "image/png", product_id="product-1", idempotency_key="create-1"
    )
    executor.run_all()
    draft_status = service.get(accepted.job_id)
    assert draft_status.status == "DRAFT_READY"
    assert draft_status.draft is not None
    assert draft_status.result is None

    edited_draft = draft_status.draft.draft.model_copy(
        update={"summary": "저장된 초안 요약"}
    )
    saved_draft = service.save_draft(
        accepted.job_id, edited_draft, expected_version=draft_status.draft.version
    )
    assert saved_draft.version == 2
    assert "html" not in saved_draft.model_dump()
    try:
        service.save_draft(accepted.job_id, edited_draft, expected_version=1)
    except DraftVersionConflictError:
        pass
    else:
        raise AssertionError("stale draft edits must be rejected")

    final = service.approve_draft(
        accepted.job_id,
        saved_draft.draft,
        product_id="product-1",
        idempotency_key="approve-1",
    )
    assert final.fe_result.detail_page.image_base64
    assert service.get(accepted.job_id).status == "COMPLETED"
    repeated = service.approve_draft(
        accepted.job_id,
        saved_draft.draft,
        product_id="product-1",
        idempotency_key="approve-1",
    )
    assert repeated.generation_id == final.generation_id
    assert renderer.calls == 1

    altered_draft = saved_draft.draft.model_copy(update={"summary": "다른 승인"})
    try:
        service.approve_draft(
            accepted.job_id,
            altered_draft,
            product_id="product-1",
            idempotency_key="approve-1",
        )
    except IdempotencyConflictError:
        pass
    else:
        raise AssertionError("same approval key with different copy must be rejected")


def test_backend_job_uses_same_generation_id_for_approved_callback():
    executor = ControlledExecutor()
    renderer = FinalRenderer()
    pipeline = DetailPagePipeline(
        analyzer=FakeAnalyzer(),
        renderer=renderer,
        backend=FinalBackend(),
        options=GenerationOptions(),
        id_factory=lambda: "analysis-generation",
    )
    service = DetailPageJobService(
        pipeline=pipeline,
        executor=executor,
        repository=MemoryJobRepository(),
    )

    accepted = service.submit(
        valid_png(),
        "image/png",
        product_id="product-42",
        options=GenerationOptions(source_generation_id="42"),
        idempotency_key="create-42",
    )
    executor.run_all()
    draft = service.get(accepted.job_id).draft

    final = service.approve_draft(
        accepted.job_id,
        draft.draft,
        product_id="product-42",
        idempotency_key="approve-42",
    )

    assert final.generation_id == "42"


def test_saved_and_approved_legacy_draft_filters_confirmed_seller_warnings():
    executor = ControlledExecutor()
    repository = MemoryJobRepository()
    pipeline = DetailPagePipeline(
        analyzer=FakeAnalyzer(), renderer=FinalRenderer(), backend=FinalBackend()
    )
    service = DetailPageJobService(
        pipeline=pipeline, executor=executor, repository=repository
    )
    care = "천천히 펴 주세요. 물기를 닦아 주세요."
    accepted = service.submit(
        valid_png(), "image/png", user_hints=UserHintsDto(care_guide=care)
    )
    executor.run_all()

    def restore_legacy_warnings(job):
        job.draft_profile = job.draft_profile.model_copy(update={
            "uncertain_information": ["정확한 크기 확인 필요", "천천히 펴 주세요."],
            "safety_notes": ["물기를 닦아 주세요.", "이미지 밖 구성품 확인 필요"],
        })

    repository.update(accepted.job_id, restore_legacy_warnings)
    draft = service.get(accepted.job_id).draft
    saved = service.save_draft(
        accepted.job_id, draft.draft, expected_version=draft.version
    )
    expected = ["정확한 크기 확인 필요", "이미지 밖 구성품 확인 필요"]
    assert saved.product.warnings == expected
    assert saved.source_sha256 == draft.source_sha256

    # Old persisted profiles must also be filtered on approval without a save first.
    repository.update(accepted.job_id, restore_legacy_warnings)
    final = service.approve_draft(accepted.job_id, saved.draft)
    assert final.fe_result.product.warnings == expected


def test_create_idempotency_returns_same_job_and_rejects_conflict():
    pipeline = DetailPagePipeline(
        analyzer=FakeAnalyzer(), renderer=FinalRenderer(), backend=object()
    )
    service = DetailPageJobService(
        pipeline=pipeline, executor=ControlledExecutor(), repository=MemoryJobRepository()
    )
    first = service.submit(valid_png(), "image/png", idempotency_key="same-key")
    second = service.submit(valid_png(), "image/png", idempotency_key="same-key")
    assert second.job_id == first.job_id

    altered = valid_png() + b"different"
    try:
        service.submit(altered, "image/png", idempotency_key="same-key")
    except IdempotencyConflictError:
        pass
    else:
        raise AssertionError("same key with different input must be rejected")
