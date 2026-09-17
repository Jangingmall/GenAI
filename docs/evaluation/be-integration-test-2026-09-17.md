# BE 연동 테스트 — 2026-09-17

> 이 문서는 2026-09-17 시점 기록이다. 이후 상태가 바뀌어도 이 문서는 고치지 않는다.

- 대상: `Jangingmall/backend` (public, `1e04949`, 2026-09-17 clone) ↔ 이 저장소 `084a804`
- 방법: BE 저장소를 받아 AI 연동 코드를 읽고, 실제로 두 방향의 HTTP 호출을 실행해 응답을 기록했다.
- 결론: **현재 두 시스템은 어느 방향으로도 연결되지 않는다.** 호출 6건 전부 실패했다.

## 실행 결과

### 방향 1 — BE → AI

AI 서비스를 `127.0.0.1:8099` 에 띄우고, BE 의 `RestAiContentClient` 가 실제로 보내는 요청을 그대로 재현했다.

| BE 가 호출하는 것 | 근거 | 응답 |
| --- | --- | ---: |
| `POST /ai/products` | `RestAiContentClient.java:53` | **404** |
| `POST /ai/products/sync` | `RestAiContentClient.java:64` | **404** |
| `PUT /ai/products/{id}` | `RestAiContentClient.java:76` | **404** |
| `DELETE /ai/products/{id}` | `RestAiContentClient.java:87` | **404** |
| `POST /ai/chat` (추천 챗봇) | 계약서 4장 | **404** |
| `POST /internal/v1/ai/detail-page-jobs` 에 BE 형식 JSON | 우리 실제 경로 | **422** — `product_image`, `metadata` 필수 |

우리 서비스에는 `/ai/*` 경로가 하나도 없다. 우리 경로에 BE 형식을 그대로 보내면 multipart 를 요구해 거부한다.

### 방향 2 — AI → BE

BE 의 `AiCallbackController` 계약(경로·본문·응답 형식)을 그대로 모사한 서버를 `127.0.0.1:8098` 에 띄우고, 우리 `BackendProductClient.persist()` 를 실제로 실행했다.

| 항목 | 값 |
| --- | --- |
| 보낸 것 | `multipart/form-data` — `metadata`(JSON 문자열) + `detail_page_image` + 섹션·사진 파트 |
| BE 가 기대하는 것 | `application/json` — `{"reactDocument": {...}}` (`AiCallbackRequest.java:8-11`) |
| **결과** | **HTTP 415 Unsupported Media Type, `retryable=False`** |

`retryable=False` 라 outbox 가 재시도하지 않고 영구 실패로 처리한다. 즉 조용히 유실된다.

## 불일치 목록

| # | 항목 | BE | 우리 | 비고 |
| --- | --- | --- | --- | --- |
| 1 | 생성 요청 경로 | `POST /ai/products` | `POST /internal/v1/ai/detail-page-jobs` | 양쪽 모두 상대 경로를 모른다 |
| 2 | 요청 형식 | `application/json` | `multipart/form-data` | 422 의 원인 |
| 3 | 이미지 전달 | `images`: S3 `imageId` 문자열 목록 | 이미지 바이트 multipart | BE 계약서 5-5 |
| 4 | 콜백 경로 | `POST /internal/generations/{id}/complete` | `BACKEND_URL` 단일 주소로 POST | 우리는 경로를 덧붙이지 않는다 |
| 5 | 콜백 형식 | JSON `{reactDocument}` | multipart `metadata` + 파일들 | 415 의 원인 |
| 6 | 콜백 응답 | `{success, status, data}` (`ApiResponse.java`) | `{generation_id, product_id, status, saved_at}` + `extra="forbid"` | 형식이 맞아도 ACK 검증에서 실패한다 |
| 7 | 인증 | BE 클라이언트가 인증 헤더를 보내지 않음 | `X-AI-Internal-Token` 필수 (없으면 401) | |
| 8 | ID 타입 | `Long` (숫자) | 문자열 | `generationId`, `productId` |
| 9 | 대상 서비스 | 콘텐츠 생성을 `ollamaUrl` 로 호출 (`AI_OLLAMA_URL`, 기본 `:8002`) | 단일 서비스 `:8000` | BE 는 AI 서버가 둘이라고 가정한다 |
| 10 | 포트 | `AI_SGLANG_URL` `:8001`, `AI_OLLAMA_URL` `:8002` | `:8000` | |
| 11 | 이미지 생성 | 계약서 5-4 "이미지 직접 생성 없음 — 업로드 사진을 블록에 배치" | FLUX 생성 + rembg 누끼 수행 | 기능 범위 자체가 다르다 |
| 12 | 추천 챗봇 | `POST /ai/chat` — 임베딩·하이브리드 검색 전제 | 구현 없음 | 이 저장소의 범위 밖 |

## 일치하는 것

- **`react_document`**: BE 콜백 컨트롤러가 `reactDocument` 를 받는다(`AiCallbackRequest.java:10`). 구조 산출물의 정본 계약은 양쪽이 같다.
- BE 계약서 3-1 의 "FE → BE → AI 단방향, AI 는 BE 에서만 호출받음" 은 우리 전제와 같다.

## 참고 — BE 문서와 BE 코드가 서로 다르다

`docs/PHASE2-3_AI_통합_계약서.md` 5-3 은 출력이 블록 배열(`{order, tag, text, imageUrl}`)이라고 적지만, 실제 `AiCallbackController` 는 `reactDocument` 를 받는다. **코드가 문서보다 최신**이다. 합의 시 어느 쪽이 정본인지 먼저 확인해야 한다.

## 실행하지 못한 것

BE 를 실제로 기동해 양쪽을 붙이는 것은 하지 못했다. `build.gradle:13` 이 Java 25 를 요구하는데 이 기기에는 JDK 26 만 있고 toolchain 다운로드 저장소가 설정돼 있지 않아 `./gradlew compileJava` 가 실패했다. 방향 2 는 BE 컨트롤러 계약을 모사한 서버로 검증했으므로, 실제 Spring 인스턴스에서 같은 결과가 나오는지는 확인되지 않았다.
