# Round 04 · Implementation Checkpoint — 레이아웃 원형 예시 주입

| 항목 | 값 |
| --- | --- |
| 차수 | 04 |
| 파일럿 디렉터리 | `generated/evaluation/pilot-20260910-123917` |
| 직전 차수 기준 | `generated/evaluation/pilot-20260910-115722` |
| 이미지 재생성 | 예 |
| 기록 시각 | 2026-09-10 |

## 변경 파일

- `src/detail_page_ai/layout_archetypes.py:load_layout_catalog`, `select_layout_archetypes`: 레이아웃 카탈로그를 읽고 이미지 SHA-256 기반으로 재현 가능한 원형 예시를 선택했다. `making_method`가 없으면 `statement` 원형을 제외했다.
- `src/detail_page_ai/prompts.py:_format_layout_archetype_examples`, `build_analysis_prompt`: 원형의 name·when·sequence를 번호 없는 예시로 프롬프트에 주입했다.
- `src/local_detail_page_ai/adapters.py:LocalProductAnalyzer.analyze`: 입력 이미지 해시로 선택된 원형 예시를 분석 프롬프트에 전달했다.
- `assets/references/detail-page-layouts.json`: 25종 레이아웃 원형 카탈로그를 추가했다.
- `tests/test_prompts.py`, `tests/test_layout_catalog.py`: 원형 로더·선택·프롬프트 주입 계약을 검증했다.

## 코드상 체크포인트

원형은 “선택 메뉴”가 아니라 상품별 구조 차이를 보여주는 예시로 제시됐다. 카탈로그가 없거나 깨지면 빈 목록으로 폴백하는 경로를 유지했고, `ProductAnalyzer` 프로토콜 시그니처는 바꾸지 않았다.

## 테스트 통과 수

- `tests/test_prompts.py`: 38 passed
- 전체 테스트: 293 passed

## 새 산출물

새 레이아웃 카탈로그 `assets/references/detail-page-layouts.json`이 추가됐다. 새 스크립트와 CSS는 없었다.
