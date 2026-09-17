# Round 03 · Inference API — 선택·생략 프롬프트 영향

| 항목 | 값 |
| --- | --- |
| 차수 | 03 |
| 파일럿 디렉터리 | `generated/evaluation/pilot-20260910-115722` |
| 직전 차수 기준 | `generated/evaluation/pilot-20260910-111715` |
| 이미지 재생성 | 예 |
| 기록 시각 | 2026-09-10 |

## 프롬프트 구성 변화

분석 프롬프트에 블록별 선택·생략 조건을 추가했다. `statement`는 creator-provided `howMade`가 있을 때만 포함하고, `usage_scene`·`palette`·`info_table` 등은 근거가 없으면 생략하도록 했다.

## 이미지·provider 계약

- text provider: `ddalcu/Qwen3.8-27B-MLX-Serve-4bit`
- image provider: `mlx-community/flux2-klein-9b-4bit`
- provider URL: `http://127.0.0.1:11234`
- 이미지 클라이언트 endpoint, `mode`, `steps`, `strength`와 외부 메시지 envelope은 변경하지 않았다.

## 호출 횟수·소요 시간 영향

6건을 실행했고 6건 모두 성공했다. 이미지를 재생성했으며 파일럿 소요 시간은 27.3분이었다. 프롬프트 조건 추가는 이미지 API 호출 파라미터나 provider를 바꾸지 않았다.
