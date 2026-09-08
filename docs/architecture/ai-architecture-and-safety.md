# 상세페이지 AI 아키텍처·평가·안전성 정책 초안

> 이 문서는 기존 통합 참고본이다. 주제별 최신 기준은 [AI 아키텍처 설계](ai-architecture-design.md)와
> [AI 평가 지표·안전성 정책 초안](ai-evaluation-and-safety-policy.md)을 각각 참고한다.

- 상태: Draft
- 최신 점검: 2026-09-08. 기본은 Gemma 12B + Flux2 Klein 9B이며, Flux2 Klein 4B는 전용 loopback endpoint로만 smoke test했다.
- FE 구조 출력: 검증된 `react_document` 제한형 JSON AST. `page_plan`은 모델·편집·하위 호환 입력이며 HTML/CSS는 내부 PNG renderer 전용이다.
- 최신 생성 기록: [local-generation-test-report.md](../operations/local-generation-test-report.md)
- 대상 서비스: 이미지 기반 상품 상세페이지 생성 시스템
- 기준 코드: `src/detail_page_ai`, `src/local_detail_page_ai`
- 작성 목적: 모델 선택, 데이터 흐름, 서빙 경계, 품질 평가, 안전성 정책을 하나의 운영 기준으로 통합

## 1. 설계 원칙

1. **제품 원본 픽셀은 변경하지 않는다.** 제품 영역을 생성형 모델이 다시 그리거나, 색·무늬·형태를 임의로 바꾸지 않는다.
2. **이미지에서 확인한 사실과 장인 입력을 분리한다.** 두 종류의 근거를 `ProductProfile`의 관찰·힌트 필드에 각각 남긴다.
3. **초안과 게시 결과를 분리한다.** AI는 구조화된 `draft`와 검증된 `react_document`를 상품 BE에 반환하고, 상품 BE/FE가 React 컴포넌트 allowlist로 미리보기를 렌더링한다. 승인 시점에만 AI 내부에서 최종 PNG를 렌더링한다.
4. **상품 BE와 AI의 책임을 분리한다.** FE는 상품 BE를 통해 AI를 사용하고, AI는 작업 결과와 저장용 메타데이터만 상품 BE에 전달한다.
5. **모델 실패는 안전한 fallback으로 끝낸다.** 분석 실패, 배경 생성 실패, fidelity 검증 실패가 제품 픽셀 변경으로 이어지지 않게 한다.
6. **로컬 모델 교체는 어댑터 뒤에서 한다.** MLX Serve와 Ollama는 동일한 내부 DTO와 포트로 연결한다.

## 2. 목표와 범위

### 2.1 목표

- 장인이 상품 이미지 1장 이상과 선택 설명을 업로드하면 제품 특징을 구조화한다.
- 제품 유형에 맞는 상세페이지 레이아웃과 한국어 카피 초안을 생성한다.
- 입력 이미지가 부족할 때 원본 기반의 역할별 컷을 보완한다.
- FE가 렌더링하는 제한형 React JSON 미리보기와 승인 후 PNG를 제공한다. HTML/CSS는 AI 내부 PNG renderer에서만 사용한다.
- 상품 BE→AI 작업과 AI→상품 BE 적재 요청을 같은 `product_id`, `request_id`, `generation_id`로 연결한다.
- 모델 버전, 프롬프트 버전, 원본 해시, 변환 이력을 추적한다.

### 2.2 범위 밖

- 이 문서는 로컬 실행 설계이며 외부 클라우드 모델·검색엔진·credential을 사용하지 않는다.
- 제품 전체를 image-to-image 방식으로 재생성하는 기능은 기본 경로에 포함하지 않는다.
- 이미지에서 확인되지 않는 브랜드, 제작자, 원산지, 정확한 소재, 성능, 인증을 자동 확정하지 않는다.

## 3. 논리 아키텍처

```text
┌──────────────┐       ┌─────────────────────┐
│   FE 입력     │──────▶│ 상품 BE              │
│ 이미지·힌트   │       │ FE 계약·상품 소유    │
└──────────────┘       └──────────┬──────────┘
                                  │ multipart + metadata
                                  ▼
┌────────────────────┐       ┌──────────────────────┐
│ AI API / Job Service│──────▶│ Job DB + Idempotency │
│ FastAPI             │       │ SQLite               │
└─────────┬──────────┘       └──────────────────────┘
          │ job enqueue
          ▼
┌────────────────────┐
│ AI Worker           │
│ 상태·재시도·outbox   │
└─────────┬──────────┘
          │
          ├── 원본 저장·해시 ────────────────▶ Local File Store
          │                                   .local/detail-page-ai/assets
          │
          ├── 로컬 이미지·텍스트 분석 ─────────▶ MLX Serve :11234
          │                                      └─ Gemma 12B → ProductProfileDto
          │
          ├── 배경·참고 컷 생성(선택) ───────────▶ MLX Serve Flux2
          │                                      └─ 제품 없는 배경판 또는 GENERATED 참고 자산
          │
          ├── 원본 RGB + 알파 마스크 합성 ─────▶ Pillow compositor
          │                                      └─ ProductPhoto + provenance
          │
          ├── fidelity·안전성 검증
          │
          ├── ApprovedDraft/page_plan ─────────▶ React JSON builder + validator
          │                                      └─ react_document → FE projection/BE metadata
          │
          └── HTML/CSS + Playwright 렌더링 ────▶ 전체 PNG + 섹션 PNG
          │
          ├───────────────────────────────────▶ 상품 BE 상태/결과 응답 ──▶ FE
          └── outbox + multipart client ───────▶ 상품 BE 적재 API
```

### 3.1 현재 코드와 운영 확장 매핑

| 책임 | 현재 구현 | 운영 확장안 |
|---|---|---|
| HTTP 진입점 | `src/detail_page_ai/app.py` | API Gateway/ALB 뒤 stateless API |
| 작업 상태 | `DetailPageJobService` + SQLite repository | 로컬 worker claim 확장 |
| 작업 실행 | 현재 background executor | 별도 로컬 worker process |
| 영속 자산 | `LocalFileAssetStore` | 로컬 파일 store 또는 NAS |
| 전달 재시도 | SQLite delivery outbox | 동일 SQLite 정책 또는 로컬 큐 |
| 분석 | `LocalProductAnalyzer` + Gemma 12B | MLX Serve worker pool |
| React 구조 출력 | `react_document_builder` + Pydantic AST validator | 공통 FE schema/package |
| 조사 | 자동 외부 조사 없음 | 상품 BE 검수 `user_hints` |
| 사진 보완 | `SourcePreservingProductPhotoGenerator` | CPU compositor, Flux는 로컬 GPU |
| 렌더링 | `HtmlDetailPageRenderer` | renderer worker pool |
| Product BE→AI 계약 | `ai_dto.py` + `/internal/v1/ai/*` | private network 또는 mTLS/API auth |
| AI→Product BE 전달 | `BackendProductClient` + outbox | 상품 BE 적재 API와 멱등 재시도 |

## 4. 모델 구성과 역할

모델은 하나의 거대한 호출로 상세페이지를 만들지 않고, 근거와 실패 경계가 분명한 단계로 나눈다.

### 4.1 모델 역할

| 단계 | 기본 후보 | 입력 | 출력 | 실패 시 동작 |
|---|---|---|---|---|
| 이미지 분석 | 로컬 MLX Serve Gemma 12B | 원본 이미지, 장인 제공 상품 데이터 | `ProductProfileDto` | 재시도 후 작업 실패, 원본은 보존 |
| 공예·제품 조사 | 자동 외부 조사 없음 | 상품 BE 검수 `user_hints` | 입력된 사실만 카피에 반영 | 미제공 내용은 `unknown` |
| 배경·참고 컷 생성 | 로컬 MLX Serve Flux2 | 역할·제품 유형·빈 배경 프롬프트, 선택적 원본 참고 | 제품 없는 배경 또는 `GENERATED` 참고 이미지 | 중립 단색 배경 또는 원본 슬롯 fallback |
| 제품 근거 컷 합성 | source 역할은 생성 모델 미사용, Pillow | 원본 RGB, 알파 마스크, 배경 | `ProductPhoto` + provenance | 원본 전체 컷 또는 해당 컷 제외 |
| React JSON 조립 | 생성 모델 미사용, deterministic builder | 검증된 draft·`page_plan` | `ReactDetailPageDocumentDto` | schema/tree 실패 시 결과 차단 |
| 상세페이지 렌더링 | 생성 모델 미사용, HTML/CSS + Playwright | 승인/초안 DTO, 사진 자산 | PNG 전체·섹션 | 렌더 실패 및 재시도 |

### 4.2 분석 모델 정책

- 분석 결과는 자유 텍스트가 아니라 Pydantic JSON Schema에 맞는 `ProductProfileDto`로 받는다.
- `features[].evidence`는 `image-visible`, `inferred`, `unknown` 중 하나로 표시한다.
- `classification_confidence`와 `craft_confidence`는 라우팅용 신호일 뿐 사실의 증명이 아니다.
- 제품 이미지와 사용자 입력이 다르게 보여도 제품명·제작 과정·관리 방법은 장인이 제공한 상품별 기준 데이터로 우선 사용한다. 이미지에서 확인되는 형태·색·문양·질감은 시각 정보 보완에 사용하며, 입력 데이터를 삭제·대체하거나 충돌로 표시하지 않는다.
- 구조화 출력이 깨지거나 필수 필드가 없으면 결과를 부분 성공으로 저장하지 않고 재시도한다.

로컬 서버의 구조화 출력은 모델·서버 버전에 따라 달라질 수 있으므로, 프롬프트에 스키마를
명시하고 애플리케이션에서 최종 Pydantic 검증을 수행한다.

### 4.3 조사 데이터 정책

- 생성 중 외부 웹 검색·원격 조사 모델을 호출하지 않는다.
- 제작자·원산지·진품성·인증·정확한 소재·성능·최신 가격은 상품 BE가 검수해
  `user_hints`로 전달하지 않으면 확정하지 않는다.
- 근거가 없거나 입력이 충돌하면 문구를 제거하고 `unknown` 또는 보수적 표현으로 낮춘다.

### 4.4 이미지 생성 모델 정책

이미지 모델은 로컬 MLX Serve Flux2로 제한한다. 제품 없는 배경판은 제품 이미지 없이 생성하고,
선택적인 lifestyle/generated_view 참고 컷은 원본을 시각 참고로 전달하는 편집 경로를 사용할 수
있다. 어느 경우에도 생성 결과를 원본 상품 근거 자산으로 승격하지 않는다.

- 배경 프롬프트에는 제품, 제품과 유사한 주 피사체, 로고, 글자, 추가 상품을 금지한다.
- 응답 이미지는 객체·문자·로고 안전성 검사를 거친다.
- 원본 `hero`·`packshot`·대표 `detail`은 원본 RGB/cutout을 사용한다. 생성 `lifestyle`·추가 `detail`은 허용된 참고 슬롯에만 배치하고 `product_generated=true`, `asset_mode`, `source_sha256`, `fidelity_status=GENERATED`를 표시한다.
- 생성 참고 자산은 현재 렌더링·상품 BE 전달 경로에 포함될 수 있지만 대표 상품 사진·상품 사실성 증거로는 사용하지 않는다. `REJECTED` 자산은 모든 출력 경계에서 제거한다.
- 배경 생성 실패, 안전성 검사 실패, 모델 timeout은 중립 배경으로 fallback한다.

### 4.5 로컬 모델 서빙 정책

모델 호출은 개인정보와 제품 이미지를 외부로 보내지 않는 loopback 로컬 서버로 제한한다.

- 텍스트·비전 모델: `mlx-community/gemma-4-12b-it-4bit`
- 이미지 모델: `mlx-community/flux2-klein-9b-4bit`
- 기본 endpoint: `http://127.0.0.1:11234`
- Ollama는 별도 로컬 검증 시에만 사용하며 외부 URL·API key를 허용하지 않는다.
- 모델 서버가 내려가거나 schema 응답이 깨지면 작업을 실패 처리하고, 이미지 생성 실패는
  중립 단색 배경으로 fallback한다.

#### Flux2 Klein 4B 비교 프로파일

`Runpod/FLUX.2-klein-4B-mflux-4bit`는 메모리 절약형 개발·비교 모델이다. 기본 11234 서버가
이 모델의 image modality를 제공하지 않아 테스트 시 `http://127.0.0.1:11235` 전용 MLX Serve를
임시 기동했고, `POST /v1/images/generations`가 `200`과 `b64_json`을 반환하는 것을 확인했다.
테스트 후 전용 서버는 종료했으며, 기본 모델·BE/FE DTO·운영 endpoint는 9B 설정을 유지한다.

## 5. 데이터 흐름과 상태 관리

### 5.1 입력

운영 FE는 상품 BE에 이미지를 보내고, 상품 BE가 다음 multipart와 JSON metadata로 AI를 호출한다.

- `product_image`: 대표 원본 1장
- `product_images`: 사용자가 직접 촬영한 추가 구도 0장 이상
- `metadata.product_id`: 상품 BE가 소유하는 필수 상품 식별자
- `metadata.source_asset_id`: 상품 BE가 소유하는 원본 자산 식별자
- `metadata.user_hints`: 작품명·제작 과정·관리 방법 기준 데이터(기존 필드명 유지)
- `metadata.request_id`, `template_id`, `locale`, `options`: 추적·렌더링 옵션

AI 내부 경로는 `/internal/v1/ai/detail-page-jobs`(생성·상태 조회·초안 저장)와
`/internal/v1/ai/detail-page-renders`(승인 렌더링)이며 모두 `X-AI-Internal-Token`을 요구한다. AI 팀은 상품 BE의
FE API나 Product DB를 구현하지 않는다. 로컬 브라우저 샘플만 legacy `/api/v1/ai/*` 경로를
사용한다.

입력 즉시 MIME, 파일 크기, 이미지 디코딩 가능 여부를 확인하고 SHA-256을 계산한다. 원본은 변환 전에 저장하며, 로그에는 이미지 본문·Base64·민감한 입력 텍스트를 남기지 않는다.

### 5.2 생성 단계

```text
QUEUED
  → ANALYZING
  → EXTRACTING
  → DRAFT_READY (draft JSON + `react_document`, 상품 BE/FE 미리보기)
  → 승인
  → GENERATING_BACKGROUNDS
  → COMPOSING
  → VERIFYING
  → RENDERING
  → DELIVERING
  → COMPLETED | FAILED
```

각 단계는 `job_id`, `request_id`, `generation_id`를 유지한다.

- `product_id`: 상품 BE가 소유하는 상품 식별자
- `job_id`: AI 내부 작업 조회 키
- `request_id`: 요청 단위 추적 키
- `generation_id`: 하나의 생성 결과와 상품 BE 적재 멱등성 키
- `prompt_version`: 프롬프트 변경에 따른 결과 비교 키
- `model/provider`: 실제 호출 모델과 공급자 기록

### 5.3 사진 자산의 provenance

각 제품 사진은 다음 정보를 가진다.

- `asset_mode`: `source`, `source_crop`, `source_composite`, `generated_scene`, `generated_view`
- `source_sha256`, `source_asset_id`
- 컷아웃을 사용하면 `cutout_sha256`, `mask_sha256`
- `transform`: crop, scale, x, y
- `background_generated`
- `product_generated`: 원본 기반 자산은 `false`, 생성 참고 자산은 `true`
- `fidelity_status`: `VERIFIED`, `FALLBACK`, `GENERATED`, `REJECTED`

`GENERATED`는 픽셀 보존 검증 성공을 뜻하지 않는다. 생성 참고 컷의 제품 형태·색·문양·구성품은
사람 검수 전까지 확정 사실로 취급하지 않는다.

검증에서 `REJECTED`인 자산은 다음 경계 모두에서 제거한다.

1. HTML/CSS 렌더러
2. 상품 BE 상태/결과 응답
3. AI→상품 BE multipart payload
4. outbox 재전송 payload

### 5.4 FE와 BE 전달

운영에서는 상품 BE가 AI 결과를 FE 응답으로 변환한다. AI 경계의 canonical DTO는
`src/detail_page_ai/ai_dto.py`에 있으며, 방향이 섞이지 않도록 다음처럼 나눈다.

- 상품 BE→AI: `ProductBeToAiCreateJobRequestDto`, `ProductBeToAiApproveDraftRequestDto`
- AI→상품 BE: `AiToProductBeAcceptedResponseDto`, `AiToProductBeStatusResponseDto`,
  `AiToProductBeApprovedResponseDto`
- AI→상품 BE 적재: `AiToProductBePersistRequestDto`

초안 단계에서는 AI가 상품 BE에 실행 가능한 HTML/JSX가 아닌 구조화된 `draft` JSON과
`draft.react_document`를 전달한다. 상품 BE/FE가 `react_document`를 React 컴포넌트 allowlist로
미리보기하고, 승인 단계에서 수정된 `draft`와 원본을 AI에 전달하면 AI는 분석 없이 AST를 재조립·검증한
뒤 내부 HTML/CSS로 PNG를 렌더링한다. 완료 단계 결과에는 전체 `image/png`, 섹션 PNG,
provenance가 있는 제품 사진, `detail_page.react_document`가 함께 포함된다.

AI→상품 BE 요청은 `AiToProductBePersistRequestDto`를 사용한다.

- 상품 분류·특징·관찰·불확실성
- 원본·최종 PNG·섹션·사진의 hash 및 asset id
- 생성 모델·프롬프트·레이아웃·조사 사용 여부
- `generation_id` 기반 idempotency key

AI→상품 BE 저장 실패는 FE 최종 결과와 분리한다. PNG를 생성했더라도 AI outbox에 저장해
같은 `generation_id`로 재시도하고, 실패 상태에는 `COMPLETED_WITH_BACKEND_PENDING`을 사용한다.

## 6. 서빙 구조

### 6.1 로컬 MVP

```text
Browser :4173
    └─ FastAPI :8000
        ├─ background executor
        ├─ SQLite job/repository/outbox
        ├─ .local/detail-page-ai/assets
        ├─ MLX Serve Gemma + Flux local adapters
        ├─ React JSON builder + validator (in-process)
        └─ Playwright renderer
```

로컬 MVP의 목적은 API 계약, `react_document` schema/tree/image reference, 원본 fidelity, HTML 렌더링,
재시도·멱등성 검증이다. 실제 트래픽 처리나 GPU 스케일링을 목표로 하지 않는다.

### 6.2 로컬 단일 호스트 구조

```text
FE
 │
 ▼
상품 BE → AI API :8000 → 로컬 Job Worker
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
          SQLite      파일 저장소  MLX Serve :11234
          job/outbox  source/result  Gemma 12B + Flux2
                         │
                         ▼
                   Playwright renderer
                         │
                         ▼
                   상품 BE 적재 API(선택)
```

권장 분리:

- **AI API**: 상품 BE 내부 인증, 업로드 검증, 작업 생성, 상태 조회. 긴 모델 호출은 worker에서 수행한다.
- **AI Worker**: 로컬 분석·사진 합성·검증·outbox 생성.
- **Renderer Worker**: Playwright와 PNG 변환. 브라우저 프로세스와 모델 메모리를 분리한다.
- **Local File Store**: 원본과 결과를 `.local/detail-page-ai/assets`에 보관한다.
- **SQLite**: job 상태, idempotency, generation metadata, outbox, lease를 보관한다.
- **MLX Serve**: loopback endpoint에서 Gemma/Flux를 제공하고 timeout을 적용한다.
- **상품 BE 연동**: `BACKEND_PRODUCT_URL`이 설정된 경우에만 생성 metadata와 PNG를 전달한다.

### 6.3 동시성·재시도

- 동일 `generation_id`는 한 번만 상품 BE에 적재한다.
- worker는 lease/heartbeat를 사용하고 lease 만료 시 작업을 재획득한다.
- 로컬 모델 endpoint 호출은 단계별 timeout과 제한된 exponential backoff를 사용한다.
- validation 실패는 무조건 재시도하지 않는다. 입력 오류·정책 위반·스키마 오류는 원인별로 분류한다.
- 로컬 worker lease는 최대 예상 작업 시간보다 길게 설정하고, stale worker 재획득을 제한한다.
- FE polling은 `status_url`을 사용하며, 결과 자산은 URL 만료 전에 재발급할 수 있어야 한다.

### 6.4 관측성

모든 로그와 metric에 `request_id`, `job_id`, `generation_id`, `provider`, `model`, `prompt_version`을 비민감 태그로 남긴다.

- API: 요청 수, 4xx/5xx, 업로드 크기, queue wait time
- Worker: 단계별 latency, retry count, timeout count, queue age
- Model: input/output token, 이미지 호출 수, endpoint error, schema failure
- Asset: 원본 hash, 결과 hash, 저장 실패, signed URL 발급 실패
- Safety: 차단 수, fallback 수, fidelity reject 수, human reject 수
- 리소스: 모델별 호출량, 이미지 생성 수, 평균 작업 시간, 메모리·큐 사용량

원본 이미지, 사용자 메모, 모델 raw response는 기본 로그에 기록하지 않는다. 장애 분석이 필요한 경우에도 제한된 보안 저장소와 보존 기간을 사용한다.

## 7. 평가 데이터셋과 평가 방법

### 7.1 골든셋 구성

초기 골든셋은 최소 다음 층으로 나눈다.

1. 단일 제품·균일 배경
2. 여러 제품이 함께 있는 세트/컬렉션
3. 반사·유리·금속처럼 분리가 어려운 제품
4. 전통 공예품·장식품
5. 배경이 복잡하거나 저해상도인 이미지
6. 추가 원본 구도가 0장, 1~3장, 4장 이상인 요청
7. 악성/무관 사용자 설명, 프롬프트 인젝션 문구가 포함된 요청

각 항목에는 원본 이미지, 허용 가능한 관찰 사실, 금지 주장, 정답 사진 역할, 필수 섹션, 사람이 검토한 레이아웃·카피 라벨을 둔다.

현재 저장소의 실제 입력 상태는 다음과 같다.

| 입력군 | 건수·구성 | 현재 상태 | 용도 |
|---|---|---|---|
| `cma_real_v1` | 공개 실물 JPEG 60건, 6개 영역 각 10건 | 파일·decode·hash·라이선스 표시 검증 완료; 권리 최종 확인·사람 라벨·모델 실행 대기 | 분석·렌더링 평가 후보 |
| `detail_page_eval_60` | 3상품 fixture, 42/9/9 단계 분할 | 계약·상태·멱등성 회귀용 | 통합 회귀 |

60건 CMA 입력은 총량 기준 50~200건 범위지만 영역별 50~200건 목표에는 미달한다. 두 최신
상세페이지 생성 결과(유리 잔·부채)는 [별도 smoke test 기록](../operations/local-generation-test-report.md)이며
정량 평가 분모에 포함하지 않는다.

### 7.2 핵심 평가 지표

목표값은 초기 운영 가설이며 골든셋 결과와 비용·지연을 측정한 뒤 확정한다.

| 영역 | 지표 | 측정 방법 | 초기 release gate |
|---|---|---|---:|
| 원본 보존 | source hash match | `source` 자산 SHA-256 일치율 | 100% |
| 원본 보존 | crop pixel equality | source crop과 결과 crop의 픽셀 동일율 | 100% |
| 원본 보존 | fidelity rejection leakage | `REJECTED` 자산이 렌더/FE/BE에 유입된 비율 | 0% |
| 분류 | product type accuracy | 사람 라벨과 top-1 일치율 | ≥ 90% |
| 분류 | craft precision | 전통 공예로 분류한 항목 중 적합 비율 | ≥ 95% |
| 사실성 | image-grounded claim precision | 카피 주장 중 이미지/자료로 입증된 비율 | ≥ 95% |
| 사실성 | unsupported claim rate | 미확인 소재·브랜드·원산지·효능 주장 비율 | ≤ 2% |
| 입력 근거 | creator-hint coverage | 상품 BE 검수 힌트가 필요한 카피에 반영된 비율 | ≥ 95% |
| 카피 | human copy score | 사실성·명료성·판매 적합성 5점 평가 | 평균 ≥ 4.0 |
| 레이아웃 | section completeness | 필수 섹션·순서·자산 링크 충족률 | 100% |
| 레이아웃 | broken asset rate | 열리지 않는 image URL 비율 | 0% |
| 이미지 | visual quality | 크롭·클리핑·배경 이질감 5점 평가 | 평균 ≥ 4.0 |
| 승인 | first-pass approval | 장인이 큰 수정 없이 승인한 비율 | ≥ 80% |
| 안정성 | job success rate | 재시도 후 정상 완료 비율 | ≥ 99% |
| 안정성 | backend delivery success | outbox 최종 적재 성공률 | ≥ 99.5% |
| 성능 | preview p95 | 초안 응답 또는 상태 확인까지 | 별도 부하 측정 |
| 성능 | final render p95 | 승인 후 PNG 생성 완료까지 | 별도 부하 측정 |
| 리소스 | local resource usage | 모델·렌더·저장 시간과 메모리 사용량 | 별도 부하 측정 |
| 안전 | release-blocking violation | 제품 변형·허위 핵심 주장·민감정보 유출 | 0건 |

### 7.3 평가 단계

- **자동 평가**: JSON Schema, DTO, React AST schema/tree/alias/image reference, hash, crop, URL, section manifest, policy lint
- **모델 평가**: 분류 정확도, claim evidence alignment, creator-hint coverage
- **이미지 평가**: fidelity validator, object/text safety classifier, broken asset 검사
- **사람 평가**: 장인/MD가 사실성·가독성·상품성·수정량을 5점 평가
- **운영 평가**: p50/p95 latency, queue age, retry, local resource usage
- **회귀 평가**: 모델·프롬프트·렌더러가 변경될 때 동일 골든셋을 재실행

### 7.4 합격 기준

다음 중 하나라도 발생하면 자동 게시하지 않고 사람 승인 또는 재처리 대상으로 보낸다.

- 제품 픽셀 보존 검증 실패
- 필수 JSON 필드 또는 섹션 누락
- 이미지에 없는 핵심 상품 속성 주장
- 상품 BE 검수 입력 없이 생성된 공예 역사·소재·인증 문구
- 배경판에 제품 유사 객체, 로고, 텍스트가 검출됨
- 악성 입력이 시스템 지시를 덮어쓴 흔적
- 원본·생성 자산·generation metadata 연결이 끊김

## 8. 안전성 정책 초안

### 8.1 정책 우선순위

안전성 정책은 판매 문구의 설득력보다 우선한다. 모델 출력이 정책과 충돌하면 더 보수적인 출력 또는 fallback을 선택한다.

### 8.2 제품 원본 보호

- 원본 파일을 읽기 전 SHA-256을 계산하고 결과와 함께 저장한다.
- `source`·`source_crop`·`source_composite` 제품 근거 자산은 원본 RGB와 원본에서 계산한 마스크로만 구성한다.
- 선택적인 `generated_scene`·`generated_view`는 원본을 시각 참고로 사용할 수 있지만, 생성 결과는 참고 자산으로만 표시하고 원본 근거·대표 상품 사진으로 승격하지 않는다.
- 원본 근거 자산에서 제품 색상·문양·형태가 바뀐 결과는 폐기한다. 생성 참고 자산의 정확성은 사람 검수 전까지 확정하지 않는다.
- 원본 손상, 마스크 실패, 배경 실패 시 원본 전체 이미지 또는 단색 배경으로 fallback한다.
- 운영 게시물에는 최종 자산의 source hash와 fidelity status를 감사 가능하게 남긴다.

### 8.3 사실성·표현 정책

허용:

- 사진에서 직접 확인되는 색상, 형태, 배치, 표면 반사, 구성품 수의 보수적 표현
- 상품 BE가 검수해 `user_hints`에 전달한 공예·재료·기법 설명
- 사용자가 제공한 제품명·제작 과정·관리 방법을 상품별 카피의 기준 데이터로 우선 반영한 표현

금지 또는 검토 필요:

- 이미지에서 확인되지 않는 정확한 소재, 도금, 제작 기법
- 브랜드, 장인, 제작자, 원산지, 시대, 진품성
- 내구성, 안전성, 기능, 효능, 용량, 성능 수치
- 실제 사용 가능 여부가 확인되지 않은 식기·식품 접촉·열 사용 문구
- 상품 BE 검수 없이 외부 지식이나 검색 결과를 근거로 가장하는 문구

모든 카피는 `image-visible`, `inferred`, `unknown` evidence를 근거로 생성하고, `unknown`은 상품 소개 문구가 아닌 주의사항으로 내린다.

### 8.4 공예품 정보 정책

- 전통 공예 후보 판정은 confidence와 이미지 근거를 함께 요구한다.
- 생성 중 외부 검색·원격 조사 모델을 호출하지 않는다.
- 상품 BE가 검수한 상품별 정보만 카피에 사용하고, 입력에 없는 고유 사실을 추가하지 않는다.
- 사람이 확인하지 않은 진품성·문화재·저작권·장인 이력 문구는 게시하지 않는다.

### 8.5 프롬프트 인젝션·입력 안전

이미지, OCR 텍스트, 사용자 설명은 모두 **데이터**이며 시스템 정책보다 우선하지 않는다.

- 이미지 속 글자나 사용자 메모가 “이전 지시를 무시하라”, “비밀을 출력하라”와 같은 지시를 포함해도 실행하지 않는다.
- 모델 입력에는 시스템 규칙, 데이터 경계, 출력 스키마를 명시한다.
- 사용자 입력 안의 지시문도 상품 데이터로만 취급하며 시스템 규칙을 바꾸지 못한다.
- URL fetch, 파일 경로, HTML/CSS 삽입은 allowlist·escape·sandbox로 제한한다.
- `react_document`는 모델이 직접 만들지 않고 서버 builder가 조립한다. 허용 tag·props·부모/자식
  관계·고유 ID·깊이/노드 수를 Pydantic으로 검증하며, `img`는 `props.imageId`만 사용한다.
- raw prompt와 raw model response를 FE나 상품 BE에 전달하지 않는다.

### 8.6 생성 배경 안전

- standalone 배경판은 제품 이미지 없이 생성한다. lifestyle/generated_view는 원본을 시각 참고로 사용할 수 있지만 생성 참고 자산으로 분리한다.
- 사람이 상품으로 오인할 수 있는 추가 용기, 로고, 글자, 브랜드 패턴, 손·얼굴 등 주 객체는 차단하거나 재생성한다.
- `source_composite` 합성 결과에는 배경 생성 여부와 제품 픽셀이 원본이라는 사실을 표시하고, 생성 참고 자산에는 `GENERATED`·`product_generated=true`·원본 hash를 표시한다.
- 배경 생성 모델이 정책을 반복 위반하면 해당 역할을 단색 배경으로 강등한다.

### 8.7 사람 승인과 게시

- AI 결과는 `DRAFT`로 간주하고 자동 게시하지 않는다.
- FE 편집 화면에서 장인이 문구와 레이아웃을 수정할 수 있어야 한다.
- 승인 요청에는 사용된 원본, draft, 모델·프롬프트 버전, 검증 결과를 연결한다.
- 승인 이후에는 분석·조사를 다시 호출하지 않고 승인된 draft만 재렌더링한다.
- 승인자, 승인 시각, 승인 전후 hash를 감사 로그에 기록한다.

### 8.8 보안·개인정보·보존

- 로컬 모델 API key는 사용하지 않으며, BE token은 `.env.example`, DTO, 로그, 이미지 metadata에 기록하지 않는다.
- MLX Serve는 loopback 주소에 바인딩하고, source/generated 자산은 로컬 job 경계 안에 보관한다.
- 원본 이미지는 업무상 필요한 기간만 보존하고, 만료 후 삭제 작업을 기록한다.
- signed URL은 짧은 TTL과 최소 권한으로 발급한다.
- 사용자 입력과 이미지는 tenant/job 경계를 넘지 않게 한다.
- 로컬 모델 서버에 전송되는 데이터와 저장 위치를 서비스 개인정보 정책에 명시한다.
- 삭제 요청 시 원본, 파생 컷, PNG, sections, thumbnails, metadata, outbox 재전송본까지 연쇄 삭제한다.

### 8.9 사고 등급과 대응

| 등급 | 예시 | 대응 |
|---|---|---|
| P0 | 제품이 변형된 이미지가 게시됨, credential/개인정보 유출 | 즉시 게시 차단·자산 회수·키 폐기·원인 분석 |
| P1 | 허위 핵심 상품 정보, 진품성·인증 오표기, 반복적인 unsafe background | 해당 모델/프롬프트 비활성화·사람 재검토·회귀셋 추가 |
| P2 | 레이아웃 깨짐, 누락된 섹션, signed URL 만료 | 자동 재시도·fallback·운영 티켓 |

모든 P0/P1은 모델 버전, prompt version, 입력 hash, 출력 hash, 검증 결과를 기준으로 재현 가능해야 한다.

## 9. 단계별 도입안

### Phase 0 — 현재 MVP 고정

- 현재 FastAPI + SQLite + local asset store 흐름 유지
- DTO, React AST, source fidelity, renderer, outbox 테스트를 release gate로 사용
- FE 자산 전달은 URL 또는 Base64 중 하나를 명시적으로 선택하고, 구조 출력은 `react_document`
  schema v2.0과 `imageId` manifest 해석을 함께 고정

### Phase 1 — 평가·안전 계측

- [CMA real v1 공개 실물 60건](../../data/evaluation/cma_real_v1/README.md)의 권리·정답 라벨을 마무리하고 분석/렌더링 실행
- [기존 60건 통합 fixture](../../data/evaluation/detail_page_eval_60.jsonl)는 API·상태·멱등성 회귀에 사용
- claim evidence 검사와 creator-hint coverage 검사 추가
- `react_document` schema/tree/alias/image reference 검사 추가
- 단계별 latency·retry·resource·fidelity metric 수집
- 승인 전 게시 차단과 감사 metadata 확인

### Phase 2 — 로컬 처리량 확장

- GPU 모델 호스트와 API/renderer 프로세스 분리
- SQLite lease 정책을 유지하면서 로컬 worker 수를 제한적으로 확장
- 모델 파일·출력 자산·로그 보존 정책을 로컬 디스크 기준으로 확정

### Phase 3 — 로컬 모델 게이트웨이

- MLX Serve와 Ollama를 동일한 local adapter로 연결
- Gemma/Flux 모델별 structured output·멀티모달·메모리·latency 비교
- 모델 변경 시 골든셋 회귀 평가와 canary 적용

### Phase 4 — 운영 최적화

- 이미지 수와 복잡도에 따른 모델 라우팅
- 반복 프롬프트·스키마 prefix cache 검토
- 렌더 worker와 모델 worker 독립 autoscaling
- 로컬 리소스 예산, rate limit, tenant quota, 품질 대시보드 운영

## 10. 결정이 필요한 항목

1. MLX Serve 단일 프로세스와 text/image 프로세스 분리 여부
2. 로컬 GPU 메모리 상한과 동시 생성 수
3. 배경 생성 실패 시 단색 fallback 수준
4. 최종 asset 전달: signed URL 중심인지, BE 내부 저장 후 FE URL만 제공할지
5. 목표 SLA와 로컬 작업 큐 상한
6. 원본·파생 자산의 보존 기간과 삭제 정책

## 11. 참고 문서

- [`docs/api/ai-dto-contract.md`](../api/ai-dto-contract.md)
- [`docs/api/react-json-output-contract.md`](../api/react-json-output-contract.md)
- [`docs/api/ai-fe-io-spec.md`](../api/ai-fe-io-spec.md)
- [`docs/operations/local-llm.md`](../operations/local-llm.md)
- [`docs/operations/server-memory-estimate.md`](../operations/server-memory-estimate.md)
- [`docs/operations/sglang-vllm-fit.md`](../operations/sglang-vllm-fit.md)
- [`docs/operations/local-generation-test-report.md`](../operations/local-generation-test-report.md)
- [`docs/superpowers/specs/2026-08-27-source-preserving-detail-page-design.md`](../superpowers/specs/2026-08-27-source-preserving-detail-page-design.md)

## 12. 초안 승인 기준

이 문서는 구현 명세가 아니라 운영 설계 초안이다. 다음 항목이 확정되면 별도 구현 계획으로 전환한다.

- 모델별 실제 local endpoint와 GPU 호스트
- 로컬 worker·파일 store·SQLite 운영 범위
- 평가 골든셋과 사람 검수자
- release gate의 목표값
- 개인정보·자산 보존 기간
- 사고 대응 책임자와 rollback 절차
