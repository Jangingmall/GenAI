# Image Detail Page AI

상품 원본 이미지에서 설명과 특징을 분석하고, 원본 제품 픽셀을 보존한 제품 사진과 FE 렌더링용 제한형 React JSON AST를 만드는 AI 서비스입니다. 입력 직후에는 실행 가능한 HTML/JSX가 아닌 구조화된 draft와 `react_document`를 BE에 반환하고, BE/FE가 미리보기를 렌더링합니다. 장인 승인 시에만 AI 내부 HTML/CSS 렌더러로 최종 PNG와 섹션 PNG를 생성합니다.

> 2026-09-16 현재 구현 기준: FE가 소비하는 정식 구조 산출물은 `react_document`이며, `page_plan`은 모델·편집·하위 호환용 입력으로 유지합니다. React AST는 서버가 검증된 draft에서 결정적으로 조립하고, 모델이 임의 JSX·HTML·CSS를 반환하지 않습니다.

> 추론 경로는 두 가지입니다. Mac 로컬 개발은 MLX Serve(`127.0.0.1:11234`)를 사용하고, 서버 운영은 Ubuntu `g6e.xlarge`에서 SGLang 텍스트·이미지 서버(`30000`/`30001`)를 사용합니다. **서버 GPU 에서는 아직 한 번도 실행되지 않았으며**, 두 모델 동시 적재와 4bit 파이프라인 실측은 미검증 상태입니다.

대표 `hero`는 촬영 원본 그대로(`asset_mode=source_original`, `fidelity_status=VERIFIED`) 사용합니다. `packshot`과 `detail`은 rembg(`birefnet-general`, `rembg==2.0.69`) 누끼·원본 crop/합성 경로를 사용하고, 누끼가 실패하면 원본 자산(`source`, `FALLBACK`)으로 되돌립니다. lifestyle과 추가 detail은 원본을 시각 참고로 넣은 Flux2 편집 결과일 수 있으며, `product_generated=true`와 `asset_mode`로 구분하고 원본 상품 근거로 승격하지 않습니다. 생성 사진에 화면상의 별도 '참고용' 표시는 붙이지 않습니다.

## 기본 처리 흐름

```text
FE 원본 이미지
  → 원본 파일 저장 + SHA-256
  → 텍스트·비전 추론 (로컬 개발: MLX Serve / 서버 운영: SGLang)
  → DRAFT_READY: JSON draft + 제한형 react_document 반환·수정 저장
  → 장인 승인
  → rembg 누끼 추출 (파편화·신뢰 불가 시 원본 fallback, RGB 생성 금지)
  → 배경·연출 추론 (로컬 개발: MLX Serve / 서버 운영: SGLang)
  → 원본 RGB + 배경 결정적 합성
  → 원본 SHA-256·crop·composite 픽셀 fidelity 검증
  → 승인된 draft → React JSON AST 조립·검증 → FE 결과
  → 내부 HTML/CSS + Playwright 전체/섹션 PNG (승인 시 1회)
  → FE 결과 + BE multipart(outbox에 react_document 포함)
```

상품별 상세페이지 레이아웃은 사용자가 고르는 고정 템플릿이 아니라 이미지 분석 결과의
`layout_id` 추천을 사용합니다. 이미지 중심 제품은 `image-first`, 공예·장식품은
`editorial-split`, 소형 제품·세트류는 `catalog-grid`로 구성하며, 판단이 불확실하면
`editorial-split`으로 안전하게 fallback합니다.

## 프로젝트 구조

```text
assets/       입력 샘플·참고 자료·ComfyUI 워크플로
src/          운영 파이프라인과 로컬 LLM 파이프라인
web/          AI 입력·상세페이지 미리보기 화면
scripts/      실행·렌더링·브라우저 테스트 스크립트
tests/        Python 구조·도메인 테스트
docs/         API·운영·참고 문서 ([문서 안내](docs/README.md))
generated/    샘플·실험·미리보기·검증 결과
.local/       모델·SQLite·로컬 런타임 상태
```

입력 샘플과 참고 PDF/이미지는 `assets/`, 실행으로 만들어진 파일은 `generated/`에
저장합니다. 모델과 로컬 상태가 들어 있는 `.local/`, 개발 의존성이 들어 있는 `.venv/`와
`node_modules/`는 프로젝트 소스와 분리된 실행 환경으로 유지합니다.

상세페이지 생성 스타일은 `assets/references/detail-page-guide/`의 색상·타이포그래피·이미지
무드·레이아웃 가이드를 `src/detail_page_ai/reference_guide.py`에 버전 고정해 반영합니다.
가이드는 방향으로만 사용하며, 샘플 문구·상품명·정확한 화면을 복사하지 않습니다.

FE 구조 출력은 [`src/detail_page_ai/react_document.py`](src/detail_page_ai/react_document.py)의
제한형 DTO와 [`src/detail_page_ai/react_document_builder.py`](src/detail_page_ai/react_document_builder.py)의
결정적 builder가 담당합니다. 최종 JSON은 `schemaVersion: "2.0"`, `canvasWidth`, `root[]`를
사용하며, 이미지 노드는 실제 URL 대신 `props.imageId`로 자산을 참조합니다.

기본 사진 역할은 다음 네 가지입니다.

- `hero`: 촬영 원본 그대로 (`source_original`, `VERIFIED`)
- `packshot`: rembg 원본 누끼 + 흰 배경 (`source_composite` 또는 실패 시 `source`, `FALLBACK`)
- `detail`: 원본 이미지 실제 영역 크롭
- `lifestyle`: 원본 이미지를 참조한 Flux2 프롬프트 기반 활용 장면(`generated_scene`, `product_generated=true`)

`scale`은 `PRODUCT_PHOTO_SHOTS`에 명시했을 때만 추가됩니다. `alternate`는 단일 이미지에서 생성하지 않으며, FE가 반복 multipart 필드 `product_images`로 추가 원본 구도를 보냈을 때만 사용합니다.

현재 레이아웃은 `hero`, `packshot`, `detail`, `lifestyle` 네 가지 사진 역할을 사용합니다. 원본이 적을 때는 `detail`, `detail-02`처럼 서로 다른 실제 원본 영역을 deterministic crop으로 뽑아 상세 컷에 배치합니다. 존재하지 않는 뒷면·측면을 생성하지 않습니다.
원본이 1~3장이면 부족한 역할을 원본 픽셀 보존 방식으로 보완하고, 4장 이상이면 보완
생성을 건너뛰고 업로드된 원본을 역할에 직접 배치합니다. `scale`을 켜면 5번째 원본부터
크기 참고 역할에 배치하고, 남는 원본은 `alternate`로 보존합니다.

누끼 추출(`src/detail_page_ai/source_photos.py`)은 rembg의 `birefnet-general` 모델(rembg==2.0.69)을 사용합니다. 누끼가 실패하거나 품질 조건을 통과하지 못하면 `hero`는 촬영 원본(`source_original`, `VERIFIED`)을 유지하고 다른 원본 역할은 `source`/`FALLBACK`으로 안전하게 대체합니다. 프롬프트 편집이 실패하면 원본 이미지 또는 중립 배경 합성으로 fallback합니다. `generated_scene`/`generated_view`는 허용된 생성 자산이며 `product_generated=true`로 구분하고, 화면에는 별도 '참고용' 라벨을 붙이지 않습니다. 최종 상품 근거는 원본 보존 자산으로 확인합니다.

## 로컬 실행 (Mac · MLX Serve)

이 절은 Mac 로컬 개발 구성에만 해당합니다. 서버 운영 구성은 [Ubuntu 배포 가이드](docs/operations/ubuntu-deployment.md)의 SGLang 경로를 사용합니다.

```bash
cp local.env.example .env
.venv/bin/python -m pip install -e '.[dev]'
npm install
npx playwright install chromium
serve-ai
```

`serve-ai`와 `scripts/runtime/run_local_detail_page.py`는 모두 `127.0.0.1:11234`의 MLX Serve를
사용합니다. MLX Serve를 먼저 실행하고 Qwen과 Flux 모델을 같은 인스턴스에서 제공해야 합니다.
이 서비스는 클라우드 모델 SDK나 credential을 읽지 않습니다. 기존 `.env`에
클라우드 provider 설정이 남아 있으면 `ANALYSIS_PROVIDER=local`로 정리하고 로컬 설정으로
교체합니다.

```bash
"/Applications/MLX Core.app/Contents/MacOS/mlx-serve" serve \
  --model ~/.mlx-serve/models/ddalcu/Qwen3.8-27B-MLX-Serve-4bit \
  --host 127.0.0.1 \
  --port 11234
```

주요 기본값:

```dotenv
ANALYSIS_PROVIDER=local
PROMPT_VERSION=local-mlx-qwen-flux-v1
LOCAL_TEXT_PROVIDER=mlx
LOCAL_TEXT_URL=http://127.0.0.1:11234
LOCAL_TEXT_MODEL=ddalcu/Qwen3.8-27B-MLX-Serve-4bit
LOCAL_IMAGE_PROVIDER=mlx
LOCAL_IMAGE_URL=http://127.0.0.1:11234
LOCAL_IMAGE_MODEL=mlx-community/flux2-klein-9b-4bit
BACKGROUND_PROVIDER=mlx
PRODUCT_PHOTO_GENERATION=source
PRODUCT_PHOTO_SHOTS=hero,packshot,detail,lifestyle
DETAIL_PAGE_RENDERER=html
ASSET_STORE_DIR=.local/detail-page-ai/assets
SQLITE_PATH=.local/detail-page-ai/state.sqlite3
RESPONSE_ASSET_MODE=base64
CRAFT_CONFIDENCE_THRESHOLD=0.65
SOURCE_PHOTO_VARIATION_THRESHOLD=4
MAX_SOURCE_IMAGES=12
MAX_REQUEST_BYTES=125829120
MAX_PENDING_GENERATIONS=100
MAX_DELIVERY_ATTEMPTS=8
ENABLE_LEGACY_DEMO_API=false
```

`PRODUCT_PHOTO_GENERATION`은 `source`만 허용합니다. 제품 전체를 생성형 모델로 다시
그리는 설정은 제공하지 않습니다.
`BACKGROUND_PROVIDER=mlx`는 제품 없는 배경·활용 장면·추가 디테일 컷에만 Flux를 사용합니다.
`hero`는 촬영 원본을 그대로 보존하고, `packshot`·대표 `detail`은 원본 RGB와 결정적 Pillow
합성으로 제품 픽셀을 보존합니다.
Flux2가 만든 `lifestyle`·추가 detail은 생성 자산으로만 취급하며 `GENERATED`, `product_generated=true`와 원본 hash를
표시합니다. GPU/모델 서버를 사용하지 않으려면 `LOCAL_IMAGE_PROVIDER=none`과 `BACKGROUND_PROVIDER=none`을 함께 설정할 수
있으며, 이 경우 중립 배경 fallback만 사용합니다.

## API

운영 구조는 `FE → BE → AI → BE → FE`입니다. FE 화면의 작품 이름·제작 과정·관리법은
BE가 `user_hints`로 묶어 AI에 전달하며, AI는 BE의 내부 호출만 받습니다. BE
API와 DB는 이 AI 저장소의 구현 범위가 아닙니다.

제품 분석은 외부 검색엔진을 호출하지 않습니다. 선택한 로컬 MLX 또는 서버 SGLang의 Qwen은 입력 이미지와 BE가
전달한 `user_hints`만 사용하며, 검색 출처·실시간 가격·제작자·원산지·진품성·정확한
소재·성능을 자동으로 확정하지 않습니다. 최신성이나 출처가 필요한 내용은 BE가
검수한 뒤 `user_hints`로 전달해야 합니다.

- `GET /health`
  - liveness 헬스체크. 무인증 HTTP 200(`{"status": "ok"}`) 반환
- `GET /health/ready`
  - readiness 헬스체크. 무인증 HTTP 200(`{"status": "ok", "components": {...}}`) 또는 서비스 불능 시 503(`{"status": "not_ready", "reason": ..., "components": ...}`) 반환
- `POST /internal/v1/ai/detail-page-jobs`
  - BE 전용. `product_image`, 반복 `product_images`, `metadata` JSON
  - `metadata.product_id`와 `source_asset_id`를 작업·결과·적재 요청에 보존
- `GET /internal/v1/ai/detail-page-jobs/{job_id}`
  - BE 전용 상태·결과 polling
- `PUT /internal/v1/ai/detail-page-jobs/{job_id}/draft`
  - 장인 문구 수정 저장. `draft`와 재조립 가능한 `react_document` 기준만 갱신하고 AI/PNG 생성을 호출하지 않음
- `POST /internal/v1/ai/detail-page-renders`
  - BE 전용. 장인이 수정한 `draft` JSON과 원본 이미지로 최종 PNG 생성
  - 분석 AI를 다시 호출하지 않고 승인 draft에서 `react_document`를 재조립·검증한 뒤 HTML/CSS + Playwright로 전체·섹션 PNG 생성
- `BACKEND_PRODUCT_URL`
  - AI가 BE로 생성 메타데이터·전체 PNG·섹션·제품 사진을 전달하는 적재 endpoint

내부 API는 `AI_INTERNAL_AUTH_TOKEN`과 `X-AI-Internal-Token`을 사용합니다. 로컬 데모 페이지는
BE가 없으므로 기존 `/api/v1/ai/*` direct 경로를 호환용으로 사용합니다. 자세한 DTO는
[`docs/api/ai-dto-contract.md`](docs/api/ai-dto-contract.md)를, FE React JSON 상세 계약은
[`docs/api/react-json-output-contract.md`](docs/api/react-json-output-contract.md)를 참고합니다.

### React JSON 출력

`react_document`는 FE가 자체 React 컴포넌트 allowlist로 렌더링하는 제한형 JSON AST입니다.
초안 응답은 `draft.react_document`, 최종 결과는 `result.detail_page.react_document`,
AI→BE 적재 metadata는 `detail_page.react_document`에 같은 문서를 담습니다. 허용 태그,
부모·자식 관계, 링크·이미지 참조, 구조화 style/layout, 노드 수·깊이는 서버 Pydantic DTO가
검증합니다. FE는 `dangerouslySetInnerHTML`, 이벤트 핸들러, raw CSS/JSX 문자열을 사용하지
않으며, `imageId`를 자산 manifest의 URL 또는 로컬 경로로 해석합니다.

로컬 runner는 `react_document.json`을 `detail_page.png`, `sections/`, `photos/`와 함께
저장합니다. HTML/CSS는 이 JSON을 FE가 렌더링하는 계약이 아니라, 승인 후 PNG를 만들기 위한
AI 내부 renderer 입력으로만 사용합니다.

작업 상태:

```text
QUEUED → ANALYZING → EXTRACTING → DRAFT_READY
→ (승인) GENERATING_BACKGROUNDS → COMPOSING → VERIFYING
→ RENDERING → DELIVERING → COMPLETED | FAILED
```

FE·BE·AI 경계 계약은 [`docs/api/ai-dto-contract.md`](docs/api/ai-dto-contract.md), FE 화면 명세는 [`docs/api/ai-fe-io-spec.md`](docs/api/ai-fe-io-spec.md), 로컬 모델 실행은 [`docs/operations/local-llm.md`](docs/operations/local-llm.md), 전체 설계·평가·안전성 기준은 [`docs/architecture/ai-architecture-and-safety.md`](docs/architecture/ai-architecture-and-safety.md)를 참고합니다.

## 로컬 영속성

- 원본·결과 자산: `ASSET_STORE_DIR`의 SHA-256 content-addressed 파일 저장소
- 작업·BE outbox: `SQLITE_PATH`
- 재시작 시 중단 작업은 `QUEUED`로 복구
- 렌더링 전에 고정 `generation_id`와 전체 결과를 outbox에 먼저 저장
- SQLite lease claim·heartbeat·owner fencing으로 같은 작업/BE 전송의 동시 실행과 stale worker 덮어쓰기 차단
- 실행 중 worker가 종료된 `DELIVERING` 항목은 lease 만료 시 예약 callback으로 재전송
- BE 실패 결과는 재시작 후에도 같은 `generation_id`로 재전송
- URL을 제공하는 운영 자산 저장소에서는 `RESPONSE_ASSET_MODE=url`로 Base64 중복을 제거

Mac 로컬 개발은 로컬 파일/SQLite와 MLX Serve 모델 서버를 기준으로 하고, 서버 운영은 Ubuntu Docker Compose와 SGLang 모델 서버를 기준으로 합니다. BE 적재 URL은 선택적으로 사용할 수 있으며, 외부 모델 API·검색 API·클라우드 credential은 호출하지 않습니다. Flux2 Klein 4B 전용 endpoint를 사용한 실제 2건 생성 기록은 [`docs/operations/local-generation-test-report.md`](docs/operations/local-generation-test-report.md)에 정리되어 있고, 이미지 생성 기본값은 두 경로 모두 9B 모델입니다.

## 서버 배포 (Ubuntu · SGLang)

서버 운영은 AWS EC2 `g6e.xlarge`(NVIDIA L40S 48GB, Ubuntu) 단일 호스트에서 Docker Compose로 `detail-page-ai`(CPU 전용, `8000`), `sglang-text`(Qwen 텍스트·비전, `30000`), `sglang-image`(FLUX 이미지 생성·편집, `30001`)를 구동하는 SGLang 확정 구성입니다. EKS 배포를 위해 단일 GPU에서 3개 서비스를 통합 실행하는 단일 컨테이너 이미지(`sglang/Dockerfile`, `sglang/entrypoint.sh`) 구성도 함께 제공합니다. 텍스트 모델은 `cyankiwi/Qwen3.8-27B-AWQ-INT4`를 `qwen-text`로, 이미지 모델은 `circulus/FLUX.2-klein-9B-bnb-4bit`를 `flux-klein`으로 노출하며, AI 서비스는 `LOCAL_TEXT_PROVIDER=sglang`, `LOCAL_IMAGE_PROVIDER=sglang`, `BACKGROUND_PROVIDER=sglang`과 해당 공개 모델명을 사용합니다. 자세한 기동·헬스체크·메모리 예산은 [Ubuntu 배포 가이드](docs/operations/ubuntu-deployment.md)를 따릅니다.

현재 Mac 로컬에서 `docker compose config`, 서비스 이미지 arm64 빌드·기동·healthy 상태와 amd64 빌드는 확인했지만, **서버 GPU 에서는 아직 한 번도 실행되지 않았으며**, 두 SGLang 프로세스 동시 적재·4bit 파이프라인·편집 품질·처리 시간은 첫 배포 실측을 통해 확인해야 합니다.

## 내부 HTML/CSS → PNG 렌더링

```bash
PYTHONPATH=src .venv/bin/python scripts/runtime/build_detail_page_html.py \
  --image assets/samples/najeon-box.jpeg \
  --profile generated/samples/najeon_box_profile.json \
  --output generated/verified/source_safe_detail_page.html

npm run render:detail-page -- \
  generated/verified/source_safe_detail_page.html \
  generated/verified/source_safe_detail_page.png \
  --sections generated/verified/source_safe_sections
```

역할 매핑은 명시적입니다.

- hero → `hero`
- wide view → `packshot`
- detail sections/gallery → `detail`
- usage → `lifestyle`
- scale reference → `scale`

역할이 없으면 primary 원본을 사용하며 `alternate`를 암묵적으로 대신 사용하지 않습니다.

## 평가 파이프라인

실제 공개 이미지 기반 정량·정성 평가 체계와 회귀 방지 품질 게이트를 제공합니다.

- **평가 데이터셋**: [`data/evaluation/cma_real_v1`](data/evaluation/cma_real_v1) (클리블랜드 미술관 소장품 6개 카테고리 × 10건, 총 60건)
- **파일럿 실행**: `scripts/run_eval_pilot.py` (카테고리당 1건씩 6건, `asset_id` 오름차순 결정적 선정 순차 실행)
- **품질 게이트**:
  - `scripts/check_cutout_fidelity.py`: 원본 대비 컷아웃 제품 픽셀 보존율(fidelity) 검증 (심각 손실 또는 산출물 누락 발생 시 종료 코드 1)
  - `scripts/check_scene_direction_coverage.py`: 카테고리별 배경 씬 연출 분기 매핑 및 기본값·오분류 검증 (기본값 또는 오분류 발생 시 종료 코드 1)
- **사람 검수**: `scripts/build_review_sheet.py`로 4대 축(사실성·명료성·상품성·시각품질) 검수 CSV 시트 생성, 평가 기준은 [`docs/evaluation/human-review-guide.md`](docs/evaluation/human-review-guide.md)
- **실행 기록**: 1차 파일럿 결과는 [`docs/evaluation/pilot-report-2026-09-09.md`](docs/evaluation/pilot-report-2026-09-09.md)에 기록

## 테스트

```bash
uv run pytest -q
# 또는
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q src scripts tests
```

전체 358개 단위 테스트가 외부 모델 호출 없이 payload, 배경 안전성 판정, 원본 해시와 crop/composite 픽셀 출처, deterministic hash, 역할 매핑, React AST 스키마·안전성·camelCase 직렬화, 로컬 `react_document.json` 산출, SQLite lease claim·재시작 복구, outbox 선저장·멱등 재전송과 FE/BE DTO를 검증합니다.
