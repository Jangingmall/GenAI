# Round 08 · 추론 API 영향 — 카탈로그와 합격 기준을 함께 수정

| 항목 | 값 |
| --- | --- |
| 차수 | 08 |
| 파일럿 디렉터리 | `generated/evaluation/pilot-20260910-161310` |
| 직전 차수 기준 | `generated/evaluation/pilot-20260910-153208` (7차) |
| 이미지 재생성 | 아니오 (--image-provider none, AI 이미지 생성 없음) |
| 기록 시각 | 2026-09-10 |

## 1. 변경 없음
이 차수는 `assets/references/detail-page-layouts.json`의 카탈로그 데이터셋과 `scripts/check_plan_diversity.py`의 검증 스크립트를 개정하고, 고속 구조 측정을 위해 `--image-provider none` 플래그로 AI 이미지 생성을 비활성화한 차수다. 모델 추론 API 호출 계약 및 프롬프트 템플릿의 변경은 없었다. 직전 차수(Round 07)의 API 호출 계약을 그대로 유지한다.

## 2. 유지된 계약 및 실행 메타데이터 요약
- **프롬프트 구성**: 선택된 단일 원형의 블록 시퀀스와 variant를 주입하는 프롬프트 유지.
- **모델 파라미터**: text `ddalcu/Qwen3.8-27B-MLX-Serve-4bit` 사용.
- **이미지 생성 비활성화**: `--image-provider none`으로 케이스별 `image_model: none`. 케이스당 4장 또는 8장 남은 사진은 전부 `product_generated: false`인 원본 파생 컷임.
- **호출 횟수 및 소요 시간**: 6건 성공, 총 11.7분 소요.
- **메타데이터 주의**: `run_index.json` 최상위 `image_model`은 설정값(flux2)으로 표기되나 실제 케이스별 `image_model`은 `none`이다.
