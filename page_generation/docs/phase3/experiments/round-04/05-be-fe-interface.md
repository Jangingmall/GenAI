# Round 04 · BE/FE Interface — 원형 내부 힌트와 외부 계약

| 항목 | 값 |
| --- | --- |
| 차수 | 04 |
| 파일럿 디렉터리 | `generated/evaluation/pilot-20260910-123917` |
| 직전 차수 기준 | `generated/evaluation/pilot-20260910-115722` |
| 이미지 재생성 | 예 |
| 기록 시각 | 2026-09-10 |

## 변경 없음

레이아웃 카탈로그와 `layout_id` 힌트를 분석 내부에 추가했지만 BE·FE 계약은 변경하지 않았다.

- 외부 `page_plan`은 기존 13종 `block_type`, `PageBlockVariant`, block object 필드를 사용했다.
- `react_document` 스키마, gallery `photo_ids`, hero/closing 위치 제약, DTO 최대 14블록은 유지됐다.
- 카탈로그의 `layout_id`는 backward-compatible style hint이며 page_plan의 새 응답 필드가 아니다.
- `ProductAnalyzer` 프로토콜 시그니처와 기존 소비자 계약은 하위 호환됐다.

## 영향

원형 예시는 모델 입력에만 존재했고 FE 렌더러가 새 카탈로그 파일을 직접 소비하지 않았다. 외부 응답에 새 필드나 허용 어휘가 추가되지 않았다.
