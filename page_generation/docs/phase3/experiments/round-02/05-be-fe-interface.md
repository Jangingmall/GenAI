# Round 02 · BE/FE Interface — prompt-only 변경

| 항목 | 값 |
| --- | --- |
| 차수 | 02 |
| 파일럿 디렉터리 | `generated/evaluation/pilot-20260910-111715` |
| 직전 차수 기준 | `generated/evaluation/pilot-20260910-102346` |
| 이미지 재생성 | 예 |
| 기록 시각 | 2026-09-10 |

## 변경 없음

이 차수는 프롬프트만 바꾸고 BE·FE 인터페이스를 바꾸지 않았다.

- `page_plan`의 13종 `block_type` 어휘와 `PageBlockVariant` 허용값은 유지됐다.
- `ProductProfileDto`의 최대 14블록, hero 첫·closing 마지막, gallery `photo_ids` 계약은 유지됐다.
- `react_document` 스키마와 `layout_id` 필드는 변경되지 않았다.
- 하위 소비자는 기존 JSON 필드와 허용 어휘를 그대로 소비할 수 있다.

## 영향

계획의 순서가 달라질 수 있게 프롬프트를 조정했지만, BE·FE가 읽는 필드명·타입·상태 전이는 달라지지 않았다.
