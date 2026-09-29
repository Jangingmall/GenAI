> 원본: docs/phase3/originals/01-implementation-checkpoint.md (2026-09-09 기준)

# AI 영역 1·2 1차 구현 체크포인트 보고서

- **문서 번호**: DELIVERABLE-01
- **작성일**: 2026-09-09
- **작성자**: agy (오케스트레이션 세션 지휘 하 작성)
- **대상 시스템**: Team3 E-Commerce Detail Page AI Generation Pipeline
- **근거 문서**: [`docs/phase2/metrics-definition.md`](../../phase2/metrics-definition.md) (1. 영역과 집계)
- **실측 데이터 기준**: `generated/evaluation/pilot-20260909-224737` (`generated/evaluation/pilot-20260909-224737`)

---

## 1. 개요 및 영역 구분 근거

본 문서는 상세페이지 생성 AI 시스템의 핵심 축인 **영역 1(분석·카피)**과 **영역 2(이미지·렌더링)**의 1차 코드 구현 상태를 기술하고, 6개 대표 카테고리 실물 자산(`cma_real_v1`) 기반 파일럿 실행에서 실측된 결과를 바탕으로 검증된 기능과 아직 완료되지 않은 한계를 객관적 사실에 입각하여 기록한 체크포인트 보고서입니다.

영역 구분은 [`docs/phase2/metrics-definition.md`](../../phase2/metrics-definition.md)의 **"1. 영역과 집계"** 계약에 따릅니다.

| 영역 | 정의 및 평가 범위 | 핵심 모델 / 런타임 | 주요 산출물 |
|---|---|---|---|
| **영역 1 (분석·카피)** | 제품 원본 이미지와 제작자 입력(`user_hints`)을 분석하여 구조화된 제품 프로필, 카테고리·공예 판정, 블록 배치 계획(`page_plan`), 섹션별 마케팅 카피를 도출 | `ddalcu/Qwen3.8-27B-MLX-Serve-4bit` (MLX-Serve, M-RoPE, Grammar Schema 강제) | `ProductProfileDto`, `PageBlockDto`, `result_summary.json`의 `product` 블록 |
| **영역 2 (이미지·렌더링)** | 제품 원본의 픽셀 무결성을 유지하는 컷아웃·합성·크롭 생성, 카테고리 적합 배경 씬 생성, FE React 문서 조립 및 최종 고해상도 상세페이지 PNG 렌더링 | `mlx-community/flux2-klein-9b-4bit`, Node + Playwright 헤드리스 브라우저 | `ProductPhotoSet`, `photos/*.png`, `sections/*.png`, `react_document.json`, `detail_page.png` |
| **공통 자동 Gate** | 양 영역을 관통하는 스키마 유효성, 트리 안전성, camelCase 직렬화 보존, 이미지 ID 참조 해석, 원본 해시 일치, 실행 코드 무누출 검증 | Python Pydantic V2, JSON AST Validator | 전건 자동 검증 (100% 통과 기준) |

---

## 2. 영역 1 — 분석·카피 (Analysis & Copy)

### 2.1 담당 코드 및 아키텍처 역할

1. **분석 프롬프트 엔지니어링 ([`src/detail_page_ai/prompts.py`](../../../src/detail_page_ai/prompts.py))**
   - **프롬프트 버전 상수**: `ANALYSIS_PROMPT_VERSION = "analysis-v11-product-intro-copy-brief-care-gate"`
   - **핵심 함수**: `build_analysis_prompt(locale: str = "ko-KR", user_hints: UserHintsDto | None = None, archetypes: Sequence[Mapping[str, Any]] | None = None)`
   - **프롬프트 편향 제거 및 블록 선택·생략 조건(Selection Gates) 개정**:
     - 기존에 모델 출력을 천편일률적 순서로 각인시키던 세 지점(Copy Map 나열 순서, 9블록 하한선, 순차 레시피 불릿)을 완전히 제거하고, 블록 역할을 알파벳순 사전식 메뉴로 분리.
     - 블록별 엄격한 선택·생략 조건 도입: 특히 `statement` 블록은 제작자 입력에 제작 기법/과정(`howMade` / `making_method`) 데이터가 공급된 경우에만 포함되며, 데이터 부재 시 완전히 생략하도록 강제 (외형 묘사를 제작 스토리로 날조 금지).
     - 주입된 레이아웃 원형 시퀀스 지시를 따르되, **근거로 뒷받침할 수 없는 블록은 지어내지 않고 생략(Grounding Omission)**하도록 지시.
   - **BE-AI 콘텐츠 생성 계약 반영**:
     - 공급자 입력 필드(`productName`, `howMade`, `careTips`)를 마케팅 카피의 최우선 근거(Product Introduction Copy Brief)로 삼도록 강제.
     - 환각(Hallucination) 방지를 위해 사실 슬롯을 6개 범주(`identity`, `making/process`, `sensory/visual`, `use`, `care`, `unknown`)로 분리 추출하도록 지시하며, 이미지로 확인되지 않는 성능·인증·가격·원산지는 추측하지 않고 미확인(`uncertain_information` 또는 "확인 필요")으로 유지.
     - 결과는 반드시 지정된 JSON 스키마만을 따르도록 MLX-Serve의 Grammar 제어(`POST /v1/chat/completions` with grammar)를 통해 문법적 완전성을 보장.

2. **코드 결정론적 레이아웃 아키텍처 ([`src/detail_page_ai/layout_archetypes.py`](../../../src/detail_page_ai/layout_archetypes.py)) 및 카탈로그 ([`assets/references/detail-page-layouts.json`](../../../assets/references/detail-page-layouts.json))**
   - **페이지 구성을 코드가 결정**: 모델에 자연어 지시만으로 구조 다양성을 유도하는 방식의 한계(모델의 default 10블록 시퀀스 고착)를 극복하기 위해, **원본 이미지 SHA-256 해시를 시드로 카탈로그에서 원형 하나를 재현 가능하게 결정론적으로 선택**하여 프롬프트의 구성 지시로 주입.
   - **레이아웃 원형 25종 카탈로그 (`detail-page-layouts.json`)**: 25종의 고유 블록 시퀀스 및 10종 이상의 고유 variant 조합 정의.
   - **카탈로그 엄격 검증 ([`tests/test_layout_catalog.py`](../../../tests/test_layout_catalog.py))**: 허용 블록 타입 및 variant 화이트리스트 검속, 4개 이상 블록 길이 분포(단일 길이 60% 미만 점유), 14블록 상한 및 edge 블록(hero/closing) 고정 강제.

3. **구조화된 DTO 계층 ([`src/detail_page_ai/dto.py`](../../../src/detail_page_ai/dto.py))**
   - **`ProductProfileDto`**: `product_type`, `display_name`, `is_traditional_craft`, `craft_type`, `classification_confidence`, `craft_confidence`, `layout_id`, `page_plan`, `summary`, `features`, `copy_sections`, `usage_scene`, `uncertain_information`, `safety_notes` 등 엄격한 필드 유효성 검증(`extra="forbid"`).
   - **`LayoutId`**: `"editorial-split"` | `"image-first"` | `"catalog-grid"` 3종 분기 지원.
   - **`PageBlockDto`**: 상세페이지를 구성하는 모듈형 블록 구조(`hero`, `statement`, `feature_grid`, `detail_split`, `wide_image`, `gallery`, `usage_scene`, `scale_reference`, `palette`, `recommendation`, `info_table`, `notice`, `closing`).
   - **`PageBlockVariant`**: 8종 스타일 variant(`paper`, `light`, `sand`, `dark`, `image-left`, `image-right`, `full-bleed`, `compact`).

4. **프로필 검증 및 레이아웃 보존 ([`src/detail_page_ai/validation.py`](../../../src/detail_page_ai/validation.py))**
   - `validate_product_profile`: `product_type`, `summary` 길이(500자 이하), `features` 개수(5개 이하), 신뢰도 범위(0.0~1.0) 검증.
   - **블록 패딩 제거 및 모델 계획 보존**: 기존의 9블록 강제 패딩 로직을 걷어내고, 중간 블록이 6개 이상(`len(middle) >= 6`)이면 모델이 결정한 블록 시퀀스와 구성을 그대로 보존.
   - **variant 고정 배정 제거**: `detail_split`이나 `usage_scene`에 `dark`나 `full-bleed`를 무조건 덮어쓰던 하드코딩을 제거하여 모델과 카탈로그의 variant 지정 의도를 존중(`block.variant or "dark"`).

5. **디자인 가이드 고정 ([`src/detail_page_ai/reference_guide.py`](../../../src/detail_page_ai/reference_guide.py))**
   - **가이드 버전**: `REFERENCE_GUIDE_VERSION = "detail-page-guide-v2-premium-editorial"`
   - `REFERENCE_GUIDE_COLORS`: Black(`#101010`), White(`#FFFFFF`), Cool Grey 계열(50~900), Jade Blue 계열(50~500), Yellow 500, Red 500 등 16색 팔레트 상수 고정.
   - `REFERENCE_GUIDE_TYPE_SCALE`: Display(28px), Title(17px), Body(16px), Body Small(13px), Caption(10px) 등 활자 계층 구조 고정.

6. **추론 백엔드 모델**
   - `ddalcu/Qwen3.8-27B-MLX-Serve-4bit`: 로컬 Apple Silicon 통합 메모리(Unified Memory)에서 구동되는 27B 규모의 비전-언어 멀티모달 모델. 단일 이미지와 텍스트 프롬프트를 결합 추론하여 JSON 응답 생성.

---

### 2.2 실제 동작 확인 및 실측 사례 (Pilot 6건 전수 검증)

최종 파일럿 재실행(`generated/evaluation/pilot-20260909-224737` (`generated/evaluation/pilot-20260909-224737`))의 각 케이스별 `result_summary.json` 내 `product` 블록을 전수 조사한 결과, 6건 모두 필수 메타데이터 필드가 누락 없이 완벽하게 추출되었습니다.

#### 표 2-1. 파일럿 6건 영역 1 분석 추출 실측 데이터
| No | 케이스 ID (asset_id) | 카테고리 | `product_type` | `display_name` | `is_traditional_craft` | `craft_type` | `layout_id` | `page_plan` 블록 수 |
|---|---|---|---|---|:---:|---|---|:---:|
| 1 | `analysis-cma-102980` | textile | 직물 | 흑백 기하학적 무늬 직물 | **True** | 직조 | editorial-split | 10 |
| 2 | `analysis-cma-101636` | box | 전통 칠기 상자 | 황색 바탕 문양 칠기 상자 | **True** | 칠기 | editorial-split | 10 |
| 3 | `analysis-cma-114971` | metalware | 금속 공예 용기 | 양각 장식 금속 용기 | **True** | 금속 양각 공예 | editorial-split | 10 |
| 4 | `analysis-cma-122443` | ceramic | 도자기 | 청자 연화문 병 | **True** | 청자 | editorial-split | 10 |
| 5 | `analysis-cma-109609` | jewelry | 보석 목걸이 | 금·보석 목걸이 | **False** | None | catalog-grid | 9 |
| 6 | `analysis-cma-110793` | furniture | 목제 생활 도구 | 곡선 목제 도구 | **False** | None | editorial-split | 10 |

#### 실측 사례 인용

1. **전통 공예 분류 및 공예 유형 식별 사례 (`analysis-cma-101636`)**:
   - `product_type`: `"전통 칠기 상자"`
   - `display_name`: `"황색 바탕 문양 칠기 상자"`
   - `is_traditional_craft`: `true` (공예 판정 신뢰도: `0.95`)
   - `craft_type`: `"칠기"`
   - `summary`: `"황색 바탕에 섬세한 덩굴 및 화문이 시문된 사각 형태의 전통 칠기 상자입니다. 뚜껑과 몸체에 걸쳐 정교한 칠 공예 기법이 적용되어 깊이 있는 색감과 은은한 광택을 자아냅니다."`

2. **비공예(일반 장신구) 분류 및 레이아웃 분기 사례 (`analysis-cma-109609`)**:
   - `product_type`: `"보석 목걸이"`
   - `display_name`: `"금·보석 목걸이"`
   - `is_traditional_craft`: `false` (전통 공예품이 아닌 패션/주얼리 자산으로 정확히 분류)
   - `layout_id`: `"catalog-grid"` (장신구 특성에 맞춰 statement 블록을 생략하고 시각적 그리드를 강조하는 9블록 레이아웃 자동 채택)

3. **기물형 공예품의 형태·특징 추출 사례 (`analysis-cma-122443`)**:
   - `product_type`: `"도자기"`
   - `display_name`: `"청자 연화문 병"`
   - `is_traditional_craft`: `true`
   - `craft_type`: `"청자"`
   - `features`: 총 3건 도출 (1: "유려한 곡선의 청자 병 형태", 2: "섬세하게 음각/양각된 연화문", 3: "비색 유약의 은은한 광택과 빙열")

---

## 3. 영역 2 — 이미지·렌더링 (Image & Rendering)

### 3.1 담당 코드 및 아키텍처 역할

1. **컷아웃 추출 및 원본 보존 합성 ([`src/detail_page_ai/source_photos.py`](../../../src/detail_page_ai/source_photos.py))**
   - **클래스**: `SolidBackgroundCutoutExtractor`, `ProductCutout`
   - **경계 연결 배경 정의(Edge-Connected Flood Fill)**:
     - 과거 픽셀 임계치 기반 단일 패스 추출 시, 제품 내부의 밝은 패턴이나 구멍이 배경으로 오인되어 지워지는 침식 결함이 발생함.
     - 이를 방지하기 위해 **이미지 사방 테두리(0, width-1, height-1)와 물리적으로 연결된 영역만을 배경 후보로 간주**하는 flood-fill 알고리즘(`_connected_foreground_mask`)을 적용함.
   - **마스크 결함 감지 및 Fallback 안전장치**:
     - 제품 본체가 파편화되거나 심각하게 훼손되는 것을 방지하기 위해 단일 최대 연결 컴포넌트 비율(`min_largest_component_ratio = 0.50`) 및 전경 비율 경계(`min_foreground_ratio = 0.01`, `max_foreground_ratio = 0.90`)를 엄격히 검사.
     - 조건 미달 시 `None`을 반환하고, 파이프라인은 원본 비배경 픽셀을 강제로 깎지 않고 원본(`source`) 그대로 대표 컷에 합성하도록 안전하게 fallback 처리.

2. **제품 유형별 배경 씬 분기 ([`src/detail_page_ai/prompts.py`](../../../src/detail_page_ai/prompts.py) - `_product_scene_direction`)**
   - **원칙**: 추가 LLM 호출 비용 없이 제품 프로필의 관찰 텍스트 및 키워드 신호를 바탕으로 결정론적(deterministic) 씬 프롬프트를 배정.
   - **지원 분기 (총 7개 분기)**:
     1. `tea`: 차/주전자/찻잔/tea → 다도용 원목 테이블, 은은한 좌측 모닝광
     2. `box`: 보관/수납/상자/box/궤 → 월넛 서재 데스크, 오후 자연광
     3. `jewelry`: 장신구/목걸이/반지/주얼리/보석 → 아이보리 린넨/스웨이드 패드, 소프트 디퓨즈 측면광, 흉상 배제
     4. `textile`: 직물/섬유/패브릭/스카프/천 → 페일 오크 및 린넨 드레이프, 자연스러운 중력감
     5. `metal`: 금속/은제/황동/유기/철/metal → 트래버틴 스톤, 정밀 하이라이트 제어
     6. `ceramic`: 도자기/청자/백자/옹기/화병 → 마일드 스톤/오크 상판, 삼분할 구도
     7. `wood` (기타 기본): 목제/원목/나무 → 오크 테이블, 자연스러운 접촉 그림자

3. **FE React 문서 조립 ([`src/detail_page_ai/react_document_builder.py`](../../../src/detail_page_ai/react_document_builder.py), [`react_document.py`](../../../src/detail_page_ai/react_document.py))**
   - `ApprovedDraftDto`와 `ProductProfileDto`를 입력받아 FE 렌더링 계약을 충족하는 `ReactDetailPageDocumentDto` JSON AST 구축.
   - 캔버스 너비 774px 고정, FE 계약용 camelCase 키(`schemaVersion: 2.0`, `canvasWidth: 774`, `imageId`) 직렬화.
   - HTML 태그 화이트리스트(`div`, `section`, `article`, `header`, `h1`~`h4`, `p`, `span`, `img`, `table` 등) 제한, 인라인 핸들러 및 위험 스크립트 원천 차단.

4. **HTML 및 PNG 렌더링 파이프라인 ([`src/detail_page_ai/html_renderer.py`](../../../src/detail_page_ai/html_renderer.py))**
   - Node + Playwright 기반 스크립트([`scripts/runtime/render_detail_page.mjs`](../../../scripts/runtime/render_detail_page.mjs))를 subprocess로 구동하여 실제 브라우저 환경에서 10개 섹션 및 전체 상세페이지를 각각 고해상도 PNG로 래스터화.

5. **이미지 생성 및 편집 모델 클라이언트 ([`src/local_detail_page_ai/clients.py`](../../../src/local_detail_page_ai/clients.py))**
   - `mlx-community/flux2-klein-9b-4bit`: 4-step 고속 추론으로 구동되는 로컬 Flux 9B 이미지 생성 모델. 원본 제품 이미지를 컨디셔닝 참조로 전달하여 배경 씬 및 활용 컷 생성.
   - **이미지 편집 전송 스키마 개정 (`mode: "edit"`)**:
     - 기존 multipart/form-data 전송 어댑터 사용 시 추론 스텝(`steps`) 및 강도(`strength`) 파라미터가 서버로 누락/전달되지 않던 문제를 해결하기 위해, JSON POST `/v1/images/generations`의 `mode: "edit"` 스키마로 전환.
     - FLUX.2 Klein 4-step 증류 모델의 기본값인 `steps=4`를 명시적으로 전달.

6. **디자인 시스템 및 시각적 Variant 확장 ([`web/detail_page.css`](../../../web/detail_page.css), [`web/variants-agy.css`](../../../web/variants-agy.css))**
   - DTO(`PageBlockVariant`)에 선언만 되어 있고 CSS 규칙 수가 0개여서 화면에 반영되지 않던 4종 variant(`sand`, `image-left`, `image-right`, `compact`) 및 `full-bleed` 오버레이 규칙 구현.
   - **실사용 공예 테이블웨어 맥락 반영**:
     - `image-left + dark`: 40%:60% 비대칭 컬럼 분할(310px:464px), 좌측 접사 이미지 세로 스택, 우측 어두운 색면(`--espresso`) 및 세리프(`Noto Serif KR`) 제목과 `01`, `02` 악센트 넘버링 항목 조판.
     - `full-bleed`: 전면 이미지 위 중앙 정렬된 흰색 세리프 문구 및 반투명 스크림 오버레이.
     - `sand`: 따뜻한 흙/모래 색면(`#EAE1D6`) 기반의 마무리 섹션 중앙 정렬 카피 조판.
     - `compact`: `info-section`의 명세 표를 2x2 그리드로 조판하여 품목명/소재/컬러/사이즈를 촘촘하게 배치하고 타이포·마진 스케일 다운.

---

### 3.2 실제 산출물 실측 통계 (Pilot 6건 전수 검증)

`generated/evaluation/pilot-20260909-224737/`의 각 디렉터리 실측치입니다.

#### 표 3-1. 케이스별 산출 사진 구성 및 역할 (건당 8장 전건 동일)
모든 케이스는 원본 기반 3장과 AI 생성 참고 컷 5장으로 구성된 총 8장의 사진 셋을 정확히 생성했습니다.

| 번호 | 파일명 | `photo_id` | 역할 및 출처 | `asset_mode` | 원본 변형 / 생성 여부 | `fidelity_status` |
|:---:|---|---|---|---|---|:---:|
| 1 | `01-hero.png` | `hero` | 원본 보존 대표 이미지 (상단 Hero 배치) | `source_composite` | 컷아웃 또는 원본 보존 합성 | **VERIFIED** |
| 2 | `02-packshot.png` | `packshot` | 원본 보존 팩샷 (단색 배경 정돈) | `source_composite` | 여백 및 캔버스 규격 정돈 | **VERIFIED** |
| 3 | `03-detail.png` | `detail` | 원본 디테일 정수 크롭 (확대 컷) | `source_crop` | 원본 픽셀 1:1 보존 크롭 | **VERIFIED** |
| 4 | `04-lifestyle.png` | `lifestyle` | AI 생성 활용 장면 (참고용) | `generated_scene` | Flux 씬 프롬프트 생성 | GENERATED |
| 5 | `05-detail-02.png` | `detail-02` | AI 생성 디테일 뷰 1 (참고용) | `generated_view` | Flux 디테일 프롬프트 생성 | GENERATED |
| 6 | `06-detail-03.png` | `detail-03` | AI 생성 디테일 뷰 2 (참고용) | `generated_view` | Flux 디테일 프롬프트 생성 | GENERATED |
| 7 | `07-detail-04.png` | `detail-04` | AI 생성 디테일 뷰 3 (참고용) | `generated_view` | Flux 디테일 프롬프트 생성 | GENERATED |
| 8 | `08-detail-05.png` | `detail-05` | AI 생성 디테일 뷰 4 (참고용) | `generated_view` | Flux 디테일 프롬프트 생성 | GENERATED |

#### 표 3-2. 케이스별 최종 렌더링 파일 규격 및 섹션 수
| 케이스 ID | 카테고리 | `detail_page.png` 용량 | 캔버스 폭 × 높이 | `sections/` PNG 수 | `react_document.json` 크기 |
|---|---|---:|:---:|:---:|---:|
| `analysis-cma-102980` | textile | 1,650,327 bytes | 774 × 4,320 px | 10개 | 81,839 bytes |
| `analysis-cma-101636` | box | 1,502,725 bytes | 774 × 4,320 px | 10개 | 84,404 bytes |
| `analysis-cma-114971` | metalware | 1,281,534 bytes | 774 × 4,320 px | 10개 | 84,435 bytes |
| `analysis-cma-122443` | ceramic | 1,340,693 bytes | 774 × 4,320 px | 10개 | 82,061 bytes |
| `analysis-cma-109609` | jewelry | 949,120 bytes | 774 × 3,850 px | 9개 | 75,446 bytes |
| `analysis-cma-110793` | furniture | 1,062,382 bytes | 774 × 4,320 px | 10개 | 81,489 bytes |

---

## 4. 검증 상태 (실측치 및 품질 게이트)

최종 재실행 디렉터리(`generated/evaluation/pilot-20260909-224737` (`generated/evaluation/pilot-20260909-224737`))를 대상으로 실행된 실측 통계 및 게이트 결과입니다.

- **실행 결과 요약**: 총 6건 중 **6건 전건 성공 (성공률 100%, 실패 0건)**
- **총 소요시간**: 1,878.74초 (31분 18.74초, 건당 평균 5분 13초)
- **단위 테스트**: 도메인 및 파이프라인 관련 단위 테스트 258개 통과

### 4.1 품질 게이트 1: 컷아웃 원본 보존율 검증 ([`scripts/check_cutout_fidelity.py`](../../../scripts/check_cutout_fidelity.py))
- **실행 명령**: `.venv/bin/python scripts/check_cutout_fidelity.py --pilot-dir generated/evaluation/pilot-20260909-224737`
- **종료 코드**: `0` (ALL_OK / PASS)
- **측정 방식**: 캔버스 전체가 아닌 원본 비배경(ink) 픽셀 영역 대비 산출물 비배경 픽셀의 유지 비율 측정.

```
| 카테고리 | case_id | photo 역할 | 원본 잉크 비율 | 산출 잉크 비율 | 보존율 | 판정 |
|---|---|---|---|---|---|---|
| textile | analysis-cma-102980 | hero | 1.0000 (100.0%) | 0.9678 (96.8%) | 0.9678 (96.8%) | OK |
| box | analysis-cma-101636 | hero | 1.0000 (100.0%) | 1.0000 (100.0%) | 1.0000 (100.0%) | OK |
| metalware | analysis-cma-114971 | hero | 0.9964 (99.6%) | 0.9964 (99.6%) | 1.0000 (100.0%) | OK |
| ceramic | analysis-cma-122443 | hero | 0.9994 (99.9%) | 0.6402 (64.0%) | 0.6406 (64.1%) | OK |
| jewelry | analysis-cma-109609 | hero | 0.9980 (99.8%) | 0.9980 (99.8%) | 1.0000 (100.0%) | OK |
| furniture | analysis-cma-110793 | hero | 0.8855 (88.6%) | 0.8855 (88.6%) | 1.0000 (100.0%) | OK |

요약: 총 6건 | OK: 6건 | 부분 손실: 0건 | 심각 손실: 0건
최종 판정: [PASS] 전건 정상 보존(ALL_OK)되었습니다.
```
*실측 분석*: ceramic(청자, 64.1%) 및 textile(직물, 96.8%)을 제외한 4개 카테고리는 100.0%의 무결한 보존율을 기록하였으며, 심각 손실(보존율 25% 미만)은 0건으로 목표 기준(건당 >60%)을 충족했습니다.

---

### 4.2 품질 게이트 2: 씬 분기 커버리지 검증 ([`scripts/check_scene_direction_coverage.py`](../../../scripts/check_scene_direction_coverage.py))
- **실행 명령**: `.venv/bin/python scripts/check_scene_direction_coverage.py --pilot-dir generated/evaluation/pilot-20260909-224737`
- **종료 코드**: `0` (PASS)

```
## 씬 분기 커버리지 진단 결과
- 대상: generated/evaluation/pilot-20260909-224737
- 평가 방식: 파일럿 실제 산출물 판정
- 총 평가 건수: 6건

### 1. 케이스별 씬 분기 판정 결과
| 카테고리 | case_id | asset_id | 제품명 / 유형 | 기대 분기 | 실제 분기 | 판정 |
|---|---|---|---|:---:|:---:|:---:|
| textile | analysis-cma-102980 | cma-102980 | 흑백 기하학적 무늬 직물 | `textile` | `textile` | 일치 (정상) |
| box | analysis-cma-101636 | cma-101636 | 황색 바탕 문양 칠기 상자 | `box` | `box` | 일치 (정상) |
| metalware | analysis-cma-114971 | cma-114971 | 양각 장식 금속 용기 | `metal` | `metal` | 일치 (정상) |
| ceramic | analysis-cma-122443 | cma-122443 | 청자 연화문 병 | `ceramic` | `ceramic` | 일치 (정상) |
| jewelry | analysis-cma-109609 | cma-109609 | 금·보석 목걸이 | `jewelry` | `jewelry` | 일치 (정상) |
| furniture | analysis-cma-110793 | cma-110793 | 곡선 목제 도구 | `wood` | `wood` | 일치 (정상) |

### 2. 카테고리별 씬 분기 집계 (Coverage Matrix)
| 카테고리 | `box` | `textile` | `ceramic` | `metal` | `wood` | `jewelry` | **합계** |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| box | 1 | - | - | - | - | - | 1 |
| ceramic | - | - | 1 | - | - | - | 1 |
| furniture | - | - | - | - | 1 | - | 1 |
| jewelry | - | - | - | - | - | 1 | 1 |
| metalware | - | - | - | 1 | - | - | 1 |
| textile | - | 1 | - | - | - | - | 1 |
| **전체 합계** | **1** | **1** | **1** | **1** | **1** | **1** | **6** |

### 3. 검증 통계 및 최종 판정
- 총 평가 건수: 6건
- 기대 분기 일치: 6건 (일치율 100%)
- 오분류(기대 불일치): 0건
- 미대응(기본값 default): 0건
- 최종 판정: PASS (종료 코드 0)
```
*실측 분석*: 신규 추가된 `jewelry` 분기를 포함하여 6개 케이스 모두 각 카테고리의 고유 전용 배경 씬으로 정확히 매칭되었습니다.

---

### 4.3 자동 구조 게이트 실측 결과 (React AST 및 자산 무결성)

6개 케이스의 `react_document.json` 및 메타데이터를 전수 자동 검사한 결과입니다.

| 구조 게이트 검증 항목 | 검증 기준 및 내용 | 실측 결과 | 판정 |
|---|---|:---:|:---:|
| **React schema validity** | `ReactDetailPageDocumentDto` Pydantic 모델 파싱 통과율 | 6 / 6 (100%) | **PASS** |
| **React tree safety** | 허용 HTML 태그 제한, 유효한 트리 깊이, 중복 없는 노드 ID | 6 / 6 (100%) | **PASS** |
| **camelCase alias serialization** | FE 규격 필수 키(`schemaVersion`, `canvasWidth`, `imageId`) 직렬화 보존 | 6 / 6 (100%) | **PASS** |
| **imageId reference resolution** | `img` 태그의 `props.imageId`가 사진 매니페스트에 100% 매핑 | 6 / 6 (100%) | **PASS** |
| **Original SHA-256 match** | 평가 데이터셋 원본 이미지와 `run_index.json` 해시값 일치율 | 6 / 6 (100%) | **PASS** |
| **Executable field leakage** | `<script>`, `javascript:`, `dangerouslySetInnerHTML`, 인라인 이벤트 누출 | 0건 (0.0%) | **PASS** |

---

### 4.4 품질 게이트 4: 섹션 구성 다양성 검증 ([`scripts/check_plan_diversity.py`](../../../scripts/check_plan_diversity.py))

AI 생성 상세페이지의 구조적 천편일률성(모든 제품이 동일한 블록 시퀀스로 고착되는 현상)을 진단하고 차단하기 위해 신설된 정량 다양성 측정 게이트입니다.

- **실행 명령**: `.venv/bin/python scripts/check_plan_diversity.py --pilot-dir generated/evaluation/pilot-20260909-224737`
- **종료 코드**: `1` (FAIL — 기준 미달)
- **품질 게이트 판정 기준 (Quality Gate Thresholds)**:
  1. 쌍별 평균 집합 일치도 (Average Jaccard Similarity): **≤ 60.0%**
  2. 전 케이스 공통 블록 종수 (Common Block Types): **≤ 4종**
  3. 완전 일치 쌍 수 (100% 동일 집합 쌍): **0쌍**

```
========================================================================
      파일럿 섹션 구성 다양성 측정 보고서 (Section Plan Diversity)
========================================================================
- 대상: generated/evaluation/pilot-20260909-224737 (총 6건)

1. 공통 블록 수: 9종 (closing, detail_split, feature_grid, gallery, hero, info_table, notice, recommendation, usage_scene)
2. 평균 집합 일치도 (Jaccard): 96.7%
3. 완전 일치 쌍 수 (100% 동일 집합): 10쌍 (6건 중 5건이 10개 블록 완전 동일 시퀀스)
4. 길이 분포: 9블록: 1건, 10블록: 5건
5. 고유 시퀀스 종수: 2종 / 6건 (최빈 시퀀스 5회 반복)

### 품질 게이트 판정 결과
- [FAIL] 평균 집합 일치도: 96.7% (기준: <= 60.0%)
- [FAIL] 공통 블록 종수: 9종 (기준: <= 4종)
- [FAIL] 완전 일치 쌍 수: 10쌍 (기준: <= 0쌍)

최종 판정: [FAIL] 구성 다양성 기준 미달로 탈락 (종료 코드 1)
========================================================================
```
*실측 분석*: 기존에는 "고유 시퀀스 3종 이상, 중간 집합 3종 이상"이라는 지나치게 느슨한 기준으로 인해 73% 이상 블록이 중복되는 상태에서도 통과 판정이 나는 심각한 결함이 있었습니다. 신규 게이트 도입 결과 96.7%의 극심한 획일성이 확인되어 명시적 탈락(FAIL)으로 판정되었습니다.

---

## 5. 아직 안 된 것 (한계 및 미구현 항목)

본 시스템의 1차 구현과 파일럿 실행은 파이프라인의 **기술적·구조적 완결성**을 입증한 것이며, 상용 배포를 위해 반드시 확인해야 할 아래 항목들은 **아직 수행되지 않았거나 기준에 미달한 미완료 상태**입니다.

1. **사람 정성 검수(Human Review) 미실행**
   - [`docs/phase2/metrics-definition.md`](../../phase2/metrics-definition.md) 3절에 정의된 **사실성(Factuality)·명료성(Clarity)·상품성(Marketability)·시각 품질(Visual Quality) 4대 축의 정량 점수(1~5점)는 아직 존재하지 않습니다.**
   - 검수용 평가 시트(`review_sheet.csv`)의 뼈대만 생성되어 있으며, 평가자의 점수 기입은 비어 있는 상태입니다. 임의로 품질 점수를 추정하거나 보고하지 않습니다.

2. **60건 전체 데이터셋 일괄 평가 미실행**
   - 현재까지의 실측치는 카테고리당 1건씩 추출한 6건의 파일럿 결과에 불과합니다.
   - `cma_real_v1` 데이터셋 60건 전체(카테고리당 10건)에 대한 대규모 일괄 배치 실행 및 통계적 유의성(95% Wilson 신뢰구간) 평가는 미실행 상태입니다.

3. **생성 참고 컷의 '참고용' 표시 노출 누락 (배포 차단 조건 5, 미수정 결정)**
   - 데이터 모델 및 메타데이터(`result_summary.json`)에는 `product_generated: true`와 `generated_scene`/`generated_view`가 정상 기록되지만, `react_document.json` 및 최종 고객 렌더 화면(HTML/PNG)에는 '참고용' 배지/라벨이 전혀 노출되지 않는 상태입니다.
   - 이는 리뷰 가이드 상의 명백한 배포 차단 조건(Release-blocking condition)이며, 현재 사이클에서는 미수정으로 유지하기로 결정되었습니다.

4. **이미지 생성 강도(`strength`) 제어 불가**
   - 로컬 엔드포인트(`flux2-klein-9b-4bit`)는 JSON `mode: "edit"` 전송을 통해 스텝 수(`steps=4`)를 전달하도록 교정되었으나, 모델 서버의 in-context edit 구현 특성상 디노이징 강도(`strength`) 파라미터는 여전히 무시됩니다.
   - 이에 따라 원본 이미지와 생성 배경 사이의 변형 강도를 미세하게 조절하는 기능은 구현되지 못했습니다.

5. **구성 다양성 기준 미달 (Section Plan Diversity Gate Failure)**
   - 최신 정량 게이트 기준인 **평균 집합 일치도 ≤ 60.0%, 공통 블록 종수 ≤ 4종, 완전 일치 0쌍**을 충족하지 못하고 있습니다.
   - 파일럿 기준 실측치는 평균 일치도 96.7%, 공통 블록 9종, 완전 일치 10쌍으로 전 항목 기준치에 미달합니다.
   - 코드 결정론적 레이아웃 원형 선택(`layout_archetypes.py`) 도입 및 프롬프트 개편 후 평균 일치도가 72.4% 수준까지 개선되었으나, 여전히 60% 상한 목표에는 미달하며 hero/closing 고정 블록으로 인한 기저 일치도 한계가 남아 있는 미해결 과제입니다.

---

## 6. 요약 및 결론

- **영역 1(분석·카피)**: Qwen-27B 멀티모달 모델, BE-AI 계약 프롬프트(`analysis-v11`), 25종 레이아웃 원형 카탈로그(`detail-page-layouts.json`), 원본 해시 기반 결정론적 원형 선택기(`layout_archetypes.py`)를 구축함. 모델의 근거 없는 블록 날조를 방지하는 생략 규칙을 도입하여 구조 제어와 카피 생성을 분리 정착시킴.
- **영역 2(이미지·렌더링)**: 테두리 연결 배경 정의와 마스크 결함 Fallback 안전장치로 컷아웃 보존율 전건 OK를 달성했고, 이미지 편집 JSON 전송 스키마(`mode: "edit"`, steps=4)와 4종 variant CSS(`sand`, `image-left`, `image-right`, `compact`)를 신규 구현하여 디자인 시스템의 시각적 표현력을 확보함.
- **품질 게이트 및 당면 과제**: 문법·스키마·보존율 게이트는 전건 통과하였으나, 구성 다양성 게이트는 최신 기준(평균 일치도 ≤60%) 대비 96.7%(개선 후 72.4%)로 기준에 미달함. 생성 컷 '참고용' 라벨링 누락(미수정)과 함께 60건 전체 데이터셋 배치 평가 및 검수자 2인의 4축 정성 평가(Human Review) 수행이 핵심 과제로 남아 있음.
