# 상세페이지 파이프라인 동작 확인 — 2026-09-17

> 이 문서는 2026-09-17 시점 기록이다. 이후 상태가 바뀌어도 이 문서는 고치지 않는다.

- 목적: BE 가 보내는 것과 같은 내용으로 상세페이지 로직이 실제로 도는지 확인
- 코드: `3e6f79a` (사진 배정 변경 `07ce5da`·생성 상한 `070d8c2` 반영 이후 첫 종단 실행)
- 모델: **`ddalcu/Qwen3.8-27B-MLX-Serve-4bit`** (MLX Serve `127.0.0.1:11234`, 상주 18.2GB) — 이 프로젝트의 텍스트 모델
- 이미지 생성: 끔 (`LOCAL_IMAGE_PROVIDER=none`)

## 결과 — 끝까지 돈다

| 단계 | 결과 |
| --- | ---: |
| 작업 접수 `POST /internal/v1/ai/detail-page-jobs` | **202 QUEUED** |
| 분석 → 초안 | **DRAFT_READY** · 약 100초 |
| 승인·렌더 `POST /internal/v1/ai/detail-page-renders` | **200** · 약 29초 |
| 최종 산출물 | PNG **774 × 3663** (1,599 KB), 섹션 이미지 8장, 사진 8장 |

### 사진 구성 — 제공 사진 우선 배정이 실제로 동작한다

사진 2장을 넣고 이미지 생성을 끈 상태에서 나온 결과다.

| photo_id | asset_mode | fidelity_status | product_generated |
| --- | --- | --- | --- |
| `hero` | `source_original` | VERIFIED | False |
| `packshot` | `source` | VERIFIED | False |
| `detail` | `source_crop` | VERIFIED | False |
| `lifestyle` | `source_composite` | VERIFIED | False |
| `detail-02` ~ `detail-05` | `source_crop` | VERIFIED | False |

**8장 전부 제공 사진에서 나왔고 생성 자산은 0장이다.** `hero` 는 원본 픽셀을 그대로 보존(`source_original`)했다.

### 생성된 내용

`layout_id` 는 `editorial-split` 이 선택됐고, BE 가 보낸 `making_method`·`care_guide` 가 카피에 반영됐다.

## 입력을 맞춘 2차 실행 — 이미지 근거가 실제로 작동한다

1차 실행은 **제 입력이 어긋나 있었다.** 사진은 직물인데 힌트는 "청자 다완"으로 넣었고, 모델은 힌트를 따라 도자기 카피를 만들면서 특징에 `evidence: image-visible` 을 붙였다. 사진에 없는 것을 이미지 근거로 표시한 셈이다.

입력을 맞춰(나전칠기 보석함 사진 + 나전칠기 힌트) 다시 돌린 결과는 달랐다.

```
summary   나전칠기 보석함은 옻칠한 목함에 전복 자개를 오려 붙이고 ... 만든 다단 서랍형 제품입니다.
keywords  ['나전칠기','보석함','자개','옻칠','다단 서랍','전통 공예','목함']
특징      다단 서랍 구조   evidence=image-visible conf=0.95
          자개 무늬 표면   evidence=image-visible conf=0.90
          옻칠 광택 마감   evidence=image-visible conf=0.85
```

**"다단 서랍 구조" 는 힌트에 없던 정보다.** 사진을 보고 얻은 것이므로 비전 분석이 실제로 동작한다.

## 남은 관찰

- **힌트와 사진이 어긋나면 힌트가 이긴다.** 1차 실행에서 모델은 사진에 없는 특징을 `image-visible` 로 표시했다. 잘못된 입력이 원인이지만, BE 가 보내는 `productName`·`howMade` 가 사진과 다를 때 같은 일이 일어난다. 사실성 게이트가 이 경우를 잡는지는 별도 확인이 필요하다.
- `BACKEND_URL` 미설정으로 최종 상태가 `COMPLETED_WITH_BACKEND_PENDING` 이었다. 산출물은 정상 생성됐고 BE 전달만 보류된 상태다(`warning: BACKEND_URL is not configured`).
- 여기서 확인한 것은 **우리 엔드포인트로 직접 넣었을 때**다. BE 가 실제로 호출하는 `POST /ai/products` 는 아직 없다(협의 문서 A-1).

## 재현

```bash
"/Applications/MLX Core.app/Contents/MacOS/mlx-serve" serve \
  --model ~/.mlx-serve/models/ddalcu/Qwen3.8-27B-MLX-Serve-4bit --host 127.0.0.1 --port 11234

PYTHONPATH=src LOCAL_TEXT_PROVIDER=mlx LOCAL_TEXT_URL=http://127.0.0.1:11234 \
  LOCAL_TEXT_MODEL=ddalcu/Qwen3.8-27B-MLX-Serve-4bit LOCAL_IMAGE_PROVIDER=none \
  AI_INTERNAL_AUTH_TOKEN=<토큰> .venv/bin/python -m uvicorn detail_page_ai.app:app --port 8002

curl -X POST localhost:8002/internal/v1/ai/detail-page-jobs -H "X-AI-Internal-Token: <토큰>" \
  -F "product_image=@assets/samples/najeon-box.jpeg;type=image/jpeg" \
  -F 'metadata={"product_id":"2","idempotency_key":"k","user_hints":{"product_name":"나전칠기 보석함","making_method":"...","care_guide":"..."}}'
```

`user_hints` 의 필드 이름은 `product_name` · `making_method` · `care_guide` 다. BE 의 `productName` · `howMade` · `careTips` 와 이름이 다르므로 어댑터에서 매핑해야 한다.
