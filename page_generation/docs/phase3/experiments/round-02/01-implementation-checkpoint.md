# Round 02 · Implementation Checkpoint — 프롬프트 순서 각인 제거

| 항목 | 값 |
| --- | --- |
| 차수 | 02 |
| 파일럿 디렉터리 | `generated/evaluation/pilot-20260910-111715` |
| 직전 차수 기준 | `generated/evaluation/pilot-20260910-102346` |
| 이미지 재생성 | 예 |
| 기록 시각 | 2026-09-10 |

## 변경 파일

- `src/detail_page_ai/prompts.py:build_analysis_prompt`: Copy Map을 순서 목록이 아닌 참조표로 바꾸고, 9블록 하한과 `Open`·`Follow`·`Include`·`Finish` 순차 레시피를 제거했다.
- `tests/test_prompts.py`: 개정된 프롬프트 계약을 검증하도록 테스트를 갱신했다.

## 코드상 체크포인트

블록 설명은 유지하되 page-plan 순서를 정하지 않는 참조표로 바꿨다. page_plan 하한을 8로 맞추고 hero 첫·closing 마지막 및 안전 어휘 같은 구조 제약을 남겼다. 이 차수에서는 블록별 생략 조건은 아직 충분히 도입하지 않았다.

## 테스트 통과 수

- `tests/test_prompts.py`: 32 passed
- 전체 테스트: 261 passed

## 새 산출물

새 스크립트·카탈로그·CSS 산출물은 없었다.
