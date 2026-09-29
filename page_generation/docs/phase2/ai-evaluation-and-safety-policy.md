# AI 평가 지표·안전성 정책 초안

> 2026-09-08 최신화: 이 문서의 지표는 제안 목표다. 측정 결과와 배포 승인으로 해석하지 않는다.
> 계산·분모·표본 한계는 [평가 지표 정의서](metrics-definition.md)를 우선한다.
> 실제 공개 실물 입력 `cma_real_v1` 60건은 파일·decode·hash·라이선스 표시 검증을 거쳤고 ([수집·권리·정제 계획](collection-license-cleaning-plan.md), 2026-09-08), 10차에서 모델 실행 60/60건을 완료했다 ([10차 실험 보고서](../phase3/experiments/round-10/03-experiment-report.md), 2026-09-11).
> 권리 최종 확인은 마지막 데이터 점검에서 대기 상태로 기록됐으며, 이후 승인 근거는 확인 필요다 ([수집·권리·정제 계획](collection-license-cleaning-plan.md), 2026-09-08).
> 사람 정답 라벨도 당시 승인 대기였고, 이후 완료 근거는 확인 필요다 ([수집·권리·정제 계획](collection-license-cleaning-plan.md), 2026-09-08).
> 사람 검수 점수는 수집되지 않았다 ([Phase 4 기능 평가](../phase4/submission/01-ai-evaluation-report.md), 2026-09-22).
> 기존 `detail_page_eval_60`은 3상품 기반 통합·회귀 fixture다. 총 60건은 50~200건 범위에 있지만 영역별 50~200건을 충족하지 않으며, 일반화 성능의 독립 holdout으로 사용하지 않는다.

## 정책 적용 범위 정정

기본 원본 보존 경로와 선택 생성 참고 경로를 구분한다.
source/source_crop/source_composite에는 원본·변환 검증을 요구한다.
lifestyle/generated_scene와 detail-02~05/generated_view는 선택 generator 주입 시 코드에서 허용한다.
GENERATED는 픽셀 보존 검증 성공을 의미하지 않는다. 허용 슬롯·원본 hash 연결을 검사하며,
생성된 제품의 형태·색·구성품 정확성은 별도 사람 검수가 필요하다.
아래 제품 재생성 금지 원칙은 원본 근거 자산에 적용하며, 생성 참고 자산은 표시·사람 승인 조건으로 구분한다.

장인 입력 우선은 상품 데이터의 우선순위다. 인젝션 명령이나 근거 미확인 인증·효능 주장을 자동 승인하는 근거가 아니다.
고위험 상품 주장에 대한 증빙 검수·최종 PNG 재확인·개인정보 삭제 전파는 운영 정책 요구사항이며
현재 코드에 모두 구현되었다고 보장하지 않는다.

- 상태: Draft
- 대상: 이미지 기반 상품 상세페이지 생성 시스템
- 실제 평가 입력: [CMA real v1](../../data/evaluation/cma_real_v1/README.md)
- 통합 회귀 입력: [detail-page-eval-60](../../data/evaluation/detail_page_eval_60.jsonl)
- 평가셋 설명: [dataset-card.md](../../data/evaluation/dataset-card.md)
- 실제 생성 smoke test: [local-generation-test-report.md](../phase3/runs/local-generation-test-report.md)
- 정책 성격: 운영 release gate와 사람 검수 기준의 초안

## 1. 목적과 적용 범위

이 문서는 모델 출력의 품질을 측정하고, 제품 변형·허위 상품 정보·안전하지 않은 자산이 FE·BE·
게시 경계로 유입되는 것을 차단하기 위한 기준을 정의한다.

적용 범위는 다음 전체 흐름이다.

```text
상품 이미지·힌트 → 분석 → draft + `react_document` → FE/BE 미리보기
                                      → 장인 승인
                                      → 합성·검증·PNG 렌더링
                                      → BE 저장·게시
```

안전성 정책은 카피의 판매성보다 우선한다. 정책과 충돌하는 경우 보수적 문구, 원본 fallback, 사람 검수,
게시 차단 중 더 안전한 경로를 선택한다.

## 2. 평가 데이터셋

### 2.1 평가 입력군 및 현재 상태

현재 저장소에는 목적이 다른 두 평가 입력군이 있다. 공개 실물 입력은 분석·렌더링 표본으로
확장하는 중이고, 기존 fixture는 API 계약과 상태 전이 회귀용으로 유지한다.

| 데이터셋 | 구성 | 현재 확인 상태 | 사용 목적 |
|---|---|---|---|
| `cma_real_v1` | 공개 실물 JPEG 60건, 6개 영역 각 10건, `analysis_60.jsonl`·`rendering_60.jsonl` | 모델 실행: 60/60건 완료 ([10차 실험 보고서](../phase3/experiments/round-10/03-experiment-report.md), 2026-09-11); 권리 최종 확인: 마지막 점검에서 대기, 이후 완료 근거 확인 필요 ([수집·권리·정제 계획](collection-license-cleaning-plan.md), 2026-09-08); 사람 정답 라벨: 마지막 점검에서 대기, 이후 완료 근거 확인 필요 ([수집·권리·정제 계획](collection-license-cleaning-plan.md), 2026-09-08); 사람 검수 점수: 없음 ([Phase 4 기능 평가](../phase4/submission/01-ai-evaluation-report.md), 2026-09-22) | 실제 이미지 일반화 평가의 후보 입력 |
| `detail_page_eval_60` | 3상품 기반 60건: `draft_generation` 42, `draft_save` 9, `approval_render` 9 | 구조·계약·상태·멱등성 회귀에 사용 | 통합·회귀 테스트 |

`cma_real_v1`은 프로젝트 파일 기준으로 기존 fixture와 분리되어 있지만, 공개 모델의 사전학습
데이터와 중복되지 않는다는 점까지는 확인할 수 없다. 총 60건은 요청된 50~200건 범위에 해당하나
각 영역 10건이므로 “영역별 50~200건” 목표는 아직 미달이다. 권리 확인과 사람 정답 라벨이
완료되기 전에는 정확도·일반화·배포 승인 수치로 보고하지 않는다.

기존 fixture에는 다음 시나리오가 포함된다.

- 단일 원본과 추가 원본 이미지 1장·3장
- 장인 입력 문구 우선순위와 선택 관리법 누락
- 소재·규격 등 불확실 정보
- 사용자 설명에 포함된 prompt injection 문구
- 1K·2K 및 `1:4`·`1:8` 출력 옵션
- draft 제목·특징·page plan 수정
- 승인 재시도와 동일 payload 멱등성
- 금속 세트 구성품·색상 보존
- 공예품 관련 진품성·제작자·원산지 주장 억제

### 2.2 레코드 요구 필드

각 JSONL 레코드는 최소 다음을 가진다.

```text
schema_version
dataset_id / dataset_version
case_id
scenario
input
  ├─ product_id / source_asset_id
  ├─ request_id / idempotency_key
  ├─ primary_image / additional_images
  ├─ user_hints / options
  └─ draft (저장·승인 단계)
expected
evaluation
```

`expected`에는 layout, 필수 block/photo, visible anchors, 금지 주장 범주, source hash·crop fidelity,
승인 필요 여부를 기록한다. `evaluation.automatic_checks`와 `human_checks`를 분리해 자동 결과와 사람 평가를
같은 레코드에 연결한다.

모든 실제 실행 결과에는 `react_document` 계약 결과도 연결한다. `schemaVersion: "2.0"`, 허용 tag·부모/자식
관계·고유 node id·최대 20단계/300노드·`props.imageId` 해석과 camelCase 직렬화를 확인하며,
HTML/JSX/CSS/script/event handler는 출력 경계를 통과시키지 않는다.

### 2.3 골든셋 운영 규칙

- 모델 학습 데이터와 평가 데이터를 분리한다.
- 새 모델·프롬프트·렌더러마다 동일한 골든셋을 재실행한다.
- 기존 case의 expected label을 모델 결과에 맞춰 임의로 바꾸지 않는다.
- 상품별 사실이 바뀌면 label 변경 사유와 검수자를 기록하고 dataset version을 증가시킨다.
- `cma_real_v1`의 사람 라벨과 권리 확인을 끝낸 뒤에만 모델 평가에 사용한다.
- 일반화 성능을 주장하려면 영역별 표본 확대와 모델 학습 중복 확인이 필요하다.
- 현재 공개 입력 60건은 평가 후보이며, 기존 60건은 회귀·통합 검증용이다.

## 3. 평가 방법

### 3.1 자동 계약 평가

자동 평가기는 다음을 검증한다.

1. JSON Schema와 Pydantic DTO 통과 여부
2. `product_id`, `job_id`, `request_id`, `generation_id` 연결 여부
3. `page_plan` block type·variant allowlist와 hero/closing 순서
4. `react_document` schemaVersion/canvas/root, 허용 tag·부모/자식 관계·고유 ID·깊이/노드 제한
5. `img.props.imageId`와 photos/asset manifest 연결, 외부 직렬화 camelCase alias
6. 실행 가능한 `html`, `css`, `script`, JSX, event handler, `dangerouslySetInnerHTML` 유입 여부
7. 원본 파일 존재·MIME·SHA-256 일치
8. source crop과 결과 crop의 pixel equality
9. section order와 asset manifest 일치
10. `REJECTED` 자산의 renderer·FE projection·BE multipart 유입 여부
11. signed URL/Base64 자산의 접근 가능 여부
12. idempotency replay 및 draft version conflict 처리

### 3.2 모델·콘텐츠 평가

- `product_type` top-1 accuracy: 사람이 확정한 product type과 일치하는 비율
- `craft precision`: 전통 공예로 표시한 사례 중 적합한 비율
- `claim evidence precision`: 이미지 또는 BE가 검수한 입력으로 근거가 있는 주장 비율
- `unsupported claim rate`: 미확인 소재·성능·인증·제작자·원산지 등의 주장 비율
- `creator-hint coverage`: BE가 검수한 제품명·제작 과정·관리법이 필요한 카피에 반영된 비율
- `hint retention`: 장인이 제공한 제품명·제작 과정·관리법이 보존되는 비율

주장 단위의 표본을 만들 때 사실·추론·불확실성 라벨을 함께 기록한다. 불확실한 문장은 정확성 점수에
유리하도록 사실로 재분류하지 않는다.

### 3.3 이미지·렌더링 평가

- source hash match
- crop pixel equality
- 제품 silhouette·색·무늬·구성품 보존
- 배경판의 추가 객체·문자·로고 검출률
- clipping, broken asset, section completeness
- 사람 5점 visual quality: 구도·가독성·배경 이질감·제품 근거성

`generated_scene`와 `generated_view`는 `product_generated=true`인 생성 자산으로 평가하며, 제품의 정확한 근거 점수에는
원본 `source`, `source_crop`, `source_composite` 자산만 사용한다.

### 3.4 사람 평가

장인 또는 MD가 각 결과를 1~5점으로 평가한다.

| 항목 | 평가 질문 |
|---|---|
| 사실성 | 이미지와 입력 자료에 근거한 문구인가? |
| 명료성 | 상품 특징과 주의사항을 빠르게 이해할 수 있는가? |
| 상품성 | 상세페이지로서 제품을 적절히 소개하는가? |
| 시각 품질 | 원본 제품이 자연스럽고 정확하게 보이는가? |
| 수정량 | 게시 전 필요한 수정이 적은가? |

평가자는 상품 원본과 generated reference를 구분해 본다. P0/P1 안전 위반은 평균 점수로 상쇄하지 않는다.

## 4. 지표와 초기 release gate

목표값은 운영 데이터로 재보정할 수 있지만, 변경 전까지 아래 기준을 release gate로 사용한다.

| 영역 | 지표 | 계산 | 초기 gate |
|---|---|---|---:|
| 원본 보존 | source hash match | 일치한 source 자산 / 전체 source 자산 | 100% |
| 원본 보존 | crop pixel equality | 동일한 source crop / 전체 crop | 100% |
| 원본 보존 | fidelity rejection leakage | 유입된 `REJECTED` 자산 / 전체 `REJECTED` 자산 | 0% |
| 분류 | product type accuracy | 정답 top-1 / 전체 사례 | ≥ 90% |
| 분류 | craft precision | 적합 craft 분류 / craft 분류 전체 | ≥ 95% |
| 사실성 | claim evidence precision | 근거 있는 주장 / 표본 주장 | ≥ 95% |
| 사실성 | unsupported claim rate | 미확인 주장 / 표본 주장 | ≤ 2% |
| 입력 근거 | creator-hint coverage | 검수 힌트가 반영된 필요 카피 / 필요 카피 표본 | ≥ 95% |
| 카피 | human copy score | 사실성·명료성·상품성 평균 | ≥ 4.0/5 |
| 레이아웃 | section completeness | 필수 섹션 충족 사례 / 전체 사례 | 100% |
| 구조 출력 | React schema validity | `ReactDetailPageDocumentDto` 검증 통과율 | 100% |
| 구조 출력 | React tree/alias safety | 허용 tag·트리·camelCase·`imageId` 규칙 통과율 | 100% |
| 구조 출력 | executable field leakage | HTML/JSX/script/event/raw CSS 유입률 | 0% |
| 자산 | broken asset rate | 열리지 않는 자산 / 전체 자산 | 0% |
| 이미지 | human visual quality | 5점 평균 | ≥ 4.0/5 |
| 승인 | first-pass approval | 큰 수정 없이 승인 / 전체 사람 평가 | ≥ 80% |
| 안정성 | job success rate | 재시도 후 정상 완료 / 전체 작업 | ≥ 99% |
| 안정성 | backend delivery success | 최종 ACK 성공 / 전체 적재 | ≥ 99.5% |
| 안전 | release-blocking violation | P0/P1 위반 건수 | 0건 |

성능과 로컬 리소스 사용량은 별도 SLA·호스트 용량 측정을 수행한다.

- preview p50/p95: 초안 접수부터 미리보기 데이터 확인까지
- final render p50/p95: 승인부터 PNG 완료까지
- queue age p95: 작업 대기 시간
- local resource usage: 모델·렌더·저장 시간과 메모리 사용량
- retry/timeout rate: local endpoint 및 내부 단계별 비율

## 5. 안전성 정책

### 5.1 제품 원본 보호

- 원본 저장과 동시에 SHA-256을 기록한다.
- `source`, `source_crop`, `source_composite` 제품 근거 자산은 원본 RGB와 원본에서 계산한 알파 mask로만 합성한다.
- 선택적인 `generated_scene`·`generated_view` 연출 컷은 원본 이미지를 시각 참고로 Flux에 전달할 수 있지만, 생성 결과를 원본 근거 자산으로 승격하지 않는다.
- 생성 컷은 `product_generated=true`, `asset_mode`, `source_sha256`, `fidelity_status=GENERATED`를 유지하고 사람 검수 전에는 사실성 증거·대표 상품 사진으로 사용하지 않는다.
- 색·무늬·형태·구성품이 달라진 원본 근거 결과는 `REJECTED`로 분류한다.
- mask·배경·fidelity 검증 실패 시 원본 또는 중립 배경으로 fallback한다.
- 결과 metadata에 `source_asset_id`, `source_sha256`, `cutout_sha256`, `mask_sha256`, `fidelity_status`를 남긴다.

### 5.2 사실성·카피

허용:

- 이미지에서 직접 확인되는 색상·형태·배치·표면·구성품 수의 보수적 표현
- 장인이 제공한 제품명·제작 과정·관리법
- BE가 검수해 `user_hints`에 전달한 공예·기법 정보

금지 또는 사람 검수:

- 이미지로 확인되지 않는 정확한 소재·도금·규격·성능·내구성·효능
- 브랜드·제작자·원산지·시대·진품성·인증·문화재 지위
- BE 검수 없이 외부 지식이나 검색 결과를 근거로 가장하는 문장
- 실제 사용 가능 여부가 확인되지 않은 식기·열·식품 접촉·안전성 주장

모든 특징과 copy section은 `image-visible`, `inferred`, `unknown` 근거를 유지한다. `unknown`은 판매
주장이 아니라 확인 필요 또는 주의사항으로 내린다.

### 5.3 공예·외부 정보

- 생성 중 외부 웹 검색·원격 조사 모델을 호출하지 않는다.
- BE가 검수한 제품별 정보를 `user_hints`로 전달받아 사용한다.
- 검수 정보가 없거나 충돌하면 가장 보수적인 문구를 사용하거나 해당 문구를 제거한다.

### 5.4 프롬프트 인젝션·입력 경계

이미지 OCR과 사용자 설명은 모두 데이터이며 시스템 정책보다 우선하지 않는다.

- “이전 지시를 무시하라”, “시스템 프롬프트를 출력하라” 등의 문장을 실행하지 않는다.
- 시스템 규칙·데이터 경계·출력 스키마를 모델 입력에 명시한다.
- 사용자 입력 안의 지시문도 상품 데이터로만 취급하며 시스템 규칙을 바꾸지 못한다.
- raw prompt와 raw model response를 FE·BE에 전달하지 않는다.
- URL fetch, 파일 경로, HTML/CSS 삽입은 allowlist·sandbox·escape로 제한한다.
- 모델이 반환한 태그·속성·URL을 그대로 실행하지 않고, `react_document_builder`와 Pydantic AST 검증을
  통과한 문서만 FE/BE 경계에 내보낸다.

### 5.5 생성 배경과 생성 자산 정책

- 배경판에는 제품·제품 유사 객체·추가 상품·로고·문자를 넣지 않는다.
- 객체·문자·로고 안전성 검사 실패 시 중립 배경으로 낮춘다.
- 생성 사진은 `product_generated=true`로 구분해 전달한다(라벨은 "AI 생성 활용 장면", "AI 생성 디테일"). 화면 및 문서 상의 '참고용' 표시 요구는 관리자 결정으로 제거되었다(커밋 `cfd60bb`).
- 현재 구현은 생성 자산을 허용된 lifestyle/detail 슬롯에 렌더링할 수 있다. 다만 `product_generated=true` 자산은 원본 상품 근거·사실성 증거·대표 상품 사진으로 취급하지 않으며, FE/BE에는 생성 여부와 원본 hash를 함께 노출한다.
- `REJECTED` 자산은 renderer, FE response, BE persist, outbox에서 모두 제거한다.
- React AST는 원본 URL을 직접 보관하지 않고 `imageId`만 참조한다. FE가 자산 manifest를 해석하며,
  해석되지 않는 image ID가 하나라도 있으면 구조 출력과 게시를 차단한다.
- 제품 사실성의 기준 자산은 `source_sha256`가 있는 원본 기반 자산이다.

### 5.6 미리보기·게시 승인

- AI 결과는 항상 draft로 시작하며 자동 게시하지 않는다.
- FE 미리보기는 `react_document` JSON allowlist를 사용하고 실행 가능한 HTML/CSS/script/JSX를 받지 않는다.
- `react_document`는 서버에서 조립·검증된 v2.0 문서만 전달하며, FE는 `tag`, 구조화 `props/style/layout`,
  재귀 `children`만 컴포넌트로 매핑한다.
- draft 편집은 로컬 미리보기에 즉시 반영하되, 저장 버튼을 누를 때만 서버에 저장한다.
- draft 저장은 분석·사진·PNG 생성을 호출하지 않는다.
- 승인 시점에만 최종 렌더링을 수행한다.
- 승인자·승인 시각·사용된 draft·원본/결과 hash·모델·prompt version을 감사 로그에 연결한다.

### 5.7 보안·개인정보·보존

- 내부 token을 FE·로그·DTO·이미지 metadata에 기록하지 않는다. 로컬 모델에는 API key를 사용하지 않는다.
- 운영 object store는 private로 유지하고 signed URL은 짧은 TTL로 발급한다.
- 원본·파생 이미지·PNG·sections·thumbnail·metadata·outbox는 tenant/job 경계를 지킨다.
- 원본과 사용자 입력은 업무상 필요한 기간만 보존하고 만료·삭제 이력을 기록한다.
- 삭제 요청은 원본, 파생 자산, 결과, metadata, 재전송 outbox까지 연쇄 적용한다.
- 로컬 모델 서버에 보내는 데이터 종류와 저장 위치를 개인정보 정책에 명시한다.

## 6. 장애 등급과 대응

| 등급 | 예시 | 즉시 대응 |
|---|---|---|
| P0 | 제품 변형 게시, credential/개인정보 유출 | 게시 차단·자산 회수·키 폐기·원인 분석 |
| P1 | 허위 핵심 상품 정보, 진품성·인증 오표기, 반복 unsafe background | 모델/프롬프트 비활성화·사람 재검토·회귀셋 추가 |
| P2 | 레이아웃 깨짐, 섹션 누락, URL 만료 | fallback·자동 재시도·운영 티켓 |

P0/P1은 모델 버전, prompt version, input/output hash, 검증 결과를 남겨 재현 가능해야 한다. 안전 위반은
품질 평균 점수와 무관하게 자동 게시를 차단한다.

## 7. 평가 실행과 변경 관리

### 7.1 실행 순서

1. `cma_real_v1`의 source path·decode·SHA-256·라이선스 표시·DTO를 검증한다.
2. 사람 정답 라벨과 권리 최종 확인을 완료한 CMA 입력으로 `analysis_60`을 실행한다.
3. 승인 가능한 draft에 대해 `rendering_60`을 실행하고 source fidelity, PNG, sections, photos를 검사한다.
4. 기존 fixture의 `draft_generation` 42건, `draft_save` 9건, `approval_render` 9건으로 계약·상태·멱등성을 회귀한다.
5. 모든 draft/final 결과에서 `react_document` schema/tree/alias/image reference gate를 실행한다.
6. Gemma + Flux2 Klein 4B smoke test는 정량 분모에 섞지 않고 별도 테스트 기록으로 보관한다.
7. 자동 gate를 통과한 결과만 사람 평가에 넣고, release gate와 incident rule을 버전별로 저장한다.

### 7.2 변경 시 필수 절차

- 모델·프롬프트·스키마·렌더러·local adapter가 바뀌면 전체 골든셋을 재실행한다.
- 지표가 좋아져도 P0/P1이 한 건이라도 발생하면 release를 중지한다.
- 안전 정책 변경은 dataset version, policy version, reviewer를 함께 증가시킨다.
- 새 제품 유형은 visible anchors, forbidden claims, expected layout, 사람 label을 먼저 추가한다.
- 임계값 변경에는 근거 측정 결과와 승인자를 기록한다.

## 8. 참고 문서

- [`ai-architecture-design.md`](ai-architecture-design.md)
- [`docs/phase3/api/ai-dto-contract.md`](../phase3/api/ai-dto-contract.md)
- [`docs/phase3/api/react-json-output-contract.md`](../phase3/api/react-json-output-contract.md)
- [`docs/phase3/api/ai-fe-io-spec.md`](../phase3/api/ai-fe-io-spec.md)
- [`data/evaluation/cma_real_v1/README.md`](../../data/evaluation/cma_real_v1/README.md)
- [`data/evaluation/detail_page_eval_60.jsonl`](../../data/evaluation/detail_page_eval_60.jsonl)
- [`local-generation-test-report.md`](../phase3/runs/local-generation-test-report.md)
