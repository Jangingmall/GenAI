# Detail Page Draft-to-PNG Flow Hardening Implementation Plan

> 2026-09-08 회고 반영: 이 계획의 “editable HTML draft” 표현은 당시 설계 기록이다.
> 현재 초안의 FE 구조 출력은 `react_document` 제한형 JSON AST이며 `page_plan`은 모델·편집·
> 하위 호환 입력으로 유지한다. HTML/CSS는 승인 후 PNG renderer에서만 사용한다. 최신 계약은
> [AI DTO 계약](../../phase3/api/ai-dto-contract.md)과 [FE 입출력 명세](../../phase3/api/ai-fe-io-spec.md)를 따른다.
> 본문에 남은 Gemini/Bedrock 조건·파일 목록은 당시 계획 이력이며, 현재 활성 provider는 로컬
> Gemma + Flux2 MLX Serve뿐이다.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal (historical wording reconciled):** Make the detail-page service produce an editable structured draft and validated `react_document` first, then render source-safe product assets and final PNG only after creator approval, with durable idempotency, retry, limits, and safety checks.

**Architecture (historical wording reconciled):** The create-job path performs image analysis and builds a structured draft/page plan plus the server-generated `react_document` using the original image references. It persists the draft and source input without invoking the PNG renderer or background generation. The approval path resolves the stored draft, applies creator edits while preserving profile facts, rebuilds/validates the React AST, generates source-safe photo roles, renders full/section PNGs through the internal HTML/CSS renderer, and delivers one idempotent multipart result to Product BE.

**Tech Stack:** Python 3.13+, FastAPI, Pydantic v2, SQLite, Pillow, Playwright, vanilla browser JavaScript, pytest.

**Spec:** `docs/common/ai-architecture-and-safety.md`, `docs/phase3/api/ai-dto-contract.md`, and the approved design in the preceding task conversation.

## Global Constraints

- Approval is the only operation allowed to invoke the final PNG/section renderer.
- Original product RGB pixels remain immutable; derived photos use source, source crop, or source composite provenance.
- Product BE identity and an idempotency key are mandatory on internal production requests.
- Legacy `/api/v1/ai/*` endpoints remain local-demo compatible but are disabled unless explicitly enabled.
- Per-image, total-image-count, and total-request-byte limits are enforced server-side.
- Unsupported or ungrounded product claims never enter rendered feature copy.
- Bedrock is not constructed or called when the configured analysis/photo background provider is Gemini-only.
- Every behavior change gets a failing test before production code is changed.

### Task 1: Add draft-first DTOs and persisted draft state

**Files:**
- Modify: `src/detail_page_ai/dto.py`
- Modify: `src/detail_page_ai/ai_dto.py`
- Modify: `src/detail_page_ai/persistence.py`
- Modify: `src/detail_page_ai/pipeline.py`
- Modify: `src/detail_page_ai/service.py`
- Test: `tests/test_draft_flow.py`
- Test: `tests/test_persistence.py`

**Interfaces:**
- Add `AiFeDraftDto`/draft result containing `draft_id`, `generation_id`, editable structured `draft`, `react_document`, and source metadata.
- Add `AiFeDraftResponse` and make create-job completion return a draft without `detail_page.image_base64`.
- Add `DetailPagePipeline.create_draft(...) -> DraftPipelineResult` and `DetailPagePipeline.render_approved_draft(...) -> PipelineResult`.
- Persist the profile, draft, HTML, source bytes, and product/source identities under a stable draft ID.

- [ ] Write a test proving create-job runs analysis and structured draft/React JSON generation but never invokes `DetailPageRenderer` or background generation.
- [ ] Run the focused test and observe failure because `DetailPagePipeline.run()` always renders PNG.
- [ ] Write a test proving approval uses the stored profile and returns PNG assets.
- [ ] Run the focused approval test and observe failure because no draft repository/result contract exists.
- [ ] Implement the minimal draft DTO, repository serialization, draft pipeline method, and approval method.
- [ ] Run focused draft-flow and persistence tests.

### Task 2: Connect the real browser preview and persist edits

**Files:**
- Modify: `src/detail_page_ai/app.py`
- Modify: `src/detail_page_ai/fe_dto.py`
- Modify: `web/ai_input.js`
- Modify: `web/ai_draft_preview.html`
- Modify: `web/ai_draft_preview.js`
- Modify: `web/ai_draft_preview.css`
- Test: `tests/test_ai_internal_app.py`
- Test: `scripts/browser/test_input_page.mjs`
- Test: `scripts/browser/test_draft_preview.mjs`

**Interfaces:**
- Add internal draft status response containing editable structured draft, `react_document`, and approved-draft metadata.
- Add local demo route/query support for `job_id` and draft loading.
- Add `POST /internal/v1/ai/detail-page-drafts/{draft_id}` to save the current draft with optimistic version checking.
- Approval sends `draft_id`, `approval_id`, edited draft, and source identity; it does not re-upload the source when the Product BE has already submitted it.

- [ ] Add browser/API tests proving the preview loads returned AI content instead of hardcoded sample text.
- [ ] Run them and observe failure because the page currently hardcodes `draft` and `imageUrl`.
- [ ] Add save-draft tests for version conflict and persisted content.
- [ ] Implement draft loading/saving and approval payload wiring.
- [ ] Run both browser scripts and focused API tests.

### Task 3: Make approval idempotent and preserve research context

**Files:**
- Modify: `src/detail_page_ai/ai_dto.py`
- Modify: `src/detail_page_ai/dto.py`
- Modify: `src/detail_page_ai/persistence.py`
- Modify: `src/detail_page_ai/service.py`
- Modify: `src/detail_page_ai/app.py`
- Test: `tests/test_idempotency.py`
- Test: `tests/test_ai_dto.py`

**Interfaces:**
- Require `idempotency_key` on internal create and approval requests.
- Return the existing accepted/completed response for repeated keys with the same product ID and reject conflicting payloads.
- Use the same approval generation ID for retries and BE `Idempotency-Key` delivery.
- Merge creator-edited copy into the stored profile without dropping `is_traditional_craft`, `craft_research`, safety notes, or verified facts.

- [ ] Write tests for duplicate create, duplicate approval, conflicting idempotency payload, and research preservation.
- [ ] Run them and observe failure because each request currently creates a new UUID and `ApprovedDraftDto.to_profile()` discards research.
- [ ] Implement idempotency records and profile merge behavior.
- [ ] Run focused idempotency/DTO tests and the full Python suite.

### Task 4: Produce distinct source-safe detail cuts and enforce input limits

**Files:**
- Modify: `src/detail_page_ai/source_photos.py`
- Modify: `src/detail_page_ai/validation.py`
- Modify: `src/detail_page_ai/app.py`
- Modify: `src/detail_page_ai/config.py`
- Test: `tests/test_source_photos.py`
- Test: `tests/test_validation.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Generate multiple deterministic detail crops from separate visible source regions when the primary image has enough foreground area; fall back to the one safe crop when it does not.
- Make gallery and split sections consume the distinct crop set.
- Pass configured `MAX_IMAGE_BYTES`, enforce maximum 12 images and total request bytes, and validate actual decodability before model calls.
- Make `PRODUCT_PHOTO_SHOTS` explicit and ensure scale is either filled or omitted consistently.

- [ ] Add tests asserting distinct crop hashes for multi-region sources, repeated-gallery absence, configured byte limits, count limits, and scale-role behavior.
- [ ] Run the focused tests and observe failure with the current single `detail` crop and hardcoded validator limit.
- [ ] Implement deterministic crop selection, limits, and safe fallback.
- [ ] Run source-photo, validation, and app tests.

### Task 5: Enforce safety, provider selection, queue capacity, and BE retry

**Files:**
- Modify: `src/detail_page_ai/bedrock_provider.py`
- Modify: `src/detail_page_ai/gemini_provider.py`
- Modify: `src/detail_page_ai/dto.py`
- Modify: `src/detail_page_ai/pipeline.py`
- Modify: `src/detail_page_ai/service.py`
- Modify: `src/detail_page_ai/persistence.py`
- Modify: `src/detail_page_ai/app.py`
- Modify: `.env.example`
- Test: `tests/test_safety.py`
- Test: `tests/test_service.py`
- Test: `tests/test_gemini_provider.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Filter non-image-visible features from rendered selling copy and move them to warnings.
- Accept only HTTPS research sources from grounded metadata and store retrieval time.
- Construct a background provider only when explicitly configured; support a no-background Gemini path.
- Enforce active-job capacity and schedule bounded exponential BE delivery retries after runtime failures.
- Add `ENABLE_LEGACY_DEMO_API=false`, configurable CORS origins, and fail closed for production routes.

- [ ] Add tests for evidence filtering, HTTPS source validation, Gemini-only service wiring, runtime retry scheduling, queue capacity, and legacy-route gating.
- [ ] Run the focused tests and observe failure against current behavior.
- [ ] Implement provider wiring, safety filters, retry scheduling, capacity checks, and route gating.
- [ ] Run focused provider/service/security tests.

### Task 6: Reduce binary duplication and complete operations documentation

**Files:**
- Modify: `src/detail_page_ai/pipeline.py`
- Modify: `src/detail_page_ai/backend_client.py`
- Modify: `src/detail_page_ai/persistence.py`
- Modify: `docs/phase3/api/ai-dto-contract.md`
- Modify: `docs/phase3/api/ai-fe-io-spec.md`
- Modify: `README.md`
- Modify: `docs/phase4/operations/local-llm.md`
- Modify: `docs/internal/sglang-vllm-fit.md`
- Test: `tests/test_backend_client.py`

**Interfaces:**
- Internal draft responses carry structured draft/`react_document`/profile metadata, not final binary assets.
- Final internal approval responses return references and ACK while AI→BE multipart remains the binary delivery channel.
- URL mode is explicit: no silent base64 fallback when a URL-capable store is required.
- Document that FLUX/ComfyUI and vLLM/SGLang are not wired into the current production path unless their adapters are configured.

- [ ] Add tests for response asset mode and internal response payload size/content.
- [ ] Run focused backend-client tests and observe current base64 duplication.
- [ ] Implement explicit asset transport behavior and update docs.
- [ ] Run documentation consistency checks.

### Task 7: Full verification

**Files:**
- Test: all `tests/`
- Test: `scripts/browser/test_input_page.mjs`
- Test: `scripts/browser/test_draft_preview.mjs`

- [ ] Run `./.venv/bin/pytest -q`.
- [ ] Run `./.venv/bin/python -m compileall -q src scripts tests`.
- [ ] Run `npm run test:input-page` and `npm run test:draft-preview`.
- [ ] Run a no-credential configuration smoke check without printing secret values.
- [ ] Inspect changed files for original-image mutations and secret leakage.
- [ ] Report remaining deployment-only boundaries: Product BE endpoint, S3/SQS/IAM, and external model credentials.
