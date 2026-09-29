# 전체 코드 정리 진단 보고서 (교차 B — agy, 개정판)

- **작성일시**: 2026-09-14 00:36:00
- **진단자**: agy (교차검증 B)
- **적용 기준**: **"굳이 안 고쳐도 되면 안 고쳐도 된다" (실제 문제 유발 건만 [필요] 판정)**
- **대상 커밋**: `cfd60bb` (feat: cut products out with rembg and stop stamping generated photos)
- **현재 베이스라인**: `pytest -q` → 348 passed (11.10s), working tree clean
- **원칙**: **코드 무수정 (Zero code modifications)**, 정량적 실측 기반, 추측 배제

---

## 0. [필요] 항목 실행 목록 (Actionable Checklist)

> **[필요] 판정 기준**: 지금 실제 문제를 일으키는 것만 (오해로 잘못된 결과 유발, 호출처 없는 순수 유지비 발생, 테스트·배포 차단/파괴, 문서 불일치로 인한 오작업 유발).

| 번호 | 등급 | 대상 파일 및 위치 | 작업 내용 | [필요] 판정 근거 (실제 문제) |
| :---: | :---: | :--- | :--- | :--- |
| **1** | B | [`scripts/runtime/generate_attached_detail_page.py`](file:///Users/jmllem/PycharmProjects/Team3_EcommerceSystemAI/scripts/runtime/generate_attached_detail_page.py) | 상단 독스트링 및 CLI 실행 시 `[DEMO / TEST FIXTURE ONLY]` 경고 문구 추가 | **[오해 유발]** 관리자가 실제 생성 파이프라인으로 오인해 잘못된 결과를 낸 사례가 직접 발생함. (단, 단순 삭제 시 테스트 2개 파괴되므로 명확한 경고 출력으로 해결) |
| **2** | A | [`docs/internal/refactoring/refactoring-plan.md:9, 53, 345`](file:///Users/jmllem/PycharmProjects/Team3_EcommerceSystemAI/docs/internal/refactoring/refactoring-plan.md#L9) | Gate 4 및 통과 조건에서 삭제된 `check_reference_label.py` 실행 지시 제거 | **[테스트·배포 차단]** 커밋 `cfd60bb`에서 삭제된 스크립트를 게이트에서 필수 실행하도록 되어 있어 `FileNotFoundError`로 리팩터링 완료를 기계적으로 차단함. |
| **3** | C | [`docs/internal/refactoring/refactoring-plan.md` Task 4](file:///Users/jmllem/PycharmProjects/Team3_EcommerceSystemAI/docs/internal/refactoring/refactoring-plan.md#L222) | Task 4 명세를 12차 정본(hero `source_original`, `RembgCutoutExtractor`, 참고용 라벨 제거)으로 갱신 | **[문서 불일치/오작업 유발]** 계획서가 구형 플러드필 및 참고용 라벨 검사를 전제하고 있어, 다음 작업자가 문서를 따를 경우 12차의 핵심 성과를 거꾸로 되돌리는 중대한 회귀를 유발함. |
| **4** | A | [`src/detail_page_ai/prompts.py:1053-1096`](file:///Users/jmllem/PycharmProjects/Team3_EcommerceSystemAI/src/detail_page_ai/prompts.py#L1053-L1096) | 미사용 함수 `build_generated_detail_view_prompt` 삭제 | **[호출처 없는 유지비]** 저장소 전체에서 호출처가 0곳인 44줄의 완전한 데드 코드로 불필요한 인지 부하 유발. |
| **5** | A | [`src/detail_page_ai/prompts.py:11-15`](file:///Users/jmllem/PycharmProjects/Team3_EcommerceSystemAI/src/detail_page_ai/prompts.py#L11-L15) | 미사용 프롬프트 버전 상수 5종 삭제 | **[호출처 없는 유지비]** 코드 내 참조처가 전혀 없으면서 프롬프트 버전 추적에 혼선만 초래함. |

---

## 1. 세부 진단 결과

---

### [등급 A] 삭제 (호출처 0, 불필요한 스크립트, 죽은 코드)

#### A-1. [필요] 미사용 디테일 뷰 프롬프트 함수: `build_generated_detail_view_prompt`
- **파일 및 심볼**: [`src/detail_page_ai/prompts.py:1053-1096`](file:///Users/jmllem/PycharmProjects/Team3_EcommerceSystemAI/src/detail_page_ai/prompts.py#L1053-L1096) (`def build_generated_detail_view_prompt`)
- **무엇이 문제인가 (코드 근거)**:
  - 44줄에 걸쳐 `detail-03`, `detail-05` 앵글 컷 프롬프트를 조립하는 함수가 정의되어 있으나, 저장소 전체(`src/`, `scripts/`, `tests/`)에서 해당 심볼을 호출하거나 임포트하는 곳이 **단 1곳도 없음 (0 callers)**.
  - 현재 실제 디테일 컷 생성은 `runner.py:111`에서 `build_generated_detail_cut_prompt(profile, role)`를 호출하여 수행하고 있음.
- **제안 조치**: **완전 삭제**.
- **영향 범위**: 실측 호출처 0곳.
- **동작 변경 여부**: **동작 변경 0**.
- **검증 방법**: `.venv/bin/python -m pytest -q tests/test_prompts.py`

---

#### A-2. [필요] 미사용 프롬프트 버전 관리 상수 5종
- **파일 및 심볼**: [`src/detail_page_ai/prompts.py:11-15`](file:///Users/jmllem/PycharmProjects/Team3_EcommerceSystemAI/src/detail_page_ai/prompts.py#L11-L15)
  - `CRAFT_RESEARCH_PROMPT_VERSION = "craft-research-v2-product-data-first"` (L11)
  - `BACKGROUND_PROMPT_VERSION = "background-v4-jewelry-coverage"` (L12)
  - `USAGE_SCENE_PROMPT_VERSION = "usage-scene-v3"` (L13)
  - `GENERATED_USAGE_SCENE_PROMPT_VERSION = "generated-usage-scene-v5-source-count-glass"` (L14)
  - `GENERATED_DETAIL_CUT_PROMPT_VERSION = "generated-detail-cut-v3-source-count-glass"` (L15)
- **무엇이 문제인가 (코드 근거)**:
  - 프롬프트 파일 상단에 버전 문자열 5개가 선언되어 있으나, 파이썬 코드베이스(`src/`, `scripts/`, `tests/`) 어디에서도 참조되거나 소비되지 않음 (0 callers).
  - 프롬프트 버전을 확인하려는 작업자에게 잘못된 정보를 주거나 갱신 누락으로 인한 오해를 유발함.
- **제안 조치**: **삭제**.
- **영향 범위**: 실측 호출처 0곳.
- **동작 변경 여부**: **동작 변경 0**.
- **검증 방법**: `.venv/bin/python -m pytest -q tests/test_prompts.py`

---

#### A-3. [필요] 삭제된 품질 게이트 잔존 참조: `scripts/check_reference_label.py`
- **파일 및 심볼**: [`docs/internal/refactoring/refactoring-plan.md:9, 53, 345`](file:///Users/jmllem/PycharmProjects/Team3_EcommerceSystemAI/docs/internal/refactoring/refactoring-plan.md#L9)
- **무엇이 문제인가 (코드 근거)**:
  - 커밋 `cfd60bb`에서 '참고용' 라벨 요구사항이 완전히 폐기되면서 `scripts/check_reference_label.py`가 삭제되었음.
  - 그러나 기존 실행 계획서 `refactoring-plan.md`의 Gate 4(L345: `.venv/bin/python scripts/check_reference_label.py <saved-pilot-or-fixture>`) 및 통과 조건(L53)에 여전히 스크립트 실행이 필수로 명시되어 있음. 이대로 계획서를 실행하면 Gate 4에서 `FileNotFoundError`로 리팩터링 완료 판정이 차단됨.
- **제안 조치**: `refactoring-plan.md` 내 `check_reference_label.py` 실행 지시 및 Gate 4 검증 항목 **삭제**.
- **영향 범위**: 문서 내 3곳.
- **동작 변경 여부**: **동작 변경 0** (실제 CI/게이트 차단 버그 해소).
- **검증 방법**: 게이트 스크립트 실행 시 오류 미발생 확인.

---

#### A-4. [불필요] `AiFeStatusResponse.completed` classmethod 제거
- **파일 및 심볼**: [`src/detail_page_ai/dto.py:404-439`](file:///Users/jmllem/PycharmProjects/Team3_EcommerceSystemAI/src/detail_page_ai/dto.py#L404-L439)
- **판정 이유**: 메서드 내부 지연 임포트로 모듈 로딩 시점의 순환 참조가 이미 회피되어 있어 현재 어떤 런타임 에러나 결함도 일으키지 않음.

---

### [등급 B] 정리 (중복·이름 오해·레거시 분리·미선언 의존성)

#### B-1. [필요] 하드코딩 부채 프로필 데모 스크립트 오해 방지 안내 보강
- **파일 및 심볼**: [`scripts/runtime/generate_attached_detail_page.py:1-140`](file:///Users/jmllem/PycharmProjects/Team3_EcommerceSystemAI/scripts/runtime/generate_attached_detail_page.py#L1-L140)
- **무엇이 문제인가 (코드 근거)**:
  - 파일명이 `generate_attached_detail_page.py`이고 위치가 `scripts/runtime/`에 있어, 실제 첨부 이미지로 AI 상세페이지를 생성하는 정본 파이프라인으로 오인하기 쉬움 (실제로 관리자가 오인하여 잘못된 결과를 낸 사례 발생).
  - 내부 구현(L53-140)은 "분홍 곡선 손잡이 부채"(`model_run: False`)가 하드코딩된 오프라인 HTML 렌더링 픽스처 데모임.
  - **주의 (삭제 금지)**: 단순 삭제 시 [`tests/test_attached_detail_page.py:1`](file:///Users/jmllem/PycharmProjects/Team3_EcommerceSystemAI/tests/test_attached_detail_page.py#L1) 및 [`tests/test_project_layout.py:24`](file:///Users/jmllem/PycharmProjects/Team3_EcommerceSystemAI/tests/test_project_layout.py#L24)가 즉시 실패함.
- **제안 조치**:
  - 파일 삭제나 이동을 하지 않고, 파일 상단 독스트링 및 CLI 실행 시 `[DEMO / TEST FIXTURE ONLY - Not a real AI generation pipeline]` 경고 문구를 크게 출력하도록 보강하여 관리자/작업자의 오해를 원천 차단.
- **영향 범위**: CLI 실행 및 독스트링 1곳. (기존 함수 시그니처 및 파일 위치 불변)
- **동작 변경 여부**: **동작 변경 0**.
- **검증 방법**:
  ```bash
  .venv/bin/python -m pytest -q tests/test_attached_detail_page.py tests/test_project_layout.py
  ```

---

#### B-2. [불필요] `SolidBackgroundCutoutExtractor` 파일 분리 (`legacy_cutouts.py`)
- **파일 및 심볼**: [`src/detail_page_ai/source_photos.py:93-386`](file:///Users/jmllem/PycharmProjects/Team3_EcommerceSystemAI/src/detail_page_ai/source_photos.py#L93-L386)
- **판정 이유**: `source_photos.py` 내에 함께 있어도 `training_augmentation`과 14개 회귀 테스트가 정상 동작하고 있어 분리하지 않아도 아무런 장애를 주지 않음.

---

#### B-3. [불필요] `scripts/compare_cutout_regression.py` 인터페이스 일반화
- **파일 및 심볼**: [`scripts/compare_cutout_regression.py:1-655`](file:///Users/jmllem/PycharmProjects/Team3_EcommerceSystemAI/scripts/compare_cutout_regression.py#L1-L655)
- **판정 이유**: 구형 플러드필 추출기 감사용 도구로 격리되어 있어 현재 배포나 메인 파이프라인에 전혀 영향을 주지 않음.

---

#### B-4. [불필요] `prompts.py` 문자열 치환 로직 리팩터링
- **파일 및 심볼**: [`src/detail_page_ai/prompts.py:446-460`](file:///Users/jmllem/PycharmProjects/Team3_EcommerceSystemAI/src/detail_page_ai/prompts.py#L446-L460)
- **판정 이유**: 현재 템플릿 키워드와 인덱스가 완벽히 일치하여 모든 테스트가 정상 통과하므로 즉각적인 수정 불필요.

---

#### B-5. [불필요] `pyproject.toml`에 `numpy`, `scipy` dev 의존성 명시
- **파일 및 심볼**: [`pyproject.toml:5-19`](file:///Users/jmllem/PycharmProjects/Team3_EcommerceSystemAI/pyproject.toml#L5-L19)
- **판정 이유**: `rembg`의 전이 의존성으로 가상환경에 이미 안정적으로 설치되어 있어 실제 실행 및 테스트에 결함이 발생하지 않음.

---

#### B-6. [불필요] `tests/build_detail_page_visual_fixtures.py` 위치 재배치
- **파일 및 심볼**: [`tests/build_detail_page_visual_fixtures.py:1-67`](file:///Users/jmllem/PycharmProjects/Team3_EcommerceSystemAI/tests/build_detail_page_visual_fixtures.py#L1-L67)
- **판정 이유**: `tests/` 루트에 위치해도 pytest가 테스트로 오인하지 않고 Node.js 레이아웃 테스트가 정상 호출하고 있음.

---

### [등급 C] 구조 (기존 계획서 Task 1~5 재검증 매트릭스)

| Task | 계획서 명칭 | 판정 | 상세 이유 |
| :--- | :--- | :---: | :--- |
| **Task 1** | `dto ↔ react_document_builder` 순환 제거 | **[불필요]** | 지연 임포트로 격리되어 있어 프로덕션 런타임에 아무런 결함이나 버그를 일으키지 않음. |
| **Task 2** | `pipeline.run` 3단 분리 | **[불필요]** | 320줄의 거대 함수이지만 현재 전 구간이 정상 동작하며 성능/메모리 장애를 일으키지 않음. |
| **Task 3** | `prompts.py` 텍스트·이미지 분리 | **[불필요]** | 1096줄 단일 파일이어도 각 소비자가 필요한 프롬프트 함수를 정상 임포트하여 쓰고 있어 장애가 없음. |
| **Task 4** | 사진 역할·provenance 정책 일원화 | **[필요]** | **계획서 명세가 현재 코드와 달라 오작업 유발**: 12차에서 hero `source_original` 정책, `RembgCutoutExtractor` 기본 채택, '참고용' 라벨 및 게이트 삭제가 완료되었으나, 기존 계획서는 구형 정책을 전제하고 있어 후속 작업자가 이를 되돌리는 중대한 회귀를 유발함. 계획서 갱신 필수. |
| **Task 5** | 렌더러 공통 계약 재평가 게이트 | **[불필요]** | 11블록 대 3블록 잠복 차이가 실제 파일럿 60건에서 전혀 발현되지 않으며 두 렌더러의 실패 격리가 정상 유지 중임. |

---

## 2. 건드리면 안 되는 것 (절대 불변 원칙 및 보존 대상)

다음 항목들은 레거시나 중복처럼 보일 수 있으나, 시스템의 안정성, 핵심 비즈니스 계약, 또는 보안/릴리스 게이트로서 의도된 설계이므로 **절대 임의로 삭제하거나 동작을 변경해서는 안 됩니다.**

1. **`scripts/check_cutout_fidelity.py` (공식 AWS 릴리스 품질 게이트)**
   - AWS 배포 명세([`aws-deployment.md:65`](file:///Users/jmllem/PycharmProjects/Team3_EcommerceSystemAI/docs/phase4/operations/aws-deployment.md#L65))에 정식 품질 게이트로 등록됨. hero 누끼 및 원본 보존율을 기계적으로 계측하며 [`test_eval_scripts.py`](file:///Users/jmllem/PycharmProjects/Team3_EcommerceSystemAI/tests/test_eval_scripts.py)에서 검증 중. CLI 변경 금지.
2. **`scripts/check_plan_diversity.py` (레이아웃 다양성 품질 게이트)**
   - 60건 전체 실행에서 블록 시퀀스의 Jaccard 유사도와 다양성을 자동 검증하는 공식 평가 게이트.
3. **`scripts/audit_cutout_truth.py` (냉동 산출물 독립 감사 도구)**
   - 60건 냉동 실행 산출물(`photos/01-hero.*`, `result_summary.json`)의 정적 픽셀만을 직접 검사하여 침식/잔존 결함을 측정하는 독립 감사기.
4. **Hero 사진의 `source_original` 정책 (커밋 `492e776`)**
   - hero 이미지는 생성/누끼를 거치지 않고 원본 사진 바이트 그대로 노출되어야 함. `AttachedPhotoCatalogBuilder`에서 `source_original`로 마킹되고 `VERIFIED` 상태 유지. BE 배송 필터에서도 hero 역할에 한해서만 허용.
5. **`RembgCutoutExtractor`의 기본 추출기 지위 (커밋 `cfd60bb`)**
   - `birefnet-general` 모델(1024px, onnx)을 lazy 세션으로 구동하여 광택·반투명 공예품 누끼 분리. 메인 생성기의 기본 추출기로 유지 필수.
6. **`src/detail_page_ai/app.py:75`의 함수 레벨 임포트**
   - `build_service` 내부의 지연 주입은 의도된 설계임. [`test_project_layout.py:129-134`](file:///Users/jmllem/PycharmProjects/Team3_EcommerceSystemAI/tests/test_project_layout.py#L129-L134)가 명시적으로 허용하고 보호함.
7. **`src/detail_page_ai/persistence.py` 모듈 구조 (560줄)**
   - JobRepository와 DeliveryOutbox가 깔끔하게 나뉜 안정 모듈로 관리자 판정에서 분리 제외 확정.
8. **`pyproject.toml` 선언 패키지 8종 전원**
   - `fastapi`, `httpx`, `onnxruntime`, `pillow`, `pydantic-settings`, `python-multipart`, `rembg`, `uvicorn` 전원 `src/` 코어에서 직접 임포트하여 사용 중.
9. **두 렌더러의 물리적 분리 (HTML/PNG 대 React JSON Document)**
   - HTML 렌더러와 React 빌더는 서로 다른 실패 경계를 유지해야 함.
10. **`web/` 및 `docs/deliverables/` 디렉터리**
    - FE 전용 영역 및 codex3 12차 작업 디렉터리로 접근 금지.
