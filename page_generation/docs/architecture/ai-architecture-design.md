# 상세페이지 AI 아키텍처 설계

> 2026-09-16 검수: 로컬 Mac 개발은 FastAPI·SQLite·프로세스 내부 executor와 MLX Serve를 사용하고,
> 서버 운영은 Ubuntu `g6e.xlarge`의 Docker Compose·SGLang 2프로세스 구성을 사용한다.
> API/worker 분리는 로컬 확장안이며 현재 서버 경로는 `detail-page-ai`와 두 SGLang 서비스로 분리돼 있다.
> 승인 POST는 현재 동기 실행이다. 아래 승인 단계 목록은 논리 처리 순서이며 polling으로 각 단계가 노출된다는 보장이 아니다.
> 같은 날 Qwen3.8 27B + Flux2 Klein 4B 전용 로컬 endpoint로 2건의 생성 smoke test를 완료했다. 이 테스트는 기본 9B 모델 설정을 변경하지 않는다.
> 서버 GPU에서는 아직 실행하지 않았으므로 두 모델 동시 적재·4bit 파이프라인 로딩·편집 품질·처리 시간은 미검증이다.

## 구현과 설계의 차이

- 로컬 개발 기본 분석 설정은 MLX Serve Qwen3.8 27B이며, 이미지 생성은 MLX Serve Flux2다.
- 서버 운영 기본 설정은 SGLang 텍스트·비전 Qwen3.8 27B와 이미지 FLUX.2-klein 9B다.
- `app.build_service`와 local CLI는 로컬 어댑터를 사용하고, 서버 배포에서는 같은 클라이언트 계약으로 SGLang 어댑터를 사용한다.
- SourcePreservingProductPhotoGenerator는 선택 주입 시 lifestyle/generated_scene와 detail-02~05/generated_view를 허용한다.
  해당 자산은 `product_generated=true`, `fidelity_status=GENERATED`이며 원본 픽셀 보존을 보장하지 않는다.
  `hero`는 촬영 원본 그대로 `source_original`/`VERIFIED`를 사용하고, 누끼가 필요한 역할은 rembg 실패 시 `source`/`FALLBACK`으로 대체한다.
  생성 자산은 별도 화면 '참고용' 표시 없이 플래그와 provenance로 구분한다.
- 승인 API는 저장된 원본을 재사용한다. 업로드 파트는 현재 주 서비스에서 원본 교체에 사용되지 않는다.
- 순차 완료 후 승인 재전송은 결과를 재사용한다. 동시 요청의 승인 claim/원자적 잠금 보장은 별도 검증·구현이 필요하다.
- 생성 완료와 BE 적재 ACK, 상품 게시 상태를 구분한다. GET의 COMPLETED만으로 게시를 허용하지 않는다.
- 승인 결과는 사진 생성 후 달라질 수 있으므로 최종 PNG 확인·게시 승인은 BE 정책으로 별도 적용한다.
- FE 구조 출력은 `react_document` 제한형 JSON AST를 canonical 결과로 사용한다. 모델은 `page_plan`과
  카피를 반환하고, 서버의 `react_document_builder`가 검증된 draft에서 AST를 결정적으로 조립한다.

- 상태: 2026-09-16 현재 검수 기준
- 대상: 이미지 기반 상품 상세페이지 생성 시스템
- 기준 코드: `src/detail_page_ai`, `src/local_detail_page_ai`
- 설계 범위: 모델 구성, 데이터 흐름, 서빙 구조, 저장·재시도·관측성

## 1. 요약

이 시스템은 상품 원본 이미지와 장인이 제공한 상품별 설명을 받아 구조화된 상세페이지 초안을 만들고,
장인 승인 이후에만 최종 PNG를 생성한다. 제품 픽셀은 생성형 모델이 다시 그리지 않으며, 원본 RGB와
알파 마스크를 결정적으로 합성한다.

운영 호출 경계는 다음과 같다.

```text
FE → BE → AI API / Worker → BE → FE
```

FE는 AI를 직접 호출하지 않는다. BE는 인증·상품 식별·게시·저장을 소유하고, AI는 분석·초안·렌더링·
생성 결과 metadata를 제공한다.

## 2. 설계 원칙

1. 제품 원본 픽셀의 형태·색·무늬·구성품을 변경하지 않는다.
2. 이미지 관찰 사실과 장인 입력을 서로 다른 provenance로 보존한다.
3. FE가 소비하는 `react_document` 초안 JSON과 최종 게시 PNG를 분리한다.
4. 분석·배경·합성·렌더링을 독립적인 실패 경계로 나눈다.
5. 모델 교체는 공통 DTO와 provider adapter 뒤에서 수행한다.
6. 실패는 재시도 또는 보수적인 fallback으로 끝내며, 실패를 제품 재생성으로 보상하지 않는다.
7. `product_id`, `source_asset_id`, `job_id`, `request_id`, `generation_id`를 전 과정에 연결한다.

## 3. 목표와 비목표

### 3.1 목표

- 원본 이미지 1장 이상으로 제품 프로필과 한국어 상세페이지 draft를 생성한다.
- 제품 특성에 맞는 `layout_id`와 adaptive `page_plan`을 구성한다.
- 초안 단계에서 BE/FE가 `react_document` 제한 AST를 안전한 React 컴포넌트 allowlist로 미리보기한다.
- 승인 후 전체 상세페이지 PNG와 순서가 있는 섹션 PNG를 생성한다.
- 생성 결과를 BE에 멱등적으로 적재하고 재시작·재시도 시 이어서 처리한다.
- 모델·프롬프트·원본·결과 hash와 검증 결과를 추적한다.

### 3.2 비목표

- 상품 전체를 image-to-image로 다시 그리는 기능
- BE의 공개 FE API와 상품 DB 구현
- 이미지에서 확인되지 않는 브랜드·제작자·원산지·진품성·성능의 자동 확정
- 승인 전 최종 PNG 또는 생성형 제품 사진 게시

## 4. 논리 아키텍처

```text
┌──────────────┐       ┌─────────────────────┐
│ FE 입력/편집  │──────▶│ BE                  │
│ 이미지·힌트   │       │ 인증·상품·게시 소유  │
└──────────────┘       └──────────┬──────────┘
                                  │ private multipart + JSON metadata
                                  ▼
                    ┌────────────────────────┐
                    │ AI API / Job Service   │
                    │ FastAPI, stateless     │
                    └──────────┬─────────────┘
                               │ enqueue / claim
                               ▼
                    ┌────────────────────────┐
                    │ AI Worker               │
                    │ analysis·asset·validate │
                    │ retry·outbox            │
                    └──────┬──────┬──────┬────┘
                           │      │      │
                           ▼      ▼      ▼
                    Object Store Job DB  ApprovedDraft/page_plan
                    source/result outbox         │
                                                  ▼
                                  React JSON builder + validator
                                      ├─ FE result projection
                                      └─ BE metadata.react_document
                           │
                           ▼
                 ┌────────────────────────────┐
                 │ Renderer Worker             │
                 │ HTML/CSS + Playwright → PNG │
                 └─────────────┬──────────────┘
                               ▼
                             BE 적재
```

### 4.1 책임별 컴포넌트

| 컴포넌트 | 책임 | 현재 구현 | 운영 확장 |
|---|---|---|---|
| API | 인증, 업로드 검증, 작업 접수·조회 | FastAPI `app.py` | API Gateway/ALB 뒤 stateless API |
| Job service | 상태 전이, lease, idempotency | `DetailPageJobService` | 로컬 worker claim 확장 |
| Asset store | 원본·결과 저장 | `LocalFileAssetStore` | 로컬 파일 store 또는 NAS |
| AI worker | 로컬 분석, 검증, outbox 생성 | background executor | 별도 로컬 worker 프로세스 |
| Renderer | HTML/CSS 및 섹션 PNG 생성 | `HtmlDetailPageRenderer` | 별도 Playwright worker pool |
| React document builder | 승인 draft → 제한 AST 조립·스키마/보안 검증 | `react_document.py`, `react_document_builder.py` | 공통 FE schema/package로 공유 |
| Backend client | BE multipart 적재 | `BackendProductClient` | private network/mTLS 또는 내부 auth |
| Model gateway | timeout/retry/version | MLX Serve/Ollama local adapter, SGLang OpenAI-compatible adapter | 서버 SGLang 텍스트·이미지 프로세스와 로컬 MLX endpoint 분리 |

## 5. 모델 구성

하나의 모델 호출에 전체 책임을 몰지 않고, 근거와 실패 경계를 기준으로 모델을 분리한다.

| 단계 | 기본 후보 | 입력 | 출력 | 실패 시 |
|---|---|---|---|---|
| 이미지 분석 | 로컬 개발: `ddalcu/Qwen3.8-27B-MLX-Serve-4bit`; 서버: `cyankiwi/Qwen3.8-27B-AWQ-INT4` (SGLang `qwen-text`) | 원본 이미지, `user_hints` | `ProductProfileDto` | 제한 재시도 후 `FAILED` |
| 공예·제품 조사 | 자동 외부 조사 없음 | BE가 검수한 `user_hints` | 입력된 사실만 카피에 반영 | 미제공 내용은 `unknown`/보수적 문구 |
| 배경·참고 컷 생성 | 로컬 개발: `mlx-community/flux2-klein-9b-4bit`; 서버: `circulus/FLUX.2-klein-9B-bnb-4bit` (SGLang `flux-klein`) | 역할·배경 프롬프트, 선택적 원본 참고 | 제품 없는 배경판 또는 `GENERATED` 자산 | 중립 단색 배경 또는 해당 슬롯 원본 fallback |
| 제품 사진 합성 | 생성 모델 미사용, Pillow | 원본 RGB·mask·배경 | provenance 포함 `ProductPhoto` | 원본 컷 또는 해당 역할 제외 |
| React JSON 조립 | 생성 모델 미사용, deterministic builder | 검증된 `ApprovedDraftDto`·`page_plan` | `ReactDetailPageDocumentDto` | schema/tree 검증 실패 시 결과 차단 |
| 상세페이지 렌더 | 생성 모델 미사용, HTML/CSS + Playwright | 승인 draft·사진 | 전체/섹션 PNG | 렌더 재시도 또는 작업 실패 |

### 5.1 분석 모델

- 출력은 자유 텍스트가 아니라 `ProductProfileDto` Pydantic 검증을 통과해야 한다.
- `features[].evidence`는 `image-visible`, `inferred`, `unknown` 중 하나다.
- `classification_confidence`, `craft_confidence`는 라우팅 신호이지 사실의 증명이 아니다.
- 장인 입력의 제품명·제작 과정·관리법은 상품별 기준 데이터로 보존하고 카피에 우선 반영한다.
- 이미지에서 보이는 형태·색·문양·질감은 입력을 보완할 뿐, 미입력 상품 고유 사실을 만들지 않는다.
- 외부 검색은 호출하지 않는다. `ProductProfileDto`는 원본 이미지와 BE가 전달한
  `user_hints`만 근거로 생성한다.
- 최신성·출처가 필요한 내용은 BE가 사전 검수해 입력해야 하며, 추론 모델이 임의 URL이나
  상품 고유 사실을 만들어내지 않도록 한다.

### 5.2 조사 데이터 정책

- 이 서비스는 생성 중 외부 웹 검색이나 원격 조사 모델을 호출하지 않는다.
- 제작자·원산지·진품성·인증·정확한 소재·성능·최신 가격은 `user_hints`로 명시되지 않으면
  확정하지 않는다.
- BE가 전달한 검수 정보가 없거나 충돌하면 해당 문구를 제거하고 `unknown` 또는
  보수적인 표현으로 낮춘다.

### 5.3 이미지 생성 모델

이미지 모델의 역할은 제품 자체가 아니라 제품이 없는 배경판·활용 장면·생성 디테일 컷으로
한정한다. 로컬 개발은 MLX Serve Flux2를 사용하고, 서버 운영은 SGLang `flux-klein`을
사용한다. 생성 사진은 `product_generated=true`로 구분해 전달하며 화면의 별도 '참고용'
표시는 사용하지 않는다. 제품 없는 배경판은 제품 이미지 없이 생성하고, 선택적인 활용
장면·디테일 컷은 원본 이미지를 시각 참고로 전달할 수 있다.
생성 결과는 원본 상품 근거 자산으로 승격하지 않는다.

- 배경 프롬프트에 추가 제품, 제품과 유사한 주 피사체, 로고, 글자, 브랜드 패턴을 금지한다.
- 배경판은 객체·문자·로고 안전성 검사를 거친다.
- 검증 실패·timeout·provider 오류는 중립 배경으로 fallback한다.
- `hero`는 촬영 원본 그대로 `asset_mode=source_original`, `fidelity_status=VERIFIED`를 사용한다.
- `packshot`·대표 `detail`은 rembg(`birefnet-general`, `rembg==2.0.69`) 누끼와 원본 RGB/crop을 사용한다. 누끼 실패 또는 품질 검증 실패 시 해당 역할은 `source`/`FALLBACK`으로 안전하게 대체한다.
- 생성 `lifestyle`·추가 `detail`은 `product_generated=true`, `asset_mode=generated_scene/generated_view`, `source_sha256`, `fidelity_status=GENERATED`를 표시하고 허용된 생성 자산 슬롯에서만 사용한다.
- 제품 형태·색·문양·구성품이 바뀐 원본 근거 결과는 `REJECTED`로 분류하고 어떤 출력 경계에도 전달하지 않는다. 생성 참고 컷은 사람 검수 전까지 상품 사실성의 증거가 아니다.
- `RembgCutoutExtractor`는 rembg `birefnet-general` 세션을 재사용해 원본 RGB 기반 마스크를 만든다.
- 마스크가 비어 있거나 foreground 비율·경계 검증을 통과하지 못해 `extract`가 `None`을 반환하면 `SourcePreservingProductPhotoGenerator`는 `hero`를 촬영 원본으로, 나머지 제품 사진 역할을 `source`/`FALLBACK`으로 대체한다.
- `_product_scene_direction`는 제품 신호에 따라 장면 방향을 결정하며, 장신구 marker에는 `jewelry` 전용 근접 tabletop 방향을 사용하고 금속 일반 분기와 분리한다.

### 5.4 로컬 개발 모델

로컬 실행은 다음 두 모델을 고정 기본값으로 사용한다.

- 텍스트·비전·한국어 카피: `ddalcu/Qwen3.8-27B-MLX-Serve-4bit`
- 배경·활용 장면·생성 디테일: `mlx-community/flux2-klein-9b-4bit` (생성 사진은 `product_generated=true`로 구분)
- 기본 `PROMPT_VERSION`: `local-mlx-qwen-flux-v1`

두 모델은 `http://127.0.0.1:11234`의 MLX Serve에서 제공한다. 외부 검색·원격 모델·API
키는 사용하지 않으며, Ollama는 별도 로컬 검증 옵션으로만 허용한다.

### 5.5 서버 운영 모델

Ubuntu `g6e.xlarge`에서는 Docker Compose로 두 SGLang 프로세스를 구동한다.

- 텍스트·비전: `cyankiwi/Qwen3.8-27B-AWQ-INT4` → `qwen-text`, 포트 `30000`
- 이미지 생성·편집: `circulus/FLUX.2-klein-9B-bnb-4bit` → `flux-klein`, 포트 `30001`
- AI 서비스 provider: `LOCAL_TEXT_PROVIDER=sglang`, `LOCAL_IMAGE_PROVIDER=sglang`, `BACKGROUND_PROVIDER=sglang`
- SGLang 두 프로세스가 NVIDIA L40S 48GB 한 장을 나눠 쓴다. 두 서비스의 준비 상태는 `GET /v1/models`로 확인한다.

기동 명령과 고정 revision은 [Ubuntu 배포 가이드](../operations/ubuntu-deployment.md)와
[SGLang 서빙 운영 조사](../operations/sglang-serving-research.md)에 정리한다. 서버 GPU에서의
실제 실행·동시 적재·4bit 로딩·편집 품질·처리 시간은 아직 검증하지 않았다.

### 5.6 Flux2 Klein 4B 검증 프로파일

`Runpod/FLUX.2-klein-4B-mflux-4bit`는 메모리 절약형 비교·개발 테스트 모델이다. 11234의
기본 이미지 서버가 이 모델의 image modality를 제공하지 않아, 테스트 때만
`http://127.0.0.1:11235`에 전용 MLX Serve를 기동했다. 4B endpoint는 `200`과
`b64_json` 응답을 반환했고, 테스트 후 서버를 종료했다. 운영 기본값과 BE/FE DTO 계약은
변경하지 않는다. 실제 유리 잔·부채 2건의 결과와 한계는
[로컬 생성 테스트 기록](../operations/local-generation-test-report.md)에 남겼다.

## 6. 데이터 흐름

### 6.1 입력과 원본 저장

1. BE가 대표 원본 `product_image`와 반복 `product_images`를 전달한다.
2. AI API가 MIME, signature, 크기, decode 가능 여부를 검증한다.
3. 변환 전 원본을 content-addressed store에 저장하고 SHA-256을 계산한다.
4. `product_id`, `source_asset_id`, `request_id`, `idempotency_key`를 작업에 기록한다.

기본 제한은 이미지 한 장 10MB, 전체 이미지 최대 12장, 전체 요청 120MB이며 설정으로 조정할 수 있다.

### 6.2 초안 생성

```text
QUEUED → ANALYZING → EXTRACTING → DRAFT_READY
```

분석 결과는 `ProductProfileDto`로 저장하고, `ApprovedDraftDto`와 원본 preview reference를 구성한다.
AI는 실행 가능한 HTML/CSS/JSX를 전달하지 않는다. 서버가 검증된 `page_plan`과 draft에서
`react_document`를 조립·검증하고, BE/FE는 이 AST를 React 컴포넌트 allowlist로 미리보기한다.

### 6.3 승인 렌더링

```text
DRAFT_READY
  → 승인
  → GENERATING_BACKGROUNDS
  → COMPOSING
  → VERIFYING
  → RENDERING
  → DELIVERING
  → COMPLETED | FAILED
```

승인 시 저장된 profile과 승인 draft를 병합한다. 모델 분석이나 외부 호출을 다시 호출하지 않고,
`react_document`를 다시 조립·검증한 뒤 검증된 사진 자산과 HTML/CSS renderer로 전체 PNG 및
순서별 섹션 PNG를 만든다.

### 6.4 결과 적재

AI는 `AiToBePersistRequestDto` metadata와 다음 multipart 파일을 BE 적재 endpoint로 보낸다.

- `detail_page_image`: 전체 PNG
- `detail_page_section_NN`: 섹션 PNG
- `product_photo_NN`: fidelity 검증을 통과한 제품 사진

`generation_id`를 적재 멱등키로 사용한다. BE 저장 실패가 발생해도 생성 결과를 outbox에 보존하고,
최종 상태는 `COMPLETED_WITH_BACKEND_PENDING`으로 표시한다.

## 7. API와 DTO 경계

### 7.1 BE → AI

```http
POST /internal/v1/ai/detail-page-jobs
GET  /internal/v1/ai/detail-page-jobs/{job_id}
PUT  /internal/v1/ai/detail-page-jobs/{job_id}/draft
POST /internal/v1/ai/detail-page-renders
```

요청은 `X-AI-Internal-Token`을 요구하며, 작업 생성·승인은 `Idempotency-Key`와 metadata의
`idempotency_key`가 일치해야 한다. 방향별 DTO는 다음과 같다.

- `BeToAiCreateJobRequestDto`
- `BeToAiSaveDraftRequestDto`
- `BeToAiApproveDraftRequestDto`
- `AiToBeAcceptedResponseDto`
- `AiToBeStatusResponseDto`
- `AiToBeApprovedResponseDto`

### 7.2 FE projection

BE가 FE에 노출하는 projection은 `AiFeDraftDto`, `AiFeResultDto`, `AiFeJobStatusResponseDto`를
기준으로 한다. 초안은 `draft.react_document`, 최종 결과는
`result.detail_page.react_document`에 위치한다. FE는 `schemaVersion: "2.0"`의 AST를
컴포넌트 allowlist로 렌더링하고, `img.props.imageId`를 photos/asset manifest와 연결한다.
이미지 바이너리는 `image_url` 또는 `image_base64`를 deployment asset policy에 따라 사용하며,
React AST 안에 실제 URL을 직접 주입하지 않는다.

## 8. 서빙 구조

### 8.1 로컬 MVP

```text
Browser :4173
    └─ FastAPI :8000
        ├─ background executor
        ├─ SQLite job/repository/outbox
        ├─ local asset store
        ├─ MLX Serve Qwen + Flux local adapters
        ├─ React JSON builder + validator (in-process)
        └─ Playwright renderer
```

로컬 MVP는 API 계약, `react_document` schema/tree/image reference, source fidelity, HTML 렌더링,
재시작·멱등성·outbox를 검증하는 환경이다.
운영 트래픽이나 GPU 수평 확장을 목표로 하지 않는다.

### 8.2 서버 운영 (확정)

```text
FE
 │
 ▼
BE → detail-page-ai :8000 (CPU 전용)
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
       sglang-text :30000      sglang-image :30001
       qwen-text               flux-klein
       Qwen3.8-27B-AWQ-INT4    FLUX.2-klein-9B-bnb-4bit
              │                     │
              └──── NVIDIA L40S 48GB 1장 공유 ────┘
                         │
                  Docker Compose
```

서버는 AWS EC2 `g6e.xlarge` Ubuntu 단일 호스트에서 `deploy/Dockerfile`,
`deploy/docker/sglang-diffusion.Dockerfile`, `deploy/docker-compose.yml`로 기동한다. 텍스트·이미지
SGLang 서비스는 `GET /v1/models`로 준비 상태를 확인하며, AI 서비스는
`LOCAL_TEXT_PROVIDER=sglang`, `LOCAL_IMAGE_PROVIDER=sglang`, `BACKGROUND_PROVIDER=sglang`과
`qwen-text`/`flux-klein` 공개 모델명을 사용한다. 상세 기동 절차는
[Ubuntu 배포 가이드](../operations/ubuntu-deployment.md)를 따른다.

서버 GPU에서는 아직 실행하지 않았으므로 두 모델 동시 적재, 4bit 파이프라인 로딩, 편집
품질, 처리 시간과 실제 peak VRAM은 미검증이다.

### 8.3 로컬 개발 확장안

```text
FE
 │
 ▼
BE → AI API :8000 → 로컬 Job Worker
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
          SQLite      파일 저장소  MLX Serve :11234
          job/outbox  source/result  Qwen3.8 27B + Flux2 9B
                                      (4B 비교 시 임시 :11235)
                         │
                         ▼
                   Playwright renderer
                         │
                         ▼
                     BE 적재 API(선택)
```

로컬 개발에서는 API·worker와 MLX Serve를 같은 Mac 또는 로컬 장비에서 실행한다. `MLX`
provider와 `127.0.0.1:11234`는 서버 운영 provider가 아니며, 서버 SGLang 설정으로
대체되지 않는다.

권장 분리:

- API: 인증·검증·작업 접수·상태 조회를 수행한다.
- Worker: 로컬 분석·합성·검증·outbox를 수행한다.
- Renderer: 브라우저 프로세스와 로컬 모델 메모리를 분리한다.
- 로컬 MLX Serve: Qwen/Flux 모델을 loopback endpoint로 제공하고 요청 timeout을 적용한다.
- SQLite/파일 저장소: job, idempotency, generation metadata, outbox, 원본·결과를 보관한다.
- BE 적재: `BACKEND_URL`이 설정된 경우에만 선택적으로 호출한다.

## 9. 동시성·재시도·멱등성

- 동일 `generation_id`는 BE에 한 번만 적재한다.
- worker는 lease·heartbeat·owner fencing으로 stale worker의 덮어쓰기를 차단한다.
- 모델 endpoint 호출은 경로(로컬 MLX 또는 서버 SGLang)에 맞는 단계별 timeout과 제한된 exponential backoff를 사용한다.
- 입력·스키마·정책 위반은 무조건 재시도하지 않고 원인별로 실패 처리한다.
- 로컬 worker lease는 최대 예상 작업 시간보다 길게 설정하고 stale worker 재획득을 제한한다.
- 같은 `Idempotency-Key`와 같은 payload는 기존 작업·결과를 재사용하고, 다른 payload는 `409`로 거절한다.

## 10. 보안과 관측성

### 10.1 보안

- AI 내부 토큰은 BE와 AI만 보유하며 FE에 전달하지 않는다.
- 모델 API key와 raw prompt, raw model response를 로그·DTO·이미지 metadata에 넣지 않는다.
- 업로드 경로는 project/object-store 경계를 벗어나지 않게 검증한다.
- FE 미리보기는 JSON allowlist와 HTML escape를 사용하며 임의 HTML/CSS/script를 수용하지 않는다.
- `react_document`는 허용 tag·부모/자식 관계·고유 ID·최대 20단계/300노드·safe URL·`imageId`
  규칙을 서버에서 검증하고, FE는 camelCase 키와 asset manifest를 사용한다.
- 원본·생성 자산은 tenant/job 경계를 넘지 않게 하고 signed URL은 짧은 TTL로 제한한다.

### 10.2 관측성

모든 비민감 metric과 trace에 `request_id`, `job_id`, `generation_id`, `provider`, `model`, `prompt_version`을 남긴다.

- API: 요청 수, 4xx/5xx, 업로드 크기, queue wait
- Worker: 단계별 latency, retry, timeout, queue age
- Model: 호출 수, token, schema failure, provider error
- Asset: 원본·결과 hash, fidelity reject, 저장·URL 오류
- 운영: outbox pending, backend ACK, 로컬 모델 메모리·대기열·작업 시간

## 11. 단계별 도입안

### Phase 0 — MVP 고정

- 현재 FastAPI·SQLite·local asset store·Playwright 흐름 유지
- DTO, React AST, fidelity, renderer, outbox 테스트를 release gate로 사용

### Phase 1 — 평가·안전 계측

- [CMA real v1 공개 이미지 60건](../../data/evaluation/cma_real_v1/README.md)으로 분석·렌더링 평가 시작
- [기존 60건 통합 fixture](../../data/evaluation/detail_page_eval_60.jsonl)는 API 계약 회귀에 사용
- claim evidence, creator-hint coverage, fidelity, latency, retry 지표 수집
- `react_document` schema/tree/alias/image reference 지표 수집
- 승인 전 게시 차단과 감사 metadata 검증

### Phase 2 — 서버 운영 검증

- Ubuntu `g6e.xlarge`에서 Docker Compose 3서비스와 SGLang 2프로세스의 기동·헬스체크를 확인
- GPU에서 두 모델 동시 적재, 4bit 파이프라인 로딩, 편집 품질, 처리 시간과 peak VRAM을 검증
- SQLite lease 정책과 모델 파일·출력 자산·로그 보존 정책을 서버 디스크 기준으로 확정

### Phase 3 — 로컬·서버 모델 게이트웨이

- 로컬 MLX Serve/Ollama와 서버 SGLang의 structured output·멀티모달·메모리·latency를 동일 골든셋으로 비교
- 모델·프롬프트 변경 시 canary와 회귀 평가를 거친다.

## 12. 결정 필요 항목

1. 서버 GPU에서 두 SGLang 프로세스의 실제 peak VRAM·동시성·처리 시간
2. GPU 검증 후의 서버 SLA와 worker 동시성
3. 배경 생성 실패 시 단색 fallback 수준
4. signed URL과 BE 내부 저장의 최종 asset 전달 방식
5. 서버 작업 큐 상한과 사용자별 quota
6. 원본·파생 자산 보존 기간과 삭제 전파 범위

## 13. 참고 문서

- [`ai-evaluation-and-safety-policy.md`](ai-evaluation-and-safety-policy.md)
- [`docs/api/ai-dto-contract.md`](../api/ai-dto-contract.md)
- [`docs/api/react-json-output-contract.md`](../api/react-json-output-contract.md)
- [`docs/api/ai-fe-io-spec.md`](../api/ai-fe-io-spec.md)
- [`docs/operations/local-llm.md`](../operations/local-llm.md)
- [`docs/operations/sglang-vllm-fit.md`](../operations/sglang-vllm-fit.md)
- [`2026-09-09 파일럿 평가 보고서`](../evaluation/pilot-report-2026-09-09.md)
