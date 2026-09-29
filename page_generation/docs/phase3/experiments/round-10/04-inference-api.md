# Round 10 · 추론 API 영향 — 라벨 계약 수정과 60건 전체 실행

| 항목 | 값 |
| --- | --- |
| 차수 | 10 |
| 파일럿 디렉터리 | `generated/evaluation/full60-20260910-204433` |
| 직전 차수 기준 | `generated/evaluation/pilot-20260910-164008` (9차) |
| 이미지 재생성 | 예 (케이스별 Flux 이미지 생성 60건, 3시간 52분) |
| 기록 시각 | 2026-09-11 |

## 변경 없음

10차의 `참고용` 라벨 수정은 모델 prompt나 모델 응답 DTO가 아니라 사진 metadata를 React 문서와 HTML로 전달하는 downstream 계약 변경이었다. 텍스트·이미지 모델의 시스템/유저 메시지 의미와 모델 호출 자체는 변경하지 않았다. 평가 러너의 실행 범위와 기록 메타데이터는 확장했지만, 추론 provider는 `mlx`로 유지됐다.

- 텍스트 모델: `ddalcu/Qwen3.8-27B-MLX-Serve-4bit`
- 이미지 모델: `mlx-community/flux2-klein-9b-4bit`
- 실제 실행 메타데이터: `image_provider=mlx`, `image_model` 및 `configured_image_model`은 Flux 모델, `image_generated_cases=60`
- API endpoint: `text_url`과 `image_url`은 `http://127.0.0.1:11234`로 기록됐다.

## 프롬프트·시스템/유저 메시지·이미지 클라이언트

- 라벨 수정으로 prompt 구성, 시스템/유저 메시지 구조, 모델 응답 형식은 바뀌지 않았다.
- `steps`, `mode`의 10차별 변경 수치는 정본에 기재되지 않아 확인 필요로 남겼다.
- 이미지 생성은 60건 모두 케이스별 `image_model=mlx-community/flux2-klein-9b-4bit`로 기록됐다.
- runner에는 `--all`, `--limit`, `--resume`가 추가됐지만 이 옵션들은 케이스 선택·재개·기록 제어이며 모델 prompt 계약은 아니었다.

## 호출 횟수·소요 시간 영향

- 60개 케이스가 모두 성공했고 `image_generated_cases`는 60이었다.
- 60건 전체 실행에 총 **3시간 52분**, 케이스당 **227초**가 기록됐다.
- 정본은 케이스별 내부 text request/image request의 정확한 횟수를 분리해 기록하지 않았으므로 개별 호출 수는 확인 필요로 남겼다.

## 하위 호환성

추론 API의 prompt·provider·모델 응답 계약은 9차의 호출 경로와 같은 상태로 유지됐다. 10차의 추가 keyword 인자는 추론 API가 아니라 `build_react_document_from_draft()`의 문서 빌더 인자였고, 기존 호출자가 이를 생략할 수 있었다.

