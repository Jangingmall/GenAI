# Round 06 · 구현 체크포인트 — variant 고정 배정 해제와 CSS 4종 구현

| 항목 | 값 |
| --- | --- |
| 차수 | 06 |
| 파일럿 디렉터리 | `generated/evaluation/pilot-20260910-145007` |
| 직전 차수 기준 | `generated/evaluation/pilot-20260910-135605` (5차) |
| 이미지 재생성 | 예 (Flux 9B 생성, 27.3분 소요) |
| 기록 시각 | 2026-09-10 |

## 1. 파일별 변경 내용

### 1) 카탈로그 원형별 variant 배정
- **파일**: `assets/references/detail-page-layouts.json`
- **위치**: 25개 레이아웃 원형 전체 객체 (`variants` 키)
- **내용**: 25개 원형 각각의 `sequence`에 일대일로 대응하는 `variants` 배열 필드를 추가했다. 카탈로그 전체에서 `paper 57`, `sand 39`, `compact 35`, `light 35`, `full-bleed 16`, `dark 16`, `image-left 11`, `image-right 11` 등 8종 variant가 원형 특성에 맞게 배정되었다.

### 2) Validation 계층의 강제 덮어쓰기 해제
- **파일**: `src/detail_page_ai/validation.py`
- **위치**: `normalize_page_plan()` (lines 135-165)
- **내용**: 코드가 `detail_split`을 무조건 `dark`, `usage_scene`을 `full-bleed`, `hero` 및 `closing`을 `paper`로 강제 덮어쓰던 하드코딩 로직을 제거했다. 모델 및 카탈로그에서 입력된 `variant` 값을 그대로 보존하도록 변경했다. 단, 에셋 참조를 연결하는 `photo_id` 정규화 로직은 그대로 유지했다.

### 3) 누락된 4종 variant CSS 규칙 구현
- **파일**: `web/detail_page.css`
- **위치**: 파일 하단 신규 variant 스타일 클래스 (117줄 추가)
- **내용**: DTO(`PageBlockVariant`)에는 정의되어 있었으나 CSS 규칙이 없어 기본 스타일로 폴백되던 4종의 스타일을 구현했다:
  - `.variant-sand`: 공예 레퍼런스 가이드 토큰에 기반한 샌드 톤 표면 색상.
  - `.variant-image-left`: 텍스트-미디어 분할 블록에서 이미지를 좌측에 배치.
  - `.variant-image-right`: 텍스트-미디어 분할 블록에서 이미지를 우측에 배치.
  - `.variant-compact`: 여백과 타이포그래피를 압축하여 정보 밀도를 높인 레이아웃.

### 4) 단위 테스트 보강
- **파일**: `tests/test_layout_catalog.py`, `tests/test_validation.py`
- **내용**: 카탈로그 원형의 variant 정합성 검증(`test_catalog_uses_only_supported_variants`, `test_catalog_variant_count_matches_sequence` 등) 및 validation 계층에서 variant가 보존되는지 확인하는 테스트를 추가했다.

## 2. 새로 추가된 산출물 목록
- `web/detail_page.css` 내 4종 신규 variant 렌더링 클래스 (117줄 추가).

## 3. 테스트 통과 현황
- 커밋(`72ee301`, `9503769`) 시점 기준 관련 카탈로그 및 검증 단위 테스트 전원 통과.
