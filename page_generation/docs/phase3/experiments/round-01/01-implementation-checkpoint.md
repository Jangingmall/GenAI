# Round 01 · Implementation Checkpoint — validation 블록 패딩 제거

| 항목 | 값 |
| --- | --- |
| 차수 | 01 |
| 파일럿 디렉터리 | `generated/evaluation/pilot-20260910-102346` |
| 직전 차수 기준 | `generated/evaluation/pilot-20260909-224737` (baseline) |
| 이미지 재생성 | 예 |
| 기록 시각 | 2026-09-10 |

## 변경 파일

- `src/detail_page_ai/validation.py:ensure_editorial_page_plan`: hero·closing을 제외한 중간 블록이 6개 이상이면 모델이 만든 블록 종류와 순서를 보존하도록 단일 가드를 추가했다. hero·closing 정규화와 fidelity 보정은 유지했다.
- `tests/test_validation.py`: 충분한 모델 계획을 보존하는 테스트와 빈약한 계획을 계속 보강하는 테스트를 추가했다.

## 코드상 체크포인트

파일럿에서 모델이 8~10개 블록을 반환했으므로 중간 블록 6개 이상을 충분한 계획의 경계로 기록했다. 중간 블록이 6개 미만인 경우에는 기존 안전 바닥 보강 경로를 유지했다. DTO의 최대 14블록 제한은 변경하지 않았다.

## 테스트 통과 수

- `tests/test_validation.py`: 9 passed
- 전체 테스트: 261 passed

## 새 산출물

새 스크립트·카탈로그·CSS 산출물은 없었다. 변경은 validation 로직과 회귀 테스트에 한정됐다.
