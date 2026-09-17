# FE 입출력 명세

> 2026-09-16 최신화: Mac 로컬 개발은 MLX Serve(`127.0.0.1:11234`)의
> `ddalcu/Qwen3.8-27B-MLX-Serve-4bit`/`mlx-community/flux2-klein-9b-4bit`, 서버 운영은
> SGLang 텍스트·이미지 서버(`30000`/`30001`)의
> `cyankiwi/Qwen3.8-27B-AWQ-INT4`/`circulus/FLUX.2-klein-9B-bnb-4bit`를 사용한다.
> Flux2 Klein 4B 비교 실행은 로컬 개발 프로파일에만 영향을 주며, FE 계약은 동일하다.
> 생성 여부는 `product_generated` 플래그로 구분하며 provenance를 제공한다.

운영 구조에서 FE는 AI를 직접 호출하지 않습니다.

```text
FE → BE → AI → BE → FE
```

BE의 FE API 경로와 DB 저장은 BE 팀이 정의합니다. 이 문서는 FE 화면에서 필요한
데이터와 AI 팀이 제공하는 내부 계약을 연결하는 기준만 설명합니다.

## 1. FE가 BE에 보내는 값

상품 생성/상세페이지 화면은 BE에 다음 정보를 보냅니다.

| 값 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| 대표 제품 이미지 | file | O | 원본 제품 이미지 |
| 추가 제품 이미지 | file, repeated | X | 실제로 촬영한 추가 구도 |
| 작품명 | string | X | 상품별 카피의 기준 데이터 |
| 제작 과정 | string | X | 상품별 제작 서사의 기준 데이터 |
| 관리 방법 | string | X | 상품별 관리 안내의 기준 데이터 |
| 편집 draft | JSON | 승인 시 O | 장인이 JSON 기반 미리보기에서 수정한 내용 |
| `request_id` | string | X | FE 추적용 요청 ID |

BE는 이 값을 검증하고 `product_id`, `source_asset_id`, `user_hints`, `options`를 묶어
AI 내부 DTO로 변환합니다. `user_hints`라는 내부 필드명은 연동 호환성을 위해 유지하지만,
내용은 장인이 제공한 상품별 기준 데이터입니다. AI는 입력된 제품명·제작 과정·관리 방법을
이미지보다 우선하여 카피에 반영하며, 이미지와 다르게 보여도 입력 데이터를 삭제하거나
추정으로 대체하지 않습니다. 이미지는 형태·색·문양·질감 등 시각 정보를 보완하는 데만 사용하고,
입력에 없는 상품 고유 주장만 생성하지 않습니다.

## 2. FE에서 보여줄 화면 상태

BE는 AI 내부 상태를 FE 화면 상태로 매핑합니다.

```text
초안 생성 중 → DRAFT_READY draft + `react_document` → BE/FE 미리보기 렌더링 → 장인 수정·저장 → 승인
→ 최종 PNG 생성 중 → 게시 대기/완료
```

초안 생성 응답에는 `status: "DRAFT_READY"`와 함께 구조화된 `draft` JSON, `react_document`,
`preview` 이미지 참조가 들어옵니다. `draft.page_plan`은 제품에 따라 AI가 구성한 섹션
순서·종류·표현 변형을 보존하는 편집·하위 호환 필드이고, `layout_id`는 호환용 힌트입니다.
AI는 실행 가능한 HTML 문서를 전달하지 않습니다. FE는 `react_document`를 태그·props
allowlist로 렌더링하고, 문구 입력 이벤트는 편집 중인 draft와 로컬 미리보기에 즉시 반영합니다.
저장 버튼을 누를 때만 `PUT /internal/v1/ai/detail-page-jobs/{job_id}/draft`로 수정된
`draft` JSON을 보냅니다. 이 저장은 AI 분석·사진·PNG 생성을 다시 호출하지 않습니다.

AI가 반환한 `result.detail_page`는 다음 자산을 제공합니다.

- `image_base64` 또는 `image_url`: 전체 상세페이지 PNG
- `sections[]`: 레이아웃별 순서가 보존된 섹션 PNG
- `react_document`: `schemaVersion: "2.0"`의 제한된 `tag + props + children` JSON AST. FE가
  상세페이지 구조를 렌더링할 때 사용하는 정식 JSON 산출물이며, `schemaVersion`, `canvasWidth`,
  `imageId` 등 camelCase로 직렬화된다.
- `photos[]`: 원본 기반 제품 사진과 생성 참고 자산을 provenance와 함께 제공한다. `hero`·
  `packshot`·대표 `detail`은 제품 픽셀을 원본 그대로 보존하고, `lifestyle`·추가 `detail`의
  Flux 편집 결과는 `product_generated=true`, `asset_mode`, `fidelity_status=GENERATED`로
  표시한다. 생성 자산은 참고 슬롯에만 사용하며 상품 사실의 근거로 삼지 않는다.
- `product`: 이미지에서 확인한 특징, 불확실성, 공예 조사 결과

초안 편집 단계에서는 JSON 필드를 사용해 텍스트를 실시간 수정하고 FE가 `react_document`를
미리보기로 렌더링합니다. 승인 전에는 최종 PNG나 배경·제품 사진 생성을 호출하지 않습니다.
승인 후에는 AI 내부에서 HTML/CSS를 렌더링해 전체 상세페이지 PNG와 섹션 PNG를 생성하고,
동일한 `react_document`와 함께 BE에 저장합니다.

## 3. BE가 AI에 전달할 생성 메타데이터

작업 생성 시 `BeToAiCreateJobRequestDto`를 사용합니다.

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

승인 시에는 `BeToAiApproveDraftRequestDto`를 사용합니다. `draft_id`에는 초안 작업의
`job_id`를 넣고 `idempotency_key`를 고정합니다. `draft`에는 장인이 수정한
문구·특징·`layout_id`만 담으며, 승인 렌더링에서 AI 분석을 다시 호출하지 않습니다.

## 4. AI 내부 엔드포인트

BE만 다음 API를 호출합니다.

```http
POST /internal/v1/ai/detail-page-jobs
GET  /internal/v1/ai/detail-page-jobs/{job_id}
PUT  /internal/v1/ai/detail-page-jobs/{job_id}/draft
POST /internal/v1/ai/detail-page-renders
X-AI-Internal-Token: <공유 내부 토큰>
```

공통 서비스 프로브는 인증 없이 호출합니다.

```http
GET /health
GET /health/ready
```

`/health`는 추론 서버를 호출하지 않는 liveness 경로이며 항상 `200 {"status":"ok"}`를 반환합니다.
`/health/ready`는 SGLang 두 서버의 `/v1/models`를 확인하고 준비되면 `200`, 실패하면 사유와 함께
`503`을 반환합니다.

생성·승인 요청은 `multipart/form-data`이며 `product_image`, 반복 `product_images`, JSON
`metadata` 파트를 사용합니다. 초안 저장은 `application/json` 본문을 사용합니다. 상세 필드와
예시는 [`ai-dto-contract.md`](ai-dto-contract.md)에 정의되어 있습니다.

AI 작업 상태는 다음과 같습니다.

```text
QUEUED → ANALYZING → EXTRACTING → DRAFT_READY
→ (승인) GENERATING_BACKGROUNDS
→ COMPOSING → VERIFYING → RENDERING → DELIVERING
→ COMPLETED | FAILED
```

내부 API는 `AI_INTERNAL_AUTH_TOKEN`이 설정되지 않으면 `503`, 토큰이 틀리면 `401`을 반환합니다.
AI 내부 토큰은 FE에 전달하지 않습니다.

내부 작업 생성·승인은 `Idempotency-Key` 헤더 또는 metadata의 `idempotency_key`를 필수로
사용합니다. 같은 키와 같은 payload는 기존 작업/결과를 재사용하고, 다른 payload는 `409`로
거절합니다. 이미지 한 장은 기본 10MB, 전체 업로드는 기본 12장·120MB까지이며 서버가 최종
한도를 적용합니다.

## 5. 결과·오류 표시

BE는 AI 응답의 `product_id`, `job_id`, `request_id`, `generation_id`를 연결해 화면과
저장 레코드를 매칭합니다.

- `COMPLETED`: PNG와 메타데이터가 생성되고 BE 적재 ACK까지 완료
- `COMPLETED_WITH_BACKEND_PENDING`: PNG는 생성됐지만 BE 저장이 재시도 대기
- `FAILED`: 입력 이미지·분석·검증·렌더링 중 실패. 사용자에게 provider credential이나 내부 URL을 노출하지 않음

`fidelity_status=REJECTED` 자산은 FE에 전달하지 않습니다. 생성 자산은 허용된 참고 슬롯만
전달합니다: `lifestyle-02/generated_scene`, `detail-02~detail-05/generated_view`.
`asset_mode=generated_scene`인 `lifestyle-02`는 원본 이미지를 참조로 넣은 Flux2 프롬프트 편집
결과입니다. 생성 여부는 `product_generated` 플래그로 구분하며, 정확한 제품 근거는
`source_sha256`가 있는 원본 `hero`·`packshot`·`detail` 자산으로 확인합니다. 프롬프트 편집이
실패한 경우에만 원본 이미지 또는 `source_composite` fallback이 전달됩니다.

`generated_view`는 제공 사진 수와 무관하게 붙이는 보조 디테일 참고 자산입니다. 제공 사진은
기본 역할에 먼저 배정하고, 사진으로 채우지 못한 역할만 생성하며, 추가 보조 생성 컷도 함께
붙일 수 있습니다.
`detail-02`는 좌측 사선 각도 보존, `detail-03`은 표면 매크로, `detail-04`는 실제 사용 상황,
`detail-05`는 탑뷰·에디토리얼 배치입니다. 각 생성이 실패하면 같은 ID의 `source_crop`으로
대체됩니다. `detail`만 성공 시 항상 검증된 원본 크롭으로 유지합니다.

## 6. 로컬 샘플 호환 경로

현재 `web/ai_input.html`과 `web/ai_draft_preview.html`은 BE가 없는 로컬 데모이므로
legacy direct-AI 경로를 사용할 수 있습니다. 이 경로는 `ENABLE_LEGACY_DEMO_API=true`를
명시했을 때만 열리며 운영 FE가 사용할 경로가 아닙니다.

```text
POST /api/v1/ai/detail-page-jobs
GET  /api/v1/ai/detail-page-jobs/{job_id}
PUT  /api/v1/ai/detail-page-jobs/{job_id}/draft
POST /api/v1/ai/detail-page-renders
```

공통 서비스 프로브는 직접 API와 별개로 인증 없이 호출합니다.

```http
GET /health
GET /health/ready
```

이 경로는 운영 FE 계약이 아니며 `product_id`가 없는 샘플도 허용합니다. BE 연동 시에는
FE 페이지의 API 주소를 BE 주소로 바꾸고, BE가 내부 AI DTO로 변환합니다.
