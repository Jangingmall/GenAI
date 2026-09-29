# Round 02 · Inference API — 프롬프트 순서 계약 변경

| 항목 | 값 |
| --- | --- |
| 차수 | 02 |
| 파일럿 디렉터리 | `generated/evaluation/pilot-20260910-111715` |
| 직전 차수 기준 | `generated/evaluation/pilot-20260910-102346` |
| 이미지 재생성 | 예 |
| 기록 시각 | 2026-09-10 |

## 프롬프트 구성 변화

`src/detail_page_ai/prompts.py:build_analysis_prompt`가 생성하는 분석 프롬프트의 page_plan 지시를 바꿨다. Copy Map은 순서가 아닌 참조표가 됐고, page_plan 하한은 8이며, 순차 레시피는 제거됐다. 시스템/유저 메시지의 외부 envelope과 provider 설정은 바꾸지 않았다.

## 이미지·provider 계약

- text provider: `ddalcu/Qwen3.8-27B-MLX-Serve-4bit`
- image provider: `mlx-community/flux2-klein-9b-4bit`
- provider URL: `http://127.0.0.1:11234`
- 이미지 클라이언트 endpoint, `mode`, `steps`, `strength`는 이 차수에서 바뀌지 않았다.

## 호출 횟수·소요 시간 영향

`run_index.json` 기준 6건을 실행했고 6건 모두 성공했다. 이미지 재생성은 수행됐으며 총 소요 시간은 27.8분이었다.
