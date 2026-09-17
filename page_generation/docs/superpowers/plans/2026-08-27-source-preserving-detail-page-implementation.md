# Source-Preserving Detail Page Implementation Plan

> 2026-09-08 회고 반영: 이 계획은 HTML 역할 매핑과 원본 보존 구현을 기록한 이력 문서다.
> 현재 FE 구조 출력은 `page_plan`을 서버에서 `react_document` 제한형 JSON AST로 결정적으로
> 변환·검증한 뒤 전달한다. HTML/CSS는 승인 후 PNG 생성용 내부 renderer로만 사용하며,
> 최신 동작·필드 위치는 [AI DTO 계약](../../api/ai-dto-contract.md)을 따른다.
> 본문에 남은 Bedrock 단계·예시는 당시 확장안을 보존한 것이고, 현재 활성 실행 경로는 로컬
> Gemma + Flux2 MLX Serve이며 외부 provider를 호출하지 않는다.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace whole-product image regeneration with a source-pixel-preserving photo pipeline, durable local job/delivery storage, explicit provenance DTOs, and safe HTML role mapping.

**Architecture:** Product analysis remains multimodal, but product photography is split into generated product-free backgrounds and deterministic Pillow composition of source pixels. Assets, jobs, and delivery retries are persisted locally through interfaces backed by the filesystem and SQLite, while S3/SQS/IAM remain deployment boundaries only.

**Tech Stack:** Python 3.13+, FastAPI, Pydantic 2, Pillow, SQLite (`sqlite3`), boto3 Bedrock Runtime, pytest, HTML/CSS, Playwright.

**Spec:** `docs/superpowers/specs/2026-08-27-source-preserving-detail-page-design.md`

## Global Constraints

- Generative models must never generate, repaint, relight, recolor, or transform the product region.
- Product transformations are limited to source crop, translation, uniform scale, and alpha composition.
- A single input image must never produce a guessed side or rear view.
- Every product photo records `asset_mode`, source/cutout/mask hashes, transform, and fidelity status.
- Rejected photos are excluded from HTML and backend multipart payloads.
- Local filesystem and SQLite are the default durable implementations.
- No S3 bucket, SQS queue, IAM role/policy, or Secrets Manager secret is created or deployed.
- Secret values and image/Base64 bytes must not appear in source, examples, or logs.
- Existing FE/BE fields remain compatible while provenance fields are added.
- Tests must follow RED-GREEN-REFACTOR and use deterministic local fixtures.
- The workspace is not a Git repository, so each task ends with a test checkpoint instead of a commit.

---

### Task 1: Secret-Safe Defaults and Dependencies

**Files:**
- Modify: `pyproject.toml`
- Delete and recreate: `.env.example`
- Create: `.gitignore`
- Modify: `src/detail_page_ai/config.py`
- Test: `tests/test_config.py`
- Test: `tests/test_security.py`

**Interfaces:**
- Consumes: Pydantic `BaseSettings` environment loading.
- Produces: `Settings.asset_store_dir: str`, `Settings.sqlite_path: str`, `Settings.response_asset_mode: Literal["base64", "url", "both"]`, `Settings.craft_confidence_threshold: float`, and a Pillow runtime dependency.

- [ ] **Step 1: Write failing configuration and security tests**

```python
def test_source_safe_local_storage_is_default():
    settings = Settings(_env_file=None)
    assert settings.product_photo_generation == "source"
    assert settings.asset_store_dir == ".local/detail-page-ai/assets"
    assert settings.sqlite_path == ".local/detail-page-ai/state.sqlite3"

def test_env_example_contains_placeholders_not_credentials():
    values = parse_env(Path(".env.example"))
    assert values["AWS_ACCESS_KEY_ID"] == ""
    assert values["AWS_SECRET_ACCESS_KEY"] == ""
    assert values["GEMINI_API_KEY"] == ""
```

- [ ] **Step 2: Run the tests and verify they fail because safe settings and files are missing**

Run: `pytest tests/test_config.py tests/test_security.py -q`

Expected: failures for the current Bedrock photo default, missing settings, non-placeholder secrets, and missing ignore rules.

- [ ] **Step 3: Add Pillow, local persistence settings, placeholder-only environment examples, and ignore rules**

```python
product_photo_generation: Literal["gemini", "bedrock", "source"] = Field(
    default="source", alias="PRODUCT_PHOTO_GENERATION"
)
asset_store_dir: str = Field(
    default=".local/detail-page-ai/assets", alias="ASSET_STORE_DIR"
)
sqlite_path: str = Field(
    default=".local/detail-page-ai/state.sqlite3", alias="SQLITE_PATH"
)
response_asset_mode: Literal["base64", "url", "both"] = Field(
    default="base64", alias="RESPONSE_ASSET_MODE"
)
craft_confidence_threshold: float = Field(
    default=0.65, alias="CRAFT_CONFIDENCE_THRESHOLD", ge=0, le=1
)
```

- [ ] **Step 4: Run the focused tests and full configuration regression tests**

Run: `pytest tests/test_config.py tests/test_security.py -q`

Expected: all pass with no credential value printed.

### Task 2: Provenance Models and DTO Contracts

**Files:**
- Modify: `src/detail_page_ai/models.py`
- Modify: `src/detail_page_ai/dto.py`
- Modify: `src/detail_page_ai/backend_client.py`
- Test: `tests/test_dto.py`
- Test: `tests/test_backend_client.py`

**Interfaces:**
- Consumes: existing `ProductPhoto`, FE photo DTO, and BE generated-photo metadata.
- Produces: `PhotoTransform`, `AssetMode`, `FidelityStatus`, provenance fields on all photo contracts, and classification confidence fields on `ProductProfileDto`.

- [ ] **Step 1: Write failing provenance serialization and rejected-asset tests**

```python
def test_photo_provenance_is_shared_by_fe_and_be_contracts():
    photo = source_composite_photo()
    assert photo.product_generated is False
    assert photo.asset_mode == "source_composite"
    assert photo.transform.scale == 0.72

def test_backend_omits_rejected_product_photo():
    image = GeneratedImage(data=b"page", mime_type="image/png", photos=(rejected_photo(),))
    client.persist(make_request(), image)
    assert not any(name.startswith("product_photo_") for name in transport.request["files"])
```

- [ ] **Step 2: Run tests and verify missing model fields and rejected filtering fail**

Run: `pytest tests/test_dto.py tests/test_backend_client.py -q`

Expected: failures identify missing provenance attributes and rejected photo filtering.

- [ ] **Step 3: Implement typed provenance with backward-compatible safe defaults**

```python
@dataclass(frozen=True, slots=True)
class PhotoTransform:
    scale: float = 1.0
    x: int = 0
    y: int = 0
    crop: tuple[int, int, int, int] | None = None

@dataclass(frozen=True, slots=True)
class ProductPhoto:
    # existing fields remain
    asset_mode: Literal["source", "source_crop", "source_composite"] = "source"
    source_asset_id: str | None = None
    source_sha256: str | None = None
    cutout_sha256: str | None = None
    mask_sha256: str | None = None
    background_generated: bool = False
    product_generated: bool = False
    transform: PhotoTransform = PhotoTransform()
    fidelity_status: Literal["VERIFIED", "FALLBACK", "REJECTED"] = "VERIFIED"
```

Add equivalent Pydantic fields to FE and BE metadata. Extend `ProductProfileDto` with `classification_confidence`, `craft_confidence`, `classification_reason`, and `candidate_types`, all with conservative defaults.

- [ ] **Step 4: Filter rejected photos from backend multipart and rerun tests**

Run: `pytest tests/test_dto.py tests/test_backend_client.py -q`

Expected: all pass and existing clients still serialize their prior fields.

### Task 3: Durable Source Asset Store

**Files:**
- Create: `src/detail_page_ai/assets.py`
- Modify: `src/detail_page_ai/ports.py`
- Test: `tests/test_assets.py`

**Interfaces:**
- Produces: `StoredAsset`, `SourceAssetStore.put(data, mime_type, category)`, `get(asset_id)`, `exists(asset_id)`, `MemoryAssetStore`, and `LocalFileAssetStore`.
- Consumes: SHA-256 and MIME validation; no network or AWS SDK.

- [ ] **Step 1: Write failing deduplication, persistence, and traversal-safety tests**

```python
def test_local_store_deduplicates_same_bytes_after_reopen(tmp_path):
    first = LocalFileAssetStore(tmp_path).put(b"same", "image/png", "source")
    second_store = LocalFileAssetStore(tmp_path)
    second = second_store.put(b"same", "image/png", "source")
    assert first.asset_id == second.asset_id
    assert second_store.get(first.asset_id) == b"same"

def test_asset_id_cannot_escape_store(tmp_path):
    with pytest.raises(KeyError):
        LocalFileAssetStore(tmp_path).get("../secret")
```

- [ ] **Step 2: Run tests and verify the store module is absent**

Run: `pytest tests/test_assets.py -q`

Expected: import failure for `detail_page_ai.assets`.

- [ ] **Step 3: Implement content-addressed memory and local stores**

Use `sha256(data).hexdigest()` as the stable asset ID, write bytes under `<root>/<category>/<sha256>.<ext>`, write metadata atomically through a temporary file, and validate IDs with a lowercase 64-character hex pattern before reads.

- [ ] **Step 4: Run store tests and verify restart deduplication**

Run: `pytest tests/test_assets.py -q`

Expected: all pass.

### Task 4: Deterministic Cutout, Composition, and Fidelity Validation

**Files:**
- Create: `src/detail_page_ai/source_photos.py`
- Modify: `src/detail_page_ai/ports.py`
- Test: `tests/test_source_photos.py`

**Interfaces:**
- Consumes: Pillow images, `SourceAssetStore`, `ProductProfileDto`, and optional `BackgroundGenerator.generate(profile, role, width, height) -> bytes`.
- Produces: `ProductCutout`, `SolidBackgroundCutoutExtractor.extract`, `SourcePreservingPhotoComposer.compose`, `ProductFidelityValidator.validate`, and `SourcePreservingProductPhotoGenerator.generate`.

- [ ] **Step 1: Write failing pixel-origin, transform, fallback, and alternate-policy tests**

```python
def test_composite_product_pixels_come_only_from_source():
    source = white_background_fixture_with_patterned_product()
    photos = generator.generate(source_image=source, source_mime_type="image/png", profile=profile, options=options)
    assert_product_pixels_match_source(photos.by_id("hero"), source)

def test_background_generator_never_receives_source_bytes():
    background = RecordingBackgroundGenerator()
    generator = SourcePreservingProductPhotoGenerator(background_generator=background)
    generator.generate(source_image=binary_source, source_mime_type="image/png", profile=profile, options=options)
    assert all("source_image" not in call for call in background.calls)

def test_single_input_never_creates_alternate():
    photos = generator.generate(source_image=source, source_mime_type="image/png", profile=profile, options=options)
    assert "alternate" not in {photo.photo_id for photo in photos.photos}
```

Also cover empty/full-frame masks, complex-background source fallback, deterministic output hashes, in-bounds detail crop, neutral background fallback, and validator rejection when `product_generated=True`.

- [ ] **Step 2: Run tests and verify the source-safe module is absent**

Run: `pytest tests/test_source_photos.py -q`

Expected: import failure for source photo components.

- [ ] **Step 3: Implement mask-only extraction and source-RGB cutout construction**

Decode the source once with Pillow, estimate a corner background color, build alpha from color distance, reject masks with foreground ratios outside `0.01..0.90`, and create RGBA by combining original RGB channels with the generated alpha channel.

- [ ] **Step 4: Implement deterministic role composition**

Create `hero` on `#F7F7F5`, `packshot` on `#FFFFFF`, a bounded source `detail` crop, `lifestyle` on a generated product-free background or neutral fallback, optional `scale`, and `alternate` only from a caller-provided additional source. Use Lanczos uniform scaling without color correction and record every transform and hash.

- [ ] **Step 5: Implement fidelity validation and fallback replacement**

Accept only `source`, `source_crop`, and `source_composite`; require `product_generated=False`; require source hashes; and convert failed generated-background roles to a `source`-mode fallback rather than returning unsafe data.

- [ ] **Step 6: Run source-photo tests, then Pillow-focused regression tests**

Run: `pytest tests/test_source_photos.py -q`

Expected: all pass with deterministic hashes across repeated runs.

### Task 5: Bedrock Product-Free Background Adapter and Explicit HTML Role Mapping

**Files:**
- Modify: `src/detail_page_ai/bedrock_provider.py`
- Modify: `src/detail_page_ai/prompts.py`
- Modify: `src/detail_page_ai/html_renderer.py`
- Test: `tests/test_bedrock_provider.py`
- Test: `tests/test_prompts.py`
- Test: `tests/test_html_renderer.py`

**Interfaces:**
- Consumes: `BedrockSdkClient.generate_background(prompt, model, options)` and safe `ProductPhotoSet`.
- Produces: `BedrockBackgroundGenerator`; explicit `hero`, `packshot`, `detail`, `lifestyle`, and `scale` mappings; no image-to-image path in the default service.

- [ ] **Step 1: Write failing payload and role-mapping tests**

```python
def test_bedrock_background_payload_contains_no_source_image():
    sdk.generate_background(prompt="empty shelf", model="image-model", options=options)
    payload = json.loads(client.invoke_calls[0]["body"])
    assert "image" not in payload

def test_usage_role_uses_lifestyle_not_alternate():
    html = build_detail_page_html(profile, source, photo_set=role_fixture())
    assert lifestyle_data_uri in usage_section(html)
    assert alternate_data_uri not in usage_section(html)
```

- [ ] **Step 2: Run tests and verify old image-to-image behavior and fallback mapping fail**

Run: `pytest tests/test_bedrock_provider.py tests/test_prompts.py tests/test_html_renderer.py -q`

Expected: failures show source image in the Bedrock generation payload and alternate mapped as usage.

- [ ] **Step 3: Add background-only prompts and Bedrock text-to-image request**

The prompt explicitly requests an empty environment with reserved placement space and prohibits products, product-like hero objects, logos, and text. The Bedrock request body contains `prompt`, `negative_prompt`, `output_format`, and `aspect_ratio`, and never contains source bytes.

- [ ] **Step 4: Replace implicit HTML substitutions with explicit role resolution**

Resolve each role independently from verified/fallback photos, otherwise use the source. Detail grids use only `detail` or source; usage uses only `lifestyle` or source; scale uses only `scale` or source. Remove alternate from all default single-image mappings.

- [ ] **Step 5: Run provider, prompt, and renderer tests**

Run: `pytest tests/test_bedrock_provider.py tests/test_prompts.py tests/test_html_renderer.py -q`

Expected: all pass and no test expects model-generated product pixels.

### Task 6: SQLite Job Repository and Delivery Outbox

**Files:**
- Create: `src/detail_page_ai/persistence.py`
- Modify: `src/detail_page_ai/pipeline.py`
- Modify: `src/detail_page_ai/service.py`
- Modify: `src/detail_page_ai/dto.py`
- Test: `tests/test_persistence.py`
- Test: `tests/test_pipeline.py`
- Test: `tests/test_service.py`

**Interfaces:**
- Produces: `JobRecord`, `SQLiteJobRepository`, `MemoryJobRepository`, `OutboxRecord`, `SQLiteDeliveryOutbox`, and `MemoryDeliveryOutbox`.
- Consumes: `AiFeResultDto`, `ErrorDto`, `AiBeProductPersistRequest`, and full generated image bytes plus child assets.

- [ ] **Step 1: Write failing restart-recovery and idempotency tests**

```python
def test_job_survives_repository_reopen(tmp_path):
    first = SQLiteJobRepository(tmp_path / "state.sqlite3")
    first.create(job_record())
    second = SQLiteJobRepository(tmp_path / "state.sqlite3")
    assert second.get("job-1").request_id == "request-1"

def test_pending_delivery_retries_after_reopen_without_rendering(tmp_path):
    first_pipeline.run(...)
    second_pipeline = pipeline_with_outbox(SQLiteDeliveryOutbox(db_path), backend=healthy_backend)
    ack = second_pipeline.retry_backend_delivery("generation-1")
    assert ack.status == "SAVED"
    assert analyzer.calls == 1
    assert renderer.calls == 1
```

- [ ] **Step 2: Run persistence, pipeline, and service tests and verify missing repositories fail**

Run: `pytest tests/test_persistence.py tests/test_pipeline.py tests/test_service.py -q`

Expected: import and restart recovery failures.

- [ ] **Step 3: Implement SQLite schema and JSON/Base64 serialization**

Create tables with `CREATE TABLE IF NOT EXISTS`: jobs keyed by `job_id`, and delivery_outbox keyed by `generation_id`. Use parameterized SQL, UTC ISO timestamps, Pydantic JSON for DTOs, Base64 only inside the SQLite payload for binary child assets, and transactional upserts for idempotency.

- [ ] **Step 4: Replace in-memory pipeline retry storage with the outbox interface**

On backend failure, enqueue one record keyed by `generation_id`. Retry reads the persisted request/image, performs one backend call, and marks delivered. A repeated enqueue updates failure metadata without duplicating the generation.

- [ ] **Step 5: Replace service `_jobs` dictionary with `JobRepository`**

Persist each status transition. Recover interrupted states (`ANALYZING` through `DELIVERING`) as `QUEUED` on startup, and expose the actual stage sequence through the expanded status literal.

- [ ] **Step 6: Run persistence and workflow tests**

Run: `pytest tests/test_persistence.py tests/test_pipeline.py tests/test_service.py -q`

Expected: all pass, including a repository/outbox reopen.

### Task 7: Pipeline, Multi-Source Input, Craft Trigger, and Asset Responses

**Files:**
- Modify: `src/detail_page_ai/pipeline.py`
- Modify: `src/detail_page_ai/service.py`
- Modify: `src/detail_page_ai/app.py`
- Modify: `src/detail_page_ai/ports.py`
- Modify: `src/detail_page_ai/dto.py`
- Test: `tests/test_pipeline.py`
- Test: `tests/test_service.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `additional_source_images: tuple[tuple[bytes, str], ...]`, `SourceAssetStore`, source-safe generator, craft confidence threshold, and response asset mode.
- Produces: optional multipart `product_images`, source asset IDs in BE metadata, URL-preferred FE assets when the store supports URLs, and stage callbacks.

- [ ] **Step 1: Write failing tests for craft confidence, additional originals, stage order, and response mode**

```python
def test_craft_confidence_can_trigger_research_without_boolean():
    profile = minimal.model_copy(update={"craft_confidence": 0.91, "candidate_types": ["나전칠기"]})
    pipeline.run(...)
    assert researcher.call_count == 1

def test_alternate_uses_only_second_uploaded_original():
    result = pipeline.run(..., additional_source_images=((side_png, "image/png"),))
    assert result.fe_result.detail_page.photos_by_id["alternate"].product_generated is False
```

- [ ] **Step 2: Run workflow tests and verify signatures and trigger behavior fail**

Run: `pytest tests/test_pipeline.py tests/test_service.py tests/test_app.py -q`

Expected: failures for absent multi-source arguments, confidence trigger, and status callback.

- [ ] **Step 3: Thread additional originals and asset metadata through API to generator**

Keep `product_image` as primary. Accept optional repeated `product_images`; validate each file; pass them as immutable `(bytes, MIME)` pairs; and create `alternate` only from those bytes.

- [ ] **Step 4: Add craft trigger policy and conservative classification copy support**

Research when the boolean is true, confidence meets the configured threshold, or a candidate/keyword matches the craft dictionary (`나전`, `칠기`, `한지`, `도자`, `옻칠`, `자개`, `공예`). Do not use search results to assert this particular item's authenticity or process.

- [ ] **Step 5: Persist source/page/section/photo assets and build FE response by configured mode**

Return Base64 for `base64`, a store URL for `url`, and both for `both`. Do not duplicate Base64 fields when URL mode is selected. Always include provenance metadata for product photos.

- [ ] **Step 6: Run API and pipeline tests**

Run: `pytest tests/test_pipeline.py tests/test_service.py tests/test_app.py -q`

Expected: all pass.

### Task 8: Service Wiring, Documentation, and End-to-End Verification

**Files:**
- Modify: `src/detail_page_ai/app.py`
- Modify: `README.md`
- Modify: `docs/api/ai-dto-contract.md`
- Modify: `docs/operations/bedrock-provider.md`
- Test: `tests/test_app.py`
- Test: `tests/test_pipeline.py`
- Test: `tests/test_html_renderer.py`

**Interfaces:**
- Consumes: all components from Tasks 1-7.
- Produces: a runnable local default service with source-safe photos, filesystem assets, SQLite state/outbox, HTML rendering, and optional Bedrock product-free backgrounds.

- [ ] **Step 1: Write failing service wiring test**

```python
def test_build_service_uses_source_safe_generator_and_durable_local_adapters(monkeypatch, tmp_path):
    service = build_service_with_paths(tmp_path)
    assert isinstance(service.pipeline.photo_generator, SourcePreservingProductPhotoGenerator)
    assert isinstance(service.repository, SQLiteJobRepository)
    assert isinstance(service.pipeline.outbox, SQLiteDeliveryOutbox)
```

- [ ] **Step 2: Run wiring test and verify old Bedrock product generator is still selected**

Run: `pytest tests/test_app.py -q`

Expected: failure until the source-safe generator is wired.

- [ ] **Step 3: Wire local durable adapters and optional background provider**

`PRODUCT_PHOTO_GENERATION=source` creates the deterministic generator. When Bedrock credentials/role access are available, it may receive `BedrockBackgroundGenerator`; otherwise it uses neutral backgrounds. Whole-product Gemini/Bedrock generators and generated final-page renderers are removed from the production modules.

- [ ] **Step 4: Update operator and DTO documentation**

Document local directories, SQLite recovery, photo provenance, multi-source behavior, safe fallback, credential rotation, and the explicit exclusion of actual S3/SQS/IAM/Secrets Manager provisioning.

- [ ] **Step 5: Run the complete automated suite**

Run: `pytest -q`

Expected: all tests pass with no failures and no secret values in output.

- [ ] **Step 6: Run syntax compilation and HTML render smoke test**

Run: `python3 -m compileall -q src scripts`

Run: `npm run render:detail-page`

Expected: compilation exits 0; the render command creates a full page and ordered section images using source-safe product photos.

- [ ] **Step 7: Inspect generated smoke assets for source fidelity**

Compare the product pixels in hero, packshot, detail, and lifestyle outputs against the original fixture using the validator and visually inspect the long page. Record whether each cut is `VERIFIED` or `FALLBACK`; no cut may be `REJECTED` in the delivered page.

## Self-Review

- Spec coverage: Tasks 1-8 cover security, provenance, source assets, cutout/composition, background-only Bedrock, explicit HTML roles, SQLite jobs/outbox, multi-source input, craft confidence, response mode, documentation, and verification.
- Placeholder scan: every implementation step names concrete files, APIs, behavior, and commands; no unfinished marker remains.
- Type consistency: `ProductPhoto` is the source of provenance for FE metadata, BE metadata, renderer filtering, asset persistence, and outbox serialization. `generation_id` remains the BE idempotency and outbox key. `additional_source_images` uses the same immutable tuple form from API through service and pipeline.
