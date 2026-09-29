# FE-BE-AI-BE-FE Contract Implementation Plan

> 2026-09-08 회고 반영: 이 계획은 Product BE 게이트웨이·multipart·상태 계약의 구현 이력이다.
> 현재 구조 출력은 `draft.react_document`, `result.detail_page.react_document`,
> `detail_page.react_document`(AI→BE metadata)로 전달되는 schema v2.0 제한 AST다. `page_plan`은
> 호환 입력이며 임의 HTML/JSX/CSS를 FE에 전달하지 않는다. 최신 필드는
> [AI DTO 계약](../../phase3/api/ai-dto-contract.md)을 따른다.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the production detail-page flow behind Product BE and expose explicit, validated DTOs for Product BE→AI and AI→Product BE communication while keeping the local direct-AI demo working.

**Architecture:** Product BE owns the FE-facing product workflow, forwards a multipart request with a JSON metadata part to AI, and receives/polls AI results. AI stores `product_id` and the upstream `source_asset_id` with every job, returns an editable structured draft plus validated `react_document`, renders the final PNG only after approval through the internal HTML/CSS renderer, then delivers a multipart persistence request to Product BE through the existing outbox. Legacy `/api/v1/ai/*` routes remain available only for local compatibility.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, SQLite job repository/outbox, pytest, existing HTML/CSS renderer.

**Spec:** `docs/common/ai-architecture-and-safety.md` and `docs/phase3/api/ai-dto-contract.md`

## Global Constraints

- FE must use Product BE as its production gateway; direct FE→AI routes are demo/compatibility routes only.
- Original product pixels are immutable; `hero`/`packshot`/대표 `detail`은 source-preserving 자산으로 유지한다. 생성 `lifestyle`/추가 `detail` 참고 자산은 `product_generated=true`, `GENERATED`로 표시하고 상품 근거로 승격하지 않는다.
- Final detail-page output and section assets use `image/png`.
- AI never writes Product DB directly; AI sends metadata and files to Product BE with an idempotency key.
- Internal AI routes fail closed when `AI_INTERNAL_AUTH_TOKEN` is not configured.
- Existing public imports and local browser tests must remain compatible.

### Task 1: Add canonical direction-specific DTO contracts

**Files:**
- Create: `src/detail_page_ai/ai_dto.py`
- Modify: `src/detail_page_ai/dto.py`
- Modify: `src/detail_page_ai/fe_dto.py`
- Modify: `src/detail_page_ai/__init__.py`
- Test: `tests/test_ai_dto.py`

**Interfaces:**
- Produces `ProductBeToAiCreateJobRequestDto`, `ProductBeToAiApproveDraftRequestDto`, `AiToProductBeAcceptedResponseDto`, `AiToProductBeStatusResponseDto`, `AiToProductBeApprovedResponseDto`, `AiToProductBePersistRequestDto`, and `ProductBeToAiPersistAckDto`.
- Preserves `AiBeProductPersistRequest.from_profile(...)` callers that do not provide `product_id`.

- [x] Write validation and serialization tests for required `product_id`, forbidden extra fields, nested `options`, approved draft, and AI→BE response fields.
- [x] Run `pytest tests/test_ai_dto.py -q` and confirm the new module/types fail before implementation.
- [x] Implement the canonical DTO module and add optional shared `product_id` to the existing persistence request.
- [x] Add FE↔Product BE naming aliases in `fe_dto.py` and package exports.
- [x] Run the focused DTO tests and the existing DTO/FE DTO tests.

### Task 2: Preserve product identity through jobs, pipeline, and outbox

**Files:**
- Modify: `src/detail_page_ai/persistence.py`
- Modify: `src/detail_page_ai/service.py`
- Modify: `src/detail_page_ai/pipeline.py`
- Test: `tests/test_service.py`
- Test: `tests/test_pipeline.py`
- Test: `tests/test_persistence.py`

**Interfaces:**
- `DetailPageJobService.submit(..., product_id=None, source_asset_id=None, status_path_prefix=...)` stores both identities.
- `DetailPagePipeline.run(..., product_id=None, source_asset_id=None)` writes them into `AiBeProductPersistRequest`.
- `DetailPageJobService.get_backend(job_id)` returns the canonical Product BE status DTO and rejects legacy jobs without `product_id`.

- [x] Add tests proving product and source asset IDs survive memory/SQLite serialization, recovery, worker execution, and outbox replay.
- [x] Run those tests and confirm they fail because the current records/pipeline do not carry the IDs.
- [x] Add fields with backward-compatible defaults, serialize them, and pass them through the worker/pipeline/backend payload.
- [x] Implement the backend-shaped status projection without adding Product BE-only fields to the FE response.
- [x] Run service, pipeline, persistence, and backend-client tests.

### Task 3: Add authenticated Product BE→AI internal routes

**Files:**
- Modify: `src/detail_page_ai/config.py`
- Modify: `.env.example`
- Modify: `src/detail_page_ai/app.py`
- Test: `tests/test_app.py`
- Test: `tests/test_security.py`

**Interfaces:**
- `POST /internal/v1/ai/detail-page-jobs` accepts `product_image`, repeated `product_images`, `metadata`, and `X-AI-Internal-Token`; returns `AiToProductBeAcceptedResponseDto`.
- `GET /internal/v1/ai/detail-page-jobs/{job_id}` returns `AiToProductBeStatusResponseDto`.
- `POST /internal/v1/ai/detail-page-renders` accepts the approved-draft metadata and images; returns `AiToProductBeApprovedResponseDto`.
- Existing `/api/v1/ai/*` handlers remain callable for the local demo and are not made to require the internal token.

- [x] Add tests for correct-token acceptance, missing/mismatched token rejection, missing configuration fail-closed behavior, product ID forwarding, and approved-draft product ID forwarding.
- [x] Run the focused app/security tests and confirm the internal routes/auth fail before implementation.
- [x] Add the setting, auth helper, shared multipart parsing helpers, and the three internal routes.
- [x] Keep error responses generic so provider credentials and internal URLs never reach callers.
- [x] Run the app/security tests and the existing direct-route tests.

### Task 4: Rewrite the API documents around the new ownership boundaries

**Files:**
- Modify: `docs/phase3/api/ai-dto-contract.md`
- Modify: `docs/phase3/api/ai-fe-io-spec.md`
- Modify: `docs/common/ai-architecture-and-safety.md`
- Modify: `README.md`
- Modify: `docs/README.md`

**Interfaces:**
- Documents Product BE-owned FE contracts separately from Product BE→AI and AI→Product BE contracts.
- Includes canonical multipart field names, authentication, status/polling behavior, PNG delivery, and a migration note for direct demo routes.

- [x] Replace direct FE→AI wording with the production FE→Product BE→AI flow and add matching JSON examples.
- [x] Document canonical DTO Python import paths and the internal token requirement without exposing any secret value.
- [x] Add the local demo compatibility note and update the project API map.
- [x] Run documentation contract checks and scan for stale statements that FE calls AI in production.

### Task 5: Full verification and regression check

**Files:**
- Test: all existing `tests/`
- Test: `scripts/browser/test_input_page.mjs`
- Test: `scripts/browser/test_draft_preview.mjs`

- [x] Run `pytest -q` from the repository root.
- [x] Run `npm run test:input-page` and `npm run test:draft-preview`.
- [x] Inspect the final diff and verify no credentials, generated caches, or original-image mutations were introduced.
- [x] Report the exact test counts and the production integration boundary.
