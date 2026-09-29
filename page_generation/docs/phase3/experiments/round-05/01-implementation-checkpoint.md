# Round 05 · Implementation Checkpoint — 코드 결정 구성과 모델 카피

| 항목 | 값 |
| --- | --- |
| 차수 | 05 |
| 파일럿 디렉터리 | `generated/evaluation/pilot-20260910-135605` |
| 직전 차수 기준 | `generated/evaluation/pilot-20260910-123917` |
| 이미지 재생성 | 예 |
| 기록 시각 | 2026-09-10 |

## 변경 파일

- `src/local_detail_page_ai/adapters.py:LocalProductAnalyzer.analyze`: 이미지 SHA-256을 시드로 카탈로그 원형 하나를 코드가 선택하도록 연결했다.
- `src/detail_page_ai/prompts.py:_format_selected_layout_instruction`, `_build_page_plan_contract`, `build_analysis_prompt`: 선택된 원형의 sequence를 확정된 page_plan 골격으로 전달하고, 모델은 지정 블록의 근거 있는 카피만 작성하도록 했다. 근거 없는 블록은 생략할 수 있게 했다.
- `tests/test_prompts.py`: 결정된 시퀀스 주입, 카탈로그 폴백, 근거 기반 생략 계약을 검증했다.

## 코드상 체크포인트

원형 선택은 `count=1`로 수행됐고, DTO를 바꾸지 않았다. validation의 hero·closing 정규화와 안전 바닥은 유지했다. 이미지 해시가 다른 상품에서도 같은 원형을 고를 수 있는 충돌 가능성은 제거하지 않았다.

## 테스트 통과 수

- `tests/test_prompts.py`: 38 passed
- 전체 테스트: 293 passed

## 새 산출물

Round 04에서 추가된 `assets/references/detail-page-layouts.json`을 재사용했다. 이 차수에 새 스크립트·카탈로그·CSS 산출물은 없었다.
