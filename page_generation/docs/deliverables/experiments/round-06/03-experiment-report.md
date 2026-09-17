# Round 06 · 실험 리포트 — variant 고정 배정 해제와 CSS 4종 구현

| 항목 | 값 |
| --- | --- |
| 차수 | 06 |
| 파일럿 디렉터리 | `generated/evaluation/pilot-20260910-145007` |
| 직전 차수 기준 | `generated/evaluation/pilot-20260910-135605` (5차) |
| 이미지 재생성 | 예 (Flux 9B 생성, 27.3분 소요) |
| 기록 시각 | 2026-09-10 |

## 1. 문제
Round 05까지 블록 구성은 평균 Jaccard 72.4%, 유효 공통 4종, 완전 일치 1쌍으로 같은 구조를 많이 공유했다. 더욱이 `validation.py` 코드가 `detail_split`을 `dark`, `usage_scene`을 `full-bleed`, `hero`/`closing`을 `paper`로 강제 덮어쓰고 있었고, DTO에 선언되어 있던 `sand`, `image-left`, `image-right`, `compact`는 CSS 규칙이 없어 실제로 값이 나와도 화면 차이를 만들지 못했다.

## 2. 가설
카탈로그 원형의 블록별 variant 배정을 활성화하고 validation의 강제 고정을 해제하며 누락된 CSS 규칙 4종을 구현하면, 구조 지표가 동일하더라도 상세페이지 시각 처리의 분포가 다채롭게 갈라질 것이다.

## 3. 실험 설계
- **변경 요소**:
  - 카탈로그 25종 원형에 `variants` 배열 필드 정의.
  - `validation.py`의 variant 덮어쓰기 제거.
  - `web/detail_page.css`에 4종 variant 클래스 규칙 구현.
- **통제 요소**:
  - 이미지 해시 기반 단일 원형 선택 메커니즘 유지.
  - 텍스트 생성 모델(`ddalcu/Qwen3.8-27B-MLX-Serve-4bit`) 및 이미지 생성 모델(`mlx-community/flux2-klein-9b-4bit`) 동일.

## 4. 실행 명령 및 환경
- 실행 디렉터리: `generated/evaluation/pilot-20260910-145007`
- 실행 모드: 6개 케이스 전체 파이프라인 (텍스트 생성 + 이미지 생성)

## 5. 측정 수치

### 1) 다양성 및 런타임 지표 (정본 검증표)
| 지표 항목 | 측정값 | 비고 |
| --- | --- | --- |
| 성공 케이스 | 6/6건 | 전체 성공 |
| 소요 시간 | 27.3분 | 이미지 재생성 수행 |
| 평균 Jaccard 유사도 | **72.4%** | 직전 5차(72.4%)와 동일 |
| 유효 공통 블록 종수 | **4종** | `detail_split, info_table, notice, usage_scene` (hero/closing 제외) |
| 전체 공통 블록 종수 | 6종 | `hero, closing` 포함 시 6종 |
| 완전 일치 쌍 수 | **1쌍** | 6건 중 1쌍 |
| 고유 시퀀스 종수 | 5종 / 6건 | 최빈 시퀀스 2회 반복 |
| 길이 분포 | 8블록 3건, 10블록 3건 | 총 54개 블록 |

### 2) 블록 Variant 출력 분포
- 총 54개 블록의 출력 variant:
  `paper 22 · light 19 · image-left 4 · dark 3 · full-bleed 3 · image-right 2 · compact 1 · sand 0`
- 카탈로그 25종 원형 기준 배정 분포:
  `paper 57 · sand 39 · compact 35 · light 35 · full-bleed 16 · dark 16 · image-left 11 · image-right 11`

## 6. 판정 결과
- **판정**: **FAIL** (당시 적용 중이던 절대 기준: 평균 Jaccard <= 60%, 전체 공통 <= 4종, 완전 일치 0쌍 미달).

## 7. 가설 검증 결과

### 1) 부분 입증: 표현 계층 다양화
기존에 `paper`, `light`, `dark`, `full-bleed`로만 획일화되던 출력에 `image-left(4)`, `image-right(2)`, `compact(1)` 등 신규 variant가 출현했고 CSS 렌더링 경로가 개방되어 시각 처리 분포가 갈라지기 시작했다.

### 2) 부분 반증: 카탈로그 배정 반영 실패
카탈로그에서 39회나 배정된 핵심 스타일인 `sand`가 실제 출력에서 0회로 전멸했다. 프롬프트가 variant 배정 정보를 모델에 전달하지 않아 카탈로그 배정이 모델 출력으로 직결된다는 가설은 반증되었다.

## 8. 남은 한계
- 프롬프트 템플릿에 variant 전달 경로가 누락되어 모델의 사전 학습 편향이 스타일을 지배함.
- 해시 1개 기반 원형 선택으로 인한 구조 수렴(평균 Jaccard 72.4%)은 전혀 개선되지 않음.
- 정량적 자동 집계와 CSS 구문 확인만 수행되었으며, 사람 검수 점수나 렌더링 품질 평가는 부재함.
