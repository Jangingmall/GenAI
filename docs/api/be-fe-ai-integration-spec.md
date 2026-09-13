# BE/FE 연동 입출력·API·화면 반영 명세

## 2026-09-10 구현 대조 갱신 및 계약 통합 (최신)

이 절은 본문과 충돌할 때 우선한다. 공개 상품 BE API는 이 저장소에 구현되지 않았으며, 다음 경로는 팀 합의용 제안이다.
실제 AI 서버의 구현은 상품 BE 연동용 내부 API(`/internal/v1/ai/...`)와 로컬 개발·검증용 직접 API(`/api/v1/ai/...`)로 구성된다.

### 엔드포인트 계층 비교

| 역할 및 계층 | 경로 패턴 | 인증 및 헤더 | 설명 |
|---|---|---|---|
| **상품 BE 공개 제안** | `POST/GET/PUT /api/v1/products/{product_id}/...` | 사용자 세션/쿠키 | 사용자 및 상품 소유권 검증 후 내부 AI 호출 |
| **AI 내부 API (운영)** | `POST/GET/PUT /internal/v1/ai/...` | `X-AI-Internal-Token` (필수)<br>`Idempotency-Key` (선택) | 상품 BE ↔ AI 서버 간 통신 전용 엔드포인트 |
| **AI 직접 데모 (로컬)** | `POST/GET/PUT /api/v1/ai/...` | 없음 (`ENABLE_LEGACY_DEMO_API=true` 필요) | 상품 BE가 없는 단독 로컬 브라우저 개발·테스트 전용 |

| 공개 경로 제안 | 요청 | 응답 |
|---|---|---|
| POST /api/v1/products/{product_id}/detail-page-jobs | multipart 이미지·상품 문구 | 202, job_id/request_id/status/status_url |
| GET /api/v1/products/{product_id}/detail-page-jobs/{job_id} | 없음 | 200, progress/draft/result/error |
| PUT /api/v1/products/{product_id}/detail-page-jobs/{job_id}/draft | version + 완전한 draft JSON | 200, 최신 draft/version |
| POST /api/v1/products/{product_id}/detail-page-jobs/{job_id}/approve | 승인 draft + request_id | 200, result/backend_delivery_pending |

상품 BE는 사용자 인증과 상품/job 소유권을 검증하고 내부 status_url을 공개 경로로 바꾼다.
FE는 공개 job 식별자를 유지할 수 있다. source_asset_id와 내부 토큰은 상품 BE에서 관리한다.
인증 방식·공개 오류 envelope·승인 장시간 timeout 처리는 상품 BE 팀 합의가 필요하다.

- 작품명·제작 과정은 현재 샘플 UI에서 필수지만 AI DTO에서는 선택이다.
- 내부 metadata.idempotency_key는 필수다. 헤더만 보내는 방식은 현재 허용되지 않으며 헤더를 추가하면 본문과 일치해야 한다.
- GET status의 허용 enum에는 COMPLETED_WITH_BACKEND_PENDING이 없다. 이 값은 승인 응답 전용이다.
  GET COMPLETED만으로 BE 저장·게시 완료를 판단하지 않는다.
- 승인 POST는 동기 응답이며 비동기 202 렌더 작업 API가 아니다.
- 내부 승인 시 저장된 원본을 재사용한다. 현재 주 서비스는 전달된 이미지로 원본을 교체하지 않는다.
- 저장 version은 DTO에서는 선택이지만 공개 계약에서는 필수로 제안한다.
  경로 job_id가 저장 대상을 결정하고 본문의 draft_id 일치 검사는 현재 구현되지 않았다.
- 잘못된 JSON body/필수 multipart 파트 누락에는 FastAPI 422도 발생한다.
- 본문의 빈 draft/product 객체 예시는 구조 축약이며 그대로 보내면 유효한 요청이 아니다.
  실제 draft 필수 필드는 6절을 따른다.
- 순차 승인 재전송은 결과를 재사용한다. 동시 승인 단일 생성 보장은 추가 검증이 필요하다.

### 화면 반영 점검 결과

문구 편집은 draft 최상위 필드와 page_plan 블록 문구를 함께 동기화해야 한다.
현재 데모는 page_plan이 있으면 블록 문구를 우선 사용하므로 최상위 필드 수정이 미리보기에 반영되지 않을 수 있다.
데모의 “자동 저장됨”은 서버 저장을 의미하지 않는다. PUT 성공 시에만 저장 완료로 표시해야 한다.
데모 승인 코드는 고정 샘플 이미지를 전송하므로 운영 원본 연동의 검증 근거로 사용할 수 없다.
저장 409 시 로컬 편집을 보존하고 최신 서버 버전과 비교하며 자동 덮어쓰지 않는다.
승인 중 편집/중복 승인 제한, 새로고침 후 job 복원, polling 중단·timeout 안내는 운영 FE에서 검증한다.
최종 PNG 생성 후에도 상품 BE 적재 확인과 게시 승인을 별도로 거쳐야 한다.

### AI → BE 적재

BACKEND_PRODUCT_URL로 metadata, detail_page_image, detail_page_section_NN,
product_photo_NN을 보낸다. Idempotency-Key는 generation_id이며 설정 시 Bearer 내부 토큰을 사용한다.
상품 BE는 generation_id에 유일 제약을 두고 파일·metadata 저장 완료 후
generation_id/product_id/status(SAVED 또는 ALREADY_SAVED)/saved_at을 ACK로 반환한다.
응답 유실 재시도는 같은 결과로 처리한다. 상품 BE의 실제 트랜잭션 구현은 별도 범위다.

## 1. 문서 목적

본 문서는 AI 상세페이지 생성 기능의 상품 FE, 상품 BE, AI 서버 간 연동 계약을 정의한다.
현재 구현과 DTO를 기준으로 작성했으며, 실제 상품 BE의 공개 URL·인증·DB 스키마는 상품 BE 팀의 책임 범위다.

## 2. 시스템 경계와 책임

```text
FE → 상품 BE → AI API
FE ← 상품 BE ← AI API
             └─ 생성 결과 적재
```

| 영역 | 책임 |
|---|---|
| 상품 FE | 이미지·상품 정보 입력, 작업 상태 표시, draft 편집, 미리보기, 승인 요청 |
| 상품 BE | 사용자 인증, 상품·원본 자산 식별, 공개 API 제공, AI 내부 API 호출, 결과 저장·게시 |
| AI 서버 | 이미지 분석, 구조화된 draft 생성, 승인 후 PNG 렌더링, 생성 결과 및 메타데이터 전달 |

FE는 AI 서버를 직접 호출하지 않는다. `X-AI-Internal-Token`, AI provider 정보, AI 내부 URL은 FE에 노출하지 않는다.

## 3. 처리 흐름

```text
1. FE가 이미지·작품 정보를 상품 BE에 전달
2. 상품 BE가 product_id/source_asset_id를 추가해 AI에 초안 생성 요청
3. AI가 202 응답으로 job_id를 반환하고 비동기 처리
4. 상품 BE가 상태를 polling하고 DRAFT_READY draft와 `react_document`를 FE에 전달
5. FE가 JSON draft를 편집하고 상품 BE에 저장하며, 상품 BE는 최신 `react_document`를 함께 반환
6. 사용자가 승인하면 상품 BE가 승인 draft를 AI에 전달
7. AI가 승인 draft에서 `react_document`를 조립·검증하고, HTML/CSS + Playwright로 전체 PNG·섹션 PNG를 생성
8. AI가 생성 결과와 `react_document`를 상품 BE에 multipart metadata로 적재
9. 상품 BE가 PNG·JSON 결과를 상품 상세페이지와 게시 대기 화면에 반영
```

초안 생성 단계에서는 최종 PNG나 배경·제품 사진 생성을 수행하지 않는다. 승인 이후에만 최종 렌더링을 수행한다.

### 3.1 React JSON 전달

AI가 FE에 전달하는 **정식 구조 산출물(Canonical Structural Artifact)은 `react_document`**다.
초안 응답에서는 `draft.react_document`, 최종 결과에서는 `result.detail_page.react_document`,
AI→BE 적재 metadata에서는 `detail_page.react_document`에 위치한다.

이 문서는 다음 핵심 규격을 준수한다:
- `schemaVersion`: `"2.0"` (고정 버전)
- `canvasWidth`: `774` (고정 캔버스 가로 너비 px)
- `root[]`: 제한된 시맨틱 태그(`section`, `div`, `h1`, `h2`, `p`, `span`, `img` 등), 구조화 props, 재귀 children으로 구성된 AST 노드 배열
- **자산 참조 (`props.imageId`)**: 문서 내의 모든 이미지 노드는 실제 외부 URL이나 거대 Base64 문자열 대신 `props.imageId`로 사진 자산(`photos[]`의 `photo_id`)을 논리적으로 참조한다. 실제 이미지 URL 매핑 및 CDN 해석은 상품 BE 및 FE의 책임이다.
- **실행 보안**: HTML/CSS 문자열, 임의 JSX, JavaScript 함수, 이벤트 핸들러, `dangerouslySetInnerHTML` 등 실행 가능 필드는 전면 차단된다.

`draft.page_plan`은 LLM의 카피·블록 기획 추론 유도, 크리에이터의 블록 단위 텍스트 편집, 기존 레거시 소비자 하위 호환을 위해 보조적으로 함께 전달될 뿐이며, **FE 화면 렌더링의 정본은 항상 `react_document`**다.

`page_plan`의 각 블록 `variant`는 `block_type`별 코드 고정 배정값이 아니다. 이미지 SHA-256으로 선택된 layout 원형이 페이지 구성 순서를 정하고, 모델이 제품의 시각적 특성과 근거에 맞춰 블록별 variant를 채운다. `PageBlockVariant`의 허용값은 `paper`, `light`, `sand`, `dark`, `image-left`, `image-right`, `full-bleed`, `compact`다. 코드의 페이지 계획 보정은 비어 있는 일부 variant에만 기본값을 채우고 이미 입력된 모델 variant는 보존한다.

세부 schema·허용 태그·트리 검증·FE 순회 규칙은 [React JSON 상세페이지 출력 계약](react-json-output-contract.md)을 따른다.

## 4. FE → 상품 BE 입력 계약

상품 BE 공개 API의 경로는 상품 BE 팀이 정한다. 다만 FE가 전달하는 의미와 필드는 다음과 같다.

### 4.1 초안 생성 요청

`multipart/form-data`

| 필드 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `product_image` | file | O | 대표 원본 제품 이미지 |
| `product_images` | file[] | X | 추가 원본 이미지. 같은 필드명을 반복 사용 |
| `product_name` | string | O | 작품명 |
| `making_method` | string | O | 제작 과정 또는 작품 설명 |
| `care_guide` | string | X | 사용·보관·관리 방법 |
| `request_id` | string | X | FE 추적용 요청 ID |
| `template_id` | string | X | `default-long-detail-page` |
| `locale` | string | X | `ko-KR` |
| `options` | JSON string | X | 생성 옵션 |

`options` 예시:

```json
{
  "aspect_ratio": "1:4",
  "image_size": "2K",
  "output_mime_type": "image/png"
}
```

기본 제한은 이미지 1장당 10MB, 전체 이미지 최대 12장, 전체 요청 최대 120MB다. 서버 설정이 최종 제한을 결정한다.

### 4.2 초안 저장 요청

상품 BE 공개 API는 다음 의미의 JSON을 받는다.

```json
{
  "draft_id": "job-42",
  "version": 1,
  "draft": {
    "product_name": "수정한 작품명",
    "product_type": "장식 보관함",
    "summary": "승인할 설명입니다.",
    "hero_headline": "장인의 시간이 머무는 문양",
    "hero_description": "이미지에서 확인되는 특징을 담았습니다.",
    "usage_scene": "서재 선반 위",
    "features": [],
    "keywords": ["공예", "보관함"],
    "layout_id": "editorial-split",
    "page_plan": []
  }
}
```

### 4.3 승인 요청

상품 BE 공개 API는 FE로부터 승인된 draft와 승인 요청 ID를 받은 뒤 AI 내부 승인 API를 호출한다.
FE가 AI 내부 API의 `draft_id`, `product_id`, `source_asset_id`를 직접 관리하지 않도록 한다.

## 5. 상품 BE → AI 내부 API

모든 내부 API는 다음 공통 헤더를 사용한다. `Idempotency-Key`는 작업 생성·승인 요청에서만
선택적으로 보낼 수 있으며, 상태 조회·초안 저장에는 사용하지 않는다.

```http
X-AI-Internal-Token: <상품 BE와 AI만 공유하는 토큰>
Accept: application/json
```

작업 생성·승인 요청은 `metadata.idempotency_key`를 필수로 보내야 한다. 필요하면 같은 값을
`Idempotency-Key` 헤더에도 보낼 수 있으며, 두 값이 다르면 `409`다.

### 5.1 초안 생성 접수

```http
POST /internal/v1/ai/detail-page-jobs
Content-Type: multipart/form-data
```

Multipart 파트:

- `product_image`: 대표 원본 이미지, 필수
- `product_images`: 추가 원본 이미지, 선택·반복
- `metadata`: `ProductBeToAiCreateJobRequestDto` JSON, 필수

`metadata` 예시:

```json
{
  "product_id": "product-42",
  "source_asset_id": "source-asset-42",
  "request_id": "request-42",
  "idempotency_key": "create-product-42-v1",
  "template_id": "default-long-detail-page",
  "locale": "ko-KR",
  "user_hints": {
    "product_name": "나전 보관함",
    "making_method": "표면 장식으로 완성했습니다.",
    "care_guide": "마른 천으로 닦아 주세요."
  },
  "options": {
    "aspect_ratio": "1:4",
    "image_size": "2K",
    "output_mime_type": "image/png"
  }
}
```

성공 응답은 `202 Accepted`다.

```json
{
  "product_id": "product-42",
  "job_id": "job-42",
  "request_id": "request-42",
  "status": "QUEUED",
  "status_url": "/internal/v1/ai/detail-page-jobs/job-42",
  "created_at": "2026-08-31T00:00:00Z"
}
```

### 5.2 작업 상태 조회

```http
GET /internal/v1/ai/detail-page-jobs/{job_id}
X-AI-Internal-Token: <internal-token>
```

응답 형식:

```json
{
  "product_id": "product-42",
  "job_id": "job-42",
  "request_id": "request-42",
  "status": "DRAFT_READY",
  "progress": 100,
  "draft": {},
  "result": null,
  "error": null,
  "updated_at": "2026-08-31T00:00:08Z"
}
```

작업 상태 전이 흐름은 파이프라인(`src/detail_page_ai/pipeline.py`)의 `emit()` 호출 및 작업 서비스(`src/detail_page_ai/service.py`)의 전이 주기를 반영한다.

```text
초안 생성 단계:
QUEUED (0%) → ANALYZING (15%) → EXTRACTING (60%) → DRAFT_READY (100%)

승인 및 최종 렌더링 단계:
(승인 요청) → ANALYZING (15%) → EXTRACTING (30%) → GENERATING_BACKGROUNDS (45%)
→ COMPOSING (55%) → VERIFYING (65%) → RENDERING (75%)
→ DELIVERING (90%) → COMPLETED (100%)

※ 실패 시 어느 단계에서든 FAILED로 전이
※ 백엔드 적재 응답 대기/재시도 시 승인 응답 상태는 COMPLETED_WITH_BACKEND_PENDING
```

| 상태값 (Status) | 진행률 (Progress) | 설명 |
|---|:---:|---|
| `QUEUED` | 0% | 작업 큐에 등록되어 워커 할당 대기 중 |
| `ANALYZING` | 15% | Qwen 27B 모델 기반 시각 자산 분석 및 메타데이터 추출 |
| `EXTRACTING` | 30% / 60% | 단색 배경 외곽 연결성(flood-fill) 기반 누끼 추출 |
| `DRAFT_READY` | 100% | 편집 가능한 초안 및 `react_document`가 준비되어 사용자 편집 대기 |
| `GENERATING_BACKGROUNDS` | 45% | Flux2 Klein 9B 모델 기반 라이프스타일/디테일 연출 컷 생성 |
| `COMPOSING` | 55% | 제품 누끼와 생성 배경의 기하학적 합성 |
| `VERIFYING` | 65% | 원본 컷아웃 보존율 및 씬 분기 적합성 자동 품질 게이트 검증 |
| `RENDERING` | 75% | React AST 기반 HTML 조립 및 Node Puppeteer 최종 PNG 렌더링 |
| `DELIVERING` | 90% | 생성 자산 및 메타데이터를 상품 BE(`BACKEND_PRODUCT_URL`)로 전달 |
| `COMPLETED` | 100% | 최종 완료 및 상품 BE 적재 성공 |
| `FAILED` | - | 처리 도중 복구 불가능한 에러 발생 |

처리 중에는 `draft`와 `result`가 없을 수 있다. `DRAFT_READY`에서는 `draft`가 제공되고, 최종 완료 시 `result`가 제공된다.

### 5.3 초안 저장

```http
PUT /internal/v1/ai/detail-page-jobs/{job_id}/draft
Content-Type: application/json
X-AI-Internal-Token: <internal-token>
```

본문:

```json
{
  "draft_id": "job-42",
  "version": 1,
  "draft": {}
}
```

- 성공 시 새 `version`과 최신 draft를 반환한다.
- 저장은 분석·사진 생성·PNG 렌더링을 호출하지 않는다.
- 저장 버전이 다르면 `409 Draft version conflict`를 반환한다.

### 5.4 승인 draft 최종 렌더링

```http
POST /internal/v1/ai/detail-page-renders
Content-Type: multipart/form-data
X-AI-Internal-Token: <internal-token>
Idempotency-Key: <approval-idempotency-key>
```

Multipart 파트:

- `metadata`: `ProductBeToAiApproveDraftRequestDto` JSON, 필수
- `product_image`: AI에 저장된 원본이 없을 때만 선택 전달
- `product_images`: 추가 원본이 필요할 때 선택 전달

`metadata` 예시:

```json
{
  "product_id": "product-42",
  "source_asset_id": "source-asset-42",
  "request_id": "approval-42",
  "idempotency_key": "approve-product-42-v1",
  "draft_id": "job-42",
  "draft": {},
  "options": {
    "aspect_ratio": "1:4",
    "image_size": "2K",
    "output_mime_type": "image/png"
  }
}
```

승인 렌더링에서는 저장된 분석 프로필과 원본을 사용하며, 이미지 분석을 다시 호출하지 않는다.

## 6. Draft JSON 계약

`draft`는 실행 가능한 HTML/CSS가 아닌 구조화된 JSON이다.

| 필드 | 타입 | 제한 |
|---|---|---|
| `product_name` | string | 필수, 최대 120자 |
| `product_type` | string/null | 최대 120자 |
| `summary` | string | 필수, 최대 500자 |
| `hero_headline` | string | 필수, 최대 80자 |
| `hero_description` | string | 필수, 최대 300자 |
| `usage_scene` | string | 최대 300자 |
| `features` | array | 최대 3개 |
| `keywords` | string[] | 최대 8개 |
| `layout_id` | enum | `editorial-split`, `image-first`, `catalog-grid` |
| `page_plan` | array | 생성 프롬프트 기준 8~12개; DTO 안전 상한 최대 14개 |

`features` 항목:

```json
{
  "title": "표면 문양",
  "description": "이미지에서 확인되는 표면의 특징입니다.",
  "evidence": "image-visible",
  "confidence": 0.92
}
```

`page_plan`의 허용 `block_type`은 다음과 같다.

```text
hero, statement, feature_grid, detail_split, wide_image,
gallery, usage_scene, scale_reference, palette, recommendation,
info_table, notice, closing
```

블록 예시:

```json
{
  "section_id": "hero",
  "block_type": "hero",
  "eyebrow": "PRODUCT STORY",
  "title": "나전 보관함",
  "body": "제품 소개 문구",
  "variant": "paper",
  "photo_id": "hero",
  "photo_ids": [],
  "items": []
}
```

예시의 `variant`는 허용값 중 하나를 보여주는 예이며, 블록 타입에 따라 고정되는 값이 아니다. 실제 값은 선택된 layout 원형과 모델의 제품별 구성에 따른다.

FE와 상품 BE는 허용된 블록 타입만 렌더링하고 모든 텍스트를 HTML escape한다. `html`, `css`, `script` 필드는 허용하지 않는다.

## 7. AI 결과 계약

### 7.1 Draft 응답

`DRAFT_READY`의 `draft` 객체는 다음 필드를 가진다.

```json
{
  "draft_id": "job-42",
  "generation_id": "generation-draft-42",
  "version": 1,
  "source_mime_type": "image/jpeg",
  "source_sha256": "source-sha256",
  "source_asset_id": "source-asset-42",
  "product": {},
  "draft": {},
  "preview": {
    "source_asset_id": "source-asset-42",
    "source_sha256": "source-sha256",
    "mime_type": "image/jpeg",
    "image_url": null,
    "image_base64": "..."
  },
  "preview_photos": [],
  "react_document": {
    "schemaVersion": "2.0",
    "canvasWidth": 774,
    "root": [{ "id": "section-01", "type": "element", "tag": "section" }]
  }
}
```

### 7.2 최종 결과

`result.detail_page`:

```json
{
  "image_url": null,
  "image_base64": "...",
  "mime_type": "image/png",
  "width": 774,
  "height": 4696,
  "sections": [],
  "photos": [],
  "react_document": {
    "schemaVersion": "2.0",
    "canvasWidth": 774,
    "root": [{ "id": "section-01", "type": "element", "tag": "section" }]
  }
}
```

`sections[]`는 다음 필드를 가진다.

```json
{
  "section_id": "hero",
  "order": 1,
  "label": "상품 소개",
  "image_url": null,
  "image_base64": "...",
  "mime_type": "image/png",
  "width": 774,
  "height": 620
}
```

`photos[]`는 이미지와 함께 원본 provenance를 제공한다.

```json
{
  "photo_id": "lifestyle",
  "order": 4,
  "label": "AI 생성 활용 장면",
  "asset_mode": "generated_scene",
  "source_asset_id": "source-asset-42",
  "source_sha256": "source-sha256",
  "product_generated": true,
  "fidelity_status": "GENERATED"
}
```

허용 `asset_mode`:

```text
source
source_crop
source_composite
generated_scene
generated_view
```

화면 표시 규칙:

- `VERIFIED`, `FALLBACK`: 일반 제품 이미지로 표시
- 생성 여부는 `product_generated` 플래그로 구분한다 (`asset_mode`가 `generated_scene`, `generated_view`인 경우 `product_generated=True`).
- `REJECTED`: FE에 전달하지 않음
- 정확한 상품 근거는 `source_sha256`가 있는 원본 기반 자산으로 확인

## 8. 화면 상태 매핑

| AI 상태 | FE 화면 상태 | 화면 동작 |
|---|---|---|
| `QUEUED` | 접수 완료 | 생성 대기 표시 |
| `ANALYZING`, `EXTRACTING` | 초안 생성 중 | 로딩·진행률 표시 |
| `DRAFT_READY` | 초안 확인·수정 | JSON 편집기와 미리보기 표시 |
| `GENERATING_BACKGROUNDS`~`VERIFYING` | 최종 이미지 생성 중 | 승인 버튼 비활성화 |
| `RENDERING`, `DELIVERING` | PNG 렌더링·저장 중 | 진행 상태 표시 |
| `COMPLETED` | 승인 완료 | 결과 이미지·섹션·게시 버튼 표시 |
| `COMPLETED_WITH_BACKEND_PENDING` | 저장 재시도 대기 | 결과는 표시하되 게시 보류 |
| `FAILED` | 생성 실패 | 안전한 오류 메시지와 재시도 제공 |

## 9. 오류와 멱등성

| HTTP | 의미 |
|---:|---|
| `400` | 이미지·JSON·옵션 형식 오류 |
| `401` | 내부 토큰 오류 |
| `404` | 작업 또는 draft 없음 |
| `409` | 멱등키 충돌 또는 draft 버전 충돌 |
| `413` | 이미지 개수·용량 초과 |
| `429` | AI 처리 용량 초과 |
| `503` | AI 설정 또는 서비스 불가 |

멱등성 규칙:

- 같은 `Idempotency-Key`와 같은 payload는 기존 작업·결과를 재사용한다.
- 같은 키에 다른 payload를 보내면 `409`다.
- 상품 BE 저장 중복은 `ALREADY_SAVED`로 처리한다.
- 결과 매칭 키는 `product_id`, `job_id`, `generation_id`다.

## 10. 로컬 데모 직접 API (`src/detail_page_ai/app.py`)

상품 BE가 없는 로컬 단독 개발 및 프로토타입 브라우저 테스트 환경에서는 다음 직접 API를 사용한다.
이 경로는 환경 변수 `ENABLE_LEGACY_DEMO_API=true`일 때만 활성화되며, 운영 상품 FE가 직접 호출해서는 안 된다.

| 메서드 및 경로 | 요청 형식 | 주요 파라미터 / 본문 | 반환 DTO 및 상태 코드 |
|---|---|---|---|
| `POST /api/v1/ai/detail-page-jobs` | `multipart/form-data` | `product_image` (파일, 필수)<br>`product_images` (파일 배열, 선택)<br>`product_name`, `making_method`, `care_guide` (폼)<br>`request_id`, `template_id`, `locale`, `options` (폼) | `202 Accepted`<br>`AiFeJobAcceptedResponseDto` |
| `GET /api/v1/ai/detail-page-jobs/{job_id}` | (없음) | 경로 파라미터 `job_id` | `200 OK`<br>`AiFeJobStatusResponseDto` |
| `PUT /api/v1/ai/detail-page-jobs/{job_id}/draft` | `application/json` | `ProductBeToAiSaveDraftRequestDto`<br>(`draft_id`, `version`, `draft`) | `200 OK`<br>`AiFeDraftResponseDto` |
| `POST /api/v1/ai/detail-page-renders` | `multipart/form-data` | `product_image` (파일, 필수)<br>`draft` (JSON 문자열, 필수)<br>`product_images`, `request_id`, `options` (폼) | `200 OK`<br>`AiFeApprovedResponseDto` |

## 11. 구현 기준 및 검증 파일

### 핵심 구현 코드
- AI 진입점 및 라우터: [`src/detail_page_ai/app.py`](../../src/detail_page_ai/app.py)
- 상품 BE ↔ AI 통신 DTO: [`src/detail_page_ai/ai_dto.py`](../../src/detail_page_ai/ai_dto.py)
- 공통 데이터 모델 및 스키마: [`src/detail_page_ai/dto.py`](../../src/detail_page_ai/dto.py)
- FE 투영 DTO: [`src/detail_page_ai/fe_dto.py`](../../src/detail_page_ai/fe_dto.py)
- 설정 및 환경 변수 정의: [`src/detail_page_ai/config.py`](../../src/detail_page_ai/config.py)
- React AST 스키마 및 검증기: [`src/detail_page_ai/react_document.py`](../../src/detail_page_ai/react_document.py), [`src/detail_page_ai/react_document_builder.py`](../../src/detail_page_ai/react_document_builder.py)
- 파이프라인 엔진: [`src/detail_page_ai/pipeline.py`](../../src/detail_page_ai/pipeline.py)
- 작업 큐 및 상태 저장소: [`src/detail_page_ai/service.py`](../../src/detail_page_ai/service.py)

### 런타임 및 렌더링 스크립트 (`scripts/runtime/`)
- Node Puppeteer HTML 렌더러: [`scripts/runtime/render_detail_page.mjs`](../../scripts/runtime/render_detail_page.mjs)
- HTML 조립 스크립트: [`scripts/runtime/build_detail_page_html.py`](../../scripts/runtime/build_detail_page_html.py)
- 로컬 단독 상세페이지 실행기: [`scripts/runtime/run_local_detail_page.py`](../../scripts/runtime/run_local_detail_page.py)
- 고정 프로필 렌더링 데모(입력 이미지를 분석하지 않음): [`scripts/runtime/demo_fixed_profile_render.py`](../../scripts/runtime/demo_fixed_profile_render.py). 실제 생성은 위 `run_local_detail_page.py`를 사용합니다.

### 브라우저 UI 및 통합 검증 (`scripts/browser/`)
- 입력 폼 동작 검증: [`scripts/browser/test_input_page.mjs`](../../scripts/browser/test_input_page.mjs)
- 초안 미리보기 및 편집 검증: [`scripts/browser/test_draft_preview.mjs`](../../scripts/browser/test_draft_preview.mjs)
- 원격 엔드포인트 연동 검증: [`scripts/browser/test_draft_preview_remote.mjs`](../../scripts/browser/test_draft_preview_remote.mjs)
- 상세페이지 레이아웃 시각 검증: [`scripts/browser/test_detail_page_layout.mjs`](../../scripts/browser/test_detail_page_layout.mjs)

### 데이터셋 구축 스크립트 (`scripts/dataset/`)
- 평가 데이터셋 생성기: [`scripts/dataset/build_detail_page_eval_dataset.py`](../../scripts/dataset/build_detail_page_eval_dataset.py)
- 실제 실물 평가셋 구축기: [`scripts/dataset/setup_real_eval_dataset.py`](../../scripts/dataset/setup_real_eval_dataset.py)

---

## 12. 설정 및 환경 변수 계약 (Settings Contract)

AI 시스템 구동 및 상품 BE 연동 시 사용되는 환경 변수 계약은 [`src/detail_page_ai/config.py`](../../src/detail_page_ai/config.py)에 정의되어 있다.

| 환경 변수명 | 타입 / 허용값 | 기본값 | 설명 |
|---|---|---|---|
| `AI_CORS_ORIGINS` | string (쉼표 구분) | `http://127.0.0.1:4173,http://localhost:4173` | CORS 허용 오리진 목록 |
| `AI_INTERNAL_AUTH_TOKEN` | string / null | `None` | 상품 BE가 `X-AI-Internal-Token` 헤더로 전송하는 공유 시크릿 토큰 |
| `BACKEND_PRODUCT_URL` | string / null | `None` | AI 서버가 최종 PNG 및 메타데이터를 적재할 상품 BE 엔드포인트 URL |
| `MAX_IMAGE_BYTES` | integer | `10485760` (10MB) | 단일 원본 이미지의 최대 허용 바이트 크기 (초과 시 413) |
| `MAX_SOURCE_IMAGES` | integer | `12` | 업로드 가능한 원본 이미지 최대 개수 (대표 1장 + 추가 11장) |
| `MAX_REQUEST_BYTES` | integer | `125829120` (120MB) | 전체 multipart 요청 본문의 최대 허용 바이트 크기 |
| `RESPONSE_ASSET_MODE` | enum (`base64`, `url`, `both`) | `base64` | 응답 객체 내 이미지 자산 전달 방식 (Base64 인라인 vs URL) |
| `ENABLE_LEGACY_DEMO_API` | boolean | `false` | 인증 없는 로컬 `/api/v1/ai/...` 데모 라우트 활성화 플래그 |
| `LOCAL_TEXT_MODEL` | string | `ddalcu/Qwen3.8-27B-MLX-Serve-4bit` | 텍스트·비전 분석 및 카피라이팅에 사용되는 주 모델 (27B) |
| `LOCAL_IMAGE_MODEL` | string | `mlx-community/flux2-klein-9b-4bit` | 연출 컷 생성에 사용되는 로컬 Flux 모델 (9B) |
| `PROMPT_VERSION` | string | `local-mlx-qwen-flux-v1` | 모델 추론에 적용되는 시스템 프롬프트 템플릿 버전 |
| `LOCAL_TEXT_TIMEOUT` | float | `300.0` (5분) | 텍스트/비전 LLM 추론 타임아웃 초 |
| `LOCAL_IMAGE_TIMEOUT` | float | `300.0` (5분) | Flux 이미지 생성 타임아웃 초 |
