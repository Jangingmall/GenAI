# AI-FE / AI-BE DTO 계약

> 2026-09-16 최신화: Mac 로컬 개발 기본 모델은 MLX Serve의
> `ddalcu/Qwen3.8-27B-MLX-Serve-4bit` + `mlx-community/flux2-klein-9b-4bit`이고,
> 서버 운영 기본 모델은 SGLang의 `cyankiwi/Qwen3.8-27B-AWQ-INT4` +
> `circulus/FLUX.2-klein-9B-bnb-4bit`이다. Flux2 Klein 4B는 로컬 전용 개발 smoke test
> 프로파일이며 DTO 필드·FE/BE 흐름을 변경하지 않는다.

이 문서는 생성형 AI 팀이 제공하는 AI 경계의 DTO와 입출력 계약입니다.
운영 호출 방향은 다음과 같습니다.

```text
FE → BE → AI API/Worker → BE → FE
                    │              │
                    └─ 생성 결과 ───┘
```

BE 자체의 FE API·상품 DB·게시 로직은 이 저장소의 범위가 아닙니다. AI 팀은 로컬 MLX
Serve 또는 서버 SGLang의 Qwen/FLUX 기반 이미지 분석, 사실 기반 문구, `react_document` 제한 AST를 포함한 JSON 초안,
원본 보존형 사진 연출, HTML/CSS 기반 최종 PNG, 그리고 BE 연동 DTO를 제공합니다. AI는 외부 검색·클라우드 모델을
호출하지 않습니다.

## 1. DTO 모듈과 책임

| 방향 | Python DTO | 책임 |
|---|---|---|
| BE → AI 작업 생성 | `ProductBeToAiCreateJobRequestDto` | 상품 식별자·원본 자산·힌트·생성 옵션 |
| BE → AI 최종 렌더링 | `ProductBeToAiApproveDraftRequestDto` | 장인이 수정·승인한 draft와 원본 식별자 |
| BE → AI 초안 저장 | `ProductBeToAiSaveDraftRequestDto` | React JSON 미리보기 문구 저장 |
| AI → BE 접수 응답 | `AiToProductBeAcceptedResponseDto` | 비동기 작업 접수와 polling URL |
| AI → BE 상태 응답 | `AiToProductBeStatusResponseDto` | 상품 식별자를 포함한 작업 상태·결과 |
| AI → BE 승인 결과 | `AiToProductBeApprovedResponseDto` | 최종 PNG 결과와 저장 ACK |
| AI → BE 적재 요청 | `AiToProductBePersistRequestDto` | 분석 전체 결과·해시·PNG 자산 메타데이터 |
| BE → AI 적재 ACK | `ProductBeToAiPersistAckDto` | `SAVED`/`ALREADY_SAVED` 멱등 결과 |

구현 위치:

```python
from detail_page_ai.ai_dto import (
    AiToProductBeAcceptedResponseDto,
    AiToProductBeApprovedResponseDto,
    AiToProductBePersistRequestDto,
    AiToProductBeStatusResponseDto,
    ProductBeToAiApproveDraftRequestDto,
    ProductBeToAiCreateJobRequestDto,
    ProductBeToAiPersistAckDto,
)
```

기존 `detail_page_ai.dto.AiBeProductPersistRequest`와 `AiBePersistAck`는 같은 검증 모델의
하위 호환 이름으로 유지합니다. 새 운영 계약에서는 `product_id`를 반드시 채웁니다. 실제
S3·SQS·IAM 인프라를 생성하거나 배포하는 범위는 포함하지 않습니다.

### 1-1. AI-FE DTO

AI-FE DTO는 AI가 분석·생성한 결과를 BE가 FE에 노출할 때 사용하는 JSON projection입니다.
FE는 AI 서버를 직접 호출하지 않습니다.

| DTO | 방향 | 역할 |
|---|---|---|
| `AiFeCreateJobRequestDto` | FE → BE | 작품명·제작과정·관리법·생성 옵션 |
| `AiFeApprovalRequestDto` | FE → BE | 장인이 수정한 승인 draft JSON |
| `AiFeDraftDto` | AI → BE → FE | 실행 가능한 HTML/CSS가 없는 편집 데이터 |
| `AiFeDraftResponseDto` | AI → BE → FE | draft·원본 미리보기·제품 분석 |
| `AiFeResultResponseDto` | AI → BE → FE | 최종 PNG·섹션·제품 사진 |
| `AiFeJobStatusResponseDto` | AI → BE → FE | 작업 상태·진행률·draft/result/error |
| `AiFeJobAcceptedResponseDto` | AI → BE → FE | 작업 접수 및 상태 URL |
| `AiFeApprovedResponseDto` | AI → BE → FE | 승인 렌더링 결과 |

AI-FE draft에는 `html`, `css`, `<script>` 같은 실행 가능한 markup을 넣지 않습니다. draft의
`page_plan`은 편집·하위 호환용 데이터로 유지하고, FE가 바로 렌더링할 수 있는 정식 산출물은
검증된 `react_document` 제한 AST입니다. 최종 `result.detail_page`와 AI→BE 적재
`detail_page`에도 같은 문서가 포함됩니다. 최종 게시용 이미지 산출물은 기존과 같이 AI가
생성한 `image/png`입니다.

AI-FE DTO의 구현 위치:

```python
from detail_page_ai.fe_dto import (
    AiFeCreateJobRequestDto,
    AiFeApprovalRequestDto,
    AiFeDraftDto,
    AiFeDraftResponseDto,
    AiFeJobAcceptedResponseDto,
    AiFeJobStatusResponseDto,
    AiFeResultResponseDto,
    AiFeApprovedResponseDto,
)
```

### 적응형 상세페이지 구성

`ProductProfileDto.page_plan`과 `ApprovedDraftDto.page_plan`은 AI가 제품마다 직접 구성하는
허용 블록 목록입니다. `layout_id`는 기존 연동 호환을 위한 스타일 힌트이며 실제 섹션 순서와
개수는 `page_plan`이 결정합니다. 각 블록은 `section_id`, `block_type`, `eyebrow`, `title`,
`body`, `variant`와 선택적인 `photo_id`, `photo_ids`, `items`를 가집니다.

허용되는 `block_type`은 `hero`, `statement`, `feature_grid`, `detail_split`, `wide_image`,
`gallery`, `usage_scene`, `scale_reference`, `palette`, `recommendation`, `info_table`,
`notice`, `closing`입니다. AI가 반환한 순서 그대로 렌더링하되, 실행 가능한 HTML이나 CSS는
DTO 경계를 넘지 않습니다. FE는 같은 allowlist로 JSON을 미리보기로 렌더링하고, 최종 승인 시
AI renderer가 동일한 계획으로 PNG를 생성합니다.

`usage_scene`이 계획에 포함되고 원본 사진이 부족하면 최종 승인 렌더링 단계에서 Flux2
이미지 편집 프롬프트를 사용합니다. 원본 이미지를 참조로 함께 전달하고, 제품의 개수·실루엣·
비율·색·표면·손잡이·주둥이·배열을 유지하면서 배경과 사용 환경만 바꾸도록 지시합니다.
결과는 `asset_mode: "generated_scene"`인 `lifestyle` 생성 자산으로 전달합니다. 디테일은
`detail` 1컷만 원본 크롭으로 유지하고, `detail-02`는 각도 보존, `detail-03`은 표면 매크로,
`detail-04`는 실제 사용 상황, `detail-05`는 탑뷰·에디토리얼 배치로 `asset_mode:
"generated_view"` 생성 자산을 만듭니다. 생성 실패 시 해당 슬롯은 원본 크롭으로 자동
대체하며, 생성 결과를 상품의 정확한 근거로 사용하지 않습니다.

생성 자산을 응답할 때는 `product_generated=true`, `asset_mode`, `source_sha256`,
`fidelity_status=GENERATED`를 함께 보냅니다. 생성 여부는 `product_generated` 플래그로
구분하며, `source_original`·`source`·`source_crop`·`source_composite`를 상품 픽셀의 권위 있는 근거로 사용합니다.
`source_original`은 `hero` 대표 이미지에 촬영 원본을 손대지 않고 사용하는 경우입니다.
Mac 로컬 개발 이미지 모델은 `mlx-community/flux2-klein-9b-4bit`이며, 서버 운영 이미지
모델은 SGLang `flux-klein`으로 제공되는 `circulus/FLUX.2-klein-9B-bnb-4bit`입니다.
`Runpod/FLUX.2-klein-4B-mflux-4bit`는 별도 로컬 endpoint의 개발 smoke test에서만 사용합니다.

### React JSON 산출물

세부 필드·FE 매핑·버전 정책은 [React JSON 상세페이지 출력 계약](react-json-output-contract.md)을
canonical 문서로 따른다.

`react_document`는 React element나 JSX 문자열이 아니라 `tag + props + children` 형태의
제한된 JSON AST다. AI 서버가 `ApprovedDraftDto`와 검증된 `page_plan`에서 결정적으로 조립하며,
모델이 임의 태그·HTML·CSS 원문을 직접 반환하지 않는다.

배치 위치는 다음과 같다.

| 응답/요청 | 경로 | 용도 |
|---|---|---|
| 초안 응답 | `draft.react_document` | FE가 초안 미리보기를 렌더링하고 편집 기준으로 사용 |
| 최종 FE 응답 | `result.detail_page.react_document` | FE가 최종 상세 구성 데이터를 렌더링 |
| AI→BE 적재 | `detail_page.react_document` | BE가 저장·게시 JSON으로 보존 |

문서의 직렬화 키는 FE 계약에 맞춰 camelCase를 사용한다.

```json
{
  "schemaVersion": "2.0",
  "canvasWidth": 774,
  "root": [
    {
      "id": "section-01-hero-root",
      "type": "element",
      "tag": "section",
      "props": {
        "variant": "paper",
        "layout": { "display": "stack", "gap": 16, "align": "stretch" }
      },
      "children": [
        {
          "id": "section-01-hero-title",
          "type": "element",
          "tag": "h2",
          "children": [
            { "id": "section-01-hero-title-text", "type": "text", "value": "상품명" }
          ]
        },
        {
          "id": "section-01-hero-figure-01",
          "type": "element",
          "tag": "figure",
          "children": [
            {
              "id": "section-01-hero-image-01",
              "type": "element",
              "tag": "img",
              "props": { "imageId": "hero", "alt": "상품명 상품 소개" }
            }
          ]
        }
      ]
    }
  ]
}
```

허용 태그·부모/자식 관계·링크·스타일·노드 수는
`detail_page_ai.react_document`의 Pydantic 모델이 검증한다. `img`는 `imageId` 자산
참조만 사용하고 실제 URL은 `photos[]`/자산 저장소에서 FE가 해석한다. FE는 `react_document`
자체를 React 컴포넌트 allowlist로 렌더링하며, `dangerouslySetInnerHTML`, 이벤트 핸들러,
raw CSS를 사용하지 않는다.

## 2. BE → AI: 작업 생성

```http
POST /internal/v1/ai/detail-page-jobs
Content-Type: multipart/form-data
X-AI-Internal-Token: <BE와 AI만 공유하는 내부 토큰>
```

Multipart 필드:

| 필드 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `product_image` | file | O | 기준 원본 제품 이미지 |
| `product_images` | repeated file | X | 장인이 추가한 원본 구도 |
| `metadata` | JSON string | O | `ProductBeToAiCreateJobRequestDto` |

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

`product_id`는 필수이며 AI 작업·상태 응답·AI→BE 적재 메타데이터에 동일하게 보존됩니다.
`source_asset_id`는 BE가 관리하는 원본 자산 ID이고, AI가 생성한 내부 asset ID와 별도로
전달됩니다. `user_hints`는 장인이 제공한 상품별 데이터이며 제품명·제작 과정·관리 방법
카피에 우선 반영됩니다. 이미지는 시각 정보 보완에 사용하고, 입력에 없는 상품 고유 주장만
생성하지 않습니다.

접수 응답은 HTTP `202`입니다.

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

## 3. BE → AI: 상태 조회

```http
GET /internal/v1/ai/detail-page-jobs/{job_id}
X-AI-Internal-Token: <BE와 AI만 공유하는 내부 토큰>
```

상태값:

```text
QUEUED | ANALYZING | EXTRACTING | DRAFT_READY | GENERATING_BACKGROUNDS
| COMPOSING | VERIFYING | RENDERING | DELIVERING
| COMPLETED | FAILED
```

처리 중 응답:

```json
{
  "product_id": "product-42",
  "job_id": "job-42",
  "request_id": "request-42",
  "status": "RENDERING",
  "progress": 75,
  "result": null,
  "error": null,
  "updated_at": "2026-08-31T00:00:08Z"
}
```

완료 시 `result.detail_page`에 전체 상세페이지 PNG와 섹션 PNG가 포함됩니다. `generation_id`는
BE의 멱등 저장 키로 사용하며, `product_id`는 결과 객체 안에 섞지 않고 응답 최상위에서
관리합니다.

## 4. BE → AI: 승인 draft 최종 렌더링

초안 문구와 FE용 React JSON을 갱신할 때는 다음 endpoint를 사용합니다.

```http
PUT /internal/v1/ai/detail-page-jobs/{job_id}/draft
Content-Type: application/json
X-AI-Internal-Token: <BE와 AI만 공유하는 내부 토큰>
```

본문은 `{ "draft_id": "job-42", "version": 1, "draft": { ...ApprovedDraftDto... } }`이며
응답은 최신 `version`, `draft_id`, `preview`, `product`, `draft`를 포함합니다. `draft`는
장인이 수정할 수 있는 구조화된 JSON이고, `preview`는 BE/FE가 고정된 템플릿으로
미리보기를 렌더링할 때 사용하는 원본 이미지 참조입니다. AI는 실행 가능한 HTML 문서를
전달하지 않고 `react_document`를 함께 반환합니다. 저장된 버전과
다르면 `409`를 반환합니다. 이 호출에서는 모델·사진 생성기·PNG renderer를 호출하지 않습니다.

초안 상태 응답 예시:

```json
{
  "product_id": "product-42",
  "job_id": "job-42",
  "request_id": "request-42",
  "status": "DRAFT_READY",
  "progress": 100,
  "draft": {
    "draft_id": "job-42",
    "generation_id": "generation-draft-42",
    "version": 1,
    "source_mime_type": "image/jpeg",
    "source_sha256": "source-sha256",
    "source_asset_id": "source-asset-42",
    "preview": {
      "source_asset_id": "source-asset-42",
      "source_sha256": "source-sha256",
      "mime_type": "image/jpeg",
      "image_url": null,
      "image_base64": "원본 이미지 Base64 또는 null"
    },
    "product": {
      "product_type": "장식 보관함",
      "summary": "이미지에서 확인된 제품 요약",
      "keywords": ["공예", "보관함"],
      "features": [],
      "warnings": []
    },
    "draft": {
      "product_name": "장식 보관함",
      "summary": "이미지에서 확인된 제품 요약",
      "hero_headline": "제품의 특징",
      "hero_description": "이미지에서 확인되는 설명",
      "usage_scene": "서재 선반 위",
      "features": [],
      "keywords": ["공예", "보관함"],
      "layout_id": "editorial-split"
    },
    "preview_photos": [],
    "react_document": {
      "schemaVersion": "2.0",
      "canvasWidth": 774,
      "root": [{ "id": "section-01", "type": "element", "tag": "section" }]
    }
  },
  "result": null,
  "error": null,
  "updated_at": "2026-08-31T00:00:08Z"
}
```

```http
POST /internal/v1/ai/detail-page-renders
Content-Type: multipart/form-data
X-AI-Internal-Token: <BE와 AI만 공유하는 내부 토큰>
```

Multipart 필드:

| 필드 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `product_image` | file | X | 기준 원본 제품 이미지. 초안 작업에 저장된 원본을 재사용할 수 있음 |
| `product_images` | repeated file | X | 추가 원본 구도 |
| `metadata` | JSON string | O | `ProductBeToAiApproveDraftRequestDto` |

`metadata` 예시:

```json
{
  "product_id": "product-42",
  "source_asset_id": "source-asset-42",
  "request_id": "approval-42",
  "draft_id": "job-42",
  "idempotency_key": "approve-product-42-v1",
  "draft": {
    "product_name": "승인한 나전 보관함",
    "summary": "승인된 설명입니다.",
    "hero_headline": "장인의 시간이 머무는 문양",
    "hero_description": "이미지에서 확인되는 특징을 담았습니다.",
    "usage_scene": "서재 선반 위",
    "features": [],
    "keywords": ["공예", "보관함"],
    "layout_id": "editorial-split"
  },
  "options": {
    "aspect_ratio": "1:4",
    "image_size": "2K",
    "output_mime_type": "image/png"
  }
}
```

승인 렌더링은 저장된 분석 프로필과 원본을 사용합니다. 새 이미지 분석은 호출하지 않고
`draft`를 기존 프로필에 병합해 AI 내부에서만 HTML/CSS와 Playwright로 재렌더링합니다. 같은 승인
`idempotency_key`를 다시 보내면 기존 `generation_id` 결과를 반환하며, 다른 payload와
재사용하면 `409`입니다. 응답은 다음 형태입니다.

```json
{
  "product_id": "product-42",
  "status": "COMPLETED",
  "result": {
    "generation_id": "generation-42",
    "product": {},
    "detail_page": {
      "image_url": null,
      "image_base64": "iVBORw0KGgo...",
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
  },
  "backend_delivery_pending": false,
  "warning": null,
  "be_ack": {
    "generation_id": "generation-42",
    "product_id": "product-42",
    "status": "SAVED",
    "saved_at": "2026-08-31T00:00:10Z"
  }
}
```

## 5. AI → BE: 생성 결과 적재

AI는 `BACKEND_PRODUCT_URL`로 설정된 BE 적재 API에 multipart 요청을 보냅니다. 적재 API의
구체적인 BE URL과 DB 구현은 BE 팀의 범위입니다.

FE/상태 응답의 자산 모드는 `RESPONSE_ASSET_MODE`로 결정합니다. `base64`는 로컬 데모용,
`url`은 URL을 발급하는 자산 저장소용이며 이 모드에서는 URL이 없다고 Base64로 조용히
대체하지 않습니다. `both`는 전환기 호환용으로만 사용합니다. 최종 바이너리의 BE 적재는
응답 JSON과 별개로 AI→BE multipart outbox가 담당합니다.

전달 내용:

| 파트 | 필수 | 내용 |
|---|---:|---|
| `metadata` | O | `AiToProductBePersistRequestDto` (`AiBeProductPersistRequest`를 상품 식별자 필수로 강화한 모델) |
| `detail_page_image` | O | 전체 상세페이지 PNG |
| `detail_page_section_NN` | X | 순서가 있는 섹션 PNG |
| `product_photo_NN` | X | fidelity 검증을 통과한 제품 사진 |

메타데이터 핵심 필드:

```json
{
  "product_id": "product-42",
  "generation_id": "generation-42",
  "job_id": "job-42",
  "request_id": "request-42",
  "idempotency_key": "generation-42",
  "source": {
    "type": "image-only",
    "mime_type": "image/png",
    "sha256": "source-sha256",
    "asset_id": "source-asset-42"
  },
  "product": {
    "product_type": "장식 보관함",
    "layout_id": "editorial-split",
    "observations": {
      "colors": ["투명", "옅은 청색"],
      "shape": "비대칭으로 흐르는 곡선형 실루엣",
      "visible_components": ["잔", "받침"]
    },
    "features": [],
    "copy_sections": [],
    "uncertain_information": [],
    "safety_notes": [],
    "craft_research": null
  },
  "detail_page": {
    "mime_type": "image/png",
    "sha256": "page-sha256",
    "asset_id": "detail-page-asset-42",
    "sections": [],
    "photos": [],
    "react_document": {
      "schemaVersion": "2.0",
      "canvasWidth": 774,
      "root": [{ "id": "section-01", "type": "element", "tag": "section" }]
    }
  },
  "generation": {
    "provider": "local",
    "analysis_model": "ddalcu/Qwen3.8-27B-MLX-Serve-4bit",
    "image_model": "mlx-community/flux2-klein-9b-4bit",
    "layout_id": "editorial-split",
    "prompt_version": "local-mlx-qwen-flux-v1",
    "research_used": false,
    "generated_at": "2026-08-31T00:00:10Z"
  }
}
```

로컬 경로의 `product.observations`에는 이미지에서 확인한 색·형태·구성 정보만 포함합니다.
상품명·제작 과정·관리법처럼 상품별 사실은 BE가 검수한 `user_hints`를 통해 전달하며,
외부 검색 출처나 검색 결과를 생성 결과에 붙이지 않습니다.

AI는 Product DB에 직접 접근하지 않습니다. 전송 실패 시 SQLite outbox에 전체 요청과 파일을
보존하고 같은 `generation_id`로 재시도합니다. 최종 ACK가 `SAVED` 또는 `ALREADY_SAVED`가
아니면 상태 결과는 `COMPLETED_WITH_BACKEND_PENDING`으로 표시합니다.

## 6. FE DTO와의 관계

`AiFeProductSummaryDto.observations`는 이미지 관찰값을 표시하는 검토용 필드입니다. FE는
BE가 검수한 `user_hints`와 이미지 관찰값을 구분해 표시하고, 모델이 생성한 미확인
소재·제작자·원산지·성능을 확정 사실처럼 표시하지 않습니다.

BE가 FE에 노출할 이름은 다음 alias를 사용할 수 있습니다.

```python
from detail_page_ai.fe_dto import (
    FeToProductBeCreateDetailPageRequestDto,
    FeToProductBeApprovalRequestDto,
    ProductBeToFeAcceptedResponseDto,
    ProductBeToFeStatusResponseDto,
    ProductBeToFeApprovedResponseDto,
)
```

FE는 AI 내부 토큰이나 AI 내부 URL을 알지 않습니다. FE에서 수정 가능한 초안은 BE가
관리하고, BE가 승인된 draft를 AI 내부 렌더링 API로 전달합니다.

## 7. 호환 경로

로컬 브라우저 샘플을 위해 다음 direct-AI 경로를 유지합니다.

```text
POST /api/v1/ai/detail-page-jobs
GET  /api/v1/ai/detail-page-jobs/{job_id}
PUT  /api/v1/ai/detail-page-jobs/{job_id}/draft
POST /api/v1/ai/detail-page-renders
```

이 경로는 `product_id` 없이 동작할 수 있는 legacy/demo 경로이며 운영 FE가 직접 사용하지
않습니다. 운영 연동은 반드시 `/internal/v1/ai/*`와 `X-AI-Internal-Token`을 사용합니다.
