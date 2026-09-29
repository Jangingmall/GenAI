# Round 13 · 추론 API 영향 — 모델·엔드포인트 변경 없음, 프롬프트 분기만 달라짐

| 항목 | 값 |
| --- | --- |
| 차수 | 13 |
| 파일럿 디렉터리 | `generated/attached/fan-set-usage-scene` |
| 직전 차수 기준 | `generated/evaluation/full60-v2-20260911-110752` (60건 실측) |
| 이미지 재생성 | 예 (부채 세트 1건, FLUX 생성컷 5장) |
| 기록 시각 | 2026-09-18 |

## 1. 외부 모델 호출 계약

이번 차수에는 모델과 엔드포인트 변경이 없다.

| 항목 | 13차 상태 |
| --- | --- |
| 텍스트 모델 | `Qwen3.8-27B` 유지 (`ddalcu/Qwen3.8-27B-MLX-Serve-4bit`) |
| 이미지 모델 | `flux2-klein-9b` 유지 (`mlx-community/flux2-klein-9b-4bit`) |
| 호출 횟수 | 상품 1건당 분석 1회 유지 (레이아웃 선택을 위한 추가 호출 없음) |
| 서비스 엔드포인트 | 변경 없음 |

레이아웃 시퀀스를 코드가 확정하는 2단계 호출 설계를 검토했으나 **채택하지 않았다.**
모델이 이미 지시를 따르고 있어 필요가 없었고, 호출이 2배가 되는 비용만 남았을 것이다.
근거는 [`03-experiment-report.md`](03-experiment-report.md) 2절에 있다.

## 2. 프롬프트 입력이 달라지는 지점

`build_analysis_prompt` 에 `image_generation_enabled` 인자가 추가됐다.
기본값은 `False` 이므로 기존 호출부는 그대로 동작한다.

| 값 | 후보 원형 | 프롬프트 |
| --- | --- | --- |
| `False` | 카탈로그 전체에서 표본 4종 | 기존과 동일 |
| `True` | `usage_scene` 을 가진 원형에서만 표본 4종 | 생성 라이프스타일 컷 안내 문단이 덧붙는다 |

플래그는 `factory.py` 에서 다음 조건으로 계산된다.

```python
image_generation_enabled = (
    local_image_provider != "none"
    and background_provider != "none"
    and max_generated_photos > 0
)
```

즉 **이미지 생성을 끈 배포에서는 레이아웃 선택이 13차 이전과 완전히 동일하다.**
회귀 위험은 생성을 켠 경로에만 있다.

## 3. 로컬 실행 절차 — MLX 2단계 교체

Mac 에서는 27B 텍스트 모델(18.2GB)과 FLUX(8.9GB)를 동시에 올릴 수 없다. 두 모델을
**같은 포트 11234 에 번갈아** 올려 돌렸다.

| 단계 | 올리는 모델 | 수행 |
| --- | --- | --- |
| 1 | `Qwen3.8-27B` | 작업 접수 → 분석 → `DRAFT_READY` |
| 2 | `flux2-klein-9b` | 승인·렌더 → 사진 생성 → 최종 산출물 |

사진 생성은 분석 단계가 아니라 **렌더 단계**에서 일어난다. 끝나면 텍스트 모델로
되돌려 놓는다.

## 4. 내부 엔드포인트에 대한 관찰 (변경 아님)

렌더 엔드포인트 `POST /internal/v1/ai/detail-page-renders` 는 JSON 본문이 아니라
**multipart 의 `metadata` 폼 필드**를 받는다. BE 계약에 맞추면서 바뀐 것이며 이번
차수의 변경은 아니다. 이전 차수 기록의 JSON 본문 예시는 현재 코드와 맞지 않는다.

```
metadata      = {product_id, idempotency_key, request_id, draft_id, draft}  (폼 필드)
product_image = 원본 이미지 (선택)
```

JSON 으로 보내면 `422` 와 함께 `{"loc":["body","metadata"],"msg":"Field required"}`
가 돌아온다.
