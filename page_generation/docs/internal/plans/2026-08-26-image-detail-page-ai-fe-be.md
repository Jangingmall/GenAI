# 이미지 기반 상세페이지 AI-FE/AI-BE Implementation Plan (보관용 초기안)

> 이 문서는 초기 생성형 최종 이미지 설계를 보관한 문서입니다. 현재 구현은 2026-08-27
> 원본 보존 설계로 대체되었습니다. Gemini/Bedrock whole-product image renderer와
> image-to-image 제품 변형 경로는 현재 서비스에 존재하지 않으며, [최신 원본 보존 설계](../../phase1/2026-08-27-source-preserving-detail-page-design.md)
> 및 [구현 계획](2026-08-27-source-preserving-detail-page-implementation.md)을 기준으로 합니다.

> 2026-09-08 최신화 메모: 이 보관용 초기안에는 React JSON 출력 계약이 없다. 현재 구현은
> `draft.react_document`와 `result.detail_page.react_document`를 제한형 AST로 제공하며,
> 제품 영역을 재생성하지 않는다. 최신 계약은 [AI DTO 계약](../../phase3/api/ai-dto-contract.md)과
> [BE/FE 연동 명세](../../phase3/api/be-fe-ai-integration-spec.md)를 따른다.
> 이 문서의 Goal/Architecture와 직접 FE→AI 표현은 과거안으로만 보존한다. 현재 운영 경계는
> `FE → 상품 BE → AI → 상품 BE → FE`다.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 상품 이미지 한 장을 분석해 긴 세로형 상세페이지 이미지를 생성하고, AI-FE와 AI-BE에 서로 다른 DTO로 전달하는 실행 가능한 Python 서비스를 구축한다.

**Architecture:** FE는 AI 서비스에 이미지를 직접 업로드하고 작업 상태를 조회한다. AI 서비스는 1차 비전 분석으로 `ProductProfile`을 만들고 2차 Gemini 이미지 생성으로 상세페이지 이미지를 만든다. 생성 결과는 AI-FE 응답으로 반환하는 동시에 AI-BE multipart 요청으로 전송하며, BE는 받은 상품 프로필과 이미지를 DB에 적재한다.

**Tech Stack:** Python 3.13+, FastAPI, Pydantic, google-genai, httpx, pytest

**Spec:** `docs/phase1/2026-08-26-image-driven-detail-page-design.md`, `docs/phase3/api/ai-dto-contract.md`

## Global Constraints

- 상품 이미지가 상품 정보의 주된 근거이며, 이미지에서 확인할 수 없는 성능·수치·인증·효능·정확한 소재는 생성하지 않는다.
- AI-FE와 AI-BE는 DTO와 전송을 분리하지만 `job_id`, `request_id`, `generation_id`로 같은 생성 건을 연결한다.
- 최종 상세페이지는 Gemini `1:4` 비율, `2K`, 이미지 한 장으로 생성한다.
- AI는 BE DB에 직접 접근하지 않고 HTTP client로 DB 적재 요청만 전송한다.
- API 키와 BE 인증 토큰은 코드·DTO·로그에 기록하지 않는다.
- 외부 Gemini/BE 호출은 테스트에서 가짜 adapter/client로 교체할 수 있어야 한다.
- 현재 workspace는 Git repository가 아니므로 구현 중 commit 단계는 실행하지 않는다.

## File Map

- Create `src/detail_page_ai/__init__.py`: 공개 서비스 진입점
- Create `src/detail_page_ai/config.py`: 환경변수 기반 설정
- Create `src/detail_page_ai/models.py`: 공통 모델과 내부 `ProductProfile`
- Create `src/detail_page_ai/dto.py`: AI-FE와 AI-BE DTO 및 직렬화
- Create `src/detail_page_ai/prompts.py`: 이미지 분석·상세페이지 생성 프롬프트
- Create `src/detail_page_ai/validation.py`: 이미지 및 AI 결과 검증
- Create `src/detail_page_ai/ports.py`: 분석기·렌더러·BE sink protocol
- Create `src/detail_page_ai/gemini_provider.py`: google-genai adapter
- Create `src/detail_page_ai/backend_client.py`: AI-BE multipart HTTP client
- Create `src/detail_page_ai/pipeline.py`: 분석→생성→두 채널 전달 orchestration
- Create `src/detail_page_ai/service.py`: 작업 생성·상태 조회·비동기 실행 관리
- Create `src/detail_page_ai/app.py`: AI-FE FastAPI endpoint
- Create `tests/test_dto.py`: DTO serialization tests
- Create `tests/test_prompts.py`: prompt policy tests
- Create `tests/test_validation.py`: input/profile validation tests
- Create `tests/test_pipeline.py`: success and independent failure tests
- Create `tests/test_backend_client.py`: AI-BE multipart payload tests
- Create `tests/test_service.py`: AI-FE job state tests
- Modify `pyproject.toml`: dependencies, pytest config, CLI entrypoint
- Modify `docs/phase3/api/ai-dto-contract.md`: MVP AI-FE image transport and implementation names

---

### Task 1: Project scaffolding and shared domain models

**Files:**
- Create: `src/detail_page_ai/__init__.py`
- Create: `src/detail_page_ai/config.py`
- Create: `src/detail_page_ai/models.py`
- Create: `src/detail_page_ai/dto.py`
- Create: `tests/test_dto.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces `ProductProfile`, `GenerationOptions`, `GeneratedImage`, `AiFeAcceptedResponse`, `AiFeStatusResponse`, `AiBeProductPersistRequest`, and `AiBePersistAck`.

- [x] **Step 1: Write failing DTO tests**

```python
from detail_page_ai.dto import (
    AiBeProductPersistRequest,
    AiFeStatusResponse,
    ProductProfileDto,
)


def test_product_profile_serializes_observations_and_copy_separately():
    profile = ProductProfileDto(
        product_type="desk lamp",
        display_name="미니멀 데스크 램프",
        summary="깔끔한 형태의 데스크 램프",
        keywords=["미니멀", "데스크"],
        observations={"colors": ["black"], "shape": "rounded"},
        features=[
            {
                "title": "컴팩트한 형태",
                "description": "작은 공간에 어울리는 형태입니다.",
                "evidence": "image-visible",
                "confidence": 0.9,
            }
        ],
        copy_sections=[
            {
                "section_type": "hero",
                "title": "매일 함께하는 깔끔함",
                "description": "단정한 디자인의 데스크 램프",
            }
        ],
        usage_scene="책상 위 사용 장면",
        uncertain_information=["정확한 밝기 수치"],
        safety_notes=["밝기 수치를 단정하지 않음"],
    )

    payload = profile.model_dump()

    assert payload["observations"]["colors"] == ["black"]
    assert payload["copy_sections"][0]["section_type"] == "hero"
    assert payload["uncertain_information"] == ["정확한 밝기 수치"]


def test_ai_fe_processing_response_has_no_ai_be_internal_fields():
    response = AiFeStatusResponse.completed(
        job_id="job-1",
        request_id="request-1",
        generation_id="generation-1",
        profile=ProductProfileDto.minimal("desk lamp"),
        image_base64="ZmFrZQ==",
        mime_type="image/png",
    )

    payload = response.model_dump()

    assert payload["result"]["generation_id"] == "generation-1"
    assert "source_image_sha256" not in payload["result"]
    assert "prompt_version" not in payload["result"]
    assert "product_id" not in payload["result"]


def test_ai_be_payload_contains_idempotency_key_and_full_profile():
    request = AiBeProductPersistRequest.from_profile(
        generation_id="generation-1",
        job_id="job-1",
        request_id="request-1",
        source_image_mime_type="image/png",
        source_image_sha256="source-hash",
        generated_image_mime_type="image/png",
        generated_width=1024,
        generated_height=4096,
        generated_image_sha256="generated-hash",
        profile=ProductProfileDto.minimal("desk lamp"),
        generation={"prompt_version": "detail-page-v1"},
    )

    payload = request.model_dump()

    assert payload["idempotency_key"] == "generation-1"
    assert payload["source"]["sha256"] == "source-hash"
    assert payload["product"]["observations"] is not None
    assert payload["generation"]["prompt_version"] == "detail-page-v1"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dto.py -q`
Expected: FAIL because the `detail_page_ai` package and DTO classes do not exist.

- [x] **Step 3: Implement domain models and DTOs**

Implement Pydantic models with these exact boundaries:

```python
class ProductProfileDto(BaseModel):
    product_type: str
    display_name: str | None
    summary: str
    keywords: list[str]
    observations: dict[str, Any]
    features: list[ProductFeatureDto]
    copy_sections: list[CopySectionDto]
    usage_scene: str
    uncertain_information: list[str]
    safety_notes: list[str]


class AiFeStatusResponse(BaseModel):
    job_id: str
    request_id: str
    status: Literal["QUEUED", "ANALYZING", "RENDERING", "DELIVERING", "COMPLETED", "FAILED"]
    progress: int
    result: AiFeResultDto | None
    error: ErrorDto | None


class AiBeProductPersistRequest(BaseModel):
    generation_id: str
    job_id: str
    request_id: str
    idempotency_key: str
    source: SourceImageDto
    product: ProductProfileDto
    detail_page: GeneratedAssetMetadataDto
    generation: GenerationMetadataDto
```

`AiFeResultDto` must expose only FE-facing summary fields and either `image_base64` for the self-contained MVP transport or `image_url` when an asset store is configured. `AiBeProductPersistRequest` must retain observations, uncertainty, hashes, model data, and prompt version.

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_dto.py -q`
Expected: PASS.

### Task 2: Prompt builders and validation policies

**Files:**
- Create: `src/detail_page_ai/prompts.py`
- Create: `src/detail_page_ai/validation.py`
- Create: `tests/test_prompts.py`
- Create: `tests/test_validation.py`

**Interfaces:**
- Produces `build_analysis_prompt(locale: str) -> str`.
- Produces `build_detail_page_prompt(profile: ProductProfileDto, locale: str) -> str`.
- Produces `validate_source_image(data: bytes, mime_type: str) -> None`.
- Produces `validate_product_profile(profile: ProductProfileDto) -> None`.

- [x] **Step 1: Write failing prompt and validation tests**

```python
import pytest

from detail_page_ai.prompts import build_analysis_prompt, build_detail_page_prompt
from detail_page_ai.validation import InvalidImageError, ProfileValidationError, validate_source_image, validate_product_profile
from detail_page_ai.dto import ProductProfileDto


def test_analysis_prompt_requires_image_visible_facts_only():
    prompt = build_analysis_prompt("ko-KR")

    assert "이미지에서 확인 가능한 정보만" in prompt
    assert "성능 수치" in prompt
    assert "JSON" in prompt


def test_render_prompt_requires_one_tall_image_and_product_identity():
    prompt = build_detail_page_prompt(ProductProfileDto.minimal("desk lamp"), "ko-KR")

    assert "1:4" in prompt
    assert "상세페이지 이미지 한 장" in prompt
    assert "제품의 형태, 색상, 비율을 유지" in prompt


def test_invalid_image_is_rejected():
    with pytest.raises(InvalidImageError):
        validate_source_image(b"not-an-image", "image/png")


def test_profile_rejects_unbounded_long_copy():
    profile = ProductProfileDto.minimal("desk lamp").model_copy(
        update={"summary": "x" * 501}
    )

    with pytest.raises(ProfileValidationError):
        validate_product_profile(profile)
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_prompts.py tests/test_validation.py -q`
Expected: FAIL because prompt builders and validation functions do not exist.

- [x] **Step 3: Implement prompts and validation**

The analysis prompt must request `ProductProfileDto` JSON, short Korean copy, confidence, uncertainty, and no unsupported claims. The render prompt must include the profile JSON, the reference-template instruction, one `1:4` image, `2K`, no template sample text, and exact product identity preservation. Image validation must accept only PNG/JPEG/WebP signatures, reject empty data, and enforce a configurable maximum byte size. Profile validation must enforce non-empty product type, maximum summary length 500, maximum five features, maximum eight copy sections, and confidence in `[0, 1]`.

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_prompts.py tests/test_validation.py -q`
Expected: PASS.

### Task 3: Gemini provider adapters

**Files:**
- Create: `src/detail_page_ai/ports.py`
- Create: `src/detail_page_ai/gemini_provider.py`
- Create: `tests/test_gemini_provider.py`
- Modify: `pyproject.toml`

**Interfaces:**
- `ProductAnalyzer.analyze(image: bytes, mime_type: str) -> ProductProfileDto`
- `DetailPageRenderer.render(source_image: bytes, source_mime_type: str, template_image: bytes | None, profile: ProductProfileDto, options: GenerationOptions) -> GeneratedImage`

- [x] **Step 1: Write failing adapter contract tests**

```python
from detail_page_ai.dto import GenerationOptions, ProductProfileDto
from detail_page_ai.gemini_provider import GeminiAnalyzer, GeminiRenderer


class FakeInteractionClient:
    def __init__(self):
        self.calls = []

    def analyze(self, **kwargs):
        self.calls.append(("analyze", kwargs))
        return ProductProfileDto.minimal("desk lamp").model_dump_json()

    def render(self, **kwargs):
        self.calls.append(("render", kwargs))
        return b"generated-image-bytes"


def test_analyzer_sends_image_and_parses_profile():
    client = FakeInteractionClient()
    profile = GeminiAnalyzer(client=client, model="analysis-model").analyze(b"png", "image/png")

    assert profile.product_type == "desk lamp"
    assert client.calls[0][1]["image"] == b"png"


def test_renderer_passes_profile_and_1_to_4_options():
    client = FakeInteractionClient()
    image = GeminiRenderer(client=client, model="gemini-3.1-flash-image").render(
        source_image=b"png",
        source_mime_type="image/png",
        template_image=b"template",
        profile=ProductProfileDto.minimal("desk lamp"),
        options=GenerationOptions(aspect_ratio="1:4", image_size="2K"),
    )

    assert image.data == b"generated-image-bytes"
    assert client.calls[0][1]["options"].aspect_ratio == "1:4"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_gemini_provider.py -q`
Expected: FAIL because provider adapters do not exist.

- [x] **Step 3: Implement provider protocols and Gemini adapters**

Keep the real SDK behind an adapter. `GeminiAnalyzer` must send the product image and analysis prompt to the configured analysis model, parse JSON, and raise `AiResponseInvalidError` for malformed output. `GeminiRenderer` must send the product image, optional template image, render prompt, `aspect_ratio="1:4"`, `image_size="2K"`, and return the final image bytes. Import `google-genai` lazily so pure unit tests can run without credentials.

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_gemini_provider.py -q`
Expected: PASS.

### Task 4: AI-BE persistence client

**Files:**
- Create: `src/detail_page_ai/backend_client.py`
- Create: `tests/test_backend_client.py`

**Interfaces:**
- `BackendProductClient.persist(request: AiBeProductPersistRequest, image: GeneratedImage) -> AiBePersistAck`

- [x] **Step 1: Write failing multipart contract tests**

```python
from detail_page_ai.backend_client import BackendProductClient
from detail_page_ai.dto import AiBeProductPersistRequest, GeneratedImage, ProductProfileDto


class FakeHttpTransport:
    def __init__(self):
        self.request = None

    def post_multipart(self, url, fields, files, headers, timeout):
        self.request = {"url": url, "fields": fields, "files": files, "headers": headers, "timeout": timeout}
        return {
            "generation_id": "generation-1",
            "product_id": "product-1",
            "status": "SAVED",
            "saved_at": "2026-08-26T08:01:12Z",
        }


def test_persist_sends_metadata_and_image_as_separate_parts():
    transport = FakeHttpTransport()
    client = BackendProductClient(
        url="https://backend.example/internal/v1/ai-generated-products",
        token="secret",
        transport=transport,
    )
    request = AiBeProductPersistRequest.from_profile(
        generation_id="generation-1",
        job_id="job-1",
        request_id="request-1",
        source_image_mime_type="image/png",
        source_image_sha256="source-hash",
        generated_image_mime_type="image/png",
        generated_width=1024,
        generated_height=4096,
        generated_image_sha256="generated-hash",
        profile=ProductProfileDto.minimal("desk lamp"),
        generation={"prompt_version": "detail-page-v1"},
    )

    ack = client.persist(request, GeneratedImage(data=b"png", mime_type="image/png", width=1024, height=4096))

    assert ack.status == "SAVED"
    assert transport.request["fields"]["metadata"]["generation_id"] == "generation-1"
    assert transport.request["files"]["detail_page_image"]["data"] == b"png"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_backend_client.py -q`
Expected: FAIL because `BackendProductClient` does not exist.

- [x] **Step 3: Implement AI-BE client**

Send `metadata` as JSON and `detail_page_image` as binary multipart. Add `Authorization: Bearer <token>` only when a token is configured. Map HTTP 2xx responses to `AiBePersistAck`, map 409 to `ALREADY_SAVED`, and map timeout/5xx/network failures to a retryable `BackendDeliveryError`. Never log the token or raw image bytes.

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_backend_client.py -q`
Expected: PASS.

### Task 5: Independent AI-FE/AI-BE pipeline

**Files:**
- Create: `src/detail_page_ai/pipeline.py`
- Create: `tests/test_pipeline.py`

**Interfaces:**
- `DetailPagePipeline.run(job_id: str, request_id: str, source_image: bytes, source_mime_type: str) -> PipelineResult`
- `DetailPagePipeline.retry_backend_delivery(generation_id: str) -> AiBePersistAck`

- [x] **Step 1: Write failing pipeline tests**

```python
from detail_page_ai.pipeline import DetailPagePipeline


def test_pipeline_analyzes_renders_delivers_to_fe_and_be():
    result = make_pipeline().run("job-1", "request-1", b"png", "image/png")

    assert result.fe_result.product.product_type == "desk lamp"
    assert result.fe_result.detail_page.image_base64 == "Z2VuZXJhdGVk"
    assert result.be_ack.status == "SAVED"


def test_backend_failure_does_not_trigger_second_image_generation():
    pipeline, renderer, backend = make_pipeline(backend_error=True, return_parts=True)

    result = pipeline.run("job-1", "request-1", b"png", "image/png")

    assert result.fe_result.product.product_type == "desk lamp"
    assert result.be_ack is None
    assert result.backend_delivery_pending is True
    assert renderer.call_count == 1
    assert backend.call_count == 1


def test_backend_retry_uses_saved_generation_without_reanalysis_or_rerender():
    pipeline, renderer, backend = make_pipeline(backend_error=True, return_parts=True)
    first = pipeline.run("job-1", "request-1", b"png", "image/png")
    backend.fail = False

    ack = pipeline.retry_backend_delivery(first.generation_id)

    assert ack.status == "SAVED"
    assert renderer.call_count == 1
    assert backend.call_count == 2
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pipeline.py -q`
Expected: FAIL because the pipeline and test fixtures do not exist.

- [x] **Step 3: Implement the pipeline**

Run the following order exactly: validate image → analyze → validate profile → render → build FE result → attempt AI-BE persistence. Store the generated bytes and full AI-BE request by `generation_id` in a bounded in-memory result store for MVP retry. FE result must be returned even when BE delivery fails, with a retryable warning. A BE delivery retry must reuse the stored profile, generated bytes, hashes, and generation metadata without calling analyzer or renderer.

The test module must define `make_pipeline(backend_error: bool = False, return_parts: bool = False)` with fake analyzer, renderer, and backend sink instances; the fake renderer increments `call_count`, the fake backend raises a retryable delivery error when `backend_error` is true, and `return_parts=True` returns the pipeline, renderer, and backend for call-count assertions.

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pipeline.py -q`
Expected: PASS.

### Task 6: AI-FE job service and HTTP endpoints

**Files:**
- Create: `src/detail_page_ai/service.py`
- Create: `src/detail_page_ai/app.py`
- Create: `tests/test_service.py`
- Modify: `pyproject.toml`

**Interfaces:**
- `POST /api/v1/ai/detail-page-jobs`: multipart `product_image`, optional `template_id`, optional `locale`, optional JSON `options`; returns `202` with `job_id`, `request_id`, `status`, and `status_url`.
- `GET /api/v1/ai/detail-page-jobs/{job_id}`: returns `AiFeStatusResponse`.

- [x] **Step 1: Write failing service tests**

```python
def test_submit_returns_queued_job_and_background_work_reaches_completed():
    service, executor = make_service()

    accepted = service.submit(b"png", "image/png", request_id="request-1")
    executor.run_all()
    status = service.get(accepted.job_id)

    assert accepted.status == "QUEUED"
    assert status.status == "COMPLETED"
    assert status.result.generation_id == "generation-1"


def test_failed_job_contains_retryable_error():
    service, executor = make_service(pipeline_error=RuntimeError("gemini down"))

    accepted = service.submit(b"png", "image/png", request_id="request-1")
    executor.run_all()
    status = service.get(accepted.job_id)

    assert status.status == "FAILED"
    assert status.error.retryable is True
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_service.py -q`
Expected: FAIL because the job service does not exist.

- [x] **Step 3: Implement service and FastAPI endpoints**

Use a thread pool/background task for MVP and an in-memory job store. Update status to `ANALYZING`, `RENDERING`, `DELIVERING`, then `COMPLETED` or `FAILED`. Return `404` for unknown jobs and the common error DTO. Keep FE response models separate from AI-BE persistence models. Use a configurable template path and load the reference template once per service instance.

The test module must define `make_service(pipeline_error: Exception | None = None)` with a deterministic fake executor exposing `run_all()`. The executor runs submitted work synchronously when `run_all()` is called so status transitions can be asserted without timing-dependent sleeps.

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_service.py -q`
Expected: PASS.

### Task 7: Configuration, documentation, and verification

**Files:**
- Modify: `pyproject.toml`
- Modify: `docs/phase3/api/ai-dto-contract.md`
- Modify: `docs/phase1/2026-08-26-image-driven-detail-page-design.md`
- Create: `.env.example`
- Create: `README.md`

- [x] **Step 1: Add runtime configuration and commands**

Add `google-genai`, `fastapi`, `uvicorn`, `python-multipart`, `httpx`, `pydantic-settings`, and `pytest` dependencies. Add a `serve-ai` command that runs `uvicorn detail_page_ai.app:app`. Add `.env.example` with `GEMINI_API_KEY`, `GEMINI_ANALYSIS_MODEL`, `GEMINI_IMAGE_MODEL`, `BACKEND_PRODUCT_URL`, `BACKEND_AUTH_TOKEN`, `BACKEND_TIMEOUT_SECONDS`, and `DETAIL_PAGE_TEMPLATE_PATH`.

- [x] **Step 2: Update DTO documentation**

Document that AI-FE final results use `image_base64` for the self-contained MVP when no image store exists, while AI-BE always receives the binary image in multipart. Document that AI-FE and AI-BE delivery have independent retry behavior and share only correlation IDs.

- [x] **Step 3: Run the full test suite**

Run: `pytest -q`
Expected: all tests PASS without requiring `GEMINI_API_KEY` or a live BE endpoint.

- [x] **Step 4: Run static compilation**

Run: `python -m compileall -q src tests`
Expected: exit code 0 with no syntax errors.

- [x] **Step 5: Verify the service contract**

Run: `python -c "from detail_page_ai.app import app; print(sorted(route.path for route in app.routes))"`
Expected: output includes `/api/v1/ai/detail-page-jobs` and `/api/v1/ai/detail-page-jobs/{job_id}`.
