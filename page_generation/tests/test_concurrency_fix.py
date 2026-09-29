"""Regression checks for approval concurrency and delivery retry boundaries."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
from threading import Barrier, Event, Lock
import time
from types import SimpleNamespace

import httpx
import pytest

import detail_page_ai.app as app_module
from detail_page_ai.backend_client import BackendDeliveryError
from detail_page_ai.dto import (
    AiBePersistAck,
    AiBeProductPersistRequest,
    AiFeProductSummaryDto,
    AiFeResultDto,
    FeDetailPageAssetDto,
    GenerationOptions,
    ProductProfileDto,
)
from detail_page_ai.models import GeneratedImage
from detail_page_ai.persistence import (
    JobRecord,
    MemoryDeliveryOutbox,
    MemoryJobRepository,
    SQLiteDeliveryOutbox,
    SQLiteJobRepository,
    _serialize_job,
)
from detail_page_ai.pipeline import DetailPagePipeline
from detail_page_ai.service import (
    ApprovalInProgressError,
    DetailPageJobService,
    DraftVersionConflictError,
)


VALID_PNG = b"\x89PNG\r\n\x1a\nimage"


class NoopExecutor:
    def submit(self, function, *args, **kwargs):
        return None


class RecordingScheduler:
    def __init__(self):
        self.calls = []

    def schedule(self, delay_seconds, function, *args):
        self.calls.append((delay_seconds, function, args))


class FixedAnalyzer:
    def analyze(self, image, mime_type, user_hints=None):
        return ProductProfileDto.minimal("장식함")


class ControlledRenderer:
    def __init__(self, *, pause=False):
        self.calls = 0
        self.lock = Lock()
        self.entered = Event()
        self.release = Event()
        if not pause:
            self.release.set()

    def render(self, **kwargs):
        with self.lock:
            self.calls += 1
        self.entered.set()
        assert self.release.wait(timeout=3)
        return GeneratedImage(data=VALID_PNG, mime_type="image/png")


class ControlledBackend:
    def __init__(self, errors=()):
        self.errors = list(errors)
        self.calls = 0

    def persist(self, request, image):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return AiBePersistAck(
            generation_id=request.generation_id,
            product_id=request.product_id,
            status="SAVED",
            saved_at="2026-09-29T00:00:00Z",
        )


def ready_service(
    *, repository=None, outbox=None, renderer=None, backend=None,
    scheduler=None, max_delivery_attempts=8,
):
    repository = repository or MemoryJobRepository()
    outbox = outbox or MemoryDeliveryOutbox()
    renderer = renderer or ControlledRenderer()
    backend = backend or ControlledBackend()
    pipeline = DetailPagePipeline(
        analyzer=FixedAnalyzer(), renderer=renderer, backend=backend, outbox=outbox
    )
    service = DetailPageJobService(
        pipeline=pipeline,
        repository=repository,
        executor=NoopExecutor(),
        retry_scheduler=scheduler or RecordingScheduler(),
        max_delivery_attempts=max_delivery_attempts,
    )
    draft = pipeline.create_draft("job-1", "request-1", VALID_PNG, "image/png")
    repository.create(
        JobRecord(
            job_id="job-1",
            request_id="request-1",
            product_id="product-1",
            generation_id="generation-1",
            source_image=VALID_PNG,
            source_mime_type="image/png",
            options=GenerationOptions(),
            draft=draft.fe_draft,
            draft_profile=draft.profile,
            status="DRAFT_READY",
        )
    )
    return service, draft.fe_draft.draft, renderer, backend, outbox


def persist_request(generation_id="delivery-1", job_id="job-1"):
    return AiBeProductPersistRequest.from_profile(
        generation_id=generation_id,
        job_id=job_id,
        request_id="request-1",
        source_image_mime_type="image/png",
        source_image_sha256="source-hash",
        generated_image_mime_type="image/png",
        generated_width=774,
        generated_height=1000,
        generated_image_sha256="page-hash",
        profile=ProductProfileDto.minimal("장식함"),
        generation={"prompt_version": "test"},
    )


def test_health_responds_while_internal_approval_renders(monkeypatch):
    class SlowService:
        def approve_draft(self, *args, **kwargs):
            time.sleep(0.5)
            return SimpleNamespace(
                fe_result=AiFeResultDto(
                    generation_id="generation-1",
                    product=AiFeProductSummaryDto.from_profile(
                        ProductProfileDto.minimal("장식함")
                    ),
                    detail_page=FeDetailPageAssetDto(mime_type="image/png"),
                ),
                be_ack=None,
                backend_delivery_pending=False,
                warning=None,
            )

    monkeypatch.setattr(app_module, "get_service", lambda: SlowService())
    monkeypatch.setattr(
        app_module, "get_settings", lambda: SimpleNamespace(ai_internal_auth_token="secret")
    )
    metadata = json.dumps(
        {
            "product_id": "product-1",
            "idempotency_key": "approval-1",
            "draft_id": "job-1",
            "draft": {
                "product_name": "장식함",
                "summary": "설명",
                "hero_headline": "제목",
                "hero_description": "소개",
            },
        }
    )

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_module.app), base_url="http://test"
        ) as client:
            started = time.monotonic()
            approval = asyncio.create_task(
                app_module.approve_internal_detail_page(
                    metadata=metadata, x_ai_internal_token="secret"
                )
            )
            await asyncio.sleep(0.03)
            response = await client.get("/health")
            health_elapsed = time.monotonic() - started
            await approval
            return response, health_elapsed

    response, elapsed = asyncio.run(scenario())
    assert response.status_code == 200
    assert elapsed < 0.3


@pytest.mark.parametrize("kind", ["memory", "sqlite"])
def test_simultaneous_approval_renders_once(tmp_path, kind):
    renderer = ControlledRenderer(pause=True)
    repository = (
        MemoryJobRepository()
        if kind == "memory"
        else SQLiteJobRepository(tmp_path / "state.sqlite3")
    )
    service, draft, _, _, _ = ready_service(renderer=renderer, repository=repository)

    def approve():
        return service.approve_draft(
            "job-1", draft, idempotency_key="approve-1", product_id="product-1"
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(approve)
        assert renderer.entered.wait(timeout=2)
        second = pool.submit(approve)
        time.sleep(0.05)
        renderer.release.set()
        outcomes = []
        for future in (first, second):
            try:
                outcomes.append(future.result(timeout=3))
            except ValueError as exc:
                outcomes.append(exc)

    assert renderer.calls == 1
    assert sum(not isinstance(item, Exception) for item in outcomes) == 1
    assert sum("in progress" in str(item).lower() for item in outcomes) == 1


def test_internal_repeat_approval_returns_in_progress_conflict(monkeypatch):
    renderer = ControlledRenderer(pause=True)
    service, draft, _, _, _ = ready_service(renderer=renderer)
    monkeypatch.setattr(app_module, "get_service", lambda: service)
    monkeypatch.setattr(
        app_module,
        "get_settings",
        lambda: SimpleNamespace(ai_internal_auth_token="secret"),
    )
    metadata = json.dumps(
        {
            "product_id": "product-1",
            "idempotency_key": "approve-1",
            "draft_id": "job-1",
            "draft": draft.model_dump(mode="json"),
        }
    )

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_module.app), base_url="http://test"
        ) as client:
            headers = {"X-AI-Internal-Token": "secret"}
            first = asyncio.create_task(
                client.post(
                    "/internal/v1/ai/detail-page-renders",
                    data={"metadata": metadata},
                    headers=headers,
                )
            )
            try:
                assert await asyncio.to_thread(renderer.entered.wait, 2)
                repeat = await client.post(
                    "/internal/v1/ai/detail-page-renders",
                    data={"metadata": metadata},
                    headers=headers,
                )
            finally:
                renderer.release.set()
            return await first, repeat

    first, repeat = asyncio.run(scenario())
    assert first.status_code == 200
    assert repeat.status_code == 409, repeat.json()
    assert repeat.json() == {"detail": "Approval is already in progress"}
    assert renderer.calls == 1


def test_replaced_approval_attempt_reports_in_progress():
    renderer = ControlledRenderer(pause=True)
    service, draft, _, _, _ = ready_service(renderer=renderer)

    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(
            service.approve_draft, "job-1", draft, idempotency_key="approve-1"
        )
        assert renderer.entered.wait(timeout=2)

        def replace_attempt(job):
            job.approval_attempt_id = "replacement-attempt"

        service.repository.update("job-1", replace_attempt)
        renderer.release.set()
        with pytest.raises(ApprovalInProgressError) as caught:
            first.result(timeout=3)

    assert str(caught.value) == "Approval is already in progress"
    assert service.repository.get("job-1").approval_attempt_id == "replacement-attempt"


@pytest.mark.parametrize("product_id", [None, "product-1"])
@pytest.mark.parametrize("kind", ["memory", "sqlite"])
def test_simultaneous_create_with_same_key_returns_one_job(tmp_path, kind, product_id):
    barrier = Barrier(2)

    base = MemoryJobRepository if kind == "memory" else SQLiteJobRepository

    class RacingRepository(base):
        def __init__(self):
            if kind == "memory":
                super().__init__()
            else:
                super().__init__(tmp_path / "state.sqlite3")
            self.query_count = 0
            self.query_lock = Lock()

        def find_by_idempotency(self, product_id, idempotency_key):
            found = super().find_by_idempotency(product_id, idempotency_key)
            with self.query_lock:
                self.query_count += 1
                pause = self.query_count <= 2
            if pause:
                barrier.wait(timeout=3)
            return found

    repository = RacingRepository()
    service = DetailPageJobService(
        pipeline=DetailPagePipeline(
            analyzer=FixedAnalyzer(),
            renderer=ControlledRenderer(),
            backend=ControlledBackend(),
        ),
        repository=repository,
        executor=NoopExecutor(),
        retry_scheduler=RecordingScheduler(),
    )

    def submit():
        return service.submit(
            VALID_PNG, "image/png", product_id=product_id, idempotency_key="same-key"
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(submit), pool.submit(submit)
        first_job, second_job = first.result(timeout=3), second.result(timeout=3)

    assert first_job.job_id == second_job.job_id


@pytest.mark.parametrize("kind", ["memory", "sqlite"])
def test_nonretryable_initial_delivery_is_not_scheduled(tmp_path, kind):
    scheduler = RecordingScheduler()
    backend = ControlledBackend([BackendDeliveryError("permanent", retryable=False)])
    outbox = (
        MemoryDeliveryOutbox()
        if kind == "memory"
        else SQLiteDeliveryOutbox(tmp_path / "state.sqlite3")
    )
    service, draft, _, _, outbox = ready_service(
        backend=backend, scheduler=scheduler, outbox=outbox
    )

    result = service.approve_draft(
        "job-1", draft, idempotency_key="approve-1", product_id="product-1"
    )

    assert result.backend_delivery_pending is True
    assert outbox.get("generation-1").status == "PERMANENT_FAILED"
    assert outbox.list_retryable() == []
    assert outbox.claim("generation-1", "another-worker") is None
    assert scheduler.calls == []


@pytest.mark.parametrize("kind", ["memory", "sqlite"])
def test_retry_limit_excludes_failed_delivery_from_list_and_claim(tmp_path, kind):
    outbox = (
        MemoryDeliveryOutbox()
        if kind == "memory"
        else SQLiteDeliveryOutbox(tmp_path / "state.sqlite3")
    )
    ready_service(outbox=outbox, max_delivery_attempts=1)
    outbox.enqueue(
        persist_request(), GeneratedImage(data=VALID_PNG, mime_type="image/png"), ""
    )
    assert outbox.claim("delivery-1", "worker-1") is not None
    outbox.mark_failed("delivery-1", "temporary", "worker-1")

    assert outbox.list_retryable() == []
    assert outbox.claim("delivery-1", "worker-2") is None


def test_failed_approval_can_be_retried_with_the_same_key():
    class FailingOnceRenderer(ControlledRenderer):
        def render(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("renderer stopped")
            return GeneratedImage(data=VALID_PNG, mime_type="image/png")

    renderer = FailingOnceRenderer()
    service, draft, _, _, _ = ready_service(renderer=renderer)

    with pytest.raises(RuntimeError, match="renderer stopped"):
        service.approve_draft("job-1", draft, idempotency_key="approve-1")

    assert service.repository.get("job-1").approval_state == "FAILED"
    result = service.approve_draft("job-1", draft, idempotency_key="approve-1")
    assert result.fe_result.generation_id == "generation-1"
    assert renderer.calls == 2


def test_save_draft_rejects_approval_in_progress_and_stale_version():
    renderer = ControlledRenderer(pause=True)
    service, draft, _, _, _ = ready_service(renderer=renderer)

    with ThreadPoolExecutor(max_workers=1) as pool:
        approval = pool.submit(
            service.approve_draft, "job-1", draft, idempotency_key="approve-1"
        )
        try:
            assert renderer.entered.wait(timeout=2)
            with pytest.raises(ValueError, match="approval|Approval"):
                service.save_draft("job-1", draft, expected_version=1)
        finally:
            renderer.release.set()
        approval.result(timeout=3)

    another, another_draft, _, _, _ = ready_service()
    another.save_draft("job-1", another_draft, expected_version=1)
    with pytest.raises(DraftVersionConflictError):
        another.save_draft("job-1", another_draft, expected_version=1)


def test_existing_database_backfills_idempotency_scope(tmp_path):
    path = tmp_path / "old.sqlite3"
    record = JobRecord(
        job_id="old-job",
        request_id="old-request",
        product_id="product-1",
        idempotency_key="create-1",
        source_image=VALID_PNG,
        source_mime_type="image/png",
        options=GenerationOptions(),
    )
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE detail_page_jobs (job_id TEXT PRIMARY KEY, status TEXT NOT NULL, "
            "updated_at TEXT NOT NULL, payload_json TEXT NOT NULL, "
            "worker_id TEXT, lease_until TEXT)"
        )
        connection.execute(
            "INSERT INTO detail_page_jobs(job_id,status,updated_at,payload_json) "
            "VALUES (?,?,?,?)",
            (record.job_id, record.status, record.updated_at.isoformat(), _serialize_job(record)),
        )

    repository = SQLiteJobRepository(path)
    assert repository.find_by_idempotency("product-1", "create-1").job_id == "old-job"
    with sqlite3.connect(path) as connection:
        scope = connection.execute(
            "SELECT idempotency_scope_key FROM detail_page_jobs WHERE job_id='old-job'"
        ).fetchone()[0]
    assert scope is not None


def test_existing_database_with_duplicate_keys_fails_migration(tmp_path):
    path = tmp_path / "old-duplicates.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE detail_page_jobs (job_id TEXT PRIMARY KEY, status TEXT NOT NULL, "
            "updated_at TEXT NOT NULL, payload_json TEXT NOT NULL)"
        )
        for job_id in ("old-1", "old-2"):
            record = JobRecord(
                job_id=job_id,
                request_id=job_id,
                idempotency_key="same-key",
                source_image=VALID_PNG,
                source_mime_type="image/png",
                options=GenerationOptions(),
            )
            connection.execute(
                "INSERT INTO detail_page_jobs VALUES (?,?,?,?)",
                (job_id, record.status, record.updated_at.isoformat(), _serialize_job(record)),
            )

    with pytest.raises(ValueError, match="duplicate|Duplicate"):
        SQLiteJobRepository(path)


def test_initial_transient_delivery_failure_schedules_retry():
    scheduler = RecordingScheduler()
    backend = ControlledBackend([BackendDeliveryError("temporary", retryable=True)])
    service, draft, _, _, outbox = ready_service(backend=backend, scheduler=scheduler)

    result = service.approve_draft("job-1", draft, idempotency_key="approve-1")

    assert result.backend_delivery_pending is True
    assert outbox.get("generation-1").status == "FAILED"
    assert len(scheduler.calls) == 1


@pytest.mark.parametrize("kind", ["memory", "sqlite"])
def test_nonretryable_retry_stops_without_new_schedule(tmp_path, kind):
    scheduler = RecordingScheduler()
    backend = ControlledBackend(
        [
            BackendDeliveryError("temporary", retryable=True),
            BackendDeliveryError("permanent", retryable=False),
        ]
    )
    outbox = (
        MemoryDeliveryOutbox()
        if kind == "memory"
        else SQLiteDeliveryOutbox(tmp_path / "state.sqlite3")
    )
    service, draft, _, _, outbox = ready_service(
        backend=backend, scheduler=scheduler, outbox=outbox
    )
    service.approve_draft("job-1", draft, idempotency_key="approve-1")
    scheduled_before = len(scheduler.calls)

    service._retry_delivery("generation-1")

    assert outbox.get("generation-1").status == "PERMANENT_FAILED"
    assert outbox.list_retryable() == []
    assert outbox.claim("generation-1", "another-worker") is None
    assert len(scheduler.calls) == scheduled_before


@pytest.mark.parametrize("kind", ["memory", "sqlite"])
def test_restarting_service_releases_unfinished_approval(tmp_path, kind):
    repository = (
        MemoryJobRepository()
        if kind == "memory"
        else SQLiteJobRepository(tmp_path / "state.sqlite3")
    )
    service, draft, _, _, _ = ready_service(repository=repository)
    record = service.repository.get("job-1")
    record.approval_state = "IN_PROGRESS"
    record.approval_idempotency_key = "approve-1"
    record.approval_fingerprint = service._approval_fingerprint(draft, record.options)
    record.approval_attempt_id = "interrupted-attempt"
    service.repository.save(record)
    if kind == "sqlite":
        repository = SQLiteJobRepository(tmp_path / "state.sqlite3")

    restarted = DetailPageJobService(
        pipeline=service.pipeline,
        repository=repository,
        executor=NoopExecutor(),
        retry_scheduler=RecordingScheduler(),
    )

    assert restarted.repository.get("job-1").approval_state == "FAILED"
    result = restarted.approve_draft("job-1", draft, idempotency_key="approve-1")
    assert result.fe_result is not None


def test_successful_retry_clears_approval_delivery_pending():
    backend = ControlledBackend([BackendDeliveryError("temporary", retryable=True)])
    service, draft, _, _, outbox = ready_service(backend=backend)
    service.approve_draft("job-1", draft, idempotency_key="approve-1")
    assert service.repository.get("job-1").approval_backend_delivery_pending is True

    service._retry_delivery("generation-1")

    record = service.repository.get("job-1")
    assert outbox.get("generation-1").status == "DELIVERED"
    assert record.approval_backend_delivery_pending is False
    assert record.approval_warning is None
    assert record.approval_be_ack.status == "SAVED"


@pytest.mark.parametrize("kind", ["memory", "sqlite"])
def test_atomic_job_update_rolls_back_when_callback_raises(tmp_path, kind):
    repository = (
        MemoryJobRepository()
        if kind == "memory"
        else SQLiteJobRepository(tmp_path / "state.sqlite3")
    )
    repository.create(
        JobRecord(
            job_id="job-1",
            request_id="request-1",
            source_image=VALID_PNG,
            source_mime_type="image/png",
            options=GenerationOptions(),
        )
    )

    def fail_after_change(record):
        record.progress = 90
        raise ValueError("abort update")

    with pytest.raises(ValueError, match="abort update"):
        repository.update("job-1", fail_after_change)
    assert repository.get("job-1").progress == 0
