# Round 10 · 에러 분석 — 라벨 계약 결함과 60건 실행 기록 오류

| 항목 | 값 |
| --- | --- |
| 차수 | 10 |
| 파일럿 디렉터리 | `generated/evaluation/full60-20260910-204433` |
| 직전 차수 기준 | `generated/evaluation/pilot-20260910-164008` (9차) |
| 이미지 재생성 | 예 (케이스별 Flux 이미지 생성 60건, 3시간 52분) |
| 기록 시각 | 2026-09-11 |

## 사건 1 — 생성 사진의 '참고용' 라벨이 React 문서 계약에서 탈락

### 증상

생성 이미지에는 `참고용` label이 있었지만 `react_document.json`에는 해당 label이 0회 나타났다. HTML도 생성 사진 label을 그리지 않았다.

### 증거

- `src/detail_page_ai/source_photos.py:793`, `:834`가 `AI 생성 활용 장면(참고용)`, `AI 생성 디테일(참고용)` label을 부여했다.
- 수정 전에는 `src/detail_page_ai/react_document_builder.py:224-232`가 `photo_id`와 블록 제목 기반 `alt`만 사용해 `PhotoAsset.label`을 버렸다.
- 독립 게이트에서 같은 `analysis-cma-102980`이 수정 전 FAIL(종료 코드 1), 수정 후 PASS(종료 코드 0)였다.
- 관리자가 실제 케이스의 HTML을 확인해 생성 컷 5장에는 figcaption이 있고 원본 컷 3장에는 label이 없음을 확인했다.

### 원인

사진 생성 단계의 metadata와 React 문서 빌더의 입력 계약 사이에 `generated_photos` 전달 경계가 없었다. HTML renderer도 generated 여부만 분기하고 label을 전달하지 않았다.

### 조치

`build_react_document_from_draft()`에 `generated_photos` keyword 인자를 추가하고 생성 사진만 필터해 figcaption을 만들었다. 파이프라인은 사진 metadata 생성 뒤 React 문서를 만들도록 순서를 옮겼고, HTML renderer와 CSS에도 생성 label 표시 경로를 추가했다. 라벨 게이트와 React/HTML 테스트를 추가했다.

### 재발 방지

`scripts/check_reference_label.py`가 React 문서와 HTML에서 생성 사진 label 전달 및 원본 사진 오표기를 함께 검사하게 됐다. `tests/test_reference_label_gate.py`, `tests/test_react_document.py`, `tests/test_html_renderer.py`가 이 계약을 고정했다.

## 사건 2 — `pipeline.py:539`를 잔여 결함으로 잘못 지목

### 증상

관리자는 `pipeline.py:539`의 `build_react_document_from_draft(approved_draft)` 호출에 `generated_photos`가 없다는 점을 잔여 label 결함으로 지목했다.

### 증거

- 해당 경로의 `preview_photos`는 항상 `[]`였다.
- `photo_generator`는 `run()`에서만 동작했다.
- `service.py:314`는 완료된 draft의 편집을 거부했다.
- `dto.py:419`는 프로덕션 호출자가 없고 테스트 전용이었다.

### 원인

빌더 호출부라는 표면적 형태만 비교하고, 해당 경로에서 생성 사진이 실제로 존재할 수 있는지와 호출 상태를 함께 확인하지 않았다.

### 조치

`pipeline.py:539`는 수정하지 않고 결함이 아닌 경로로 분류했다. 생성 사진이 존재하는 `run()` 및 recovery 경로에만 `generated_photos`를 전달했다.

### 재발 방지

호출부를 잔여 결함으로 분류하기 전에 입력 데이터의 생성 가능성, 호출자, 상태 전이를 함께 확인하는 방식으로 기록했다.

## 사건 3 — `orc task` 브리프 전달 방식 오용

### 증상

`orc task`가 브리프를 stdin으로 받는데 브리프를 인자로 넘겼고, 그 결과 세 워커의 브리프 본문이 통째로 비어 한 번의 배정이 헛돌았다.

### 증거

빈 브리프를 받은 세 워커가 지시 본문 없이 배정되었고, 해당 배정은 유효한 작업 근거로 사용할 수 없었다.

### 원인

오케스트레이션 명령의 입력 전달 계약(stdin)과 인자 전달을 혼동했다.

### 조치

본문이 비어 있는 배정을 유효 결과로 채택하지 않고, 실제 브리프 본문이 전달된 작업만 10차 기록의 근거로 사용했다.

### 재발 방지

작업 배정 직후 워커가 받은 브리프 본문이 비어 있지 않은지 확인하는 검사를 기록 절차에 포함했다.

## 사건 4 — 데이터셋 중복 원본 발견

### 증상

60건 평가 입력 중 `cma-165266`과 `cma-165267`이 서로 다른 asset ID이지만 픽셀이 동일한 중복 원본이었다.

### 증거

두 원본의 차이 bounding box가 `None`이었고 md5만 달랐다. 따라서 60건 입력에서 고유 제품 수는 59종으로 기록됐다.

### 원인

데이터셋에 동일 픽셀 원본이 서로 다른 항목으로 포함되어 있었다. 10차 기록에는 그 원인이나 생성 경위가 추가로 확인되지 않았다.

### 조치

중복을 발견 사실로 기록하고 60건 결과를 60개 입력·59개 고유 제품으로 구분해 해석했다. 평가 코드는 변경하지 않았다.

### 재발 방지

10차 기록에는 중복 원본을 식별한 사실만 남았고, 별도 데이터 정제 조치는 확인되지 않았다.

## 신규 런타임 실패와 이월 상태

- 60건 실행은 60/60 성공, 실패 0건이었다.
- 당시 컷아웃 게이트는 OK 55건, 부분 손실 5건으로 기록됐다.
- 사람 검수 점수는 존재하지 않았다.

