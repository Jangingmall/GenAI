# 코드 정리 진단 — Codex 교차 A

기준 커밋: `cfd60bb` (`feat: cut products out with rembg and stop stamping generated photos`)
진단 범위: `src/detail_page_ai`, `src/local_detail_page_ai`, `scripts`, `tests`, `docs` (단, `docs/deliverables/`, `web/` 제외)
판정 기준: `[필요]`는 현재 오사용·실패·문서 불일치·호출처 없는 유지비를 실제로 만드는 경우만 표시했다. 구조를 보기 좋게 만드는 제안은 현재 문제가 없으면 `[불필요]`다.

## [필요] 실행 목록

1. **[필요]** `src/detail_page_ai/prompts.py`의 호출 없는 `build_generated_detail_view_prompt`와 사용되지 않는 프롬프트 버전 상수 6개를 삭제한다.
2. **[필요]** 하드코딩된 분홍 손잡이 부채 데모를 실제 실행기처럼 보이는 `scripts/runtime/generate_attached_detail_page.py`에서 분리하거나 이름을 명확히 바꾸고, 이를 실제 일괄 생성기로 소개하는 API 문서를 고친다.
3. **[필요]** 더 이상 출력하지 않는 `참고용` 라벨을 배포 차단 조건으로 요구하는 검수·안전 문서를 현재 `product_generated` 메타데이터 정책과 맞춘다.
4. **[필요]** `docs/internal/refactoring/refactoring-plan.md`의 기준선·삭제된 라벨 게이트·사진 정책을 `cfd60bb` 기준으로 다시 고정한 뒤에만 기존 구조 리팩터링 계획을 실행한다.
5. **[필요]** 전수 테스트가 모든 assertion 뒤 인터프리터 종료에서 `recursive_mutex` 오류로 `134`가 되는 원인을 별도 디버깅해, 회귀 게이트가 실제 종료 코드 0으로 끝나게 한다.

## 조사 방법과 한계

- `rg -n`으로 Python import/call, 문서 문자열, 스크립트 파일명, 프롬프트 심볼을 검색했다. `src`·`scripts`의 `importlib`, `__import__`, `runpy`, subprocess 기반 모듈 실행도 검색했으며 대상 심볼·파일명을 문자열로 불러오는 동적 참조는 찾지 못했다. 각 CLI의 `if __name__ == "__main__"` 진입점도 확인했다.
- 의존성은 `pyproject.toml`, `uv.lock`, `uv pip tree --python .venv/bin/python`, `uv pip check --python .venv/bin/python`으로 대조했다. `uv pip check`은 설치된 51개 패키지 모두 호환된다고 보고했다.
- 이는 저장소 내부 근거다. 공개되지 않은 외부 사용자가 Python 내부 심볼을 직접 import하는지는 저장소만으로 증명할 수 없으므로, 삭제 후보는 먼저 전체 테스트와 새 인터프리터 import를 통과시켜야 한다.

## A. 삭제

### [필요] 호출 없는 이미지 프롬프트 빌더와 버전 상수

- **파일·심볼:** `src/detail_page_ai/prompts.py:10-15, 1053-1095`의 `ANALYSIS_PROMPT_VERSION`, `CRAFT_RESEARCH_PROMPT_VERSION`, `BACKGROUND_PROMPT_VERSION`, `USAGE_SCENE_PROMPT_VERSION`, `GENERATED_USAGE_SCENE_PROMPT_VERSION`, `GENERATED_DETAIL_CUT_PROMPT_VERSION`, `build_generated_detail_view_prompt`.
- **코드 근거:** `SUPPORTED_LAYOUT_VARIANTS`만 이 파일 안에서 실제 사용된다. `rg` 결과에서 여섯 버전 상수는 선언 외 Python 소비자가 없고(일부는 과거 진단/평가 문서의 문자열 언급만 있음), `build_generated_detail_view_prompt`는 정의 한 곳뿐이다. 반면 실제 실행 경로는 `src/local_detail_page_ai/runner.py`가 `build_background_prompt`, `build_usage_context_background_prompt`, `build_generated_usage_scene_prompt`, `build_generated_detail_cut_prompt` 네 개를 import하여 호출한다. 따라서 그 네 개는 삭제 대상이 아니다.
- **제안 조치:** 위 여섯 심볼을 삭제한다. 프롬프트 버전 값을 산출물 메타데이터에 실제 기록하려는 별도 요구가 생기면, 그때 생성 경로와 함께 명시적으로 도입한다.
- **영향 범위:** 저장소 실행 코드 호출 0곳, 테스트 호출 0곳. 동적 import·문자열 실행 참조도 0곳이다. 과거 문서의 버전 설명은 실제 런타임 추적 근거가 아니므로, 삭제 시 해당 문구를 현재 사실로 오해하지 않게 함께 정리한다.
- **동작 변경 여부:** 없음. 현재 어떤 실행도 이 심볼을 읽지 않는다.
- **검증 방법:** `rg` 재검색으로 정의/호출이 사라졌는지 확인하고, `.venv/bin/python -m pytest -q` 및 `PYTHONPATH=src .venv/bin/python -c 'import detail_page_ai.prompts'`를 실행한다.

### [불필요] `SolidBackgroundCutoutExtractor` 삭제

- **파일·심볼:** `src/detail_page_ai/source_photos.py:103-396`, `SolidBackgroundCutoutExtractor`.
- **코드 근거:** 상세페이지 기본 추출기는 `RembgCutoutExtractor`다(`SourcePreservingProductPhotoGenerator.__init__`: 679, `ProductFidelityValidator.__init__`: 509). 그러나 legacy extractor는 `src/detail_page_ai/training_augmentation.py:172`의 결정론적 학습 증강과 `scripts/compare_cutout_regression.py`의 비교 기준선에서 실제 생성된다. `tests/test_source_photos.py`와 `tests/test_cutout_regression.py`도 이를 직접 검증한다.
- **제안 조치:** 삭제하지 않는다. 이름·모듈 분리는 구조 작업을 승인할 때만 별도로 판단한다.
- **영향 범위:** 실행 코드 2곳(학습 증강 1, 비교 스크립트 1), 테스트 2파일의 직접 사용, 비교·학습 용도 문서 참조가 있다.
- **동작 변경 여부:** 삭제하면 재현 가능한 증강과 rembg 이전/이후 비교 기준선을 없앤다.
- **검증 방법:** 현 상태 유지. 추후 폐기 결정을 내릴 때에만 `tests/test_training_augmentation.py tests/test_cutout_regression.py tests/test_source_photos.py`와 비교 산출물 재현성을 함께 검증한다.
- **불필요 이유:** 실제 호출처와 보존 목적이 있으므로, 단지 기본 추출기가 아니라는 이유만으로 지우면 안 된다.

### [불필요] 컷아웃 평가 스크립트 삭제

- **파일·심볼:** `scripts/compare_cutout_regression.py`, `scripts/audit_cutout_truth.py`, `scripts/check_cutout_fidelity.py`.
- **코드 근거:** `compare_cutout_regression.py`는 legacy extractor를 직접 import하며 `tests/test_cutout_regression.py`가 함수·CLI를 10회 참조하고 `docs/phase4/evaluation/full60-runs.md`가 실행 절차를 남긴다. `audit_cutout_truth.py`는 60건 ground-truth 진단을 수행하며 `tests/test_cutout_truth.py`가 5회 참조한다. `check_cutout_fidelity.py`는 legacy extractor를 import하지 않고 산출물 provenance/이미지 비율을 검사하며 `tests/test_eval_scripts.py`가 15회, 운영·평가 문서가 여러 번 참조한다.
- **제안 조치:** 셋 모두 유지한다. rembg 기준의 새 품질 지표가 필요하면 기존 도구를 삭제하지 말고 별도 검증 요구로 추가한다.
- **영향 범위:** 파이프라인 런타임 호출은 0곳이지만, 각각 테스트와 재현 가능한 평가 CLI의 공개 진입점이다.
- **동작 변경 여부:** 삭제하면 과거 기준선 비교, 60건 ground-truth 감사 또는 현재 fidelity gate가 사라진다.
- **검증 방법:** 현 상태 유지. 향후 교체 시 기존 저장 산출물에서 세 도구의 목적별 결과를 비교한다.
- **불필요 이유:** 기본 추출기 변경만으로 평가·회귀 도구의 목적이 사라지지 않았다.

## B. 정리

### [필요] 실제 파이프라인처럼 보이는 하드코딩 데모와 문서 연결

- **파일·심볼:** `scripts/runtime/generate_attached_detail_page.py:1-211`, 특히 `build_profile()` 25행과 `generate()` 151행; `docs/phase3/api/be-fe-ai-integration-spec.md:563`.
- **문제 근거:** 스크립트 자체 docstring은 로컬 모델이 없을 때 hand-checked profile을 사용한다고 말하고, `build_profile()`은 제목·특징·페이지 블록을 모두 “분홍 곡선 손잡이 부채”로 고정한다. `generate()`도 `model_run: False` 산출물을 만든다. 반면 API 문서는 이 파일을 “첨부 산출물 일괄 생성기”로 소개한다. 관리자가 실제 첨부 이미지 파이프라인으로 오인해 잘못된 결과를 낸 사실과 정확히 일치한다.
- **제안 조치:** 이 데모를 예시/fixture 성격이 드러나는 이름과 위치로 옮기거나 이름을 바꾸고, 문서에는 실제 입력 기반 진입점인 `scripts/runtime/run_local_detail_page.py`만 운영 실행기로 표시한다. 데모를 보존할 경우 첫 줄·CLI 도움말·출력 메타데이터에도 하드코딩 프로필/비모델 실행임을 명시한다.
- **영향 범위:** 다른 실행 코드의 import/호출은 0곳이다. 테스트는 `tests/test_attached_detail_page.py`의 `build_profile` import 1곳과 `tests/test_project_layout.py`의 경로 검증 2곳, 문서는 위 API 목록 1곳이 직접 영향을 받는다. 동적 import는 없다.
- **동작 변경 여부:** 실제 생성 동작은 바꾸지 않고 데모의 발견 경로와 명칭만 바로잡는다. 기존 파일명을 제거하면 테스트·문서 링크는 함께 옮겨야 한다.
- **검증 방법:** `rg`로 기존 이름을 문서·테스트에서 제거/갱신했는지 확인하고, `tests/test_attached_detail_page.py tests/test_project_layout.py` 및 실제 진입점의 `--help`를 실행한다.

### [필요] 제거된 `참고용` UI 라벨을 요구하는 검수·안전 문서

- **파일·심볼:** `docs/phase2/human-review-guide.md:124-129, 165-166, 224`; `docs/phase2/ai-evaluation-and-safety-policy.md:251-256`.
- **문제 근거:** `cfd60bb`에서 `react_document_builder`의 `generated_photos` 인자와 `figcaption` reference-label 노드가 삭제됐고, `SourcePreservingProductPhotoGenerator`의 생성 라벨도 `AI 생성 활용 장면`/`AI 생성 디테일`로 바뀌었다. 현재 React 계약도 `docs/phase3/api/react-json-output-contract.md:97`에서 `figcaption`을 붙이지 않는다고 명시한다. 그런데 human review guide는 세 위치에서 “참고용” 라벨이 반드시 노출돼야 한다고 요구하고, safety policy도 두 생성 mode의 표시 문자열을 여전히 적고 있다. 현재 구현을 검수자가 거짓 FAIL로 판정하게 만드는 문서 불일치다.
- **제안 조치:** 라벨 노출 요구와 배포 차단 항목을 제거하고, 생성 여부는 `asset_mode`, `product_generated`, `fidelity_status`, `source_sha256`로 확인한다고 명시한다. 생성 결과를 원본 근거로 승격하지 않는 기존 안전 규칙은 유지한다.
- **영향 범위:** 실행 호출 0곳, 문서 2파일의 4개 정책/체크 항목. React contract와 `tests/test_react_document.py`의 무라벨 AST 기대는 유지한다.
- **동작 변경 여부:** 없음. 현재 코드·API 계약에 문서를 맞춘다.
- **검증 방법:** `rg -n '참고용|reference-label' docs`로 남은 의도적 역사 기록과 현재 운영 규칙을 구분하고, `pytest -q tests/test_react_document.py tests/test_html_renderer.py tests/test_source_photos.py`를 실행한다.

### [필요] 현재 HEAD와 맞지 않아 실행을 막는 리팩터링 계획 기준선

- **파일·심볼:** `docs/internal/refactoring/refactoring-plan.md:9, 17, 46-53, 123, 261, 323, 343-348`.
- **문제 근거:** 계획은 `c1d413f`, 328개 테스트, `scripts/check_reference_label.py`를 공통 기준으로 요구한다. 현재 HEAD는 `cfd60bb`, 기준 테스트 수는 348개이며 `cfd60bb`가 `scripts/check_reference_label.py`와 `tests/test_reference_label_gate.py`를 삭제했다. 따라서 계획대로 Gate 4를 실행하면 존재하지 않는 파일에서 실패하고, reference-label의 출력 동일성 비교는 현재 의도와 반대다.
- **제안 조치:** 코드 리팩터링 전에 계획 문서를 현 HEAD의 보존 산출물과 테스트 수로 rebaseline한다. 라벨 게이트는 제거된 UI 라벨이 아니라 provenance(`source_original`, `asset_mode`, `product_generated`, `fidelity_status`)의 현재 계약을 확인하는 방식으로 다시 정의한다. `build_react_document_from_draft`에는 더 이상 `generated_photos` 인자가 없지만, BE 요청의 `generated_photos` 메타데이터는 `pipeline.py:276-331`에 계속 존재하므로 둘을 혼동하지 않는다.
- **영향 범위:** 실행 코드 호출 0곳, 계획의 전역 gate와 Task 0~5의 acceptance criterion 전체에 영향이 있다. 현 계획을 실행하려는 모든 작업자가 영향을 받는다.
- **동작 변경 여부:** 없음. 실패하는/오래된 실행 계획을 현재 계약에 맞춘다.
- **검증 방법:** 새 기준선에서 전체 테스트 수, 삭제된 스크립트 부재, 생성·원본 사진 metadata fixture, HTML/React AST를 기록하고 계획의 모든 명령이 실제 파일로 실행되는지 dry run한다.

### [불필요] 의존성 제거·추가

- **파일·심볼:** `pyproject.toml`, `uv.lock`.
- **코드 근거:** 선언된 런타임 의존성은 모두 근거가 있다. FastAPI·Uvicorn은 `app.py`, HTTPX는 backend client/데이터셋 스크립트, Pillow는 사진·검증·평가 코드, Pydantic Settings는 설정, rembg는 `RembgCutoutExtractor`의 지연 import에 쓰인다. `onnxruntime`은 Python AST에 직접 import되지 않지만 rembg 세션의 명시적 CPU runtime으로 고정돼 있다. `python-multipart`도 `FastAPI`의 `File`/`Form` route 등록에 필요하다. pydantic은 직접 import하지만 fastapi/pydantic-settings의 전이 의존성으로 lock에 해석된다.
- **제안 조치:** 이번 정리에서 `pyproject.toml`과 `uv.lock`을 수정하지 않는다.
- **영향 범위:** `uv pip tree`의 51개 설치 패키지는 루트 선언 또는 그 전이 의존성이다. 호환성 검사는 통과했다.
- **동작 변경 여부:** 제거하면 API route·이미지 생성·rembg 런타임을 깨뜨릴 수 있다.
- **검증 방법:** 현 상태 유지.
- **불필요 이유:** 미선언 직접 import는 pydantic 하나뿐이나 두 직접 의존성이 항상 제공하므로 현재 배포 실패 근거가 없다.

### [불필요] 사용 중인 배경 프롬프트 빌더 삭제·이름 변경

- **파일·심볼:** `build_background_prompt`, `build_usage_context_background_prompt`, `build_generated_usage_scene_prompt`, `build_generated_detail_cut_prompt`.
- **코드 근거:** `src/local_detail_page_ai/runner.py:11, 49-51, 81, 111`가 네 빌더를 실제 MLX generator 요청에 사용하고 `tests/test_prompts.py`가 각 계약을 검증한다.
- **제안 조치:** 유지한다. 프롬프트 모듈 분리는 아래 C의 별도 구조 선택지로 남긴다.
- **영향 범위:** 실행 코드 소비자 2모듈(`adapters.py`의 분석 prompt 포함, `runner.py`의 이미지 prompt), 이미지 빌더 네 개와 관련 prompt 테스트가 영향을 받는다.
- **동작 변경 여부:** 삭제/이름 변경 시 로컬 이미지 생성 경로가 실패한다.
- **검증 방법:** 현 상태 유지.
- **불필요 이유:** 호출처가 있고, 현 시점의 문제가 아니라 구조 배치 문제일 뿐이다.

### [필요] 전수 회귀 게이트의 인터프리터 종료 실패

- **파일·심볼:** 아직 특정 파일/심볼로 귀속하지 못했다. `.venv/bin/python -m pytest -q`의 프로세스 종료 단계다.
- **문제 근거:** 전수 실행을 세 번 재현했으며 매번 348개 assertion이 통과한 직후 `libc++abi: terminating due to uncaught exception of type std::__1::system_error: recursive_mutex lock failed: Invalid argument`가 출력되고 종료 코드는 `134`였다. `PYTHONFAULTHANDLER=1`도 추가 Python traceback 없이 같은 결과였다. 반면 `tests/test_source_photos.py`는 `34 passed`, 종료 코드 0이고, 전수 파일을 `80`개 assertion 그룹과 `265`개 assertion 그룹(그리고 `test_security.py` 3개)으로 각각 별도 프로세스에서 실행하면 모두 종료 코드 0이었다.
- **제안 조치:** 테스트 설정을 숨기거나 `|| true`로 통과 처리하지 않는다. 결합 실행에서만 남는 native library/thread/resource 상태를 파일 이분 탐색으로 좁히고, 해당 fixture 또는 라이브러리 수명 주기를 고친 뒤 전수 명령의 종료 코드 0을 확인한다.
- **영향 범위:** 모든 PR/배포의 단일 전수 회귀 판정이 실패한다. assertion 실패는 없지만 CI는 비정상 종료를 실패로 처리한다.
- **동작 변경 여부:** 제품 동작 변경이 아니라 검증 인프라의 실패를 고치는 작업이다.
- **검증 방법:** `.venv/bin/python -m pytest -q`가 348개 assertion 통과뿐 아니라 종료 코드 0으로 끝나는지 확인하고, 필요하면 문제 조합과 단독 실행의 종료 코드도 regression test/CI 로그로 남긴다.

## C. 구조 — 기존 계획 Task 0~5 재검증

| 항목 | 상태 및 판정 | 코드 근거·영향 범위 | 제안 조치와 검증 |
| --- | --- | --- | --- |
| **[필요] Task 0 — 기준선 고정** | **변경됨.** 이전 기준선(`c1d413f`, 328, reference-label gate)은 현재 계약과 반대이거나 삭제됐다. 계획을 그대로 실행하면 존재하지 않는 CLI에서 막힌다. | `cfd60bb`는 hero `source_original`, rembg 기본 추출, 라벨 AST 제거를 도입했다. 전체 테스트 기준도 348로 바뀌었다. | B의 계획 rebaseline을 먼저 완료한다. 새 fixture에는 hero/fallback, rembg cutout, generated scene/detail metadata, 무라벨 React AST를 포함한다. |
| **[불필요] Task 1 — `dto ↔ react_document_builder` 순환 제거** | **유효.** `dto.py:417`의 함수 내부 import와 builder의 top-level DTO import는 아직 있다. 다만 `AiFeStatusResponse.completed`의 프로덕션 호출은 0곳, 테스트 호출은 `tests/test_dto.py:89` 1곳이며 현재 실패 증거가 없다. | public classmethod를 성급히 제거하면 저장소 밖 소비자를 끊을 수 있다. 라벨 제거로 builder 인자는 단순해졌지만 순환 자체는 남아 있다. | 구조 작업을 승인할 때만 새 인터프리터 import, DTO serialization, React AST를 기준선과 대조한다. 지금은 파일 분리만을 이유로 고치지 않는다. |
| **[불필요] Task 2 — `pipeline.run` 3단 분리** | **유효.** `pipeline.py`는 767행이고 `run()`은 분석·사진·렌더·asset·전달을 함께 처리한다. 하지만 현재 API/테스트 실패나 배포 장애는 확인되지 않았다. | `run()`의 실행 호출은 6곳: `app.py` 2, `service.py` 2, `scripts/runtime/run_local_detail_page.py` 1, `scripts/run_eval_pilot.py` 1이다. | Task 0 rebaseline 뒤에만 공개 signature·상태 전이·BE/FE/photo metadata를 비교하는 별도 리팩터링으로 실행한다. |
| **[불필요] Task 3 — 텍스트/이미지 `prompts.py` 분리** | **유효.** 1,095행 파일에서 `build_analysis_prompt()`의 452~459행은 문자열 `index`/`replace`로 section을 교체한다. 이 방식은 장래 문구 수정에 취약하지만 현재 테스트 실패는 없다. | 텍스트 소비자는 `adapters.py` 1곳, 이미지 소비자는 `runner.py`의 네 빌더와 `check_scene_direction_coverage.py`의 private helper다. | 이번 A의 진짜 죽은 심볼 삭제와 섞지 않는다. 분리하려면 기존 prompt byte snapshot과 기존 `prompts.py` import 호환을 보장하는 계획을 재사용한다. |
| **[불필요] Task 4 — 사진 역할·provenance 정책 일원화** | **변경됨.** 역할 정책이 여러 파일에 있는 사실은 남아 있지만, 계획의 Solid-only cutout 전제와 reference-label 비교는 `cfd60bb` 이후 낡았다. | 기본 extractor는 rembg이며, hero는 `source_original`; `ProductFidelityValidator`는 `source_original`을 hero·`VERIFIED`로 제한하고 generated mode의 `product_generated`/source hash를 검증한다. 생성기 생성 위치는 factory, runner, 하드코딩 데모의 3곳이다. | 실행하려면 matrix에 Rembg session/실패 fallback, hero 조건, 라벨 없는 React, 계속 존재하는 BE `generated_photos` metadata를 반영한다. 현재 불일치 증거가 없으므로 코드 분리는 보류한다. |
| **[불필요] Task 5 — 두 렌더러 공통 계약 재평가** | **유효하되 보류.** HTML의 11-block default와 React의 3-block fallback 차이는 남아 있고 빈 `page_plan`에서만 도달한다. 현재 저장된 경로에서 장애가 보고되지 않았고, 어느 fallback이 제품 요구인지 결정되지 않았다. | private mapping은 `html_renderer.py`와 `react_document_builder.py` 두 모듈에만 있다. HTML/React는 서로 다른 실패 경계를 가진다. | Task 4 이후 output-equivalence gate로만 재평가한다. fallback을 맞추는 것은 정리가 아니라 별도 제품/버그 결정이다. |

## 건드리면 안 되는 것

- **[불필요] hero `source_original` 정책과 BE/renderer 검증 조건:** `source_photos.py:764-774, 1017-1080`의 hero 원본 바이트 보존과 `ProductFidelityValidator.validate()`의 hero-only `source_original` 조건(547-550)은 이번에 채택된 정책이다. `pipeline.py:216, 229`의 전·후 photo set 재검증과 276~331행의 provenance 전달도 유지한다.
- **[불필요] rembg 기본 추출과 실패 폴백:** `RembgCutoutExtractor`의 lazy session·mask 안전 검증, `SourcePreservingProductPhotoGenerator`의 기본 extractor(679), cutout 실패 시 hero 원본/나머지 `source` fallback(718-761)은 바꾸지 않는다. 이는 기본 경로와 안전 저하 경계를 정의한다.
- **[불필요] `product_generated`·`asset_mode`·`fidelity_status` 의미:** 생성 scene/view의 허용 role 검증(517-536)과 원본 기반 자산의 재생성 거부(537-640)는 label UI를 없앤 뒤에도 남은 provenance 계약이다.
- **[불필요] `app.py`의 함수 내부 local factory import, `persistence.py`, `web/`:** 기존 계획이 의도된 계층 경계 또는 이번 범위 밖으로 명시했으며, 이번 조사에서도 현재 실패 근거를 찾지 못했다.

## 실행 순서와 완료 판정

1. **[필요]** 먼저 문서/데모 경로와 리팩터링 기준선을 바로잡고, 죽은 프롬프트 심볼만 별도 작은 변경으로 제거한다.
2. **[불필요]** Task 1~5 구조 작업은 새 기준선이 기록되고 실제 기능 문제가 발생하거나 관리자가 구조 개선 비용을 승인할 때만 시작한다.
3. **[필요]** 각 실제 변경 후 `git diff --check`, 해당 focused test, 전체 `.venv/bin/python -m pytest -q`, 새 인터프리터 import를 실행한다. 사진 정책 변경이 포함되는 작업은 저장 fixture의 hero/fallback/generated provenance와 HTML/React output을 함께 비교한다.
