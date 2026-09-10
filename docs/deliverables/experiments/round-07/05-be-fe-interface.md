# Round 07 · BE/FE 인터페이스 영향 — 원형 variant 전달 경로 개방

| 항목 | 값 |
| --- | --- |
| 차수 | 07 |
| 파일럿 디렉터리 | `generated/evaluation/pilot-20260910-153208` |
| 직전 차수 기준 | `generated/evaluation/pilot-20260910-145007` (6차) |
| 이미지 재생성 | 아니오 (--image-provider none, AI 이미지 생성 없음) |
| 기록 시각 | 2026-09-10 |

## 1. 변경 없음
이 차수는 프롬프트 내부에서 모델에게 전달하는 지시 텍스트를 개선하고 고속 구조 측정을 위해 AI 이미지 생성을 비활성화(`--image-provider none`)한 차수로, BE와 FE 간의 통신 규약이나 데이터 스키마 자체를 건드리지 않았다. 직전 차수(Round 06)의 인터페이스 계약을 그대로 유지한다.

## 2. 유지된 계약의 핵심 요약
- **`page_plan` 스키마**: 각 블록의 `section_id`, `block_type`, `variant`, `photo_id` 필드 구조 유지.
- **`PageBlockVariant` 8종**: `paper`, `light`, `sand`, `dark`, `image-left`, `image-right`, `full-bleed`, `compact` 열거형 유지.
- **FE 렌더링 계약**: `web/detail_page.css`에 선언된 4종 신규 variant 스타일 및 기존 스타일 계약 그대로 유지.
- **실제 전달 페이로드**: 8종의 variant가 모델 출력 결과에 골고루 실려 FE 렌더러로 전달됨 (`sand` 5회, `compact` 5회 등).
