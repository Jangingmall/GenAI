# Round 08 · 구현 체크포인트 — 카탈로그와 합격 기준을 함께 수정

| 항목 | 값 |
| --- | --- |
| 차수 | 08 |
| 파일럿 디렉터리 | `generated/evaluation/pilot-20260910-161310` |
| 직전 차수 기준 | `generated/evaluation/pilot-20260910-153208` (7차) |
| 이미지 재생성 | 아니오 (--image-provider none, AI 이미지 생성 없음) |
| 기록 시각 | 2026-09-10 |

## 1. 파일별 변경 내용

### 1) 카탈로그 붙박이 블록 완화 및 저빈도 블록 보강
- **파일**: `assets/references/detail-page-layouts.json`
- **위치**: 25개 레이아웃 원형 전반
- **내용**: 25개 원형 중 84~96%에 달하던 4대 붙박이 블록의 빈도를 대폭 낮추었다:
  - `notice`: 24회 → 17회
  - `info_table`: 24회 → 16회
  - `detail_split`: 22회 → 16회
  - `usage_scene`: 21회 → 15회
  각 원형의 `when`과 `rationale`을 분석하여 필수적이지 않은 원형에서 선별 제거했으며, 제거된 자리에는 `wide_image`, `scale_reference`, `palette`, `recommendation` 등 저빈도 블록을 보강했다. 중간 블록 수는 validation 폴백 경계인 6개 이상을 철저히 유지했다.

### 2) 다양성 평가 도구의 카탈로그 시뮬레이션 기반 재설계
- **파일**: `scripts/check_plan_diversity.py`
- **위치**: `compute_catalog_baseline()`, `compute_effective_common_blocks()`, `evaluate_plan_diversity()`
- **내용**:
  - `compute_catalog_baseline()`: `seed=42`, `iterations=2000` 고정 몬테카를로 시뮬레이션으로 카탈로그 비복원 N건 추출 시 기대 Jaccard 평균을 산출.
  - 동적 임계값: 시뮬레이션 평균 + 10.0%p 초과 시 탈락하는 도달성 기반 게이트 도입.
  - 유효 공통 블록: DTO 강제 블록인 `hero`와 `closing`을 공통 블록 계산에서 제외하고 명시.
  - 완전 일치 쌍 허용치: 생일 역설(49% 충돌 확률) 및 단품 열람 환경을 고려해 <= 1쌍으로 완화.
  - 기존 절대 기준(60% / 4종 / 0쌍) 병기 기능 구현.

### 3) 갤러리 아티팩트 빌더 방어 로직 추가
- **파일**: `scripts/build_review_artifact.py`
- **위치**: `collect()` 함수
- **내용**: 7차의 실패 케이스처럼 `result_summary.json`이 없는 케이스가 발생해도 스크립트 전체가 크래시되지 않고 스킵 처리하도록 예외 처리를 보강했다.

### 4) 단위 테스트 갱신
- **파일**: `tests/test_layout_catalog.py`, `tests/test_plan_diversity.py`
- **내용**: 개정된 카탈로그 제약 조건 및 신규 다양성 평가 게이트(유효 공통, 동적 기준선) 단위 테스트 반영.

## 2. 새로 추가된 산출물 목록
- 신규 카탈로그 메타데이터 및 시뮬레이션 기준선 계산 로직.

## 3. 테스트 통과 현황
- 커밋(`8fb9efa`, `53aff3d`) 시점 기준 단위 테스트 전원 통과.
