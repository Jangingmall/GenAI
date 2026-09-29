# Round 04 · Inference API — 원형 예시 프롬프트 영향

| 항목 | 값 |
| --- | --- |
| 차수 | 04 |
| 파일럿 디렉터리 | `generated/evaluation/pilot-20260910-123917` |
| 직전 차수 기준 | `generated/evaluation/pilot-20260910-115722` |
| 이미지 재생성 | 예 |
| 기록 시각 | 2026-09-10 |

## 프롬프트 구성 변화

분석 프롬프트에 카탈로그 원형의 name·when·sequence 예시를 추가했고, 어댑터가 이미지 해시 기반 예시를 전달했다. 예시는 모델 분석 입력을 늘렸지만 외부 추론 endpoint나 메시지 envelope은 바꾸지 않았다.

## 이미지·provider 계약

- text provider: `ddalcu/Qwen3.8-27B-MLX-Serve-4bit`
- image provider: `mlx-community/flux2-klein-9b-4bit`
- provider URL: `http://127.0.0.1:11234`
- 이미지 클라이언트 endpoint, `mode`, `steps`, `strength`는 변경하지 않았다.

## 호출 횟수·소요 시간 영향

6건을 실행했고 6건 모두 성공했다. 이미지를 재생성했으며 소요 시간은 27.1분이었다. 원형 카탈로그 로딩과 프롬프트 주입 외에 provider 호출 횟수 계약을 바꾸지 않았다.
