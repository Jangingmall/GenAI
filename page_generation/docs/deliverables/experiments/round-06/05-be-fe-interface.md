# Round 06 · BE/FE 인터페이스 영향 — variant 고정 배정 해제와 CSS 4종 구현

| 항목 | 값 |
| --- | --- |
| 차수 | 06 |
| 파일럿 디렉터리 | `generated/evaluation/pilot-20260910-145007` |
| 직전 차수 기준 | `generated/evaluation/pilot-20260910-135605` (5차) |
| 이미지 재생성 | 예 (Flux 9B 생성, 27.3분 소요) |
| 기록 시각 | 2026-09-10 |

## 1. BE 계약 변화 (page_plan 페이로드)

### 1) variant 값의 유효 보존
기존에는 `validation.py`가 특정 블록의 variant를 강제로 덮어씌워 FE에 전달했으나, Round 06부터는 모델이 생성한 `image-left`, `image-right`, `compact` 등의 값이 유실되지 않고 `result_summary.json` 및 `react_document.json`의 `page_plan[].variant` 필드로 온전히 보존되어 내려간다.

### 2) DTO 스키마
`PageBlockVariant` 열거형(`paper`, `light`, `dark`, `sand`, `image-left`, `image-right`, `full-bleed`, `compact`)에 이미 8종이 정의되어 있었으므로, DTO 필드 스키마의 수정은 발생하지 않았다.

## 2. FE 계약 변화 (CSS 및 렌더러)

### 1) 신규 CSS 클래스 지원
`web/detail_page.css`에 4종의 신규 클래스 스타일이 구현되었다:
- `.variant-sand`: 공예 레퍼런스 스타일 배경 토큰 지원.
- `.variant-image-left` / `.variant-image-right`: 텍스트와 이미지의 플렉스 정렬 방향 전환.
- `.variant-compact`: 좁은 간격의 조밀한 레이아웃 스타일.

### 2) 렌더링 경로 활성화
FE가 수신한 `variant` 문자열을 바탕으로 블록 DOM에 해당 클래스를 주입할 때, 이전에는 브라우저가 기본 스타일로 폴백되었으나 이제는 의도된 시각 처리가 즉시 렌더링된다.

## 3. 하위 호환성 여부
**완벽한 하위 호환 유지**. 신규 필드 추가가 아닌 기존 열거형 값의 데이터 보존 및 누락되었던 CSS 정의 추가이므로, 기존 클라이언트나 이전 차수의 결과물을 소비하는 환경을 전혀 깨뜨리지 않는다.
