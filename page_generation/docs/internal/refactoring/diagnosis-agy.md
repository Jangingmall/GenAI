# 구조 리팩터링 진단서 (Diagnosis Report B)

- **작성 워커**: agy
- **진단 일시**: 2026-09-10 20:35:00 KST
- **대상 패키지**: `src/detail_page_ai` (10,118줄), `src/local_detail_page_ai` (880줄)
- **현재 테스트 상태**: 328 passed (pytest 기준 회귀 없음)

---

## 1. 진단 요약 및 로드맵 매트릭스

본 진단은 코드 줄 수의 다과("크니까 쪼갠다")가 아니라, **단일 책임 원칙(SRP)**, **관심사의 분리(SoC)**, **순환 결합 제거**, **안정적 변경 경계 형성** 관점에서 수행되었습니다. 특히 **60건 전체 평가(약 3시간 45분 소요)** 가 예정되어 있으므로, 런타임 안정성을 해치지 않도록 **평가 전(Pre-eval)** 과 **평가 후(Post-eval)** 실행 시점을 엄격히 분리했습니다.

### 결함 항목 요약 매트릭스

| 번호 | 결함 항목 | 위치 (핵심 파일) | 유형 | 위험도 | 효과 | 추천 시점 | 영향 호출부 수 |
|:---:|---|---|:---:|:---:|:---:|:---:|:---:|
| 1 | `dto.py` ↔ `react_document_builder.py` 순환 의존 및 지연 import 회피 | `dto.py:404-422` | 순수 구조 변경 | 최저 | 높음 | 평가 직후 1순위 (또는 평가 전 가능) | 프로덕션 0곳, 테스트 1곳 |
| 2 | `source_photos.py` 내 3중 책임 혼재 (CV 알고리즘 / 검증 게이트 / 합성 파이프라인) | `source_photos.py:87-1120` | 순수 구조 변경 | 낮음 (Facade 사용) | 매우 높음 | 평가 후 | 내부 2곳, 외부 5곳 |
| 3 | `pipeline.py` 거대 메서드(`run`, 323줄) 및 `create_draft` 간 분석·기획 로직 중복 | `pipeline.py:146-524` | 순수 구조 변경 | 낮음 (내부 private) | 매우 높음 | 평가 후 | 내부 전용 (외부 0곳) |
| 4 | `prompts.py` 텍스트 LLM 기획과 디퓨전 이미지 프롬프트·비주얼 휴리스틱 혼재 | `prompts.py:30-1095` | 순수 구조 변경 | 낮음 (Facade 사용) | 높음 | 평가 후 | 텍스트 1곳, 이미지 4곳 |
| 5 | `persistence.py` 내 이종 저장소 책임 혼재 (Job 상태 관리 vs Outbox 배송·임대) | `persistence.py:47-1028` | 순수 구조 변경 | 낮음 (Facade 사용) | 중간 | 평가 후 | Job 3곳, Outbox 3곳 |
| 6 | `app.py`의 `local_detail_page_ai` 역방향 지연 import 및 패키지 계층 위반 | `app.py:73-79` | 순수 구조 변경 | 중간 | 중간 | 평가 후 | 2곳 |
| 7 | `html_renderer.py`와 `react_document_builder.py` 간 블록 기본값·폴백 로직 중복 | `html_renderer.py`, `react_document_builder.py` | 순수 구조 변경 | 중간 | 중간 | 평가 후 | 렌더러 내부 2곳 |

---

## 2. 구조적 결함 상세 진단 (7개 항목)

### [결함 1] `dto.py` ↔ `react_document_builder.py` 순환 의존 및 지연 import

- **무엇이 문제인가**:
  - 패키지의 가장 저수준 기초 계층이어야 하는 `dto.py`가 상위 계층인 `react_document_builder.py`를 참조하여 순환 의존성이 발생하고, 이를 감추기 위해 메서드 내부 지연 import(`from .react_document_builder import ...`)를 사용하고 있습니다.
- **어느 파일·심볼인가**:
  - `src/detail_page_ai/dto.py:404-422`: `AiFeStatusResponse.completed` 클래스메서드
  - `src/detail_page_ai/dto.py:417`: `from .react_document_builder import build_react_document_from_draft`
  - `src/detail_page_ai/react_document_builder.py:6-20`: `from .dto import ApprovedDraftDto, PageBlockDto, ...`
- **왜 문제인가 (코드 근거)**:
  - `dto.py:417`의 지연 import를 모듈 상단으로 올리면 즉시 `ImportError: cannot import name 'ApprovedDraftDto' from partially initialized module 'detail_page_ai.dto'`가 발생합니다.
  - 실측 확인 결과, `AiFeStatusResponse.completed`는 **프로덕션 코드에서 단 한 번도 호출되지 않습니다**. 유일한 호출처는 `tests/test_dto.py:89` 뿐입니다.
  - 프로덕션 런타임(`service.py:_run_job`, `pipeline.py:run`)에서는 `AiFeStatusResponse` DTO를 직접 필드 매핑하여 인스턴스화하지, 이 헬퍼를 사용하지 않습니다.
  - 순수 데이터 규격 정의(DTO) 모듈이 presentation AST 조립 엔진(`react_document_builder`)의 실행 로직을 내장하는 것은 계층 역전(Layer Inversion) 결함입니다.
- **고치지 않으면 무엇이 계속 어려운가**:
  - DTO 모듈을 참조하는 정적 분석기, 순환 참조 감지 도구, 패키징 도구에서 지속적으로 경고가 발생합니다.
  - 개발자가 DTO에 비즈니스/프레젠테이션 로직을 추가해도 된다는 잘못된 선례를 남깁니다.
  - 향후 DTO 분리 또는 모듈 임포트 순서 변경 시 예기치 못한 런타임 모듈 초기화 에러가 잠재합니다.
- **제안 조치 및 영향 범위**:
  - **조치**: `dto.py`에서 `AiFeStatusResponse.completed` 클래스메서드를 제거합니다. `tests/test_dto.py:89`에서는 테스트 헬퍼 함수로 분리하거나 `AiFeStatusResponse(...)`를 직접 생성하도록 수정합니다.
  - **공개 심볼 변경**: `AiFeStatusResponse.completed` 제거
  - **호출부 실측**: 프로덕션 0곳, 테스트 1곳 (`tests/test_dto.py:89`)
  - **유형**: 순수 구조 변경 (동작 변경 없음)
  - **타이밍**: **평가 직후 1순위** (프로덕션 영향이 전혀 없어 원한다면 평가 전에도 가능하나, 런타임 동결 원칙상 평가 직후 권장)

---

### [결함 2] `source_photos.py` 내 3중 책임 혼재 (알고리즘 vs 검증 vs 파이프라인)

- **무엇이 문제인가**:
  - `source_photos.py` 한 파일(1,120줄)에 (1) 픽셀 단위 컴퓨터 비전/알파 마스크 추출 알고리즘, (2) 보존율·바운딩 박스 검증 게이트, (3) 생성형 이미지 합성 및 다각도 컷 생성 오케스트레이터가 한데 엉켜 있습니다.
- **어느 파일·심볼인가**:
  - `src/detail_page_ai/source_photos.py`:
    1. `SolidBackgroundCutoutExtractor` (L87-376, 290줄): BFS flood-fill, 코너 균일도 계산, 연결 요소 탐색, 섀도우 억제 등 순수 CV 알고리즘
    2. `ProductFidelityValidator` (L379-512, 134줄): 잉크 비율 보존율, 바운딩 박스 오차 판정 게이트
    3. `SourcePreservingProductPhotoGenerator` (L515-1120, 606줄): 원본 보존 컷, 라이프스타일 씬 생성, 다각도 디테일 생성, 그림자 합성 오케스트레이션
- **왜 문제인가 (코드 근거)**:
  - 파일 내 최장 함수는 209줄에 달하며, 역할이 완전히 다른 3개 도메인이 섞여 있습니다.
  - 호출부를 실측해 보면:
    - `src/detail_page_ai/pipeline.py:38`은 오직 `ProductFidelityValidator` 하나만 필요해서 이 1,120줄짜리 무거운 모듈 전체를 import합니다.
    - `src/detail_page_ai/training_augmentation.py:20`은 학습 데이터셋 증강용 누끼 추출을 위해 오직 `SolidBackgroundCutoutExtractor` 하나만 필요해서 이 모듈을 import합니다.
    - 즉, 파이프라인과 학습 증강 모듈이 불필요하게 거대한 생성형 사진 합성 엔진 전체와 결합되어 있습니다.
- **고치지 않으면 무엇이 계속 어려운가**:
  - 누끼(Cutout) 알고리즘 튜닝(예: 테두리 섀도우 억제 계수 조정) 시 합성 및 다각도 생성 코드가 같은 파일에 있어 git 충돌 위험이 상존합니다.
  - 회귀 평가 게이트(`check_cutout_fidelity.py`)와 파이프라인 검증 단계에서 검증 모듈만 격리하여 단위 테스트하기 어렵습니다.
- **제안 조치 및 영향 범위**:
  - **조치**: 세 기능 영역을 독립 파일로 분리합니다.
    1. `src/detail_page_ai/cutouts.py`: `ProductCutout`, `SolidBackgroundCutoutExtractor`, `_encode_png`, `_decode_rgb`
    2. `src/detail_page_ai/fidelity.py`: `ProductFidelityValidator`
    3. `src/detail_page_ai/source_photos.py`: `SourcePreservingProductPhotoGenerator`, 프로토콜 3종(`BackgroundGenerator`, `UsageSceneGenerator`, `DetailViewGenerator`), 합성 헬퍼.
    - *하위 호환성*: 기존 `source_photos.py`에서 `SolidBackgroundCutoutExtractor`, `ProductFidelityValidator`를 Re-export하여 외부 호출부의 무중단 유지.
  - **공개 심볼 변경**: 없음 (Re-export Facade 유지)
  - **호출부 실측**:
    - `SolidBackgroundCutoutExtractor`: 내부 1곳 (`source_photos.py`), 외부 1곳 (`training_augmentation.py`), 테스트 6곳
    - `ProductFidelityValidator`: 내부 1곳 (`source_photos.py`), 외부 1곳 (`pipeline.py`), 테스트 3곳
    - `SourcePreservingProductPhotoGenerator`: 외부 3곳 (`factory.py`, `runner.py`, `generate_attached_detail_page.py`), 테스트 2곳
  - **유형**: 순수 구조 변경
  - **타이밍**: **평가 후 (Post-eval)**. 60건 평가 중 사진 생성 파이프라인의 파일 I/O나 임포트 경로가 변경되는 위험을 원천 차단.

---

### [결함 3] `pipeline.py` 거대 메서드(`run`, 323줄) 및 `create_draft` 간 분석·기획 로직 중복

- **무엇이 문제인가**:
  - `DetailPagePipeline.run` 메서드가 323줄(L146-444)에 걸쳐 단일 블록으로 작성되어 있고, 그 전반부(입력 검증 → LLM 분석 → 공예 연구 → 기획안 수립 및 살균 → 초안 생성) 약 40줄이 `create_draft`(L460-524)와 글자 그대로 복사-붙여넣기(Copy-Paste) 중복되어 있습니다.
- **어느 파일·심볼인가**:
  - `src/detail_page_ai/pipeline.py`:
    - `DetailPagePipeline.run` (L146-444, 323줄)
    - `DetailPagePipeline.create_draft` (L460-524, 65줄)
- **왜 문제인가 (코드 근거)**:
  - `pipeline.py` L161-198(`run`)과 L479-514(`create_draft`)를 대조하면 다음 7단계 로직이 완전히 일치합니다:
    1. `self._validate_inputs(source_image, source_mime_type, ...)`
    2. `self.analyzer.analyze(source_image, source_mime_type, user_hints=...)`
    3. `validate_product_profile(profile)`
    4. `self._should_research_craft(profile, user_hints)` 판단 및 `self.researcher.research(...)`
    5. `ensure_editorial_page_plan(profile)` (기획안 기본 블록 보장)
    6. `sanitize_profile_for_render(profile)` (텍스트 길이 및 안전 제약 살균)
    7. `ApprovedDraftDto.from_profile(profile)` (초안 조립)
  - 또한 `run` 메서드는 1개 함수 안에서 (1) LLM 분석, (2) 이미지 디퓨전 생성, (3) HTML PNG 렌더링, (4) AssetStore 적재, (5) Outbox 트랜잭션 적재 및 LeaseHeartbeat 백엔드 배송 루프까지 5단계의 서로 다른 추상화 레벨을 한 호흡에 처리하고 있습니다.
- **고치지 않으면 무엇이 계속 어려운가**:
  - 분석 로직이나 공예 연구 조건(예: 신규 카테고리 추가나 힌트 우선순위 변경)을 수정할 때, 개발자가 `run`과 `create_draft` 중 하나만 수정하고 다른 쪽을 누락하여 초안 단계와 최종 생성 단계의 결과물이 달라지는 버그가 필연적으로 발생합니다.
  - `run` 내부에서 특정 단계(예: Outbox 배송 실패 재시도)만 격리하여 단위 테스트하기 불가능하여 항상 전체 파이프라인 모킹이 강제됩니다.
- **제안 조치 및 영향 범위**:
  - **조치**: `DetailPagePipeline` 내부에 private 헬퍼 메서드를 추출하여 단일화합니다.
    1. `_analyze_and_build_draft(...)`: `run`과 `create_draft`가 공유하는 분석·연구·기획안 수립 40줄 로직 통합.
    2. `_deliver_via_outbox(...)`: Outbox enqueue, claim, lease heartbeat 백엔드 배송 로직 분리.
  - **공개 심볼 변경**: 없음 (클래스 내부 private 리팩터링)
  - **호출부 실측**: 외부 영향 0곳 (`run`과 `create_draft`의 외부 인터페이스 및 반환 DTO 100% 동일 유지)
  - **유형**: 순수 구조 변경
  - **타이밍**: **평가 후 (Post-eval)**.

---

### [결함 4] `prompts.py` 텍스트 LLM 기획과 디퓨전 이미지 프롬프트·비주얼 휴리스틱의 혼재

- **무엇이 문제인가**:
  - `prompts.py` 한 파일(1,095줄)에 완전히 다른 모델 및 역할을 가진 (1) 텍스트 LLM(Qwen 27B)용 제품 분석·카피라이팅·블록 기획 프롬프트와, (2) 이미지 디퓨전(FLUX2)용 화각·배경·소품·조명·질감 프롬프트 생성 로직이 동거하고 있습니다.
- **어느 파일·심볼인가**:
  - `src/detail_page_ai/prompts.py`:
    - 텍스트 LLM 영역 (L30-518, 488줄): `build_analysis_prompt`, `build_craft_research_prompt`, `_format_selected_layout_instruction`, `_build_page_plan_contract`
    - 이미지 디퓨전 영역 (L521-1095, 574줄): `build_background_prompt`, `build_usage_context_background_prompt`, `build_generated_usage_scene_prompt`, `build_generated_detail_cut_prompt`, `_product_scene_direction` (244줄의 카테고리별 소품/배경 휴리스틱)
- **왜 문제인가 (코드 근거)**:
  - 호출부의 관심사가 완벽히 양분되어 있습니다:
    - `src/local_detail_page_ai/adapters.py` (텍스트 LLM 어댑터)는 오직 `build_analysis_prompt` 1개 심볼만 임포트합니다.
    - `src/local_detail_page_ai/runner.py` (이미지 디퓨전 러너)는 오직 이미지 프롬프트 4개 심볼(`build_background_prompt`, `build_generated_detail_cut_prompt`, `build_generated_usage_scene_prompt`, `build_usage_context_background_prompt`)만 임포트합니다.
  - 특히 `_product_scene_direction` 함수는 244줄(L521-764)에 걸쳐 도자기, 금속공예, 나전칠기, 텍스타일 등의 촬영 소품, 배경 표면, 조명 분위기 키워드를 매핑하는 순수 시각 연출 엔진입니다. 텍스트 카피라이팅 프롬프트와는 아무런 공통점이 없습니다.
  - 프롬프트 버전 관리 상수도 `ANALYSIS_PROMPT_VERSION`과 `BACKGROUND_PROMPT_VERSION` 등 6개가 한 파일에서 관리되어 어느 모델 프롬프트가 변경되었는지 추적이 모호합니다.
- **고치지 않으면 무엇이 계속 어려운가**:
  - 텍스트 모델(Qwen) 프롬프트 엔지니어링 작업과 이미지 모델(FLUX) 프롬프트 엔지니어링 작업이 동일 파일 충돌을 일으킵니다.
  - 프롬프트 회귀 테스트(`test_prompts.py`)가 비대해져 개별 모델별 프롬프트 검증 주기가 길어집니다.
- **제안 조치 및 영향 범위**:
  - **조치**: 관심사별 모듈로 분리하되, 기존 `prompts.py`를 Facade로 유지합니다.
    1. `src/detail_page_ai/text_prompts.py`: 분석, 공예 연구, 레이아웃 기획 프롬프트 및 버전 상수
    2. `src/detail_page_ai/image_prompts.py`: 배경, 사용 씬, 디테일 컷 프롬프트 및 `_product_scene_direction`
    3. `src/detail_page_ai/prompts.py`: 기존 심볼 전체를 re-export하여 하위 호환성 100% 보장
  - **공개 심볼 변경**: 없음 (Facade 유지)
  - **호출부 실측**:
    - `adapters.py`: 1곳
    - `runner.py`: 4곳
    - `check_scene_direction_coverage.py`: 1곳
    - `tests/test_prompts.py`, `test_user_hints.py`: 2개 테스트 파일
  - **유형**: 순수 구조 변경
  - **타이밍**: **평가 후 (Post-eval)**.

---

### [결함 5] `persistence.py` 내 이종 저장소 책임 혼재 (Job 상태 관리 vs Outbox 배송·임대)

- **무엇이 문제인가**:
  - `persistence.py` 한 파일(1,028줄, 77개 def)에 상호 무관한 2개의 독립 서브시스템(클라이언트 비동기 작업 추적용 `JobRepository`와 백엔드 트랜잭셔널 메시징용 `DeliveryOutbox`)이 각각 Memory와 SQLite 구현체로 묶여 있습니다.
- **어느 파일·심볼인가**:
  - `src/detail_page_ai/persistence.py`:
    - Job 상태 서브시스템 (L47-553, 506줄): `JobRecord`, `JobRepository`, `MemoryJobRepository`, `SQLiteJobRepository`, `_serialize_job`, `_deserialize_job`
    - Outbox 배송 서브시스템 (L555-1028, 474줄): `OutboxRecord`, `DeliveryOutbox`, `MemoryDeliveryOutbox`, `SQLiteDeliveryOutbox`, `LeaseOwnershipError`, payload 직렬화 헬퍼들
- **왜 문제인가 (코드 근거)**:
  - 두 시스템은 DB 테이블(`jobs` vs `delivery_outbox`), 생명주기, 호출 계층이 다릅니다:
    - `pipeline.py`는 `JobRepository`를 전혀 모르며, 오직 `DeliveryOutbox`와 `LeaseOwnershipError`만 임포트합니다 (`pipeline.py:30`).
    - `leases.py`는 오직 `LeaseOwnershipError` 하나만 임포트합니다 (`leases.py:6`).
    - `service.py`는 작업 큐 및 상태 조회를 위해 `JobRepository`를 주력으로 사용합니다.
  - 1개 파일에 4개의 구체 클래스(`MemoryJobRepository`, `SQLiteJobRepository`, `MemoryDeliveryOutbox`, `SQLiteDeliveryOutbox`)와 각각의 DDL 생성, 직렬화, 트랜잭션 메서드가 뒤섞여 있습니다.
- **고치지 않으면 무엇이 계속 어려운가**:
  - Outbox 재시도/하트비트 로직 개선 시 Job 저장소 코드와 섞여 단위 테스트 및 코드 리뷰 범위가 불필요하게 넓어집니다.
  - 향후 PostgreSQL 등 다른 DB 어댑터 도입 시 1,000줄짜리 모듈 전체를 재구현하거나 손대야 합니다.
- **제안 조치 및 영향 범위**:
  - **조치**:
    1. `src/detail_page_ai/jobs_repository.py`: Job 관련 레코드, 인터페이스, Memory/SQLite 구현체
    2. `src/detail_page_ai/outbox.py`: Outbox 레코드, 인터페이스, Memory/SQLite 구현체, `LeaseOwnershipError`
    3. `src/detail_page_ai/persistence.py`: 기존 심볼 전체 Re-export Facade
  - **공개 심볼 변경**: 없음 (Facade 유지)
  - **호출부 실측**:
    - Job 계열: `service.py`, `factory.py`, 테스트 4곳
    - Outbox 계열: `pipeline.py`, `service.py`, `factory.py`, `leases.py`, 테스트 4곳
  - **유형**: 순수 구조 변경
  - **타이밍**: **평가 후 (Post-eval)**.

---

### [결함 6] `app.py`의 `local_detail_page_ai` 역방향 지연 import 및 패키지 계층 위반

- **무엇이 문제인가**:
  - 상위/코어 패키지인 `src/detail_page_ai`의 엔트리포인트(`app.py`)가 하위 어댑터 패키지인 `src/local_detail_page_ai`를 함수 내에서 직접 지연 임포트하여, 패키지 간 양방향 순환 의존 구조를 형성하고 있습니다.
- **어느 파일·심볼인가**:
  - `src/detail_page_ai/app.py:73-79`: `build_service` 함수 내부
  - `from local_detail_page_ai.factory import build_service as build_local_service`
- **왜 문제인가 (코드 근거)**:
  - `local_detail_page_ai`는 이미 `detail_page_ai`의 거의 모든 모듈(`pipeline`, `service`, `persistence`, `html_renderer`, `dto` 등)을 임포트하여 구현하고 있습니다.
  - 그런데 `detail_page_ai/app.py`가 다시 `local_detail_page_ai.factory`를 임포트함으로써 패키지 레벨 순환 참조(`detail_page_ai` ↔ `local_detail_page_ai`)가 발생합니다.
  - 코어 라이브러리(`detail_page_ai`)만 별도 환경이나 컨테이너에 배포하려 할 때, 로컬 MLX 전용 패키지(`local_detail_page_ai`)가 강제로 요구됩니다.
- **고치지 않으면 무엇이 계속 어려운가**:
  - 클라우드 환경(예: vLLM, S3 기반 어댑터) 등 다른 런타임 팩토리를 주입할 때 `app.py`의 하드코딩된 import를 우회하기 어렵습니다.
  - 패키지 간 명확한 계층 경계(코어 인터페이스 vs 런타임 구현체)가 무너집니다.
- **제안 조치 및 영향 범위**:
  - **조치**: 환경 변수 또는 의존성 주입(DI) 팩토리 레지스트리를 통해 서비스 생성자를 바인딩하거나, 로컬 실행 시 `local_detail_page_ai` 측의 엔트리포인트를 사용하도록 구조를 정돈합니다.
  - **공개 심볼 변경**: 없음 (`build_service()` 시그니처 유지)
  - **호출부 실측**: `app.py:84` (`get_service()`), `tests/test_app.py`
  - **유형**: 순수 구조 변경
  - **타이밍**: **평가 후 (Post-eval)**.

---

### [결함 7] `html_renderer.py`와 `react_document_builder.py` 간 블록 기본값·폴백 로직 중복

- **무엇이 문제인가**:
  - 상세페이지 섹션 블록(`PageBlockDto`)을 시각 요소로 변환할 때 필요한 기본 사진 매핑(`_DEFAULT_PHOTO_BY_BLOCK`)과 블록이 비었을 때 생성하는 기본 레이아웃 시퀀스(`_default_page_plan` vs `_fallback_blocks`)가 두 렌더러에 각각 따로 하드코딩되어 있습니다.
- **어느 파일·심볼인가**:
  - `src/detail_page_ai/html_renderer.py:142-293` (`_default_page_plan`), `304-320` (`_block_image`)
  - `src/detail_page_ai/react_document_builder.py:23-30` (`_DEFAULT_PHOTO_BY_BLOCK`), `545-569` (`_fallback_blocks`)
- **왜 문제인가 (코드 근거)**:
  - 모델이 생성한 `page_plan`이 없을 때, `html_renderer`는 9개 블록(`hero`, `feature_cards`, `gallery`, `story`, `usage_scene`, `notice_table`, `closing`)을 독자 조립하고, `react_document_builder`는 7개 블록(`hero`, `detail_split`, `usage_scene`, `story`, `notice_table`, `closing`)을 독자 조립합니다.
  - 즉, 입력이 동일해도 초안 JSON(React AST)과 최종 HTML PNG 렌더러가 서로 다른 기본 블록 시퀀스를 만들어냅니다.
  - 최근 '참고용' 라벨 누락 버그 해결 시에도 두 렌더러에 각각 별도의 라벨 부착 코드를 중복 작성해야 했습니다.
- **고치지 않으면 무엇이 계속 어려운가**:
  - 신규 블록 타입(예: scale_reference, palette) 추가 시 한쪽 렌더러에만 반영되어 불일치가 발생할 위험이 높습니다.
  - FE 미리보기 화면(React AST 기반)과 실제 게시물(HTML PNG 기반)의 레이아웃 불일치가 발생합니다.
- **제안 조치 및 영향 범위**:
  - **조치**: 블록 타입별 기본 사진 매핑 및 기본 레이아웃 시퀀스를 단일 소스(`src/detail_page_ai/layout_archetypes.py` 또는 신규 `presentation_contracts.py`)로 추출하여 두 렌더러가 공통 참조하도록 일원화합니다.
  - **공개 심볼 변경**: 없음
  - **호출부 실측**: `html_renderer.py` 내부, `react_document_builder.py` 내부
  - **유형**: 순수 구조 변경
  - **타이밍**: **평가 후 (Post-eval)**.

---

## 3. 리팩터링 우선순위 및 위험 대비 효과 분석

### 우선순위 결정 원칙
1. **"크니까 쪼갠다" 배제**: 파일이 1,000줄이라도 단일 책임에 응집되어 있다면 리팩터링 우선순위가 낮습니다. 반대로 500줄이라도 순환 참조를 일으키거나 3개 이상의 이종 도메인이 결합된 곳을 우선합니다.
2. **60건 대규모 평가(약 3시간 45분) 안정성 보호**:
   - 곧 실행될 60건 전체 평가는 GPU/MLX 로컬 리소스를 장시간 점유하는 고비용 작업입니다.
   - 따라서 **평가 실행 직전에는 어떤 파일도 건드리지 않는 것(Code Freeze)** 이 원칙입니다.
   - 모든 리팩터링은 **평가 후(Post-eval)** 실행을 기본으로 계획합니다.

### 단계별 실행 로드맵

```text
[현재] ──(Code Freeze)──▶ [60건 전체 평가 실행: ~3h 45m] ──▶ [평가 완료 및 데이터 확보]
                                                                     │
 ┌───────────────────────────────────────────────────────────────────┘
 │
 ├── [Phase 1: 최저위험 순환 제거 (즉시)]
 │    └── 결함 1: dto.py 순환 의존 제거 (AiFeStatusResponse.completed 정리)
 │
 ├── [Phase 2: 핵심 모듈 SRP 분리 (단기)]
 │    ├── 결함 2: source_photos.py 3단 분리 (cutouts / fidelity / source_photos)
 │    ├── 결함 3: pipeline.py run-create_draft 분석/기획 중복 헬퍼 추출
 │    ├── 결함 4: prompts.py 텍스트/이미지 프롬프트 분리
 │    └── 결함 5: persistence.py Jobs / Outbox 분리
 │
 └── [Phase 3: 아키텍처 경계 및 계약 일원화 (중기)]
      ├── 결함 6: app.py 역방향 지연 import 해소
      └── 결함 7: html_renderer / react_document_builder 기본 블록 계약 일원화
```

---

## 4. 건드리면 안 되는 것 (의도된 설계 보존 대상)

리팩터링 과정에서 "단순화"라는 명목으로 건드려서는 안 되는 핵심 설계 원칙 6가지를 정의합니다.

1. **`src/detail_page_ai`와 `src/local_detail_page_ai`의 패키지 분리 유지**:
   - `detail_page_ai`는 프레임워크/플랫폼 중립적인 코어 도메인 로직 및 계약입니다.
   - `local_detail_page_ai`는 로컬 개발/평가 환경(MLX Serve, 로컬 디렉터리 기반 SQLite 등)을 위한 구체 어댑터 팩토리입니다.
   - 두 패키지를 하나로 합치면 코어가 특정 로컬 실행 환경에 영구 종속되므로 분리 구조를 유지해야 합니다.

2. **`ports.py`의 `typing.Protocol` 기반 구조적 서브타이핑 유지**:
   - `ports.py`는 `abc.ABC`를 통한 강제 상속 대신 `typing.Protocol`을 채택하고 있습니다.
   - 이는 어댑터(`LocalQwenDetailAnalyzer`, `LocalFluxPhotoGenerator` 등)가 코어 라이브러리와 물리적으로 결합되지 않고 덕 타이핑(Duck typing)으로 구현체를 자유롭게 교체할 수 있도록 한 훌륭한 설계(설계 원칙 5)이므로 ABC 상속 구조로 바꾸지 말아야 합니다.

3. **`react_document.json` (React AST)과 `detail_page.png` (HTML 렌더) 이원화 구조 유지**:
   - 두 렌더러가 병존하는 것은 중복이 아니라 **의도적인 실패 경계 분리(Failure Domain Isolation)** 입니다 (설계 원칙 3).
   - `react_document`는 FE 에디터가 안전하게 소비하는 제한형 JSON AST(No executable HTML/CSS)이며, `html_renderer`는 Playwright/wkhtmltoimage 전용 전체 페이지 정적 PNG 인쇄용입니다.
   - 하나를 없애고 다른 쪽으로 단일화하려는 시도는 제품 요구사항(크리에이터 초안 편집 vs 최종 게시 이미지 배포)을 위반합니다.

4. **`react_document.py`의 엄격한 AST Pydantic 제약(`extra="forbid"`) 유지**:
   - 노드 깊이 제한(`MAX_REACT_DOCUMENT_DEPTH = 20`), 노드 개수 제한(300), 색상 정규식 검증, URL 프로토콜 검증 등은 다소 엄격해 보이지만 FE 보안 및 렌더링 성능을 보장하는 핵심 방어선입니다. 유연성을 핑계로 완화해서는 안 됩니다.

5. **2단계 비동기 라이프사이클 (`create_draft` → `approve_draft` → `run`) 유지**:
   - 저비용/고속 초안 생성(수 초)과 고비용 GPU 확산 생성(수 분)을 분리한 것은 시스템의 핵심 경제성 설계입니다. 이를 단일 동기 API 호출로 합치면 안 됩니다.

6. **`web/` 디렉터리 내 프런트엔드 미리보기 코드 수정 금지**:
   - 우리 팀은 생성형 AI 팀이며, `web/` 코드는 프런트엔드 영역입니다. 백엔드 리팩터링의 범위에 포함되지 않습니다.

---

## 5. 검증 방법 및 무회귀 보장 전략

모든 리팩터링 조치는 **"동작 변경 0, 순수 구조 개선 100%"** 를 목표로 합니다. 이를 보장하기 위해 4단계 검증 게이트를 적용합니다.

### 1단계: 단위·통합 테스트 스위트 회귀 검증
- **대상**: 전체 테스트 328개 (`pytest -q`)
- **기준**: 리팩터링 전후 328 passed 유지 (0 failed, 0 error).
- **소요 시간**: 약 3.7초로 즉각적 피드백 가능.

### 2단계: Facade Re-export 패턴을 통한 공개 심볼 무중단 검증
- 기존 파일(`source_photos.py`, `prompts.py`, `persistence.py`)을 삭제하지 않고, 분리된 하위 모듈의 모든 심볼을 그대로 `__all__` 또는 모듈 레벨에서 Re-export합니다.
- 기존 외부 호출부(`runner.py`, `factory.py`, `pipeline.py`, 테스트 코드)가 import 경로를 바꾸지 않아도 100% 정상 작동함을 보장합니다.

### 3단계: 정적 순환 참조 및 AST 검증
- Python `ast` 파서를 통해 `src/` 전체의 import 그래프를 재분석하여 순환 참조가 0건임을 기계적으로 검증합니다.
- `dto.py:417`의 lazy import 제거 후, 모듈 임포트 시 `ImportError`가 발생하지 않는지 `python -c "import detail_page_ai"`로 검증합니다.

### 4단계: 파일럿 품질 게이트 3종 교차 검증
- 기존 산출물 및 샘플 케이스에 대해 독립 평가 게이트 3종을 실행하여 동일한 판정이 유지되는지 확인합니다:
  1. `check_cutout_fidelity.py`: 누끼 잉크 비율 보존율 판정 불변 확인
  2. `check_plan_diversity.py`: 기획 다양성 및 Jaccard 일치도 지표 불변 확인
  3. `check_reference_label.py`: '참고용' 라벨 도달 및 원본 오표기 판정 불변 확인
