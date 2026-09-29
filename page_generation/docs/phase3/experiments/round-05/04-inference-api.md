# Round 05 · Inference API — 코드 선택 구성 프롬프트

| 항목 | 값 |
| --- | --- |
| 차수 | 05 |
| 파일럿 디렉터리 | `generated/evaluation/pilot-20260910-135605` |
| 직전 차수 기준 | `generated/evaluation/pilot-20260910-123917` |
| 이미지 재생성 | 예 |
| 기록 시각 | 2026-09-10 |

## 프롬프트·호출 구성 변화

어댑터가 이미지 해시로 원형 하나를 고르고, `build_analysis_prompt`에 확정 sequence를 전달했다. 분석 모델은 page_plan 구조를 선택하지 않고 지정 블록의 카피와 근거 기반 생략만 수행하도록 프롬프트가 바뀌었다.

## 이미지·provider 계약

- text provider: `ddalcu/Qwen3.8-27B-MLX-Serve-4bit`
- image provider: `mlx-community/flux2-klein-9b-4bit`
- provider URL: `http://127.0.0.1:11234`
- 이미지 client의 endpoint, `mode`, `steps`, `strength`와 외부 메시지 envelope은 변경하지 않았다.

## 호출 횟수·소요 시간 영향

6건을 실행했고 6건 모두 성공했다. 이미지를 재생성했으며 총 소요 시간은 26.6분이었다. 원형 선택은 분석 프롬프트 입력을 바꿨지만 provider 호출 수 계약은 바꾸지 않았다.
