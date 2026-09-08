# Image Detail Page AI

상품 원본 이미지에서 설명과 특징을 분석하고, 원본 제품 픽셀을 보존한 제품 사진과 FE 렌더링용 제한형 React JSON AST를 만드는 AI 서비스입니다. 입력 직후에는 실행 가능한 HTML/JSX가 아닌 구조화된 draft와 `react_document`를 상품 BE에 반환하고, 상품 BE/FE가 미리보기를 렌더링합니다. 장인 승인 시에만 AI 내부 HTML/CSS 렌더러로 최종 PNG와 섹션 PNG를 생성합니다.

> 2026-09-08 최신 구현 기준: FE가 소비하는 정식 구조 산출물은 `react_document`이며, `page_plan`은 모델·편집·하위 호환용 입력으로 유지합니다. React AST는 서버가 검증된 draft에서 결정적으로 조립하고, 모델이 임의 JSX·HTML·CSS를 반환하지 않습니다.

대표·팩샷·디테일은 **생성형 모델이 제품을 다시 그리지 않고 원본 이미지를 그대로 사용**합니다. lifestyle과 추가 detail은 원본을 시각 참고로 넣는 Flux2 프롬프트 편집으로 활용 장면·디테일을 만들 수 있으며, 세부 형태 보존 지시와 낮은 편집 강도를 적용합니다. 이 결과는 `generated_scene`/`generated_view` 참고용 이미지로 표시하고 원본 hash를 연결하지만, 제품 형태·색·구성품의 정확한 근거로 승격하지 않습니다.

## 기본 처리 흐름

```text
FE 원본 이미지
  → 원본 파일 저장 + SHA-256
  → 로컬 MLX Serve Gemma 12B 상품 분석
  → DRAFT_READY: JSON draft + 제한형 react_document 반환·수정 저장
  → 장인 승인
  → 알파 마스크 추출(RGB 생성 금지)
  → 로컬 MLX Serve Flux2 제품 없는 배경·참고 컷 생성
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

- `hero`: 원본 컷아웃 + 중립 배경
- `packshot`: 원본 컷아웃 + 흰 배경
- `detail`: 원본 이미지 실제 영역 크롭
- `lifestyle`: 원본 이미지를 참조한 Flux2 프롬프트 기반 활용 장면(`generated_scene`, 참고용)

`scale`은 `PRODUCT_PHOTO_SHOTS`에 명시했을 때만 추가됩니다. `alternate`는 단일 이미지에서 생성하지 않으며, FE가 반복 multipart 필드 `product_images`로 추가 원본 구도를 보냈을 때만 사용합니다.

현재 레이아웃은 `hero`, `packshot`, `detail`, `lifestyle` 네 가지 사진 역할을 사용합니다. 원본이 적을 때는 `detail`, `detail-02`처럼 서로 다른 실제 원본 영역을 deterministic crop으로 뽑아 상세 컷에 배치합니다. 존재하지 않는 뒷면·측면을 생성하지 않습니다.
원본이 1~3장이면 부족한 역할을 원본 픽셀 보존 방식으로 보완하고, 4장 이상이면 보완
생성을 건너뛰고 업로드된 원본을 역할에 직접 배치합니다. `scale`을 켜면 5번째 원본부터
크기 참고 역할에 배치하고, 남는 원본은 `alternate`로 보존합니다.

프롬프트 편집이 실패하면 원본 이미지 또는 중립 배경 합성으로 fallback합니다. `generated_scene`은 `lifestyle` 슬롯에서만 허용하는 참고용 이미지이며, FE/BE DTO에 생성형 자산임을 표시합니다. 최종 상품 근거는 항상 원본 `hero`, `packshot`, `detail` 자산으로 확인합니다.

## 로컬 실행

```bash
cp local.env.example .env
.venv/bin/python -m pip install -e '.[dev]'
npm install
npx playwright install chromium
serve-ai
```

`serve-ai`와 `scripts/run_local_detail_page.py`는 모두 `127.0.0.1:11234`의 MLX Serve를
사용합니다. MLX Serve를 먼저 실행하고 Gemma와 Flux 모델을 같은 인스턴스에서 제공해야 합니다.
이 서비스는 클라우드 모델 SDK나 credential을 읽지 않습니다. 기존 `.env`에
클라우드 provider 설정이 남아 있으면 `ANALYSIS_PROVIDER=local`로 정리하고 로컬 설정으로
교체합니다.

```bash
"/Applications/MLX Core.app/Contents/MacOS/mlx-serve" serve \
  --model ~/.mlx-serve/models/mlx-community/gemma-4-12b-it-4bit \
  --host 127.0.0.1 \
  --port 11234
```

주요 기본값:

```dotenv
ANALYSIS_PROVIDER=local
LOCAL_TEXT_PROVIDER=mlx
LOCAL_TEXT_URL=http://127.0.0.1:11234
LOCAL_TEXT_MODEL=mlx-community/gemma-4-12b-it-4bit
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
`BACKGROUND_PROVIDER=mlx`는 제품 없는 배경·활용 장면·추가 디테일 참고 컷에만 Flux를 사용합니다.
`hero`·`packshot`·대표 `detail` 제품 픽셀은 계속 원본 RGB와 결정적 Pillow 합성으로 보존합니다.
Flux2가 만든 `lifestyle`·추가 detail은 생성 참고 자산으로만 취급하며 `GENERATED`와 원본 hash를
표시합니다. GPU/모델 서버를 사용하지 않으려면 `LOCAL_IMAGE_PROVIDER=none`과 `BACKGROUND_PROVIDER=none`을 함께 설정할 수
있으며, 이 경우 중립 배경 fallback만 사용합니다.

## API

운영 구조는 `FE → 상품 BE → AI → 상품 BE → FE`입니다. FE 화면의 작품 이름·제작 과정·관리법은
상품 BE가 `user_hints`로 묶어 AI에 전달하며, AI는 상품 BE의 내부 호출만 받습니다. 상품 BE
API와 DB는 이 AI 저장소의 구현 범위가 아닙니다.

제품 분석은 외부 검색엔진을 호출하지 않습니다. 로컬 Gemma는 입력 이미지와 상품 BE가
전달한 `user_hints`만 사용하며, 검색 출처·실시간 가격·제작자·원산지·진품성·정확한
소재·성능을 자동으로 확정하지 않습니다. 최신성이나 출처가 필요한 내용은 상품 BE가
검수한 뒤 `user_hints`로 전달해야 합니다.

- `POST /internal/v1/ai/detail-page-jobs`
  - 상품 BE 전용. `product_image`, 반복 `product_images`, `metadata` JSON
  - `metadata.product_id`와 `source_asset_id`를 작업·결과·적재 요청에 보존
- `GET /internal/v1/ai/detail-page-jobs/{job_id}`
  - 상품 BE 전용 상태·결과 polling
- `PUT /internal/v1/ai/detail-page-jobs/{job_id}/draft`
  - 장인 문구 수정 저장. `draft`와 재조립 가능한 `react_document` 기준만 갱신하고 AI/PNG 생성을 호출하지 않음
- `POST /internal/v1/ai/detail-page-renders`
  - 상품 BE 전용. 장인이 수정한 `draft` JSON과 원본 이미지로 최종 PNG 생성
  - 분석 AI를 다시 호출하지 않고 승인 draft에서 `react_document`를 재조립·검증한 뒤 HTML/CSS + Playwright로 전체·섹션 PNG 생성
- `BACKEND_PRODUCT_URL`
  - AI가 상품 BE로 생성 메타데이터·전체 PNG·섹션·제품 사진을 전달하는 적재 endpoint

내부 API는 `AI_INTERNAL_AUTH_TOKEN`과 `X-AI-Internal-Token`을 사용합니다. 로컬 데모 페이지는
상품 BE가 없으므로 기존 `/api/v1/ai/*` direct 경로를 호환용으로 사용합니다. 자세한 DTO는
[`docs/api/ai-dto-contract.md`](docs/api/ai-dto-contract.md)를, FE React JSON 상세 계약은
[`docs/api/react-json-output-contract.md`](docs/api/react-json-output-contract.md)를 참고합니다.

### React JSON 출력

`react_document`는 FE가 자체 React 컴포넌트 allowlist로 렌더링하는 제한형 JSON AST입니다.
초안 응답은 `draft.react_document`, 최종 결과는 `result.detail_page.react_document`,
AI→상품 BE 적재 metadata는 `detail_page.react_document`에 같은 문서를 담습니다. 허용 태그,
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

FE·상품 BE·AI 경계 계약은 [`docs/api/ai-dto-contract.md`](docs/api/ai-dto-contract.md), FE 화면 명세는 [`docs/api/ai-fe-io-spec.md`](docs/api/ai-fe-io-spec.md), 로컬 모델 실행은 [`docs/operations/local-llm.md`](docs/operations/local-llm.md), 전체 설계·평가·안전성 기준은 [`docs/architecture/ai-architecture-and-safety.md`](docs/architecture/ai-architecture-and-safety.md)를 참고합니다.

## 로컬 영속성

- 원본·결과 자산: `ASSET_STORE_DIR`의 SHA-256 content-addressed 파일 저장소
- 작업·BE outbox: `SQLITE_PATH`
- 재시작 시 중단 작업은 `QUEUED`로 복구
- 렌더링 전에 고정 `generation_id`와 전체 결과를 outbox에 먼저 저장
- SQLite lease claim·heartbeat·owner fencing으로 같은 작업/BE 전송의 동시 실행과 stale worker 덮어쓰기 차단
- 실행 중 worker가 종료된 `DELIVERING` 항목은 lease 만료 시 예약 callback으로 재전송
- BE 실패 결과는 재시작 후에도 같은 `generation_id`로 재전송
- URL을 제공하는 운영 자산 저장소에서는 `RESPONSE_ASSET_MODE=url`로 Base64 중복을 제거

현재 코드는 로컬 파일/SQLite와 로컬 MLX Serve 모델 서버를 기준으로 합니다. 상품 BE 적재 URL은 선택적으로 사용할 수 있으며, 클라우드 모델·클라우드 credential·클라우드 인프라는 생성하거나 호출하지 않습니다. Flux2 Klein 4B 전용 endpoint를 사용한 실제 2건 생성 기록은 [`docs/operations/local-generation-test-report.md`](docs/operations/local-generation-test-report.md)에 정리되어 있고, 운영 기본값은 Flux2 Klein 9B입니다.

## 내부 HTML/CSS → PNG 렌더링

```bash
PYTHONPATH=src .venv/bin/python scripts/build_detail_page_html.py \
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

## 테스트

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q src scripts tests
```

테스트는 외부 모델 호출 없이 payload, 배경 안전성 판정, 원본 해시와 crop/composite 픽셀 출처, deterministic hash, 역할 매핑, React AST 스키마·안전성·camelCase 직렬화, 로컬 `react_document.json` 산출, SQLite lease claim·재시작 복구, outbox 선저장·멱등 재전송과 FE/BE DTO를 검증합니다.
