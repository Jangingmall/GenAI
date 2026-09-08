from datetime import datetime, timezone
import pytest

from detail_page_ai.dto import (
    AiBeProductPersistRequest,
    AiFeProductSummaryDto,
    AiFeResultDto,
    ErrorDto,
    FeDetailPageAssetDto,
    GenerationOptions,
    ProductProfileDto,
    UserHintsDto,
)
from detail_page_ai.models import GeneratedImage, GeneratedSection, PhotoTransform, ProductPhoto
from detail_page_ai.persistence import (
    JobRecord,
    LeaseOwnershipError,
    SQLiteDeliveryOutbox,
    SQLiteJobRepository,
)


def _job_record(status: str = "QUEUED") -> JobRecord:
    profile = ProductProfileDto.minimal("장식함")
    return JobRecord(
        job_id="job-1",
        request_id="request-1",
        product_id="product-1",
        source_asset_id="source-asset-1",
        generation_id="generation-1",
        source_image=b"source-bytes",
        source_mime_type="image/png",
        options=GenerationOptions(),
        additional_source_images=((b"side-bytes", "image/png"),),
        status=status,
        progress=35,
        result=AiFeResultDto(
            generation_id="generation-1",
            product=AiFeProductSummaryDto.from_profile(profile),
            detail_page=FeDetailPageAssetDto(
                image_base64="cGFnZQ==", mime_type="image/png"
            ),
        ),
        error=ErrorDto(
            code="DELIVERY_PENDING",
            message="retry later",
            retryable=True,
            request_id="request-1",
            generation_id="generation-1",
        ),
    )


def _persist_request() -> AiBeProductPersistRequest:
    return AiBeProductPersistRequest.from_profile(
        generation_id="generation-1",
        job_id="job-1",
        request_id="request-1",
        source_image_mime_type="image/png",
        source_image_sha256="source-hash",
        generated_image_mime_type="image/png",
        generated_width=774,
        generated_height=3000,
        generated_image_sha256="page-hash",
        profile=ProductProfileDto.minimal("장식함"),
        generation={"prompt_version": "source-safe-v2"},
        product_id="product-1",
        source_asset_id="source-asset-1",
    )


def test_job_repository_round_trips_user_hints(tmp_path):
    record = _job_record()
    record.user_hints = UserHintsDto(
        product_name="나전 보관함",
        making_method="표면 장식으로 완성했습니다.",
        care_guide="마른 천으로 닦아 주세요.",
    )
    repository = SQLiteJobRepository(tmp_path / "state.sqlite3")

    repository.create(record)

    assert repository.get(record.job_id).user_hints == record.user_hints


def _generated_image() -> GeneratedImage:
    return GeneratedImage(
        data=b"page-bytes",
        mime_type="image/png",
        width=774,
        height=3000,
        sections=(
            GeneratedSection(
                section_id="hero",
                order=1,
                label="상품 소개",
                data=b"section-bytes",
                mime_type="image/png",
                width=774,
                height=526,
            ),
        ),
        photos=(
            ProductPhoto(
                photo_id="lifestyle",
                order=1,
                label="활용 장면",
                data=b"photo-bytes",
                mime_type="image/png",
                asset_mode="source_composite",
                source_asset_id="asset-1",
                source_sha256="source-hash",
                cutout_sha256="cutout-hash",
                mask_sha256="mask-hash",
                background_generated=True,
                product_generated=False,
                transform=PhotoTransform(scale=0.72, x=20, y=30),
                fidelity_status="VERIFIED",
            ),
        ),
    )


def test_job_survives_repository_reopen_with_binary_inputs_and_result(tmp_path):
    path = tmp_path / "state.sqlite3"
    SQLiteJobRepository(path).create(_job_record())

    restored = SQLiteJobRepository(path).get("job-1")

    assert restored.request_id == "request-1"
    assert restored.product_id == "product-1"
    assert restored.source_asset_id == "source-asset-1"
    assert restored.source_image == b"source-bytes"
    assert restored.additional_source_images == ((b"side-bytes", "image/png"),)
    assert restored.result.generation_id == "generation-1"
    assert restored.error.code == "DELIVERY_PENDING"


def test_only_one_repository_claims_an_interrupted_job(tmp_path):
    path = tmp_path / "state.sqlite3"
    first = SQLiteJobRepository(path)
    first.create(_job_record(status="COMPOSING"))

    second = SQLiteJobRepository(path)
    first_claim = second.claim_recoverable("worker-a")
    competing_claim = SQLiteJobRepository(path).claim_recoverable("worker-b")

    assert first_claim == ["job-1"]
    assert competing_claim == []
    assert second.get("job-1").status == "QUEUED"
    assert second.get("job-1").progress == 0


def test_job_cannot_be_claimed_twice_by_same_worker_before_lease_expires(tmp_path):
    path = tmp_path / "state.sqlite3"
    repository = SQLiteJobRepository(path)
    repository.create(_job_record())

    first_claim = repository.claim("job-1", "worker-a")
    duplicate_claim = repository.claim("job-1", "worker-a")

    assert first_claim is not None
    assert duplicate_claim is None


def test_expired_job_owner_cannot_overwrite_new_owner(tmp_path):
    path = tmp_path / "state.sqlite3"
    repository = SQLiteJobRepository(path)
    repository.create(_job_record())
    stale = repository.claim("job-1", "worker-a", lease_seconds=0)
    current = repository.claim("job-1", "worker-b")

    stale.status = "FAILED"
    with pytest.raises(LeaseOwnershipError):
        repository.save(stale, worker_id="worker-a")

    assert current is not None
    assert repository.get("job-1").status == "QUEUED"


def test_job_owner_can_renew_lease(tmp_path):
    path = tmp_path / "state.sqlite3"
    repository = SQLiteJobRepository(path)
    repository.create(_job_record())
    repository.claim("job-1", "worker-a", lease_seconds=1)

    assert repository.renew_lease("job-1", "worker-a", lease_seconds=300)
    assert repository.claim("job-1", "worker-b") is None


def test_outbox_survives_reopen_with_full_generated_image(tmp_path):
    path = tmp_path / "state.sqlite3"
    first = SQLiteDeliveryOutbox(path)
    first.enqueue(_persist_request(), _generated_image(), "backend unavailable")

    restored = SQLiteDeliveryOutbox(path).get("generation-1")

    assert restored.status == "PENDING"
    assert restored.request.idempotency_key == "generation-1"
    assert restored.request.product_id == "product-1"
    assert restored.request.source.asset_id == "source-asset-1"
    assert restored.image.data == b"page-bytes"
    assert restored.image.sections[0].data == b"section-bytes"
    assert restored.image.photos[0].transform.scale == 0.72
    assert restored.image.photos[0].product_generated is False


def test_outbox_state_transitions_are_idempotent(tmp_path):
    outbox = SQLiteDeliveryOutbox(tmp_path / "state.sqlite3")
    outbox.enqueue(_persist_request(), _generated_image(), "first failure")

    outbox.mark_delivering("generation-1")
    outbox.mark_failed("generation-1", "second failure", "legacy-worker")
    claimed = outbox.claim("generation-1", "delivery-worker")
    assert claimed is not None
    outbox.mark_delivered("generation-1", "delivery-worker")
    with pytest.raises(LeaseOwnershipError):
        outbox.mark_delivered("generation-1", "delivery-worker")

    record = outbox.get("generation-1")
    assert record.status == "DELIVERED"
    assert record.attempts == 2
    assert record.last_error is None


def test_only_one_worker_can_claim_the_same_outbox_delivery(tmp_path):
    path = tmp_path / "state.sqlite3"
    first = SQLiteDeliveryOutbox(path)
    first.enqueue(_persist_request(), _generated_image(), "first failure")

    claimed = first.claim("generation-1", "worker-a")
    competing_claim = SQLiteDeliveryOutbox(path).claim(
        "generation-1", "worker-b"
    )

    assert claimed is not None
    assert claimed.status == "DELIVERING"
    assert competing_claim is None
    assert SQLiteDeliveryOutbox(path).list_retryable() == []


def test_expired_outbox_owner_cannot_finish_new_owner_delivery(tmp_path):
    path = tmp_path / "state.sqlite3"
    outbox = SQLiteDeliveryOutbox(path)
    outbox.enqueue(_persist_request(), _generated_image(), "")
    outbox.claim("generation-1", "worker-a", lease_seconds=0)
    current = outbox.claim("generation-1", "worker-b")

    with pytest.raises(LeaseOwnershipError):
        outbox.mark_delivered("generation-1", worker_id="worker-a")

    assert current is not None
    assert outbox.get("generation-1").status == "DELIVERING"


def test_outbox_owner_can_renew_lease(tmp_path):
    path = tmp_path / "state.sqlite3"
    outbox = SQLiteDeliveryOutbox(path)
    outbox.enqueue(_persist_request(), _generated_image(), "")
    outbox.claim("generation-1", "worker-a", lease_seconds=1)

    assert outbox.renew_lease("generation-1", "worker-a", lease_seconds=300)
    assert outbox.claim("generation-1", "worker-b") is None
