# BE ↔ AI 연동 합의 필요 사항 — 2026-09-17

- 범위: BE·AI·챗봇이 함께 정해야 하는 항목
- 근거: [`../../internal/be-request-2026-09-17.md`](../../internal/be-request-2026-09-17.md), [`../../internal/be-ai-integration-negotiation.md`](../../internal/be-ai-integration-negotiation.md)
- 시점 기록: [`three-service-integration-test-2026-09-17.md`](../runs/three-service-integration-test-2026-09-17.md), [`container-integration-test-2026-09-17.md`](../runs/container-integration-test-2026-09-17.md)

> **중요:** 상세페이지 AI는 아직 **GPU에서 한 번도 실행되지 않았습니다.** 서버 GPU 실측이 필요한 수치는 확정값으로 쓰지 않습니다.

## D-1. `POST /ai/products`는 무엇을 반환해야 합니까 (R-12)

`GenerationService.java:77-89`는 `/ai/products`의 **동기 응답 본문을 완성된 react_document로 간주**하고 검증 없이 저장합니다.

```java
String reactDocumentJson = aiContentClient.requestGeneration(...);
generation.complete(reactDocumentJson);
contentService.storeReactDocument(new ContentCommand.StoreReactDocument(..., reactDocumentJson, ...));
```

그런데 같은 BE에 **콜백 경로도 있습니다**(`AiCallbackRequest.java:10`). 완료 처리 경로가 둘이고 실제로 도는 것은 동기 경로입니다.

**어느 쪽으로 갈지 정해 주세요.**

| 안 | BE가 할 일 | AI가 할 일 |
| --- | --- | --- |
| **가. 동기 유지** | 없음 | `/ai/products` 응답으로 **react_document를 직접 반환**. 수 분간 블로킹됩니다 |
| **나. 비동기 + 콜백** (권장) | R-11 수정 후 콜백 경로 사용 | 즉시 202 반환, 완료 시 `POST /internal/generations/{id}/complete` 호출 |

> **지금 상태에서는 위험합니다.** 저희가 접수 응답(`{"job_id":...}`)을 반환하면 BE는 그것을 **react_document로 저장**합니다. 오류 없이 잘못된 데이터가 들어갑니다.
>
> 처리 시간(초안까지 160초, 이미지 생성 포함 시 더 김)과 BE의 `AI_TIMEOUT_SECONDS` 기본 300초를 함께 고려하면 **나 안을 권합니다.**

## D-2. 생성 이미지를 어떻게 넘길지 (C-1, C-2)

AI 팀 결정: 생성합니다. 상세페이지는 대표 컷·패키지샷·디테일·활용 장면을 필요로 하는데 장인이 그만큼 올리지 않는 경우가 많습니다. 그래서 **제공 사진을 우선 쓰되 모자란 만큼 채우는** 방식입니다. 장인이 올린 사진은 한 장도 버리지 않습니다.

생성 컷은 `product_generated=true`와 `asset_mode`(`generated_scene` / `generated_view`)로 구분해 전달합니다. 생성 장수는 설정(`MAX_GENERATED_PHOTOS`, 기본 5)으로 조절되며, **`0`으로 두면 생성을 전혀 하지 않습니다.**

생성 이미지를 넘길 방법을 정해 주세요. 셋 중 하나입니다.

1. **BE가 이미지 업로드 API를 열고** AI가 그리로 올린 뒤 받은 `imageId`를 `reactDocument`에 심습니다.
2. **AI가 S3에 직접 올리고** URL을 심습니다. 현재 AI는 AWS SDK 의존성이 없어 추가 작업이 필요합니다.
3. **콜백 본문을 확장해** 이미지를 함께 받습니다.

**저희는 ①을 권합니다** — 이미지 저장·CDN은 이미 BE 책임이고(계약서 5-5), AI에 S3 권한을 새로 주지 않아도 됩니다.

BE 팀은 계약서 5-4를 현재 동작에 맞게 고칠지, 아니면 생성을 끄는 쪽(`MAX_GENERATED_PHOTOS=0`)으로 갈지 회신해 주세요. 생성을 유지한다면 위 전달 방식을 먼저 정해야 합니다.

## D-3. 양방향 내부 호출 인증 (R-8, C-4)

AI의 `/internal/v1/ai/*`는 `X-AI-Internal-Token`을 요구합니다(없으면 401). BE 클라이언트는 인증 헤더를 보내지 않습니다. 반대로 BE의 `/internal/generations/{id}/complete`도 인증 없이 열려 있었습니다. **양방향 내부 호출 인증을 어떻게 할지** 정해야 합니다. 토큰 발급 주체도 함께 정해 주세요.

| 방향 | 현재 | 서버에서 필요한 것 |
| --- | --- | --- |
| BE → AI | 인증 헤더 없음 | AI의 `/internal/v1/ai/*`는 `X-AI-Internal-Token`을 요구합니다. BE 클라이언트가 이 헤더를 보내야 합니다 |
| AI → BE | `/internal/generations/{id}/complete`가 인증 없이 열려 있음 | 최소한 내부 전용으로 제한하거나 토큰 검증을 붙여 주세요 |

토큰 값은 양 팀 시크릿으로 주입합니다. **발급 주체만 정해 주시면** 저희가 맞추겠습니다.

## D-4. `POST /ai/products`의 경로 의미 (R-3, C-3, 결정 2-1)

같은 경로를 세 곳이 다르게 씁니다.

| 주체 | `POST /ai/products`의 의미 | 본문 |
| --- | --- | --- |
| BE `RestAiContentClient.java:54` | **상세페이지 생성 요청** | `{generationId, productId, images[], productName, howMade, careTips}` |
| `GenAI/chat_bot` `app/main.py:112` | **추천 색인용 상품 upsert** | `{artisan, product}` |
| BE 계약서 5-3 | 상품 게시 시점 **동기화** | `{artisan, product}` |

여기서 두 가지 문제가 나옵니다.

1. **BE는 상품 동기화를 `AI_OLLAMA_URL`(= 상세페이지 서버)로 보냅니다**(`RestAiContentClient.java:64,78,92`). 그런데 그 데이터가 실제로 필요한 곳은 추천 색인을 가진 챗봇입니다.
2. **챗봇에는 `/ai/products/sync`가 없습니다.** 챗봇은 upsert를 `POST /ai/products`로 받습니다. BE가 부르는 `/ai/products/sync`와 경로가 다릅니다.

**제안**: 상품 동기화 3종(`sync`, `PUT`, `DELETE`)은 **챗봇 서비스(`AI_SGLANG_URL`)로 보내고**, 상세페이지 생성만 `AI_OLLAMA_URL`로 보내 주세요. 경로 이름은 세 팀이 한 번에 맞추는 편이 낫습니다. **챗봇 팀도 이 결정에 참여해야 합니다.** 저희는 어느 쪽으로 정하든 따르겠습니다.

## D-5. 처리 시간과 타임아웃 (C-5, 9-5)

BE는 `AI_TIMEOUT_SECONDS` 기본 300초입니다.

- 상세페이지 1건 생성은 **로컬 Apple Silicon 기준 평균 226초**였습니다(이미지 생성 포함).
- 서버 GPU 실측치는 **아직 없습니다**.
- 장인이 올린 사진이 적어 생성 컷이 많아지면 300초를 넘길 수 있습니다.

**요청**: 생성 요청은 **즉시 접수(202)하고 완료 시 콜백**받는 구조로 가 주세요. 계약서 5-1의 비동기 설계와도 맞고, R-4에서 말씀드린 "202 안에 FAILED" 문제도 같이 해소됩니다. 지금처럼 동기로 호출하면 서버에서는 타임아웃으로 실패합니다.

### 참고 — 챗봇 팀 항목 (R-13)

챗봇(`Jangingmall/GenAI/chat_bot/`)에는 Dockerfile이 없으므로 챗봇 팀에서 확인할 항목입니다.

---

## 주체별 문서

- [BE 인계 목록](be-handoff-2026-09-17.md)
- [AI 작업 목록](ai-worklist-2026-09-17.md)
