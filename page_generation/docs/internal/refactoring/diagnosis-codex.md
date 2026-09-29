# 구조 리팩터링 진단 — 교차검증 A

## 결론과 범위

이 문서는 현재 코드의 책임 경계와 호출 관계를 읽어 작성한 진단서다. 제공된 패키지·함수 규모 수치는 다시 산정하지 않았다. 제안은 모두 **동일한 입력에 동일한 DTO, 사진 provenance, HTML, outbox 상태 전이, 프롬프트 문자열을 내는 순수 구조 변경**을 전제로 한다. 역할 정책, 프롬프트 문구, 사진 허용 조건, 재시도 정책을 바꾸는 일은 별도 기능 변경으로 분리해야 한다.

60건 평가가 시작되면 `src/`와 `scripts/`를 바꾸지 않아야 하므로, 아래의 구현은 전부 **평가 종료 후**에 한다. 평가지표·출력의 기준선만 평가 전에 보존할 수 있다.

| 우선순위 | 진단 | 효과 | 평가 전/후 |
| --- | --- | --- | --- |
| P0 | `DetailPagePipeline.run`의 생성·조립·전달 단계 혼합 | 배포/재시도 변경의 회귀 범위 축소, 단계별 테스트 가능 | 후 |
| P1 | 사진 역할·생성 허용 정책의 다중 정의 | provenance 안전 규칙의 drift 방지 | 후 |
| P1 | 분석 프롬프트의 문자열 절단 조립 | 프롬프트 계약 수정의 예측 가능성 향상 | 후 |
| P2 | 서버 HTML 조립 함수의 입력 검증·사진 정책·마크업 혼합 | HTML 계약 테스트의 국소화 | 후 |
| P3 | DTO에서 발생하는 지연 import 순환 | 의존 방향 정리, import-time 위험 제거 | 후, 외부 소비자 확인 뒤 |

P0/P1은 파일이 크기 때문에 우선하는 것이 아니다. 각각 한 흐름에서 서로 다른 실패/변경 원인을 분리할 수 없는 지점과, 안전 정책을 여러 곳에서 동기화해야 하는 지점이기 때문이다.

## P0 — `DetailPagePipeline.run`은 네 종류의 작업을 한 트랜잭션 흐름에 섞는다

### 코드 근거

`src/detail_page_ai/pipeline.py:126-447`의 `DetailPagePipeline.run`에는 다음 경계가 한 함수에 함께 있다.

- `:146-197`: 입력 검증, analyzer 호출, 선택적 craft research, profile/page-plan 정규화
- `:201-233`: 사진 생성, provenance 검증, HTML/PNG renderer 호출
- `:235-385`: asset 저장, hash·section·photo metadata 생성, React/BE/FE DTO 조립
- `:388-447`: outbox enqueue/claim, lease heartbeat, backend 전달 실패와 경쟁 claim 처리

또한 `create_draft`(`:449-523`)는 분석·research·profile 정규화의 상당 부분을 별도 경로로 다시 수행한다. 즉 "프로필을 준비한다"는 책임이 최종 생성과 draft 생성에 중복되어 있다.

직접 `run` 호출은 실행 코드에 6곳이다. `service.py` 2곳(승인 및 레거시 fallback), `app.py` 2곳, `scripts/runtime/run_local_detail_page.py` 1곳, `scripts/run_eval_pilot.py` 1곳이다. 따라서 호출부를 새 서비스 API로 교체하는 방식은 불필요하게 위험하다.

### 계속 어려운 점

- photo metadata를 하나 추가해도 renderer 반환값, BE request, FE response, recovery, outbox 전달 순서를 동시에 이해해야 한다.
- backend 전달 실패를 변경하려면 앞선 분석/렌더와 관계없는 `run` 본문을 통과해야 하며, delivery만의 단위 테스트를 만들기 어렵다.
- draft와 final의 profile 정규화가 따로 있어, research 조건이나 sanitizer 변경 시 두 흐름의 차이를 의도적으로 검토해야 한다.

### 제안 조치와 영향 범위

공개 `DetailPagePipeline.run(...) -> PipelineResult`와 `create_draft(...) -> DraftPipelineResult`는 그대로 둔다. 내부에서만 다음 세 단위로 추출한다.

1. `prepare_profile(...)`: validate/analyze/research/page-plan/sanitize를 수행하고 `profile`, `ApprovedDraftDto`, source asset 정보를 반환한다. final과 draft가 공유한다.
2. `assemble_generation_artifacts(...)`: renderer 결과를 검증하고 asset 저장, section/photo metadata, React document, BE/FE DTO를 하나의 내부 immutable bundle로 조립한다.
3. `deliver_artifacts(...)`: outbox enqueue/claim/heartbeat/backend persist와 `PipelineResult`의 delivery 상태만 담당한다.

후보 파일은 `pipeline.py`와 새 내부 모듈 2개(예: `profile_preparation.py`, `generation_delivery.py`)이며, `tests/test_pipeline.py`, `tests/test_draft_flow.py`, `tests/test_service.py`를 보강한다. 공개 심볼 변경은 없다. `run`의 6개 실행 호출부는 유지된다.

### 검증

- final과 draft에 대해 현재 fixture의 profile, approved draft, 진행 상태 sequence를 characterization test로 고정한다.
- 정상 전달, `BackendDeliveryError`, `LeaseOwnershipError`, outbox recovery, approval 재실행 각각에서 BE request/FE result/outbox 상태가 현재와 같은지 비교한다.
- pipeline·draft·service 테스트와 전체 328개 기준 회귀를 실행한다.

### 분류 및 시점

순수 구조 변경이다. research 조건, renderer 순서, delivery retry 횟수/시간, status/progress 값은 바꾸지 않는다. 평가 산출물의 단계 순서와 asset 메타데이터에 직접 닿으므로 평가 종료 후에만 구현한다.

## P1 — 사진 역할과 provenance 허용 정책이 여러 모듈에 흩어져 있다

### 코드 근거

생성 사진의 역할·허용 조건·라벨 규칙이 하나의 정책으로 표현되지 않는다.

- `source_photos.py:515-555`는 `SourcePreservingProductPhotoGenerator`의 기본 역할과 원본 라벨을, `:557-764`는 source 수/role/cutout 여부에 따른 생성 경로를 결정한다.
- 같은 파일 `ProductFidelityValidator.validate`(`:379-510`)는 `generated_scene`은 `lifestyle`만, `generated_view`는 `detail-02`~`detail-05`만 허용하는 별도 조건을 가진다.
- `html_renderer.py:580-615`는 최종 HTML에 포함할 사진을 고르면서 다시 `lifestyle`와 `detail-02`~`detail-05`의 생성 허용 조건을 직접 열거한다.
- `react_document_builder.py:13-25`와 `:211-222`도 block type별 기본 photo ID와 gallery 상한을 별도로 관리한다.

이는 단순한 상수 중복이 아니다. 하나의 새 생성 role을 안전하게 추가하거나 현 역할을 막을 때 생성, validator, HTML 출력이 서로 다른 결과를 낼 수 있는 구조다. 생성기 construction은 실행 코드에 3곳(`local_detail_page_ai/factory.py`, `local_detail_page_ai/runner.py`, `scripts/runtime/generate_attached_detail_page.py`)이고, validator는 pipeline과 생성기 내부에서 각각 기본 인스턴스로 만들어진다.

### 계속 어려운 점

- role 추가 시 "생성되지만 출력되지 않음" 또는 "출력되지만 validator가 거부함" 같은 provenance 불일치가 생길 수 있다.
- 라벨/asset mode/product_generated 조합을 수정할 때 안전 규칙의 완전성을 코드 리뷰만으로 확인하기 어렵다.
- 현재 최근에 추가된 생성 참고용 라벨처럼, metadata를 소비하는 각 경계가 role 정책을 자체적으로 해석하게 된다.

### 제안 조치와 영향 범위

새 내부 `photo_role_policy.py`에 role별 다음 순수 정보를 둔다: source 기본 라벨, 허용 asset mode, product-generated 허용 여부, HTML 표시 가능 여부, block 기본 ID. `source_photos.py`, `html_renderer.py`, `react_document_builder.py`, 그리고 필요 시 validator가 이 정책만 조회하도록 한다.

`SourcePreservingProductPhotoGenerator.generate`, `ProductFidelityValidator.validate`, `build_detail_page_html`, `build_react_document_from_draft`의 공개 시그니처는 유지한다. role 값, 기존 라벨 문구, whitelist 결과도 그대로 둔다. 영향을 받는 테스트는 `tests/test_source_photos.py`, `tests/test_html_renderer.py`, `tests/test_react_document.py`, `tests/test_pipeline.py`다.

### 검증

- `role × asset_mode × product_generated × fidelity_status` 행렬 테스트를 추가해 현재 허용/거부 결과를 먼저 고정한다.
- source/fallback/composite/generated scene/generated detail view별 `ProductPhoto`의 id, label, provenance 필드를 golden fixture로 비교한다.
- HTML과 React document가 같은 허용 사진 ID만 참조하는지 검증한다.

### 분류 및 시점

정책값을 전혀 바꾸지 않는 경우에만 순수 구조 변경이다. 허용 role 확대, 생성 이미지 표시 위치 변경, 라벨 문구 변경은 기능/안전 정책 변경으로 별도 승인해야 한다. 안전 및 평가 출력에 직접 영향을 주므로 평가 종료 후에만 구현한다.

## P1 — `build_analysis_prompt`가 섹션 모델이 아니라 본문 문자열 위치에 의존한다

### 코드 근거

`prompts.py:212-461`의 `build_analysis_prompt`는 product data, copy brief, care/search gate, DTO schema, adaptive layout, reference guide, final checklist를 한 f-string에 담는다. 선택 archetype이 있을 때 `:446-460`은 `prompt.index(adaptive_start)`, 두 번째 `prompt.index(example_block, start)`, `prompt.replace(..., 1)`로 이미 만든 본문 일부를 교체한다.

따라서 layout 설명의 문장·줄바꿈·heading을 편집하는 것만으로도 런타임 `ValueError` 또는 의도하지 않은 구간 치환을 유발할 수 있다. `build_analysis_prompt`의 실행 소비자는 `local_detail_page_ai/adapters.py:77` 한 곳이며, 현재 프롬프트 테스트에는 15개 직접 호출이 있다. 공개 함수의 호출 폭이 좁아, 내부 구조를 고정하기에 적절하다.

### 계속 어려운 점

- copy rule을 추가할 때 adaptive/selected-layout 두 경로에 포함되는지 사람이 본문 검색으로 판단해야 한다.
- 테스트가 하나의 계약 섹션의 누락을 알려도, 어떤 substring replacement가 원인인지 분리하기 어렵다.
- 프롬프트 내용을 바꾸지 않는 리팩터링조차 whitespace나 삽입 위치 변화로 모델 평가 결과에 영향을 줄 위험이 있다.

### 제안 조치와 영향 범위

문자열 교체를 없애고, 명명된 section renderer를 순서대로 조립한다. 예: `_analysis_contract_section`, `_creator_data_section`, `_page_plan_section(selected_layout_instruction)`, `_final_checks_section(selected_layout_instruction)`처럼 각 함수가 완결된 문자열을 반환하도록 한다. `build_analysis_prompt`의 인자와 반환값은 유지한다.

변경 파일은 `prompts.py`와 `tests/test_prompts.py`다. 공개 심볼 변경과 실행 호출부 변경은 없다(실행 소비자 1곳 유지).

### 검증

- 구조 변경 전, archetype 없음/빈 목록/단일 선택/복수 후보와 user hints 유무의 출력 snapshot을 만든다.
- 리팩터링 후 동일 입력에서 바이트 단위 동등성을 확인한다. 문구 개선은 이 작업과 섞지 않는다.
- 기존 `tests/test_prompts.py` 및 전체 회귀를 실행하고, 평가 종료 뒤 소규모 고정 fixture로 출력 JSON의 schema/page-plan을 비교한다.

### 분류 및 시점

구조 변경 자체는 순수하게 만들 수 있지만 prompt bytes는 모델 입력이다. 따라서 현재 평가 종료 후에만 실행하며, 문구·규칙의 의미 변경은 후속 기능 작업으로 분리한다.

## P2 — 서버 HTML 조립은 provenance 선별과 block별 마크업을 동시에 안다

### 코드 근거

`html_renderer.py:337-493`의 `_render_page_block`은 block type별 HTML을 직접 반환하고, `:556-681`의 `build_detail_page_html`은 입력 검증, template/CSS 읽기, provenance 필터(`:580-600`), detail gallery 자산 정렬, 동적 section 조립, placeholder 치환까지 수행한다. 이어 `HtmlDetailPageRenderer.render`(`:745-793`)는 이미 별도 Chromium capture 책임을 갖지만 같은 모듈에서 composer를 호출한다.

`build_detail_page_html`의 실행 호출은 3곳이다: `HtmlDetailPageRenderer.render`, `scripts/runtime/generate_attached_detail_page.py`, `scripts/runtime/build_detail_page_html.py`. 이 중 `web/` 코드는 건드리지 않아도 server-side composer의 경계를 개선할 수 있다.

### 계속 어려운 점

- 새로운 block/사진 provenance 조건을 추가할 때 HTML 마크업과 사진 선택을 한 함수에서 함께 변경해야 한다.
- unit test가 전체 self-contained HTML에 묶여 있어, photo catalog 선택 오류와 markup 오류를 구별하기 어렵다.
- image-label처럼 metadata 기반 마크업을 추가할 때 gallery/detail/fallback 경로마다 동일 정책을 전달해야 한다.

### 제안 조치와 영향 범위

`build_detail_page_html`은 compatibility façade로 남긴다. 내부의 사진 provenance filtering과 URI/label lookup을 `RenderPhotoCatalog`(순수 값 객체)로, block type별 HTML 생성을 `PageBlockHtmlComposer` 또는 dispatch map으로 분리한다. Chromium capture와 `HtmlDetailPageRenderer`의 public API는 바꾸지 않는다.

후보 변경 파일은 `html_renderer.py`, 새 내부 composer/catalog 모듈, `tests/test_html_renderer.py`, `tests/test_safety.py`다. `web/` 아래 파일과 FE 연동은 범위 밖이다. 공개 호출부 3곳은 유지된다.

### 검증

- 현재 HTML fixture에서 source/fallback/generated/rejected 사진의 포함 여부, escaped text, gallery deduplication, unresolved placeholder failure를 characterise한다.
- 같은 profile/photo set으로 facade 반환 HTML이 구조 변경 전후 동일한지 비교한다.
- 기존 browser layout 검사와 renderer capture 테스트를 실행한다.

### 분류 및 시점

순수 구조 변경이다. HTML 클래스명, placeholder, CSS, template, 허용 provenance, 생성 참고용 라벨 문구는 바꾸지 않는다. 평가에 쓰이는 서버 renderer이므로 종료 후에만 구현한다.

## P3 — DTO가 builder를 지연 import해 순환 의존을 숨긴다

### 코드 근거

`react_document_builder.py`는 모듈 최상단에서 `ApprovedDraftDto` 등 DTO를 import한다. 반대로 `dto.py:404-439`의 `AiFeStatusResponse.completed`는 `:417`에서 `build_react_document_from_draft`를 함수 내부 import한다. 제공된 사실과 호출 대조대로 `AiFeStatusResponse.completed`의 저장소 내 호출은 `tests/test_dto.py:89` 한 곳이고 프로덕션 호출은 없다.

지연 import는 import-time 실패를 피하지만, response DTO가 AST compiler를 알아야 하는 의존 방향은 그대로다. 현재 builder의 source 호출은 `pipeline.py` 3곳과 이 DTO helper 1곳이다.

### 계속 어려운 점

- DTO 모듈을 독립적인 계약 패키지로 읽거나 재사용하기 어렵다.
- builder의 입력을 바꿀 때 실행 경로가 없는 convenience classmethod까지 함께 추적해야 한다.

### 제안 조치와 영향 범위

먼저 외부 SDK/문서가 `AiFeStatusResponse.completed`를 호출하는지 확인한다. 외부 소비자가 없으면 method를 제거하고 `tests/test_dto.py`는 명시적으로 response DTO를 조립한다. 외부 호환이 필요하면 DTO가 아닌 `response_factory.py`에 같은 convenience factory를 두고, DTO는 AST builder를 import하지 않게 한다.

저장소 내 직접 호출은 테스트 1곳뿐이다. public classmethod를 제거하거나 이동하는 경우에는 외부 소비자 확인이 끝나기 전까지 breaking change로 취급한다.

### 검증

- 새 Python interpreter에서 `detail_page_ai.dto`, `detail_page_ai.react_document_builder`, 패키지 root import를 각각 수행해 순환 import가 없는지 확인한다.
- DTO serialization alias, AST schema validation, `tests/test_dto.py`, `tests/test_react_document.py`를 실행한다.

### 분류 및 시점

저장소 안에서는 순수 구조 변경이지만 외부 호출 여부가 확인되지 않았다. 확인 전에는 보류하고, 평가 종료 후 독립적으로 수행한다.

## 지금은 건드리지 않을 것

| 대상 | 유지 판단 | 이유 |
| --- | --- | --- |
| `persistence.py`의 JobRepository/DeliveryOutbox와 Memory/SQLite 구현 | 분리 보류 | 두 protocol과 두 구현은 테스트용 메모리·운영용 SQLite라는 명확한 adapter 경계이며, lease/transaction/serialization 의미를 함께 검증한다. 파일 이동만으로는 효과가 작고 상태 전이 drift 위험이 크다. |
| `react_document_builder.py`의 card/list/table/media helper들 | cycle 해소 외 분리 보류 | 한 AST 언어의 node ID, style, parent-child 규칙을 공유하는 순수 compiler다. helper를 파일별로 나누면 AST 규칙이 분산된다. |
| `SolidBackgroundCutoutExtractor`의 mask/image 연산과 `ProductFidelityValidator`의 임계값 | 알고리즘 변경 금지 | provenance와 source fidelity를 보장하는 안전 경계다. P1에서 policy 위치만 정리할 수 있으며 tolerance, mask, crop/composite 판정은 별도 이미지 품질 작업 없이는 바꾸지 않는다. |
| DTO field명과 `react_document` schema | 계약 변경 금지 | BE/FE 및 persisted outbox가 소비하는 직렬화 계약이다. 구조 리팩터링의 대상이 아니다. |
| `web/` 미리보기 코드 및 FE 구현 | 범위 밖 | 생성형 AI 팀의 서버 렌더·계약 범위를 넘는다. |
| `scripts/run_eval_pilot.py`와 평가 중인 `src/` | 평가 중 변경 금지 | 동일 평가에서 서로 다른 코드 산출물이 섞이는 것을 방지한다. |

## 권장 실행 순서와 공통 검증

1. 평가 종료와 산출물 보존을 확인한다. 평가 중에는 이 진단서 외 코드 변경을 하지 않는다.
2. P0을 먼저 수행한다. profile preparation, generation assembly, delivery의 characterization test를 만들고 `run` façade를 유지한다.
3. P1 사진 정책을 role/provenance 행렬 test로 고정한 뒤 한 곳으로 모은다.
4. P1 프롬프트는 snapshot의 바이트 동등성을 먼저 확보한 뒤 section renderer로 바꾼다.
5. P2 HTML composer는 P1의 role policy가 안정된 뒤 진행한다. 동일 HTML 비교와 browser capture를 통과시킨다.
6. P3은 외부 소비자 확인이 끝난 뒤 작은 독립 변경으로 한다.

각 단계는 `pytest -q` 전체(현재 기준 328개), 해당 모듈 테스트, `git diff --check`를 통과해야 한다. P0/P1/P2는 고정 source/profile fixture로 BE request, FE result, React document, HTML, photo provenance를 구조 변경 전후 비교한다. 기능 변경이 필요하다고 판명되면 해당 리팩터링 PR에서 멈추고 별도 요구사항·평가 계획으로 분리한다.
