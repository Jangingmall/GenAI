# Round 03 · BE/FE Interface — 선택 블록의 계약 유지

| 항목 | 값 |
| --- | --- |
| 차수 | 03 |
| 파일럿 디렉터리 | `generated/evaluation/pilot-20260910-115722` |
| 직전 차수 기준 | `generated/evaluation/pilot-20260910-111715` |
| 이미지 재생성 | 예 |
| 기록 시각 | 2026-09-10 |

## 변경 없음

프롬프트가 블록을 생략할 수 있게 됐지만 BE·FE가 소비하는 계약은 바꾸지 않았다.

- 허용 `block_type` 13종과 `PageBlockVariant` 값은 유지됐다.
- `page_plan`의 block 수 안전 상한 14, hero 첫·closing 마지막, gallery `photo_ids` 계약은 유지됐다.
- `statement`가 생략되는 것은 허용된 선택 블록의 내용 변화이며 DTO 필드 삭제가 아니다.
- `react_document` 스키마와 `layout_id`는 변경되지 않아 하위 호환됐다.

## 영향

출력에 선택 블록이 빠질 수 있지만 기존 소비자는 같은 block object 구조와 허용 어휘를 받는다. 새 필드나 상태 전이는 추가되지 않았다.
