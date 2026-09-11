# 구조 리팩터링 확정 실행 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 진행 중인 60건 평가의 기준선과 공개 계약을 보존하면서, 교차검증된 구조 결합만 단계적으로 분리하고 모든 변경을 전후 산출물 비교로 검증한다.

**Architecture:** `detail_page_ai`의 공개 호출 경로와 두 렌더러의 제품 역할은 유지한다. 내부 책임만 프로필 준비, 생성 산출물 조립, 배송, 사진 정책, 프롬프트 영역으로 나누고, 기존 모듈은 필요한 경우 호환 façade/re-export로 남긴다. 기능·정책·문구·스키마 변경은 이 계획에서 수행하지 않는다.

**Tech Stack:** Python, Pydantic DTO, `pytest`, Python `ast` import-graph 검사, 저장된 파일럿 품질 게이트(`check_cutout_fidelity.py`, `check_plan_diversity.py`, `check_reference_label.py`), Markdown.

**Spec:** [교차검증 A — diagnosis-codex.md](diagnosis-codex.md), [교차검증 B — diagnosis-agy.md](diagnosis-agy.md), 관리자 대조 판정이 포함된 작업 지시서 `.orchestration/tasks/20260910-204743-codex3.md`

## 전역 제약

- 현재 진행 중인 60건 평가가 끝나고 산출물이 보존될 때까지 `src/`와 `scripts/`를 변경하지 않는다. 이 계획서를 작성하는 현재 작업도 문서만 변경한다.
- 리팩터링은 `동작 변경 0, 순수 구조 개선 100%`를 목표로 한다. 역할 정책, 프롬프트 문구의 의미, 사진 허용 조건, 재시도 횟수·시간, 진행 상태, HTML/CSS/template, DTO field명, `react_document` schema는 바꾸지 않는다.
- 비교 기준선은 `generated/evaluation/full60-20260910-204433`이며 기준선 커밋은 `c1d413f`다. 기준선이 보존되지 않았거나 평가 완료가 확인되지 않으면 구현을 시작하지 않는다.
- `DetailPagePipeline.run(...) -> PipelineResult`, `create_draft(...) -> DraftPipelineResult`, renderer 공개 API, 기존 import 경로와 façade 심볼을 유지한다. `AiFeStatusResponse.completed`만 외부 소비자 확인 후 별도 판정한다.
- `react_document`와 `detail_page.png`/HTML 렌더러는 서로 다른 실패 경계로 유지한다. FE 구현과 `web/` 디렉터리는 범위 밖이다.
- 두 진단서([A](diagnosis-codex.md), [B](diagnosis-agy.md))는 근거 문서로 남기며 삭제하지 않는다.
- 기능 변경이 필요하다는 신호가 나오면 해당 리팩터링 단계에서 중단하고 별도 요구사항·테스트·평가 계획으로 분리한다.

---

## 관리자 대조 판정과 반영 위치

### 양쪽 진단이 합치한 5건

1. `pipeline.run`이 323줄에 걸쳐 생성·조립·전달을 한 트랜잭션 흐름에 섞고, `create_draft`와 프로필 준비 로직을 중복한다. `pipeline.py:146-524` 및 `DetailPagePipeline.run`/`create_draft`를 1차 실행 항목으로 삼는다.
2. 사진 역할·provenance 정책이 `source_photos.py`, `html_renderer.py`, `react_document_builder.py`에 분산되어 있다. 생성기·검증기·렌더러가 같은 정책을 조회하도록 4차에서 고정한다.
3. `prompts.py`를 분리한다. 두 진단의 근거는 서로 다르지만 둘 다 사실이다. 교차검증 A는 `prompts.py:452-455`의 `prompt.index()` 두 번과 `replace(..., 1)`에 의한 본문 구간 치환 취약성을 지적했고, 교차검증 B는 텍스트 LLM 프롬프트(30~463행)와 디퓨전 이미지 프롬프트(521~1095행)가 한 파일에 섞였음을 지적했다.
4. `dto.py`와 `react_document_builder.py`가 순환한다. 프로덕션 호출자는 0곳이고 `tests/test_dto.py:89`만 사용하므로 가장 위험이 낮은 워밍업으로 먼저 외부 소비자를 확인한다.
5. 두 렌더러 내부의 기본 사진 매핑·기본 레이아웃 책임이 중복된다. 다만 구체적인 fallback divergence는 별건 버그로 분리하며, 4차가 끝난 뒤 공통 계약을 만들 수 있는지 재평가한다.

### 한쪽만 지적했지만 사실인 2건

6. 교차검증 B의 결함 7이 말한 “9블록 대 7블록” 수치는 틀렸다. 정본은 `html_renderer._default_page_plan`의 11블록(`hero`, `statement`, `feature_grid`, `detail_split`, `wide_image`, `gallery`, `usage_scene`, `palette`, `scale_reference`, `notice`, `closing`) 대 `react_document_builder._fallback_blocks`의 3블록(`hero`, `statement`, `closing`)이다. `validation.py:82-83`의 빈 `page_plan` 처리 때문에 fallback은 도달 가능하지만, 저장된 파일럿 69건의 `page_plan`은 모두 비어 있지 않아 현재는 잠복 상태다. 이는 리팩터링 항목이 아니라 별건 버그 절에 기록한다.
7. 교차검증 B의 `app.py:75` 함수 내부 `local_detail_page_ai.factory` import는 사실이다. 그러나 `tests/test_project_layout.py:127-129`가 함수 레벨 import를 의도적으로 허용한다고 명시하므로 결함으로 수정하지 않고 의도된 설계 절에 기록한다.

### 상충한 1건

8. `persistence.py`에 대해 교차검증 A는 유지, 교차검증 B는 Jobs/Outbox 분리를 제안했다. 관리자 실측은 Job/Outbox가 560행에서 깔끔히 갈리고 최장 함수가 55줄인 넓고 얕은 모듈이며, 분리는 쉽지만 얻는 것이 적다는 결론이다. 따라서 1차 범위에서는 제외한다. 두 진단의 주장은 근거 기록으로 남기되, 파일 이동·re-export façade 도입은 이 계획에서 하지 않는다.

## 기준선과 공통 합격 판정

기준선은 “리팩터링 전후 산출물이 같은가”를 확인하는 유일한 안전장치다. 구조가 좋아졌다는 정성 판단만으로는 프롬프트 byte, DTO alias, 사진 provenance, HTML, React AST, outbox 상태 전이 중 하나의 미세한 변경을 발견할 수 없다. 따라서 모든 대상은 같은 입력과 같은 fixture를 기준선 커밋 `c1d413f`의 산출물과 새 산출물로 나란히 비교한다. 현재 실행 중인 60건은 변경 전의 비교 기준으로만 보존하고, 평가 중인 코드에 섞이지 않게 한다.

공통 통과 조건은 다음과 같다.

- 현재 기준 회귀인 `pytest -q`가 리팩터링 전후 각각 328 passed, 0 failed, 0 error다.
- 공개 호출부와 직렬화 계약이 동일하다. `PipelineResult`, `DraftPipelineResult`, BE request, FE result, `react_document`, HTML, photo metadata, outbox 상태 전이를 기준선과 구조적으로 비교한다.
- 기존 import 경로가 계속 동작한다. 분리된 모듈을 직접 참조하게 바꾸더라도 기존 façade의 공개 심볼과 `__all__`/module-level re-export 결과가 동일하다.
- 저장된 동일 fixture에 대해 `check_cutout_fidelity.py`, `check_plan_diversity.py`, `check_reference_label.py`의 판정이 기준선과 달라지지 않는다.
- 각 단계 전후 `git diff --check`와 새 Python interpreter import 검사를 통과한다.

합격 조건을 만족하지 못한 단계는 다음 단계로 진행하지 않는다. “차이가 있지만 더 좋아 보인다”는 합격 사유가 아니며, 그 차이가 기능 변경이면 별도 작업으로 분리한다.

## 확정 실행 순서

### Task 0: 평가 완료 확인과 기준선 고정

**Files:**

- Read: `generated/evaluation/full60-20260910-204433`
- Read: 기준선 커밋 `c1d413f`의 코드·테스트·기존 평가 산출물
- Do not modify: `src/`, `scripts/`, 현재 실행 중인 평가 산출물

**Interfaces:**

- Consumes: 평가 완료 신호, 기준선 커밋, 저장된 60건 산출물
- Produces: 이후 각 단계가 비교할 변경 전 output set과 회귀 명세

- [ ] **Step 1: 평가 완료와 산출물 보존을 확인한다.**

  `generated/evaluation/full60-20260910-204433`의 상태와 기준선 커밋 `c1d413f`를 확인한다. 실행 중이거나 산출물이 불완전하면 이 계획의 코드 작업을 시작하지 않는다.

- [ ] **Step 2: 변경 전 characterization 목록을 고정한다.**

  final/draft의 profile, `ApprovedDraftDto`, 진행 상태 sequence, BE request, FE result, React AST, HTML, photo provenance, outbox 전이를 기준선과 함께 보관한다. 프롬프트는 archetype 없음·빈 목록·단일 선택·복수 후보 및 user hints 유무를 각각 저장한다.

- [ ] **Step 3: 기준선의 품질 게이트를 기록한다.**

  저장된 동일 fixture에 세 게이트를 적용해 기준선 판정을 기록한다. 모델이나 파일럿을 다시 실행하지 않으며, 이후 단계의 비교 입력과 기대 결과는 이 기록을 사용한다.

**Acceptance criteria:** 평가가 완료되고 기준선 산출물이 읽히며, 변경 전 characterization set과 세 품질 게이트 결과가 재현 가능하다. 기준선 산출물 누락·손상, 평가 미완료, 현재 코드와 기준선 커밋의 대상 불일치가 있으면 중단한다.

### Task 1: `dto ↔ react_document_builder` 순환 제거

**Files:**

- Modify: `src/detail_page_ai/dto.py:404-439`, `AiFeStatusResponse.completed`
- Modify: `tests/test_dto.py:89`
- Possible create only if an external consumer is confirmed: `src/detail_page_ai/response_factory.py`
- Test: `tests/test_dto.py`, `tests/test_react_document.py`

**Interfaces:**

- Consumes: Task 0의 `AiFeStatusResponse` serialization/AST characterization과 외부 소비자 확인 결과
- Produces: DTO가 `react_document_builder`를 import하지 않는 구조, 기존 내부 호출 계약, 외부 소비자에 대한 명시적 보존 또는 breaking-change 판정

- [ ] **Step 1: 저장소 및 외부 소비자 호출을 확인한다.**

  `AiFeStatusResponse.completed`의 저장소 내 호출은 `tests/test_dto.py:89` 한 곳이고 프로덕션 호출은 0곳이라는 정본을 다시 확인한다. SDK·문서 등 저장소 외 소비자가 확인되지 않기 전에는 public classmethod를 제거하지 않는다.

- [ ] **Step 2: 외부 소비자가 없을 때 테스트를 명시적 DTO 조립으로 바꾼다.**

  외부 소비자가 없으면 `tests/test_dto.py:89`에서 `AiFeStatusResponse(...)`를 직접 조립하거나 테스트 전용 helper를 사용한다. `dto.py`의 `completed`가 `react_document_builder`를 참조하지 않게 하고 DTO field명·alias·serialization 결과는 그대로 둔다.

- [ ] **Step 3: 외부 소비자가 있을 때 façade 위치를 별도로 보존한다.**

  외부 소비자가 확인되면 classmethod 제거를 수행하지 않는다. 필요한 경우에만 `response_factory.py`로 convenience factory를 이동하고, DTO 모듈은 builder를 import하지 않도록 한다. 외부 호환을 깨는 변경은 관리자 승인 전에는 이 Task에서 수행하지 않는다.

- [ ] **Step 4: import와 DTO/AST 회귀를 실행한다.**

  다음 검사를 수행한다.

  ```bash
  python -c "import detail_page_ai.dto; import detail_page_ai.react_document_builder; import detail_page_ai"
  pytest -q tests/test_dto.py tests/test_react_document.py
  pytest -q
  ```

**Acceptance criteria:** 새 interpreter에서 `detail_page_ai.dto`, `detail_page_ai.react_document_builder`, `detail_page_ai` import가 모두 성공하고, DTO serialization alias·AST schema·전체 테스트가 기준선과 동일하다. `AiFeStatusResponse.completed` 제거 또는 이동 후에도 저장소 내 프로덕션 호출이 0이고 테스트가 328 passed다.

**Stop conditions:** 외부 SDK/문서 호출이 발견됨, DTO dump/alias/schema가 변경됨, import cycle이 남음, 테스트 실패, 또는 classmethod 제거를 위해 다른 기능을 바꿔야 함. 이 경우 해당 변경을 되돌리고 외부 호환성 문제를 별도 결정으로 올린다.

### Task 2: `pipeline.run` 3단 분리

**Files:**

- Modify: `src/detail_page_ai/pipeline.py:126-524`, `DetailPagePipeline.run`, `DetailPagePipeline.create_draft`
- Create: `src/detail_page_ai/profile_preparation.py` — `prepare_profile(...)` 내부 책임
- Create: `src/detail_page_ai/generation_delivery.py` — `assemble_generation_artifacts(...)`, `deliver_artifacts(...)` 내부 책임
- Keep unchanged: `service.py`, `app.py`, `scripts/runtime/run_local_detail_page.py`, `scripts/run_eval_pilot.py`의 기존 `run` 호출부 6곳
- Test: `tests/test_pipeline.py`, `tests/test_draft_flow.py`, `tests/test_service.py`

**Interfaces:**

- Consumes: Task 0 characterization과 Task 1 이후의 동일 DTO/import 계약
- Produces: 공개 `run(...) -> PipelineResult`와 `create_draft(...) -> DraftPipelineResult`를 유지하는 세 내부 경계
  1. `prepare_profile(...)`: validate/analyze/research/page-plan/sanitize를 수행하고 `profile`, `ApprovedDraftDto`, source asset 정보를 반환한다.
  2. `assemble_generation_artifacts(...)`: renderer 결과 검증, asset 저장, hash·section·photo metadata, React document, BE/FE DTO를 하나의 내부 immutable bundle로 조립한다.
  3. `deliver_artifacts(...)`: outbox enqueue/claim/heartbeat/backend persist와 `PipelineResult`의 delivery 상태만 담당한다.

- [ ] **Step 1: final/draft 공통 준비 경계를 characterization test로 고정한다.**

  `run`과 `create_draft`에서 현재 7단계인 입력 검증, analyzer 호출, profile 검증, craft research 판단/호출, editorial page plan 보장, render sanitizer, `ApprovedDraftDto.from_profile`의 결과와 호출 순서를 고정한다. agy 진단의 `_analyze_and_build_draft(...)` 제안은 이 공통 `prepare_profile(...)` 경계로 반영한다.

- [ ] **Step 2: profile preparation을 내부 모듈로 추출한다.**

  `run`과 `create_draft`가 같은 `prepare_profile(...)` 결과를 사용하게 하되, research 조건·sanitizer·기본 page plan의 의미와 호출 순서는 바꾸지 않는다. `run`의 외부 호출부와 반환 타입은 수정하지 않는다.

- [ ] **Step 3: 생성 산출물 조립을 immutable bundle로 추출한다.**

  renderer 반환값에서 asset 저장, photo/section metadata, React document, BE/FE DTO를 만드는 기존 순서를 `assemble_generation_artifacts(...)`로 옮긴다. ID, hash, metadata field, photo provenance, asset 저장 시점은 기준선과 같아야 한다.

- [ ] **Step 4: 배송·상태 전이를 별도 경계로 추출한다.**

  outbox enqueue/claim, lease heartbeat, backend persist, `BackendDeliveryError`, `LeaseOwnershipError`, recovery와 경쟁 claim 처리를 `deliver_artifacts(...)`로 옮긴다. retry 횟수·시간, progress/status 값, approval 재실행 순서는 바꾸지 않는다.

- [ ] **Step 5: 정상·실패 흐름을 비교한다.**

  다음 경우의 기준선 output과 새 output을 비교한다: 정상 전달, `BackendDeliveryError`, `LeaseOwnershipError`, outbox recovery, approval 재실행, final flow, draft flow. BE request, FE result, React document, HTML, outbox state transition을 필드 단위로 비교한다.

  ```bash
  pytest -q tests/test_pipeline.py tests/test_draft_flow.py tests/test_service.py
  pytest -q
  ```

**Acceptance criteria:** `run`/`create_draft`의 공개 signature·return DTO와 6개 실행 호출부가 동일하고, 위 정상·실패 시나리오의 profile, approved draft, 진행 상태 sequence, asset/photo metadata, BE/FE 결과, outbox 상태가 기준선과 동일하다. 새 모듈은 내부 구현 경계만 제공하며 retry·research·renderer 순서를 바꾸지 않는다.

**Stop conditions:** 한 시나리오라도 output/state/progress/asset metadata가 기준선과 다름, public signature 변경 필요, delivery retry/lease 의미 변경 필요, 새 기능 요구가 발생함, 또는 전체 328 테스트 실패. 차이를 “개선”으로 흡수하지 말고 해당 단계에서 멈춘다.

### Task 3: `prompts.py` 텍스트·이미지 프롬프트 분리

**Files:**

- Modify: `src/detail_page_ai/prompts.py:30-1095` — 기존 심볼을 유지하는 façade/re-export
- Create: `src/detail_page_ai/text_prompts.py` — 텍스트 LLM 영역(30~518행)의 분석·공예 연구·레이아웃 기획 프롬프트와 버전 상수
- Create: `src/detail_page_ai/image_prompts.py` — 이미지 영역(521~1095행)의 배경·사용 씬·디테일 컷 프롬프트와 `_product_scene_direction`
- Test: `tests/test_prompts.py`, `tests/test_user_hints.py`

**Interfaces:**

- Consumes: Task 0에 저장한 모든 `build_analysis_prompt` snapshot과 기존 import 경로
- Produces: `prompts.py`에서 기존 공개 심볼을 re-export하는 하위 호환 façade, section renderer 기반의 byte-equivalent prompt builder

- [ ] **Step 1: 기존 프롬프트 소비자와 symbol inventory를 고정한다.**

  텍스트 소비자는 `src/local_detail_page_ai/adapters.py`의 `build_analysis_prompt` 1곳, 이미지 소비자는 `src/local_detail_page_ai/runner.py`의 4개 심볼과 `check_scene_direction_coverage.py`다. `ANALYSIS_PROMPT_VERSION` 및 `BACKGROUND_PROMPT_VERSION`을 포함한 기존 심볼을 inventory로 만든다.

- [ ] **Step 2: section renderer를 먼저 만든다.**

  이미 조립된 본문을 `prompt.index()`와 `replace(..., 1)`로 다시 치환하지 않고 다음 이름 있는 section renderer를 순서대로 조립한다.

  ```text
  _analysis_contract_section
  _creator_data_section
  _page_plan_section(selected_layout_instruction)
  _final_checks_section(selected_layout_instruction)
  ```

  각 함수는 완결된 문자열을 반환하고, `build_analysis_prompt`의 인자·반환값과 문구·공백·줄바꿈은 변경하지 않는다.

- [ ] **Step 3: 텍스트·이미지 모듈을 분리하고 façade를 채운다.**

  텍스트 LLM 심볼은 `text_prompts.py`, 이미지 디퓨전 심볼과 `_product_scene_direction`은 `image_prompts.py`로 이동한다. `prompts.py`는 기존 import 경로에서 같은 객체/상수/함수를 제공하도록 re-export한다. 호출부는 이 Task에서 새 경로로 일괄 교체하지 않는다.

- [ ] **Step 4: byte equality와 기존 테스트를 검증한다.**

  archetype 없음, 빈 목록, 단일 선택, 복수 후보, user hints 유무의 각 입력에서 기준선 prompt bytes와 새 prompt bytes가 `==`인지 비교한다. `prompt.index()` 실패나 의도하지 않은 section 중복이 없어야 한다.

  ```bash
  pytest -q tests/test_prompts.py tests/test_user_hints.py
  pytest -q
  ```

**Acceptance criteria:** 모든 고정 입력에서 `old_prompt_bytes == new_prompt_bytes`, 기존 `prompts.py` import 결과와 `__all__`가 호환되고, 텍스트/이미지 소비자 호출부가 같은 심볼을 얻으며, 전체 328 테스트가 통과한다. 문구 개선이나 모델 입력 의미 변경은 포함하지 않는다.

**Stop conditions:** snapshot byte 불일치, whitespace·heading 차이, `ValueError`, façade에서 빠진 심볼, 이미지 프롬프트 출력 차이, 모델 평가 결과를 확인하기 위해 문구를 바꿔야 하는 상황. byte equality를 포기하고 진행하지 않는다.

### Task 4: 사진 역할·provenance 정책 일원화

**Files:**

- Create: `src/detail_page_ai/photo_role_policy.py` — role별 source 기본 label, 허용 asset mode, `product_generated` 허용 여부, HTML 표시 가능 여부, block 기본 ID
- Create: `src/detail_page_ai/cutouts.py` — `ProductCutout`, `SolidBackgroundCutoutExtractor`, `_encode_png`, `_decode_rgb`의 순수 CV 책임
- Create: `src/detail_page_ai/fidelity.py` — `ProductFidelityValidator`
- Modify: `src/detail_page_ai/source_photos.py:87-1120` — 생성기·프로토콜·합성 오케스트레이션과 호환 re-export façade
- Modify: `src/detail_page_ai/html_renderer.py:580-615`
- Modify: `src/detail_page_ai/react_document_builder.py:13-25, 211-222`
- Possible modify: validator 호출 경계가 policy를 조회하도록 연결되는 현재 위치
- Test: `tests/test_source_photos.py`, `tests/test_html_renderer.py`, `tests/test_react_document.py`, `tests/test_pipeline.py`

**Interfaces:**

- Consumes: Task 0의 source/fallback/composite/generated scene/generated detail view fixture와 기존 public signatures
- Produces: generator, validator, HTML, React builder가 동일 policy source를 조회하고 기존 `ProductPhoto` id/label/provenance와 whitelist 결과를 유지하는 구조

- [ ] **Step 1: role matrix의 현재 결과를 먼저 고정한다.**

  `role × asset_mode × product_generated × fidelity_status` 행렬의 현재 허용/거부 결과를 테스트로 고정한다. `source_photos.py:379-510`의 `ProductFidelityValidator`, `:515-764`의 생성 경로, `html_renderer.py:580-615`의 출력 필터, `react_document_builder.py:13-25, 211-222`의 block/photo 기본값을 같은 fixture에 대조한다.

- [ ] **Step 2: 정책 값을 단일 읽기 경로로 옮긴다.**

  `photo_role_policy.py`가 위 행렬에 필요한 순수 값을 제공하도록 하고, `SourcePreservingProductPhotoGenerator.generate`, `ProductFidelityValidator.validate`, `build_detail_page_html`, `build_react_document_from_draft`의 공개 signature는 유지한다. role 값, label 문구, whitelist 결과는 그대로 둔다.

- [ ] **Step 3: `source_photos.py`의 순수 CV·검증·생성 책임을 분리한다.**

  `cutouts.py`와 `fidelity.py`로 옮긴 뒤 `source_photos.py`에서 기존 심볼을 re-export한다. `training_augmentation.py`, `pipeline.py`, `factory.py`, `runner.py`, `generate_attached_detail_page.py`와 테스트가 기존 import 경로로 계속 동작하는지 확인한다. 알고리즘 계수, mask/crop/composite tolerance, 생성 경로는 수정하지 않는다.

- [ ] **Step 4: HTML·React가 같은 허용 사진을 참조하는지 검증한다.**

  source/fallback/composite/generated scene/generated detail view의 `ProductPhoto` id, label, provenance를 golden fixture와 비교하고, HTML과 React document의 허용 사진 ID 집합이 같은지 확인한다.

  ```bash
  pytest -q tests/test_source_photos.py tests/test_html_renderer.py tests/test_react_document.py tests/test_pipeline.py
  pytest -q
  ```

**Acceptance criteria:** role matrix의 허용/거부 결과, `ProductPhoto` id·label·provenance, HTML/React 허용 사진 ID, cutout fidelity 판정이 기준선과 동일하다. `source_photos.py`의 기존 공개 import 경로와 생성기·validator signature가 유지되고 전체 테스트가 328 passed다.

**Stop conditions:** role 확대/차단, label 문구 변경, `asset_mode`·`product_generated` 판정 변경, HTML 표시 위치 변경, cutout 알고리즘/tolerance 변경, HTML과 React의 사진 ID 집합 불일치, 또는 provenance 안전 경계의 기능 변경이 필요해짐. 해당 변경은 별도 안전·기능 작업으로 올린다.

### Task 5: 두 렌더러 공통 계약 재평가 게이트

이 항목은 Task 4 완료 후에만 재평가한다. `react_document`와 HTML/PNG 렌더러 자체를 합치지 않으며, 공통 source를 도입하는 경우에도 두 실패 경계를 유지한다.

**Files:**

- Read/compare: `src/detail_page_ai/html_renderer.py`의 `_default_page_plan`, `_block_image`
- Read/compare: `src/detail_page_ai/react_document_builder.py`의 `_DEFAULT_PHOTO_BY_BLOCK`, `_fallback_blocks`
- Candidate only after the gate: `src/detail_page_ai/layout_archetypes.py` 또는 `src/detail_page_ai/presentation_contracts.py`
- Test: `tests/test_html_renderer.py`, `tests/test_react_document.py`, `tests/test_safety.py`

**Interfaces:**

- Consumes: Task 4 이후 안정화된 photo policy와 기준선 HTML/React fallback fixture
- Produces: 공통 계약을 도입할지에 대한 output-equivalence 판정. 1차 확정 실행의 완료 조건은 “기능 변경 없이 공통화 가능” 또는 “효과보다 위험이 커 보류” 중 하나를 근거와 함께 확정하는 것이다.

- [ ] **Step 1: 기본 매핑 중복과 fallback을 별도로 계측한다.**

  block type별 default photo mapping과 empty `page_plan` 경로를 HTML/React 각각 기록한다. 관리자 정본에 따라 HTML은 11블록, React는 3블록이며, 이는 agy 진단서의 9 대 7 수치로 대체하지 않는다.

- [ ] **Step 2: 공통 source의 무회귀 가능성을 비교한다.**

  동일 profile/photo set에서 공통 mapping source를 사용했을 때 HTML과 React의 public output, AST, page plan, photo ID가 기준선과 byte/구조적으로 같은지 확인한다. 공통화가 fallback 시퀀스나 렌더러의 실패 경계를 바꾸면 도입하지 않는다.

- [ ] **Step 3: 재평가 결과를 확정한다.**

  output-equivalence와 기존 browser/layout 검사를 모두 통과한 경우에만 candidate module을 별도 작업으로 승인한다. 하나라도 기준선과 다르거나 FE/web 변경이 필요하면 이 계획에서는 중복을 유지하고 보류 사유를 기록한다.

**Acceptance criteria:** 두 renderer의 공개 API·실패 경계가 유지되고, 공통화 후보를 적용한 경우에도 기준선의 HTML, React AST, page-plan, photo mapping과 정확히 동일하다. 이 게이트에서 fallback divergence 자체를 수정하는 것은 합격 조건이 아니다.

**Stop conditions:** 두 renderer를 하나로 합쳐야 함, fallback output을 “올바르게” 맞추기 위해 기대 동작을 새로 정해야 함, FE/web 변경이 필요함, HTML/AST/사진 ID가 기준선과 다름. 이 경우 별도 버그/제품 요구사항으로 분리한다.

## 리팩터링과 분리할 사실·버그·의도된 설계

### 별건 버그: 빈 `page_plan` fallback divergence

- `src/detail_page_ai/validation.py:82-83`의 `ensure_editorial_page_plan`은 빈 `page_plan`을 그대로 반환하므로 fallback 경로가 도달 가능하다.
- 정본 fallback은 `html_renderer._default_page_plan` 11블록 대 `react_document_builder._fallback_blocks` 3블록이다.
- 저장된 파일럿 69건은 모두 `page_plan`이 비어 있지 않아 현재 잠복 상태다.
- 이 계획에서는 divergence를 고치지 않는다. 원하는 fallback 시퀀스, 두 renderer의 실패 경계, HTML/React 계약을 별도로 결정한 뒤 별도 버그 계획과 fixture를 만든다.

### 의도된 설계: `app.py` 함수 레벨 import

- `src/detail_page_ai/app.py:73-79`의 `build_service` 내부 `from local_detail_page_ai.factory import build_service as build_local_service`는 사실이다.
- `tests/test_project_layout.py:127-129`가 함수 레벨 import를 의도적으로 허용한다.
- 따라서 코어/로컬 패키지 계층을 재설계하라는 별도 요구가 없으면 이 import를 결함으로 취급하거나 수정하지 않는다.

### 1차 범위 제외: `persistence.py`

- 교차검증 A는 JobRepository/DeliveryOutbox를 현재 adapter 경계로 유지하자고 했고, 교차검증 B는 `jobs_repository.py`·`outbox.py`·façade 분리를 제안했다.
- 관리자 실측은 560행에서 Job/Outbox가 깔끔히 갈리고 최장 함수가 55줄인 넓고 얕은 모듈이며, 분리 난이도보다 얻는 효과가 작다고 결론냈다.
- 따라서 `persistence.py`의 파일 이동, 심볼 re-export, DDL/직렬화/transaction 경계 변경은 1차에 포함하지 않는다. 향후 별도 가치·위험 분석 없이 다시 열지 않는다.

## 최종 검증 게이트와 인수 조건

### Gate 1: 테스트와 import

- Task 1~4 각각의 대상 모듈 테스트와 전체 `pytest -q`를 실행한다.
- 기대 결과는 리팩터링 전과 동일한 328 passed, 0 failed, 0 error다.
- 새 Python interpreter에서 `detail_page_ai.dto`, `detail_page_ai.react_document_builder`, 패키지 root를 import하고, `dto.py:417` 지연 import 순환이 사라졌는지 확인한다.

### Gate 2: 공개 façade와 계약

- `source_photos.py`, `prompts.py`에서 기존 public symbol/import path가 그대로 resolve되는지 확인한다. `persistence.py`는 이번 계획에서 변경하지 않는다.
- `run`, `create_draft`, `build_detail_page_html`, renderer public API와 DTO field/alias를 기준선과 비교한다.
- `react_document`는 `extra="forbid"`, depth 20, node 300, 색상·URL 제약을 완화하지 않는다.

### Gate 3: 정적 의존성과 결과 비교

- Python `ast`로 `src/` import graph를 다시 분석해 순환 참조가 0건인지 확인한다.
- 같은 source/profile/photo fixture로 BE request, FE result, React AST, HTML, photo provenance와 outbox state transition을 기준선과 비교한다.
- `prompts.py` 분리 결과는 prompt bytes가 입력별로 `==`인지 비교하고, HTML/React 공통 계약 재평가 결과는 browser/layout 검사까지 포함한다.

### Gate 4: 저장 산출물 품질 게이트

- 기존 산출물 또는 승인된 고정 fixture에 다음 세 스크립트를 적용한다.

  ```bash
  .venv/bin/python scripts/check_cutout_fidelity.py <saved-pilot-or-fixture> --role hero
  .venv/bin/python scripts/check_plan_diversity.py <saved-pilot-or-fixture>
  .venv/bin/python scripts/check_reference_label.py <saved-pilot-or-fixture>
  ```

- cutout fidelity, plan diversity/Jaccard, `참고용` 라벨 및 원본 오표기 판정이 기준선과 달라지지 않아야 한다. 스크립트 인자나 대상 경로가 실제 저장 산출물과 맞지 않으면 실행을 강행하지 말고 확인 필요로 남긴다.

### 인수 및 중단 원칙

- 네 가지 핵심 리팩터링(Task 1~4)은 각 단계의 acceptance criteria와 모든 공통 gate를 통과해야 다음 단계로 진행한다.
- Task 5는 공통화 여부를 재평가하는 결정 게이트이며, fallback divergence를 고치는 기능 작업이 아니다.
- 어느 단계에서든 출력·상태·프롬프트 bytes·사진 provenance·public contract가 변하면 그 단계는 실패다. 차이를 고치는 과정에서 정책·문구·기능 변경이 필요하면 관리자에게 올리고 별도 계획으로 분리한다.
- 현재 요청에서는 위 계획서를 제외한 `src/`, `scripts/`, 모델·파일럿 산출물을 변경하거나 60건 평가를 재실행하지 않는다.
