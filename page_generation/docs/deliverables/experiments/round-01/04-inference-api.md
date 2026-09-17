# Round 01 · Inference API — validation 변경의 추론 영향

| 항목 | 값 |
| --- | --- |
| 차수 | 01 |
| 파일럿 디렉터리 | `generated/evaluation/pilot-20260910-102346` |
| 직전 차수 기준 | `generated/evaluation/pilot-20260909-224737` (baseline) |
| 이미지 재생성 | 예 |
| 기록 시각 | 2026-09-10 |

## 변경 없음

이 차수는 모델 호출 계약을 바꾸지 않고 `validation.py`의 후처리만 바꿨다.

- text provider는 `ddalcu/Qwen3.8-27B-MLX-Serve-4bit`, image provider는 `mlx-community/flux2-klein-9b-4bit`였다.
- 로컬 provider URL은 `http://127.0.0.1:11234`로 유지됐다.
- 시스템/유저 메시지 구조, 이미지 클라이언트의 endpoint·`mode`·`steps`·`strength` 계약은 바뀌지 않았다.
- 6건을 이미지 재생성했고 파일럿 소요 시간은 28.2분이었다.

## 호출 횟수·소요 시간 영향

`run_index.json` 기준 실행 케이스는 6건, 성공 6건이었다. validation의 충분한 계획 보존 분기는 모델 호출 횟수를 늘리지 않았고, 해당 실행의 총 소요 시간은 28.2분이었다.
