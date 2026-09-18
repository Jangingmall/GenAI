# 재연동 테스트 (BE 대응 이후) — 2026-09-18

> 이 문서는 2026-09-18 시점 기록이다. 이후 상태가 바뀌어도 이 문서는 고치지 않는다.

- 환경: Ubuntu 서버(사내 LAN, GPU 없음) · 전부 **컨테이너**로 실행
- 대상: `Jangingmall/GenAI` main(`6a4c2b4`) 의 `page_generation` · `Jangingmall/backend` develop(`6533a71`)
- 텍스트 모델: Mac 의 MLX `Qwen3.8-27B` 를 LAN 으로 연결
- 앞선 테스트와의 차이: **BE 가 우리 요청 사항을 반영한 뒤** 다시 붙였다.

## 결론 — 전 구간이 처음으로 이어졌다

```
FE 역할 → BE → AI 작업 접수(202) → 파이프라인 실행(DRAFT_READY)
        → 콜백 → BE 상태 COMPLETED
```

다만 **콜백은 수동으로 보냈다.** 우리 서비스가 자동으로 거는 부분은 아직 맞지 않는다(아래 남은 문제 참고).

## BE 가 반영한 것 — 확인됨

| 우리 요청 | 반영 | 확인 방법 |
| --- | --- | --- |
| **BE-1** HTTP/1.1 고정 | **됨** | 두 클라이언트 모두 `.version(HttpClient.Version.HTTP_1_1)` |
| **BE-2** `@Async` 자기 호출 | **됨** | `GenerationAsyncExecutor` 별도 빈으로 분리. 응답이 `202` + `PROCESSING` 으로 바뀌었다(이전에는 202 안에 `FAILED`) |
| **BE-4** 재시도 | **됨** | 로그에 `attempt=2`, `attempt=3` 후 최종 실패 |
| **BE-7** 설정 이름 | **됨** | `AI_SGLANG_URL`·`AI_OLLAMA_URL` → **`AI_CHAT_BOT_URL`·`AI_CONTENT_URL`**. 용도 기준으로 바뀌었다 |
| 요청 경로·형식 | **우리 계약으로 맞춰 옴** | `POST /internal/v1/ai/detail-page-jobs`, multipart(`metadata` + `product_image`), `X-AI-Internal-Token`, `Idempotency-Key` |
| 콜백 ACK 스키마 | **우리 스키마 그대로** | `{generation_id, product_id, status, saved_at}`, `status` 는 `SAVED`/`ALREADY_SAVED` |
| 인증 | 추가됨 | 콜백에 `Authorization: Bearer {BACKEND_AUTH_TOKEN}` 필수 |

**우리가 맞추기로 했던 A-1~A-6 중 상당수가 불필요해졌다.** BE 가 우리 경로와 형식으로 와 주었다.

## 실행 결과

| 단계 | 결과 |
| --- | --- |
| 이미지 빌드 3종 | 상세페이지 **4.99GB** · BE 619MB · **챗봇 10.4GB** (챗봇도 이번에 처음 빌드됨) |
| 컨테이너 기동 | 4개 정상. 상세페이지 `(healthy)`, `/health/ready` **200** |
| BE → AI 작업 접수 | **202 Accepted**, `jobId` 발급 |
| 파이프라인 | **DRAFT_READY, progress 100** |
| 콜백(수동, camelCase) | **200 `SAVED`** |
| BE 생성 상태 | **COMPLETED** |

## 남은 문제

### 1. 문서화된 콜백 경로가 존재하지 않는다

`AI_로컬_연동_가이드` 3-3 은 두 경로를 안내한다.

```
POST /internal/generations/complete/multipart
POST /internal/generations/complete/json
```

**둘 다 없다.** 실제 구현은 `AiCallbackController` 의 `POST /internal/generations/{generationId}/completion` 이다.

```
NoResourceFoundException: No static resource internal/generations/complete/multipart
```

가이드 경로로 보내면 **500** 이 돌아온다. 실제 경로로 보내면 200 `SAVED` 다. **어느 쪽이 정본인지 확인이 필요하다.** BE 문서와 코드가 어긋난 사례가 이번이 두 번째다.

곁들여, 없는 경로에 404 가 아니라 **500** 이 나온다. `GlobalExceptionHandler` 가 `NoResourceFoundException` 을 잡아 500 으로 바꾸기 때문이다. 경로 오타를 찾기 어렵게 만든다.

### 2. metadata 키 표기가 다르다 — 우리가 맞춰야 한다

BE 는 `metadata.productId`, `metadata.detailPage.reactDocument` 로 **camelCase** 를 읽는다. 우리가 보내는 metadata 는 **snake_case** 다.

```
우리: product_id, generation_id, job_id, request_id, idempotency_key, detail_page.react_document
BE  : productId,  generationId,  jobId,  requestId,  idempotencyKey,  detailPage.reactDocument
```

같은 경로에 snake_case 로 보내면 **500**, camelCase 로 보내면 **200 `SAVED`** 였다. 우리 쪽 직렬화를 맞춰야 한다.

### 3. 우리가 콜백을 자동으로 걸지 않는다

파이프라인은 `DRAFT_READY` 에서 멈춘다. 우리 설계상 그다음은 **승인(approve)** 단계이고, 콜백(BE 전달)은 승인 뒤에 일어난다. 그런데 BE 는 작업 제출 후 **콜백을 기다린다.** 이번 테스트에서 BE 가 10분간 `QUEUED` 로 남아 있었던 이유다.

**누가 승인하는지, 초안 시점에 콜백할지 승인 뒤에 할지** 정해야 한다. BE 가이드 3-3 은 "생성 완료 후 콜백" 이라고만 되어 있다.

### 4. 콜백 URL 은 이제 설정으로 해결된다

우리 `BACKEND_URL` 은 경로를 조립하지 못하는 단일 주소다(AI-D1). 실제 BE 경로가 `/{generationId}/completion` 이면 **건마다 경로가 달라 조립이 필요하다.** 가이드의 고정 경로(`/complete/multipart`)가 정본이면 설정만으로 해결된다. 위 1번 확인에 달려 있다.

### 5. BE 의 이미지 수집

BE 는 `images[0]` URL 을 직접 내려받아 multipart 로 우리에게 보낸다. 리다이렉트하는 URL(`picsum.photos`)을 주면 **400 `Invalid product image`** 가 났다. 네트워크 안에서 직접 제공한 JPEG 로는 정상 동작했다. 실제 S3 presigned URL 에서 어떻게 동작하는지는 확인하지 않았다.

## 챗봇

`chat_bot/Dockerfile` 이 올라와 **이미지 빌드에 성공했다(10.4GB)**. 다만 이번 테스트에서 기동은 하지 않았다.

Dockerfile 머리말에 따르면 챗봇은 **Ollama 에서 SGLang(gemma4)으로 옮겼고**, 임베딩 모델(BGE-M3)은 **인프라가 S3 → 볼륨으로 마운트**해 주는 방식이다. 우리 상세페이지와 같은 방식이다.

- `EXPOSE 8000`, `CMD uvicorn app.main:app --port 8000` — 인프라 요구와 맞는다
- **`USER` 지시가 없어 root 로 실행된다.** 인프라 운영 기준의 "가능하면 Non-root" 항목에 걸린다
- PostgreSQL + pgvector 가 여전히 필요하다

## 재현

```bash
docker network create it2
docker run -d --name rd2 --network it2 redis:8
docker run -d --name pg2 --network it2 -e POSTGRES_DB=midam -e POSTGRES_USER=midam \
  -e POSTGRES_PASSWORD=midam pgvector/pgvector:pg17

docker build -f page_generation/deploy/Dockerfile -t dp-ai:v2 page_generation
docker run -d --name dp2 --network it2 -p 8002:8000 \
  -e LOCAL_TEXT_PROVIDER=mlx -e LOCAL_TEXT_URL=http://<모델서버>:11234 \
  -e LOCAL_IMAGE_PROVIDER=none -e AI_INTERNAL_AUTH_TOKEN=<토큰> dp-ai:v2

cd backend && docker build --target local -t be:v2 .
docker run -d --name be2 --network it2 -p 8080:8080 \
  -e SPRING_PROFILES_ACTIVE=local -e SPRING_DATA_REDIS_HOST=rd2 \
  -e AI_CHAT_BOT_URL=http://cb2:8000 -e AI_CONTENT_URL=http://dp2:8000 \
  -e AI_INTERNAL_AUTH_TOKEN=<토큰> -e BACKEND_AUTH_TOKEN=<토큰> be:v2
```

이미지 URL 은 네트워크 안에서 제공해야 한다(리다이렉트 없는 직접 URL).
