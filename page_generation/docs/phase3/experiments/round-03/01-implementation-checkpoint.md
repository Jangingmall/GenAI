# Round 03 · Implementation Checkpoint — 블록별 선택·생략 조건

| 항목 | 값 |
| --- | --- |
| 차수 | 03 |
| 파일럿 디렉터리 | `generated/evaluation/pilot-20260910-115722` |
| 직전 차수 기준 | `generated/evaluation/pilot-20260910-111715` |
| 이미지 재생성 | 예 |
| 기록 시각 | 2026-09-10 |

## 변경 파일

- `src/detail_page_ai/prompts.py:build_analysis_prompt`: 블록별 사용·생략 조건을 도입했다. `statement`는 creator-provided 제작 과정 데이터(`howMade`)가 있을 때만 포함하고, 근거가 없는 블록은 생략하도록 했다.
- `tests/test_prompts.py`: 블록 조건과 `statement` 게이트를 검증하도록 테스트를 갱신했다.

## 코드상 체크포인트

선택 조건은 detail, feature, info, palette, recommendation, scale, statement, usage 관련 블록에 적용됐다. 구조보다 이미지·제공 데이터 근거를 우선하고, 근거가 없으면 카피를 지어내지 않고 생략하는 지시를 유지했다.

## 테스트 통과 수

- `tests/test_prompts.py`: 32 passed
- 전체 테스트: 261 passed

## 새 산출물

새 스크립트·카탈로그·CSS 산출물은 없었다.
