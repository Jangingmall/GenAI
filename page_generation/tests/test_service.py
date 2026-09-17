from dataclasses import dataclass
from datetime import datetime, timezone
import sqlite3
import time
import pytest

from detail_page_ai.dto import (
    AiBePersistAck,
    AiBeProductPersistRequest,
    AiFeResultDto,
    AiFeProductSummaryDto,
    FeDetailPageAssetDto,
    ErrorDto,
    GenerationOptions,
    ProductProfileDto,
    UserHintsDto,
)
from detail_page_ai.pipeline import PipelineResult
from detail_page_ai.persistence import (
    JobRecord,
    MemoryDeliveryOutbox,
    MemoryJobRepository,
    SQLiteJobRepository,
    SQLiteDeliveryOutbox,
)
from detail_page_ai.models import GeneratedImage
from detail_page_ai.pipeline import DetailPagePipeline
from detail_page_ai.service import CapacityExceededError, DetailPageJobService


VALID_PNG = b"\x89PNG\r\n\x1a\nimage"


class ControlledExecutor:
    def __init__(self):
        self.jobs = []

    def submit(self, function, *args, **kwargs):
        self.jobs.append((function, args, kwargs))

    def run_all(self):
        jobs, self.jobs = self.jobs, []
        for function, args, kwargs in jobs:
            function(*args, **kwargs)


class ControlledRetryScheduler:
    def __init__(self):
        self.calls = []

    def schedule(self, delay_seconds, function, *args):
        self.calls.append((delay_seconds, function, args))

    def run_next(self):
        _, function, args = self.calls.pop(0)
        function(*args)


class FakePipeline:
    def __init__(self, error=None):
        self.error = error
        self.additional_source_images = None
        self.user_hints = None
        self.product_id = None
        self.source_asset_id = None
        self.outbox = MemoryDeliveryOutbox()

    def run(
        self,
        job_id,
        request_id,
        source_image,
        source_mime_type,
        *,
        options=None,
        additional_source_images=(),
        user_hints=None,
        product_id=None,
        source_asset_id=None,
        status_callback=None,
        generation_id=None,
    ):
        if self.error:
            raise self.error
        self.additional_source_images = additional_source_images
        self.user_hints = user_hints
        self.product_id = product_id
        self.source_asset_id = source_asset_id
        for status, progress in (
            ("ANALYZING", 15),
            ("EXTRACTING", 30),
            ("GENERATING_BACKGROUNDS", 45),
            ("COMPOSING", 55),
            ("VERIFYING", 65),
            ("RENDERING", 75),
            ("DELIVERING", 90),
        ):
            if status_callback:
                status_callback(status, progress)
        profile = ProductProfileDto.minimal("desk lamp")
        fe_result = AiFeResultDto(
            generation_id="generation-1",
            product=AiFeProductSummaryDto.from_profile(profile),
            detail_page=FeDetailPageAssetDto(
                image_base64="Z2VuZXJhdGVk", mime_type="image/png"
            ),
        )
        return PipelineResult(
            generation_id=generation_id or "generation-1",
            fe_result=fe_result,
            be_ack=None,
            backend_delivery_pending=False,
        )


def make_service(pipeline_error=None):
    executor = ControlledExecutor()
    service = DetailPageJobService(
        pipeline=FakePipeline(error=pipeline_error), executor=executor
    )
    return service, executor


def test_submit_returns_queued_job_and_background_work_reaches_completed():
    service, executor = make_service()

    accepted = service.submit(VALID_PNG, "image/png", request_id="request-1")
    executor.run_all()
    status = service.get(accepted.job_id)

    assert accepted.status == "QUEUED"
    assert status.status == "COMPLETED"
    assert status.result.generation_id == "generation-1"


def test_submit_rejects_when_active_job_capacity_is_reached():
    service = DetailPageJobService(
        pipeline=FakePipeline(),
        executor=ControlledExecutor(),
        repository=MemoryJobRepository(),
        max_pending_generations=1,
    )

    service.submit(VALID_PNG, "image/png", idempotency_key="capacity-1")

    with pytest.raises(CapacityExceededError):
        service.submit(VALID_PNG, "image/png", idempotency_key="capacity-2")


def test_failed_job_contains_retryable_error():
    service, executor = make_service(pipeline_error=RuntimeError("local model down"))

    accepted = service.submit(VALID_PNG, "image/png", request_id="request-1")
    executor.run_all()
    status = service.get(accepted.job_id)

    assert status.status == "FAILED"
    assert status.error.retryable is True


def test_failed_job_does_not_expose_provider_exception_details():
    internal_detail = (
        "local-model.internal LocalModelError LOCAL-TOKEN-EXAMPLE"
    )
    service, executor = make_service(
        pipeline_error=RuntimeError(internal_detail)
    )

    accepted = service.submit(VALID_PNG, "image/png", request_id="request-1")
    executor.run_all()
    status = service.get(accepted.job_id)

    assert status.error.message == "AI processing failed. Please retry."
    assert internal_detail not in status.error.message


def test_service_persists_actual_stage_order():
    class RecordingRepository(MemoryJobRepository):
        def __init__(self):
            super().__init__()
            self.saved_statuses = []

        def save(self, record, worker_id=None, lease_seconds=300):
            self.saved_statuses.append(record.status)
            super().save(record, worker_id, lease_seconds)

    executor = ControlledExecutor()
    repository = RecordingRepository()
    service = DetailPageJobService(
        pipeline=FakePipeline(), executor=executor, repository=repository
    )

    service.submit(VALID_PNG, "image/png", request_id="request-1")
    executor.run_all()

    assert repository.saved_statuses == [
        "ANALYZING",
        "EXTRACTING",
        "GENERATING_BACKGROUNDS",
        "COMPOSING",
        "VERIFYING",
        "RENDERING",
        "DELIVERING",
        "COMPLETED",
    ]


def test_service_resumes_interrupted_sqlite_job_after_reopen(tmp_path):
    database = tmp_path / "state.sqlite3"
    first_repository = SQLiteJobRepository(database)
    first_repository.create(
        JobRecord(
            job_id="job-restart",
            request_id="request-restart",
            source_image=VALID_PNG,
            source_mime_type="image/png",
            options=GenerationOptions(),
            status="COMPOSING",
            progress=50,
        )
    )
    executor = ControlledExecutor()

    service = DetailPageJobService(
        pipeline=FakePipeline(),
        executor=executor,
        repository=SQLiteJobRepository(database),
    )
    executor.run_all()

    assert service.get("job-restart").status == "COMPLETED"


def test_service_persists_and_forwards_additional_originals():
    executor = ControlledExecutor()
    pipeline = FakePipeline()
    service = DetailPageJobService(pipeline=pipeline, executor=executor)
    side = b"\x89PNG\r\n\x1a\nside"

    service.submit(
        VALID_PNG,
        "image/png",
        additional_source_images=((side, "image/png"),),
    )
    executor.run_all()

    assert pipeline.additional_source_images == ((side, "image/png"),)


def test_service_persists_and_forwards_user_hints():
    executor = ControlledExecutor()
    pipeline = FakePipeline()
    repository = MemoryJobRepository()
    service = DetailPageJobService(
        pipeline=pipeline, executor=executor, repository=repository
    )
    hints = UserHintsDto(
        product_name="작은 보관함",
        making_method="표면 장식으로 완성했습니다.",
        care_guide="마른 천으로 닦아 주세요.",
    )

    accepted = service.submit(VALID_PNG, "image/png", user_hints=hints)
    assert repository.get(accepted.job_id).user_hints == hints

    executor.run_all()

    assert pipeline.user_hints == hints


def test_service_persists_and_forwards_product_identity():
    executor = ControlledExecutor()
    pipeline = FakePipeline()
    repository = MemoryJobRepository()
    service = DetailPageJobService(
        pipeline=pipeline, executor=executor, repository=repository
    )

    accepted = service.submit(
        VALID_PNG,
        "image/png",
        product_id="product-42",
        source_asset_id="source-asset-42",
    )

    stored = repository.get(accepted.job_id)
    assert stored.product_id == "product-42"
    assert stored.source_asset_id == "source-asset-42"

    executor.run_all()

    assert pipeline.product_id == "product-42"
    assert pipeline.source_asset_id == "source-asset-42"


def test_submit_persists_generation_id_before_background_execution():
    executor = ControlledExecutor()
    repository = MemoryJobRepository()
    service = DetailPageJobService(
        pipeline=FakePipeline(), executor=executor, repository=repository
    )

    accepted = service.submit(VALID_PNG, "image/png")

    assert repository.get(accepted.job_id).generation_id is not None


def test_service_replays_persisted_outbox_on_startup_without_rerender(tmp_path):
    database = tmp_path / "state.sqlite3"
    repository = SQLiteJobRepository(database)
    outbox = SQLiteDeliveryOutbox(database)
    profile = ProductProfileDto.minimal("장식함")
    request = AiBeProductPersistRequest.from_profile(
        generation_id="generation-replay",
        job_id="job-replay",
        request_id="request-replay",
        source_image_mime_type="image/png",
        source_image_sha256="source-hash",
        generated_image_mime_type="image/png",
        generated_width=774,
        generated_height=3000,
        generated_image_sha256="page-hash",
        profile=profile,
        generation={"prompt_version": "source-safe-v2"},
    )
    image = GeneratedImage(data=b"page", mime_type="image/png")
    outbox.enqueue(request, image, "backend unavailable")
    repository.create(
        JobRecord(
            job_id="job-replay",
            request_id="request-replay",
            generation_id="generation-replay",
            source_image=VALID_PNG,
            source_mime_type="image/png",
            options=GenerationOptions(),
            status="COMPLETED",
            progress=100,
            result=FakePipeline().run(
                "job-replay", "request-replay", VALID_PNG, "image/png"
            ).fe_result,
            error=ErrorDto(
                code="AI_BE_DELIVERY_FAILED",
                message="Backend delivery is pending",
                retryable=True,
            ),
        )
    )

    class HealthyBackend:
        def __init__(self):
            self.calls = 0

        def persist(self, request, image):
            self.calls += 1
            return AiBePersistAck(
                generation_id=request.generation_id,
                status="SAVED",
                saved_at="2026-08-27T00:00:00Z",
            )

    class UnusedAnalyzer:
        def analyze(self, image, mime_type):
            raise AssertionError("analysis must not run during outbox replay")

    class UnusedRenderer:
        def render(self, **kwargs):
            raise AssertionError("render must not run during outbox replay")

    backend = HealthyBackend()
    pipeline = DetailPagePipeline(
        analyzer=UnusedAnalyzer(),
        renderer=UnusedRenderer(),
        backend=backend,
        outbox=outbox,
    )
    executor = ControlledExecutor()

    service = DetailPageJobService(
        pipeline=pipeline,
        executor=executor,
        repository=SQLiteJobRepository(database),
    )
    executor.run_all()

    assert backend.calls == 1
    assert outbox.get("generation-replay").status == "DELIVERED"
    assert service.get("job-replay").error is None


def test_service_renews_job_lease_during_slow_provider_call():
    class RecordingRepository(MemoryJobRepository):
        def __init__(self):
            super().__init__()
            self.renewals = 0

        def renew_lease(self, job_id, worker_id, lease_seconds=300):
            self.renewals += 1
            return super().renew_lease(job_id, worker_id, lease_seconds)

    class SlowPipeline(FakePipeline):
        def run(self, *args, **kwargs):
            time.sleep(0.02)
            return super().run(*args, **kwargs)

    repository = RecordingRepository()
    executor = ControlledExecutor()
    service = DetailPageJobService(
        pipeline=SlowPipeline(),
        executor=executor,
        repository=repository,
        lease_seconds=1,
        heartbeat_interval_seconds=0.001,
    )

    service.submit(VALID_PNG, "image/png")
    executor.run_all()

    assert repository.renewals > 0


def test_service_schedules_replay_for_unexpired_delivering_outbox(tmp_path):
    database = tmp_path / "state.sqlite3"
    outbox = SQLiteDeliveryOutbox(database)
    request = AiBeProductPersistRequest.from_profile(
        generation_id="generation-active",
        job_id="missing-job",
        request_id="request-active",
        source_image_mime_type="image/png",
        source_image_sha256="source-hash",
        generated_image_mime_type="image/png",
        generated_width=774,
        generated_height=3000,
        generated_image_sha256="page-hash",
        profile=ProductProfileDto.minimal("장식함"),
        generation={"prompt_version": "source-safe-v2"},
    )
    outbox.enqueue(request, GeneratedImage(data=b"page", mime_type="image/png"), "")
    outbox.claim("generation-active", "crashed-worker", lease_seconds=300)

    class HealthyBackend:
        def __init__(self):
            self.calls = 0

        def persist(self, request, image):
            self.calls += 1
            return AiBePersistAck(
                generation_id=request.generation_id,
                status="SAVED",
                saved_at="2026-08-27T00:00:00Z",
            )

    backend = HealthyBackend()
    pipeline = DetailPagePipeline(
        analyzer=FakePipeline(),
        renderer=FakePipeline(),
        backend=backend,
        outbox=outbox,
    )
    executor = ControlledExecutor()
    scheduler = ControlledRetryScheduler()

    DetailPageJobService(
        pipeline=pipeline,
        executor=executor,
        repository=SQLiteJobRepository(database),
        retry_scheduler=scheduler,
    )

    assert executor.jobs == []
    assert len(scheduler.calls) == 1
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE delivery_outbox SET lease_until = ? WHERE generation_id = ?",
            ("2000-01-01T00:00:00+00:00", "generation-active"),
        )
    scheduler.run_next()
    executor.run_all()

    assert backend.calls == 1
    assert outbox.get("generation-active").status == "DELIVERED"
