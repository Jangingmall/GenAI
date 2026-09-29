# Round 05 · BE/FE Interface — 코드 결정 구성의 하위 호환

| 항목 | 값 |
| --- | --- |
| 차수 | 05 |
| 파일럿 디렉터리 | `generated/evaluation/pilot-20260910-135605` |
| 직전 차수 기준 | `generated/evaluation/pilot-20260910-123917` |
| 이미지 재생성 | 예 |
| 기록 시각 | 2026-09-10 |

## 변경 없음

코드가 page_plan의 구성과 순서를 결정했지만 BE·FE가 소비하는 응답 계약은 바꾸지 않았다.

- `page_plan`은 기존 13종 `block_type`, `section_id`, `eyebrow`, `title`, `body`, `variant` 필드를 사용했다.
- `PageBlockVariant` 허용값, gallery의 `photo_ids`, `react_document` 스키마, `layout_id` 필드는 유지됐다.
- DTO 최대 14블록과 hero 첫·closing 마지막 제약은 유지됐다. 근거 부족으로 블록을 생략하는 것은 기존 optional block의 유효한 결과다.
- 기존 BE·FE 소비자는 새 필드 없이 같은 구조를 읽으므로 하위 호환됐다.

## 영향

생성 결과의 block set과 order는 코드 선택에 따라 달라졌지만, 외부 계약의 vocabulary·schema·상태 전이는 달라지지 않았다.
