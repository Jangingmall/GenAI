# BE 팀 2차 요청 문서

- 작성일: 2026-09-18
- 대상: `Jangingmall/backend` develop(`6533a71`) ↔ `Jangingmall/GenAI` main(`6a4c2b4`)의 `page_generation`
- 근거: [재연동 테스트 기록](../runs/reintegration-test-2026-09-18.md)

이번 문서는 BE가 2026-09-17 요청을 반영한 뒤 2026-09-18에 다시 붙여 본 결과를 바탕으로 작성했습니다. 먼저 해결된 사항을 확인하고, 남은 계약·운영 결정을 요청드립니다.

> 테스트 환경은 GPU 없는 Ubuntu 사내 LAN에서 컨테이너로 실행했습니다. 텍스트 모델은 LAN으로 연결한 Mac MLX Qwen3.8-27B였습니다. 서버 GPU에서는 아직 한 번도 실행하지 않았습니다.

## 1. 먼저 — 해결된 것

| 항목 | BE 반영 내용 | 확인 근거 |
|---|---|---|
| **BE-1** HTTP/1.1 고정 | 두 클라이언트 모두 `.version(HttpClient.Version.HTTP_1_1)`을 사용합니다. | 재연동 기록의 BE 반영 표 |
| **BE-2** `@Async` 자기 호출 | `GenerationAsyncExecutor`를 별도 빈으로 분리했습니다. 응답이 `202` + `PROCESSING`으로 바뀌었습니다. | 이전의 `202` 안 `FAILED`와 달라진 응답 확인 |
| **BE-4** 재시도 | 재시도 로그에 `attempt=2`, `attempt=3`이 남고 최종 실패했습니다. | 재연동 로그 확인 |
| **BE-7** 설정 이름 | `AI_SGLANG_URL`·`AI_OLLAMA_URL`이 용도 기준의 `AI_CHAT_BOT_URL`·`AI_CONTENT_URL`로 바뀌었습니다. | 재연동 기록의 설정 확인 |
| 요청 경로·형식 | 우리 계약에 맞춰 `POST /internal/v1/ai/detail-page-jobs`, multipart(`metadata` + `product_image`), `X-AI-Internal-Token`, `Idempotency-Key`를 사용합니다. | 재연동 기록의 요청 확인 |
| 콜백 ACK 스키마 | `{generation_id, product_id, status, saved_at}`를 사용하고 `status`는 `SAVED`/`ALREADY_SAVED`입니다. | 재연동 기록의 ACK 확인 |
| 콜백 인증 | 콜백에 `Authorization: Bearer {BACKEND_AUTH_TOKEN}`이 필수입니다. | 재연동 기록의 인증 확인 |

덕분에 전 구간이 처음으로 이어졌습니다.

```text
FE 역할 → BE → AI 작업 접수(202) → 파이프라인 실행(DRAFT_READY)
        → 콜백 → BE 상태 COMPLETED
```

실측 결과도 작업 접수 `202 Accepted` 및 `jobId` 발급, 파이프라인 `DRAFT_READY`·progress `100`, 콜백 `200 SAVED`, BE 생성 상태 `COMPLETED`였습니다. 단, 이번 콜백은 **수동으로 보냈습니다.** 우리 서비스가 자동으로 콜백하는 부분은 아래 요청 사항처럼 아직 맞지 않습니다.

## 2. 남은 요청

### BE-9. 가이드의 콜백 경로가 실제 구현과 다릅니다

**증상**

BE의 `AI_로컬_연동_가이드` 3-3은 아래 두 경로를 안내합니다.

```text
POST /internal/generations/complete/multipart
POST /internal/generations/complete/json
```

하지만 실제 `AiCallbackController` 구현 경로는 다음입니다.

```text
POST /internal/generations/{generationId}/completion
```

**근거**

가이드 경로로 보내면 `NoResourceFoundException: No static resource internal/generations/complete/multipart`와 함께 **500**이 돌아왔습니다. 실제 구현 경로로 보내면 **200 `SAVED`**였습니다.

**요청**

어느 경로를 정본으로 사용할지 알려 주세요. 가이드의 고정 경로가 정본이면 우리 쪽은 설정만으로 맞출 수 있습니다. `/{generationId}/completion` 경로가 정본이면 우리 클라이언트가 `generationId`를 포함해 경로를 조립하도록 고치겠습니다.

### BE-10. 없는 경로에 404가 아니라 500이 돌아옵니다

**증상**

콜백 경로를 잘못 입력했을 때 경로 없음 응답이 404가 아니라 **500**으로 반환됩니다. 경로 오타와 서버 내부 오류를 구분하기 어렵습니다.

**근거**

재연동 기록에서 가이드 경로 요청이 `NoResourceFoundException`과 함께 500이 되었습니다. `GlobalExceptionHandler`가 `NoResourceFoundException`을 잡아 500으로 변환하는 동작이 원인으로 기록되어 있습니다.

**요청**

존재하지 않는 경로는 404로 보존해 주세요. 최소한 `NoResourceFoundException`을 500으로 변환하지 않도록 처리해 경로 오타를 HTTP 상태로 식별할 수 있게 해 주세요.

### BE-11. 콜백 시점을 정해 주세요

**증상**

우리 파이프라인은 `DRAFT_READY`에서 멈춥니다. 설계상 다음 단계는 장인의 **승인**이고, BE 전달은 승인 뒤에 일어납니다. 반면 BE는 작업 제출 뒤 콜백을 기다립니다. 이번 테스트에서는 BE가 10분간 `QUEUED`로 남았습니다.

**근거**

재연동 기록은 `DRAFT_READY` 이후 콜백이 자동으로 이어지지 않았고, 수동 콜백을 보낸 뒤에야 BE 상태가 `COMPLETED`가 되었다고 기록합니다. BE 가이드 3-3은 “생성 완료 후 콜백”이라고만 되어 있습니다.

**요청**

다음 중 어떤 계약을 사용할지 정해 주세요.

1. 초안이 `DRAFT_READY`가 되는 시점에 콜백합니다.
2. 장인 승인 뒤에 콜백합니다.

또한 승인을 누가 수행하는지와 승인 API를 함께 지정해 주세요. 결정에 따라 우리 파이프라인의 자동 콜백 시점을 맞추겠습니다.

### BE-12. 이미지 URL 수집을 확인해 주세요

**증상**

BE가 `images[0]` URL을 직접 내려받아 우리에게 multipart로 보냅니다. 리다이렉트하는 URL을 사용하면 이미지 검증이 실패했습니다.

**근거**

`picsum.photos`처럼 리다이렉트하는 URL을 주었을 때 **400 `Invalid product image`**가 났습니다. 리다이렉트하지 않는 직접 제공 JPEG URL에서는 정상 동작했습니다. 실제 S3 presigned URL의 동작은 아직 확인하지 않았습니다.

**요청**

실제 S3 presigned URL이 리다이렉트 없이 최종 이미지 바이트를 반환하는지 확인해 주세요. 리다이렉트가 발생할 수 있다면 BE의 다운로드 처리 또는 허용 URL 계약을 정해 주세요.

## 3. 우리가 고치는 것

`metadata` 키 표기를 BE가 읽는 **camelCase**로 맞추는 작업은 우리 쪽에서 진행합니다. BE에 수정을 요청하는 사항이 아닙니다.

재연동 실측에서 같은 경로에 snake_case metadata를 보내면 **500**, camelCase로 보내면 **200 `SAVED`**였습니다.

```text
우리 현재 표기: product_id, generation_id, job_id, request_id,
                idempotency_key, detail_page.react_document
BE가 읽는 표기: productId, generationId, jobId, requestId,
                idempotencyKey, detailPage.reactDocument
```

우리는 콜백 metadata 직렬화를 위 camelCase 계약에 맞추겠습니다.

## 4. 챗봇 (참고)

- `chat_bot/Dockerfile`은 **10.4GB** 이미지 빌드에 성공했지만 `USER` 지시가 없어 root로 실행되므로, Non-root 운영 기준을 챗봇 팀에서 확인해 주세요. 우리 상세페이지 AI 소관은 아닙니다.
