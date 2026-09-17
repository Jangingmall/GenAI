# Round 12 · 추론 API 영향 — 로컬 rembg 추가와 Flux 활용 장면 유지

| 항목 | 값 |
| --- | --- |
| 차수 | 12 |
| 파일럿 디렉터리 | `generated/attached/najeon-hero-030813`, `generated/attached/petal-rembg-000846`, `generated/cutout-compare/`, `generated/composite-check/{nacre,petals}` |
| 직전 차수 기준 | `generated/evaluation/full60-20260910-204433` (11차 되돌림 후 기준) |
| 이미지 재생성 | 예 (나전칠기·꽃잎 적용 결과와 합성 시도; 활용 장면 Flux 생성 유지) |
| 기록 시각 | 2026-09-14 |

## 1. 외부 모델 호출 계약

이번 차수에는 외부 모델 호출 모델과 엔드포인트 변경이 없었다.

| 항목 | 12차 상태 |
| --- | --- |
| 텍스트 모델 | `Qwen3.8-27B` 유지 |
| 이미지 모델 | `flux2-klein-9b` 유지 |
| 엔드포인트 | 변경 없음; 구체적인 URL은 확인 필요 |
| 활용 장면 경로 | Flux 생성 유지 |
| 상세 생성 경로 | detail-02~05는 합성 시도 범위 밖이며 기존 계약 유지 |

합성 시도 중에는 배경 prompt 버전만 `background-v4-jewelry-coverage`에서 `background-v5-front-facing-composite`로 바꾸었다. 이 시도는 반려되어 prompt v4로 되돌아갔다. 따라서 최종 모델·엔드포인트·활용 장면 prompt 계약에는 v5가 남아 있지 않다.

## 2. 추가된 로컬 추론 단계

rembg를 onnxruntime으로 로컬 추론하는 `RembgCutoutExtractor`가 추가되었다. 이는 Qwen 또는 Flux 서버 호출의 endpoint가 아니라 이미지 전처리용 로컬 단계다.

- rembg 모델은 `birefnet-general`이다.
- 첫 추론에서 `~/.u2net/birefnet-general.onnx` 캐시를 만들고, 캐시 크기는 973MB였다.
- 비교 때 2.0.83이 받은 `~/.rembg/models/birefnet-general/`의 930MiB 캐시는 사용하지 않았다.
- 세션은 지연 생성하고 한 번 만든 세션을 재사용했다.
- 최종 잠금은 rembg `2.0.69`, Pillow `11.3.0`, NumPy `2.5.3`, onnxruntime `1.29.0`이다.

## 3. 호출 횟수와 소요 시간

정본에는 케이스별 Qwen·Flux의 정확한 호출 횟수나 rembg 로컬 추론만의 소요 시간이 별도로 기록되어 있지 않다. 두 값은 확인 필요다.

합성 시도에서 생성된 대조 산출물의 측정 시간은 다음과 같다.

| 산출물 | 소요 시간 |
| --- | ---: |
| `generated/composite-check/nacre` | 322.13초 |
| `generated/composite-check/petals` | 267.83초 |

위 두 값은 반려된 합성 시도의 실측값이며, 최종 파이프라인의 전체 호출 시간이나 모델별 평균을 뜻하지 않는다.

## 4. 최종 추론 상태

최종 상태에서는 Qwen3.8-27B와 flux2-klein-9b 호출 계약을 유지하고, 활용 장면 Flux 생성을 유지했다. 합성 시도의 v5 배경 prompt는 되돌려져 v4가 유지된다. 추가된 추론 계약은 로컬 rembg·onnxruntime과 `~/.u2net` 모델 캐시이며, 외부 모델 endpoint는 그대로다.

