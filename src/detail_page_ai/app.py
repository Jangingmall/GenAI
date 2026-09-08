from pathlib import Path
from typing import Annotated
import hmac
import uuid

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .assets import LocalFileAssetStore
from .ai_dto import (
    AiToProductBeAcceptedResponseDto,
    AiToProductBeApprovedResponseDto,
    AiToProductBeStatusResponseDto,
    ProductBeToAiApproveDraftRequestDto,
    ProductBeToAiCreateJobRequestDto,
    ProductBeToAiSaveDraftRequestDto,
)
from .backend_client import BackendDeliveryError, BackendProductClient
from .config import get_settings
from .dto import (
    ApprovedDraftDto,
    GenerationMetadataDto,
    GenerationOptions,
    UserHintsDto,
)
from .fe_dto import (
    AiFeApprovedResponseDto,
    AiFeDraftResponseDto,
    AiFeJobAcceptedResponseDto,
    AiFeJobStatusResponseDto,
    AiFeResultResponseDto,
)
from .html_renderer import HtmlDetailPageRenderer
from .pipeline import DetailPagePipeline
from .persistence import SQLiteDeliveryOutbox, SQLiteJobRepository
from .service import (
    CapacityExceededError,
    DetailPageJobService,
    DraftVersionConflictError,
    IdempotencyConflictError,
)
from .source_photos import SourcePreservingProductPhotoGenerator
from local_detail_page_ai.adapters import LocalProductAnalyzer
from local_detail_page_ai.clients import (
    MlxServeChatClient,
    MlxServeImageClient,
    OllamaChatClient,
)
from local_detail_page_ai.runner import (
    MlxServeBackgroundGenerator,
    MlxServeDetailViewGenerator,
    MlxServeUsageSceneGenerator,
)


class UnconfiguredBackend:
    def persist(self, request, image):
        raise BackendDeliveryError(
            "BACKEND_PRODUCT_URL is not configured", retryable=True
        )


app = FastAPI(
    title="Image Detail Page AI",
    version="0.1.0",
)
_cors_origins = [
    origin.strip()
    for origin in getattr(
        get_settings(),
        "cors_origins",
        "http://127.0.0.1:4173,http://localhost:4173",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=[
        "Accept",
        "Content-Type",
        "Idempotency-Key",
        "X-AI-Internal-Token",
    ],
)
_service: DetailPageJobService | None = None


def build_service() -> DetailPageJobService:
    settings = get_settings()
    template_image = None
    if settings.detail_page_template_path:
        template_image = Path(settings.detail_page_template_path).read_bytes()

    if settings.analysis_provider != "local":
        raise ValueError("ANALYSIS_PROVIDER must be local")
    if settings.local_text_provider == "mlx":
        chat_client = MlxServeChatClient(
            base_url=settings.local_text_url,
            model=settings.local_text_model,
            timeout=settings.local_text_timeout_seconds,
        )
    elif settings.local_text_provider == "ollama":
        chat_client = OllamaChatClient(
            base_url=settings.local_text_url,
            model=settings.local_text_model,
            timeout=settings.local_text_timeout_seconds,
        )
    else:
        raise ValueError("LOCAL_TEXT_PROVIDER must be 'mlx' or 'ollama'")
    analyzer = LocalProductAnalyzer(chat_client=chat_client)
    analysis_model = settings.local_text_model
    asset_store = LocalFileAssetStore(
        getattr(settings, "asset_store_dir", ".local/detail-page-ai/assets")
    )
    sqlite_path = getattr(
        settings, "sqlite_path", ".local/detail-page-ai/state.sqlite3"
    )
    outbox = SQLiteDeliveryOutbox(sqlite_path)
    repository = SQLiteJobRepository(sqlite_path)
    photo_provider = getattr(settings, "product_photo_generation", "source")
    if photo_provider != "source":
        raise ValueError(
            "Original product pixels are immutable; set "
            "PRODUCT_PHOTO_GENERATION=source. Local Flux may generate backgrounds only."
        )
    configured_shots = tuple(
        shot.strip()
        for shot in getattr(
            settings,
            "product_photo_shots",
            "hero,packshot,detail,lifestyle",
        ).split(",")
        if shot.strip()
    )
    if not configured_shots or any(
        shot not in {"hero", "packshot", "detail", "lifestyle", "scale"}
        for shot in configured_shots
    ):
        raise ValueError(
            "PRODUCT_PHOTO_SHOTS must contain only hero, packshot, detail, lifestyle, scale"
        )
    background_generator = None
    usage_scene_generator = None
    detail_view_generator = None
    image_model = "source-preserving-pillow-compositor"
    if settings.background_provider == "mlx":
        if settings.local_image_provider != "mlx":
            raise ValueError(
                "BACKGROUND_PROVIDER=mlx requires LOCAL_IMAGE_PROVIDER=mlx"
            )
        image_client = MlxServeImageClient(
            base_url=settings.local_image_url,
            model=settings.local_image_model,
            timeout=settings.local_image_timeout_seconds,
        )
        background_generator = MlxServeBackgroundGenerator(image_client)
        usage_scene_generator = MlxServeUsageSceneGenerator(image_client)
        detail_view_generator = MlxServeDetailViewGenerator(image_client)
        image_model = settings.local_image_model
    elif settings.local_image_provider not in {"none", "mlx"}:
        raise ValueError("LOCAL_IMAGE_PROVIDER must be 'none' or 'mlx'")
    photo_generator = SourcePreservingProductPhotoGenerator(
        asset_store=asset_store,
        background_generator=background_generator,
        usage_scene_generator=usage_scene_generator,
        detail_view_generator=detail_view_generator,
        include_scale="scale" in configured_shots,
        photo_roles=configured_shots,
        source_photo_variation_threshold=getattr(
            settings, "source_photo_variation_threshold", 4
        ),
    )
    if settings.detail_page_renderer != "html":
        raise ValueError(
            "Original product pixels are immutable; set DETAIL_PAGE_RENDERER=html."
        )
    renderer = HtmlDetailPageRenderer()
    backend = (
        BackendProductClient(
            url=settings.backend_product_url,
            token=settings.backend_auth_token,
            timeout=settings.backend_timeout_seconds,
        )
        if settings.backend_product_url
        else UnconfiguredBackend()
    )
    return DetailPageJobService(
        pipeline=DetailPagePipeline(
            analyzer=analyzer,
            photo_generator=photo_generator,
            renderer=renderer,
            backend=backend,
            template_image=template_image,
            generation_metadata=GenerationMetadataDto(
                provider=settings.analysis_provider,
                analysis_model=analysis_model,
                image_model=image_model,
                prompt_version=settings.prompt_version,
            ),
            outbox=outbox,
            asset_store=asset_store,
            response_asset_mode=getattr(settings, "response_asset_mode", "base64"),
            craft_confidence_threshold=getattr(
                settings, "craft_confidence_threshold", 0.65
            ),
            max_image_bytes=getattr(settings, "max_image_bytes", 10 * 1024 * 1024),
            max_source_images=getattr(settings, "max_source_images", 12),
            max_total_input_bytes=getattr(
                settings, "max_request_bytes", 120 * 1024 * 1024
            ),
            max_pending_generations=getattr(settings, "max_pending_generations", 100),
            require_decodable_images=getattr(
                settings, "require_decodable_images", True
            ),
        ),
        repository=repository,
        max_pending_generations=getattr(settings, "max_pending_generations", 100),
        max_image_bytes=getattr(settings, "max_image_bytes", 10 * 1024 * 1024),
        max_source_images=getattr(settings, "max_source_images", 12),
        max_total_input_bytes=getattr(
            settings, "max_request_bytes", 120 * 1024 * 1024
        ),
        max_delivery_attempts=getattr(settings, "max_delivery_attempts", 8),
        require_decodable_images=getattr(
            settings, "require_decodable_images", True
        ),
    )


def get_service() -> DetailPageJobService:
    global _service
    if _service is None:
        _service = build_service()
    return _service


def _require_internal_auth(token: str | None) -> None:
    configured_token = getattr(get_settings(), "ai_internal_auth_token", None)
    if not configured_token:
        raise HTTPException(
            status_code=503,
            detail="AI internal integration is unavailable",
        )
    if not token or not hmac.compare_digest(token, configured_token):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _require_legacy_demo_api() -> None:
    if not getattr(get_settings(), "enable_legacy_demo_api", False):
        raise HTTPException(
            status_code=404,
            detail="Legacy demo API is disabled; use the Product BE internal API",
        )


def _resolve_idempotency_key(header_key: str | None, body_key: str) -> str:
    if header_key and header_key != body_key:
        raise HTTPException(status_code=409, detail="Idempotency key conflict")
    return header_key or body_key


async def _read_additional_source_images(
    product_images: list[UploadFile] | None,
) -> tuple[tuple[bytes, str], ...]:
    settings = get_settings()
    max_images = getattr(settings, "max_source_images", 12)
    max_bytes = getattr(settings, "max_image_bytes", 10 * 1024 * 1024)
    max_total = getattr(settings, "max_request_bytes", 120 * 1024 * 1024)
    uploads = product_images or []
    if len(uploads) + 1 > max_images:
        raise HTTPException(status_code=413, detail="Too many source images")
    images = []
    total = 0
    for upload in uploads:
        data = await upload.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise HTTPException(status_code=413, detail="Source image is too large")
        total += len(data)
        if total > max_total:
            raise HTTPException(status_code=413, detail="Source images are too large")
        images.append((data, upload.content_type or "application/octet-stream"))
    return tuple(images)


async def _read_primary_source_image(upload: UploadFile) -> bytes:
    settings = get_settings()
    max_bytes = getattr(settings, "max_image_bytes", 10 * 1024 * 1024)
    data = await upload.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail="Source image is too large")
    return data


@app.post(
    "/api/v1/ai/detail-page-jobs",
    response_model=AiFeJobAcceptedResponseDto,
    status_code=202,
)
async def create_detail_page_job(
    product_image: Annotated[UploadFile, File(...)],
    product_images: Annotated[list[UploadFile] | None, File()] = None,
    product_name: Annotated[str | None, Form()] = None,
    making_method: Annotated[str | None, Form()] = None,
    care_guide: Annotated[str | None, Form()] = None,
    request_id: Annotated[str | None, Form()] = None,
    template_id: Annotated[str | None, Form()] = None,
    locale: Annotated[str, Form()] = "ko-KR",
    options: Annotated[str | None, Form()] = None,
    _legacy_demo: None = Depends(_require_legacy_demo_api),
):
    if template_id not in (None, "default-long-detail-page"):
        raise HTTPException(status_code=400, detail="Unsupported template_id")
    if locale != "ko-KR":
        raise HTTPException(status_code=400, detail="Only ko-KR locale is supported")
    image_bytes = await _read_primary_source_image(product_image)
    additional_source_images = await _read_additional_source_images(product_images)
    try:
        generation_options = (
            GenerationOptions.model_validate_json(options)
            if options
            else GenerationOptions()
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid generation options") from exc
    try:
        user_hints = UserHintsDto(
            product_name=product_name,
            making_method=making_method,
            care_guide=care_guide,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid creator notes") from exc
    try:
        service = get_service()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="AI service is unavailable") from exc
    try:
        return service.submit(
            image_bytes,
            product_image.content_type or "application/octet-stream",
            request_id=request_id,
            options=generation_options,
            user_hints=user_hints,
            additional_source_images=additional_source_images,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid product image") from exc


@app.post(
    "/api/v1/ai/detail-page-renders",
    response_model=AiFeApprovedResponseDto,
)
async def approve_detail_page(
    product_image: Annotated[UploadFile, File(...)],
    draft: Annotated[str, Form(...)],
    product_images: Annotated[list[UploadFile] | None, File()] = None,
    request_id: Annotated[str | None, Form()] = None,
    options: Annotated[str | None, Form()] = None,
    _legacy_demo: None = Depends(_require_legacy_demo_api),
):
    image_bytes = await _read_primary_source_image(product_image)
    additional_source_images = await _read_additional_source_images(product_images)
    try:
        approved_draft = ApprovedDraftDto.model_validate_json(draft)
        generation_options = (
            GenerationOptions.model_validate_json(options)
            if options
            else GenerationOptions()
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid approved draft") from exc
    try:
        service = get_service()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="AI service is unavailable") from exc
    try:
        pipeline_result = service.pipeline.run(
            job_id=f"approved-{uuid.uuid4()}",
            request_id=request_id or str(uuid.uuid4()),
            source_image=image_bytes,
            source_mime_type=product_image.content_type or "application/octet-stream",
            options=generation_options,
            additional_source_images=additional_source_images,
            profile_override=approved_draft.to_profile(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid product image") from exc
    status = (
        "COMPLETED_WITH_BACKEND_PENDING"
        if pipeline_result.backend_delivery_pending
        else "COMPLETED"
    )
    return AiFeApprovedResponseDto(
        status=status,
        result=AiFeResultResponseDto.model_validate(
            pipeline_result.fe_result.model_dump()
        ),
        backend_delivery_pending=pipeline_result.backend_delivery_pending,
        warning=pipeline_result.warning,
        be_ack=pipeline_result.be_ack,
    )


@app.post(
    "/internal/v1/ai/detail-page-jobs",
    response_model=AiToProductBeAcceptedResponseDto,
    status_code=202,
)
async def create_internal_detail_page_job(
    product_image: Annotated[UploadFile, File(...)],
    metadata: Annotated[str, Form(...)],
    product_images: Annotated[list[UploadFile] | None, File()] = None,
    x_ai_internal_token: Annotated[str | None, Header(alias="X-AI-Internal-Token")] = None,
    idempotency_header: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    """Product BE → AI job intake; FE must not call this route directly."""

    _require_internal_auth(x_ai_internal_token)
    try:
        request = ProductBeToAiCreateJobRequestDto.model_validate_json(metadata)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid AI job metadata") from exc

    image_bytes = await _read_primary_source_image(product_image)
    additional_source_images = await _read_additional_source_images(product_images)
    try:
        service = get_service()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="AI service is unavailable") from exc
    try:
        accepted = service.submit(
            image_bytes,
            product_image.content_type or "application/octet-stream",
            request_id=request.request_id,
            options=request.options,
            user_hints=request.user_hints,
            additional_source_images=additional_source_images,
            product_id=request.product_id,
            source_asset_id=request.source_asset_id,
            idempotency_key=_resolve_idempotency_key(
                idempotency_header, request.idempotency_key
            ),
            status_path_prefix="/internal/v1/ai/detail-page-jobs",
        )
    except CapacityExceededError as exc:
        raise HTTPException(status_code=429, detail="AI job capacity is full") from exc
    except IdempotencyConflictError as exc:
        raise HTTPException(status_code=409, detail="Idempotency key conflict") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid product image") from exc
    accepted_payload = (
        accepted.model_dump(mode="json")
        if hasattr(accepted, "model_dump")
        else accepted
    )
    return AiToProductBeAcceptedResponseDto(
        product_id=request.product_id,
        **accepted_payload,
    )


@app.get(
    "/internal/v1/ai/detail-page-jobs/{job_id}",
    response_model=AiToProductBeStatusResponseDto,
)
def get_internal_detail_page_job(
    job_id: str,
    x_ai_internal_token: Annotated[str | None, Header(alias="X-AI-Internal-Token")] = None,
):
    """Product BE → AI recovery/status polling endpoint."""

    _require_internal_auth(x_ai_internal_token)
    try:
        return get_service().get_backend(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="Job has no Product BE identity") from exc


@app.put(
    "/internal/v1/ai/detail-page-jobs/{job_id}/draft",
    response_model=AiFeDraftResponseDto,
)
async def save_internal_detail_page_draft(
    job_id: str,
    request: ProductBeToAiSaveDraftRequestDto,
    x_ai_internal_token: Annotated[str | None, Header(alias="X-AI-Internal-Token")] = None,
):
    """Persist creator edits while keeping the preview as restricted React JSON."""
    _require_internal_auth(x_ai_internal_token)
    try:
        return get_service().save_draft(
            job_id,
            request.draft,
            expected_version=request.version,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Draft not found") from exc
    except DraftVersionConflictError as exc:
        raise HTTPException(status_code=409, detail="Draft version conflict") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="Draft cannot be saved") from exc


@app.post(
    "/internal/v1/ai/detail-page-renders",
    response_model=AiToProductBeApprovedResponseDto,
)
async def approve_internal_detail_page(
    metadata: Annotated[str, Form(...)],
    product_image: Annotated[UploadFile | None, File()] = None,
    product_images: Annotated[list[UploadFile] | None, File()] = None,
    x_ai_internal_token: Annotated[str | None, Header(alias="X-AI-Internal-Token")] = None,
    idempotency_header: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    """Product BE → AI approved-draft render endpoint."""

    _require_internal_auth(x_ai_internal_token)
    try:
        request = ProductBeToAiApproveDraftRequestDto.model_validate_json(metadata)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid approved draft metadata") from exc

    try:
        service = get_service()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="AI service is unavailable") from exc
    try:
        if hasattr(service, "approve_draft"):
            if not request.draft_id:
                raise ValueError("draft_id is required for internal approval")
            pipeline_result = service.approve_draft(
                request.draft_id,
                request.draft,
                request_id=request.request_id,
                idempotency_key=_resolve_idempotency_key(
                    idempotency_header, request.idempotency_key
                ),
                options=request.options,
                product_id=request.product_id,
                source_asset_id=request.source_asset_id,
            )
        else:
            if product_image is None:
                raise ValueError("product_image is required for legacy approval")
            image_bytes = await _read_primary_source_image(product_image)
            additional_source_images = await _read_additional_source_images(product_images)
            pipeline_result = service.pipeline.run(
                job_id=f"approved-{uuid.uuid4()}",
                request_id=request.request_id or str(uuid.uuid4()),
                source_image=image_bytes,
                source_mime_type=product_image.content_type or "application/octet-stream",
                options=request.options,
                additional_source_images=additional_source_images,
                profile_override=request.draft.to_profile(),
                product_id=request.product_id,
                source_asset_id=request.source_asset_id,
            )
    except IdempotencyConflictError as exc:
        raise HTTPException(status_code=409, detail="Idempotency key conflict") from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Draft not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid product image") from exc
    status = (
        "COMPLETED_WITH_BACKEND_PENDING"
        if pipeline_result.backend_delivery_pending
        else "COMPLETED"
    )
    return AiToProductBeApprovedResponseDto(
        product_id=request.product_id,
        status=status,
        result=pipeline_result.fe_result,
        backend_delivery_pending=pipeline_result.backend_delivery_pending,
        warning=pipeline_result.warning,
        be_ack=pipeline_result.be_ack,
    )


@app.get(
    "/api/v1/ai/detail-page-jobs/{job_id}",
    response_model=AiFeJobStatusResponseDto,
)
def get_detail_page_job(
    job_id: str,
    _legacy_demo: None = Depends(_require_legacy_demo_api),
):
    try:
        return get_service().get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


@app.put(
    "/api/v1/ai/detail-page-jobs/{job_id}/draft",
    response_model=AiFeDraftResponseDto,
)
async def save_detail_page_draft(
    job_id: str,
    request: ProductBeToAiSaveDraftRequestDto,
    _legacy_demo: None = Depends(_require_legacy_demo_api),
):
    try:
        return get_service().save_draft(
            job_id, request.draft, expected_version=request.version
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Draft not found") from exc
    except DraftVersionConflictError as exc:
        raise HTTPException(status_code=409, detail="Draft version conflict") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="Draft cannot be saved") from exc


def run() -> None:
    import uvicorn

    uvicorn.run("detail_page_ai.app:app", host="0.0.0.0", port=8000, reload=False)
