# BE 팀에 드리는 요청 — 2026-09-17

- 보내는 곳: 생성형 AI 팀 (상세페이지 생성)
- 근거: `docs/evaluation/three-service-integration-test-2026-09-17.md` — 세 서비스를 모두 로컬에 띄워 측정한 기록
- 로그: `docs/evaluation/logs/` — BE 원본 상태(패치 없음)로 재실행한 2026-09-17 로그 묶음
- 컨테이너 테스트: `docs/evaluation/container-integration-test-2026-09-17.md`
- 함께 보실 것: `docs/api/be-ai-integration-negotiation.md` — 항목별 연동 협의

## 요청 일람

| # | 요청 | 급함 | 근거 |
| --- | --- | :---: | --- |
| **R-1** | `HttpClient` 를 HTTP/1.1 로 고정 | **차단** | 실측 · 수정 검증 완료 |
| **R-2** | 상품 동기화를 챗봇(`AI_SGLANG_URL`)으로 라우팅 | 높음 | 실측 |
| R-3 | `POST /ai/products` 경로 의미 정리 (세 곳이 다름) | 높음 | 코드 대조 |
| R-4 | 생성 요청을 진짜 비동기로 분리 (202 안에 `FAILED`) | 중간 | 실측 |
| R-5 | 콘텐츠 생성 실패 시 재시도 확인 (계약서 3-6) | 중간 | 실측 |
| R-6 | 계약서 5-3 과 코드 중 어느 쪽이 정본인지 | 중간 | 코드 대조 |
| R-7 | 로컬 가이드의 `.env` 미동작 | 낮음 | 실측 |
| R-8 | 양방향 내부 호출 인증 합의 | 높음 | 코드 대조 |
| **R-9** | **AWS 배포 시 주소·포트·인증·타임아웃 설정** | 높음 | 아래 전용 절 |
| **R-10** | **`AI_SGLANG_URL`·`AI_OLLAMA_URL` 이름이 실제 엔진과 반대** | 중간 | 코드 대조 |
| **R-11** | **`@Async` 자기 호출로 비동기가 동작하지 않음** | **차단** | 실측 · 원인 규명 |
| **R-12** | **`/ai/products` 응답을 무엇으로 줄지 확정 필요** | **차단** | 코드 대조 |
| R-13 | 챗봇에 Dockerfile 이 없음 | 중간 | 저장소 확인 |

**R-1 이 먼저입니다.** 이것이 막혀 있으면 나머지를 고쳐도 BE 는 어떤 AI 서비스와도 통신하지 못합니다.

---

## 요약

BE · 챗봇(`GenAI/chat_bot`) · 상세페이지(`GenAI/page_generation`) 세 서비스를 로컬에서 실제로 기동해 붙여 봤습니다.

**BE 가 AI 서비스에 HTTP 요청 본문을 전달하지 못하고 있습니다.** 계약이 틀린 것이 아니라 HTTP 프로토콜 문제이며, **BE 코드 한 줄**이면 해결됩니다. 저희가 로컬에서 고쳐 **동작까지 확인**했습니다.

이 문제 때문에 지금은 챗봇 추천이 항상 폴백 문구로 나가고, 상세페이지 연동도 같은 이유로 막힙니다.

---

## R-1. `HttpClient` 를 HTTP/1.1 로 고정해 주세요

### 무슨 일이 일어나는가

FE 역할로 챗봇에 메시지를 보내면 이렇게 돌아옵니다.

```json
{"reply":"현재 AI 추천을 이용할 수 없습니다","intent":null,"products":[]}
```

BE 로그:

```
WARN  RestAiChatClient : AI 챗봇 호출 실패 attempt=1
      reason=422 Unprocessable Content: {"detail":[{"type":"missing","loc":["body"],...}]}
WARN  RestAiChatClient : AI 챗봇 호출 실패 attempt=2
      reason=400 Bad Request: "Invalid HTTP request received."
WARN  RestAiChatClient : AI 챗봇 호출 실패 attempt=3   (동일)
ERROR RestAiChatClient : AI 챗봇 최종 실패
```

### 계약 문제가 아닙니다

BE 가 만드는 본문을 **그대로** 챗봇에 직접 보내면 정상 동작합니다.

```
POST http://localhost:8001/ai/chat
{"session_id":"...","message":"엄마 환갑 선물 고급스러운 걸로 5만원대","history":[]}

→ 200
{"reply":"5만 원대 환갑 선물로 3점을 골랐어요...","intent":"gift_recommendation",
 "product_ids":[42,105,427],"suggestions":[...]}
```

### 원인

BE 가 실제로 보내는 바이트를 소켓에서 그대로 기록했습니다.

```
POST /ai/chat HTTP/1.1
Connection: Upgrade, HTTP2-Settings
HTTP2-Settings: AAEAAEAAAAIAAAAAAAMAAAAAAAQBAAAAAAUAAEAAAAYABgAA
Upgrade: h2c
Transfer-encoding: chunked
Content-Type: application/json

7f
{"session_id":"...","message":"테스트","history":[{"sender":"USER","content":"테스트"}]}
0
```

본문은 정상적으로 실려 있습니다. 문제는 **`Upgrade: h2c` / `Connection: Upgrade`** 입니다.

`HttpClient.newBuilder()` 는 **기본값이 HTTP/2** 이고, 평문 HTTP 에서는 h2c 업그레이드를 시도합니다. 그런데 AI 서비스들이 쓰는 uvicorn(h11)은 **HTTP/1.1 만** 말합니다. uvicorn 은 이 요청을 프로토콜 업그레이드로 처리해 **본문을 애플리케이션에 넘기지 않습니다.** 그래서 FastAPI 가 "본문 없음"으로 422 를 반환하고, 그 뒤 연결 상태가 깨져 재시도는 `Invalid HTTP request received` 가 됩니다.

### 고칠 곳

두 파일이 같은 패턴입니다. **둘 다** 고쳐야 합니다.

| 파일 | 행 |
| --- | --- |
| `chatbot/infrastructure/RestAiChatClient.java` | 33 |
| `content/infrastructure/RestAiContentClient.java` | 33 |

```java
// 현재
HttpClient.newBuilder().connectTimeout(timeout).build()

// 요청
HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1).connectTimeout(timeout).build()
```

### 검증 결과

저희가 BE 를 로컬에서 위와 같이 고치고 다시 빌드·기동했습니다. **챗봇 추천이 끝까지 동작합니다.**

```
POST /api/chatbot/sessions/{id}/messages   {"content":"엄마 환갑 선물 고급스러운 걸로 5만원대"}
→ 201
reply       "5만 원대에서 고급스러운 환갑 선물로 3점을 골랐어요. 분청 다완과 분청 찻잔은
             전통 분청 기법으로 만든 작품이고, 치자염 파우치는 자연염색으로 만든 상품입니다."
intent      "gift_recommendation"
suggestions ["분청 재질 상품","흰색 상품","여주 지역 장인"]
```

> 이 변경은 BE 저장소에서 해주셔야 합니다. 저희 쪽에서 우회할 방법이 없고, 고치기 전에는 **어떤 AI 서비스도 BE 와 통신할 수 없습니다.**

---

## R-2 · R-3. 상품 동기화를 챗봇 쪽으로 보내 주세요

실측 두 가지를 나란히 놓습니다.

- 같은 질의를 **챗봇에 직접** 보내면 `product_ids: [42, 105, 427]` 을 돌려줍니다
- 같은 질의를 **BE 를 통해** 보내면(R-1 패치 후) `reply`·`intent`·`suggestions` 는 정상인데 `products` 는 **빈 배열**입니다

BE 가 받은 id 로 자기 카탈로그에서 카드를 조립하는데, 두 쪽의 상품 집합이 다르기 때문입니다. 이 테스트에서는 챗봇 색인이 샘플 CSV 기준 **832건**, BE 로컬 DB 는 `/dev/setup` 이 만든 **1건**이었습니다.

근본 원인은 **상품 동기화가 도착하는 곳이 잘못돼 있다**는 점입니다.

- `RestAiContentClient.java:64,78,92` — `syncProduct`, `updateProduct`, `deleteProduct` 가 모두 `ollamaUrl`(= **상세페이지 서버**)로 갑니다
- 그런데 그 데이터가 필요한 곳은 **추천 색인을 가진 챗봇**입니다

이대로면 챗봇 색인은 영영 채워지지 않고, 추천 결과가 화면에 뜨지 않습니다.

**요청**: 동기화 3종을 `AI_SGLANG_URL`(챗봇)로 보내 주세요. 상세페이지 생성만 `AI_OLLAMA_URL` 로 가면 됩니다.

### 덧붙여 — `POST /ai/products` 가 세 곳에서 뜻이 다릅니다

| 주체 | 의미 | 본문 |
| --- | --- | --- |
| `RestAiContentClient.java:54` | 상세페이지 **생성 요청** | `{generationId, productId, images[], productName, howMade, careTips}` |
| `GenAI/chat_bot` `app/main.py:112` | 추천 색인 **상품 upsert** | `{artisan, product}` |
| 계약서 5-3 | 게시 시점 **동기화** | `{artisan, product}` |

또한 챗봇에는 `/ai/products/sync` 가 없습니다(upsert 를 `POST /ai/products` 로 받습니다). 세 팀이 한 번에 경로를 정리하는 편이 낫겠습니다. **저희는 어느 쪽으로 정하든 따르겠습니다.**

---

## R-4 ~ R-8. 확인 부탁드리는 것들

| # | 내용 | 근거 |
| --- | --- | --- |
| 3-1 | **202 안에 이미 `FAILED` 가 들어옵니다.** 원인은 아래 **R-11** 입니다. `POST /api/content/products/{id}/generations` 가 `202 Accepted` 를 주는데 본문 `status` 가 `FAILED` 였습니다. AI 호출이 동기로 일어나 즉시 실패한 뒤 202 로 감싸집니다. 계약서 5-1 의 비동기가 의도라면 호출을 분리해 주세요 | 실측 |
| 3-2 | **콘텐츠 생성 실패 시 재시도가 없습니다.** 계약서 3-6 은 "최대 2회 재시도"인데 로그에는 1회 호출 후 즉시 실패로 남았습니다. (챗봇 쪽 `RestAiChatClient` 에는 재시도가 있습니다) | 실측 |
| 3-3 | **문서와 코드가 다릅니다.** 계약서 5-3 은 출력이 블록 배열(`{order, tag, text, imageUrl}`)인데 `AiCallbackController` 는 `reactDocument` 를 받습니다. 저희는 **코드 기준**으로 맞추겠습니다 | `AiCallbackRequest.java:10` |
| 3-4 | **`.env` 가 동작하지 않습니다.** `AI_로컬_연동_가이드` 1장이 루트 `.env` 로 `AI_OLLAMA_URL` 을 설정하라고 하는데, `build.gradle` 에 dotenv 의존성이 없어 Spring 이 읽지 않고 기본값으로 호출합니다. AI 팀이 로컬 재현할 때 처음 걸리는 지점입니다 | 실측 |
| 3-5 | **양방향 인증을 정해야 합니다.** 저희 `/internal/v1/ai/*` 는 `X-AI-Internal-Token` 을 요구하는데 BE 클라이언트는 인증 헤더를 보내지 않습니다. 반대로 BE 의 `/internal/generations/{id}/complete` 도 인증 없이 열려 있습니다. 토큰 발급 주체도 함께 정해 주세요 | 코드 |

---

## R-11. `@Async` 가 동작하지 않습니다 — 자기 호출이라 프록시를 우회합니다

`GenerationService.java:45` 가 같은 클래스의 `executeAsync`(`:73`)를 직접 호출합니다.

```java
ContentGeneration saved = generationRepository.save(generation);
executeAsync(saved.getId(), command);   // ← 같은 클래스 내부 호출

@Async
public void executeAsync(Long generationId, GenerationCommand.Request command) { ... }
```

Spring 의 `@Async` 는 프록시로 동작하므로 **같은 빈 안에서 자기 메서드를 부르면 애노테이션이 무효**가 됩니다. `@EnableAsync` 는 `global/config/AsyncConfig.java:6` 에 정상 선언돼 있어 설정 문제가 아닙니다.

이것이 앞서 보고드린 **R-4(202 안에 `FAILED`)의 원인**입니다. AI 호출이 응답 직렬화 전에 끝나 버립니다.

**실패했을 때만의 문제가 아닙니다.** AI 가 정상 동작하면 이 호출은 성공할 때까지 **요청 스레드를 붙잡습니다.** 상세페이지 1건은 초안까지만 저희 측정에서 **160초**였습니다. 그동안 FE 와 BE 가 함께 대기합니다.

> 해결은 호출을 다른 빈으로 빼거나 `ApplicationEventPublisher` 를 쓰는 등 **프록시를 거치게** 만드는 것입니다. R-4 와 같은 항목이므로 함께 처리하시면 됩니다.

## R-12. `POST /ai/products` 가 무엇을 반환해야 합니까 — 정해 주셔야 구현을 시작합니다

`GenerationService.java:77-89` 는 `/ai/products` 의 **동기 응답 본문을 완성된 react_document 로 간주**하고 검증 없이 저장합니다.

```java
String reactDocumentJson = aiContentClient.requestGeneration(...);
generation.complete(reactDocumentJson);
contentService.storeReactDocument(new ContentCommand.StoreReactDocument(..., reactDocumentJson, ...));
```

그런데 같은 BE 에 **콜백 경로도 있습니다**(`AiCallbackRequest.java:10`). 완료 처리 경로가 둘이고 실제로 도는 것은 동기 경로입니다.

**어느 쪽으로 갈지 정해 주세요.**

| 안 | BE 가 할 일 | AI 가 할 일 |
| --- | --- | --- |
| **가. 동기 유지** | 없음 | `/ai/products` 응답으로 **react_document 를 직접 반환**. 수 분간 블로킹됩니다 |
| **나. 비동기 + 콜백** (권장) | R-11 수정 후 콜백 경로 사용 | 즉시 202 반환, 완료 시 `POST /internal/generations/{id}/complete` 호출 |

> **지금 상태에서는 위험합니다.** 저희가 접수 응답(`{"job_id":...}`)을 반환하면 BE 는 그것을 **react_document 로 저장**합니다. 오류 없이 잘못된 데이터가 들어갑니다.
>
> 처리 시간(초안까지 160초, 이미지 생성 포함 시 더 김)과 BE 의 `AI_TIMEOUT_SECONDS` 기본 300초를 함께 고려하면 **나 안을 권합니다.**

## R-13. 챗봇에 Dockerfile 이 없습니다 (챗봇 팀 확인)

`Jangingmall/GenAI` 의 `chat_bot/` 과 저장소 어디에도 Dockerfile 이 없습니다(`page_generation/` 제외). 인프라팀이 요청한 "런타임별 Dockerfile" 기준으로 챗봇은 아직 배포 가능한 형태가 아닙니다. 저희 쪽 이미지는 빌드·기동을 확인했습니다(아래).

## 참고 — 컨테이너로도 확인했습니다

두 서비스를 컨테이너로 올려 도커 네트워크로 붙여 봤습니다. **결과는 프로세스로 돌렸을 때와 같습니다**(404). 실행 방식이 아니라 계약 문제라는 뜻입니다.

| 확인 | 결과 |
| --- | --- |
| 상세페이지 이미지 빌드 | 성공 (4.99GB) · `appuser` 비 root · HEALTHCHECK 동작 |
| BE 이미지 빌드 | 성공 (619MB, `--target local`) |
| 컨테이너 이름 해석 | `AI_OLLAMA_URL=http://dp-ai:8000` 동작 |
| 내부 포트 | **8000** (로컬의 8002 는 호스트 매핑일 뿐) |

자세한 기록은 `docs/evaluation/container-integration-test-2026-09-17.md` 에 있습니다.

## R-9. AWS 배포 기준 — 로컬과 달라지는 것

위 내용은 전부 로컬(`localhost`) 기준 실측입니다. 서버에 올리면 **주소·인증·타임아웃 세 가지가 달라집니다.**

> 상세페이지 AI 는 아직 **GPU 에서 한 번도 실행되지 않았습니다.** 아래 수치 중 처리 시간은 추정이며, 첫 배포에서 실측해 다시 알려 드리겠습니다.

### 9-1. 변수 이름이 실제 엔진과 반대입니다 — 먼저 정리해 주세요

지금 BE 의 두 설정은 **엔진 이름**을 쓰고 있는데, 실제 엔진과 **정확히 반대**입니다.

| BE 변수 | BE 가 연결한 서비스 | 그 서비스가 실제로 쓰는 엔진 |
| --- | --- | --- |
| `AI_SGLANG_URL` | 챗봇 (`GenAI/chat_bot`) | **Ollama** (`app/config.py:43,47` — `OLLAMA_HOST`, `gemma2:9b`) |
| `AI_OLLAMA_URL` | 상세페이지 (`GenAI/page_generation`) | **SGLang** (`deploy/sglang/Dockerfile:42-43`) |

이대로 두면 설정하는 사람마다 반대로 꽂습니다. **용도 기준 이름을 권합니다.**

```
AI_CHAT_URL      → 챗봇        (POST /ai/chat)
AI_CONTENT_URL   → 상세페이지   (POST /ai/products 등)
```

엔진은 나중에 바뀔 수 있지만 용도는 바뀌지 않습니다. 이름을 바꾸기 어렵다면 최소한 **주석과 가이드 문서에 어느 서비스인지** 명시해 주세요.

### 9-2. 서버 주소와 포트

| 설정 | 로컬 재현값 | **서버** |
| --- | --- | --- |
| 챗봇 | `http://localhost:8001` | 챗봇 서비스 주소 — **챗봇 팀 확인 필요** |
| 상세페이지 | `http://localhost:8002` | **`:8000`** 의 상세페이지 서비스 주소 |

**포트에 관해 주의하실 점이 있습니다.**

- 로컬 재현에서 쓴 `8001`·`8002` 는 **BE 기본값에 맞추려고 저희가 임시로 띄운 포트**입니다. 두 서비스의 실제 기본 포트가 아닙니다.
- **두 AI 서비스 모두 기본 포트가 `8000` 입니다.** 챗봇 README 5장이 `--port 8000`, 저희 컨테이너도 `EXPOSE 8000` 입니다.
- 따라서 **한 호스트에 둘을 같이 올리면 포트가 충돌합니다.** 이때는 한쪽을 다른 포트로 띄우고 그 값을 BE 설정에 넣어야 합니다.
- **쿠버네티스처럼 파드가 분리되면 둘 다 `8000` 이어도 문제없습니다.** 서비스마다 주소가 다르기 때문입니다. 이 경우 BE 는 `http://<서비스명>:8000` 형태로 잡으면 됩니다.

저희 워크로드는 파드 하나에 컨테이너 하나이고 **Service 로 노출할 포트는 `8000` 뿐**입니다. 컨테이너 안에서 SGLang 이 `30000`·`30001` 을 쓰지만 **내부 전용이라 BE 가 알 필요도, 노출할 필요도 없습니다.**

> **확정 주소는 인프라팀이 Service 를 만든 뒤 저희가 알려 드리겠습니다.** 지금은 포트만 `8000` 으로 기억해 주세요.

> 두 URL 설정을 **하나로 합치지는 마세요.** 챗봇과 상세페이지는 서로 다른 서비스입니다.

### 9-3. 콜백이 닿을 BE 주소가 필요합니다

상세페이지 AI 는 생성이 끝나면 BE 를 호출합니다. 로컬에서는 `localhost:8080` 이었지만 서버에서는 **BE 의 내부 주소**가 필요합니다.

| 저희 설정 | 채울 값 |
| --- | --- |
| `BACKEND_URL` | BE 콜백 엔드포인트 **전체 URL** (환경별) |
| `BACKEND_AUTH_TOKEN` | 저희가 BE 호출 시 `Authorization: Bearer` 에 넣을 토큰 |

**요청**: 개발/스테이징/운영 각각의 BE 내부 주소를 알려 주세요. AI 파드에서 BE 로 나가는 통신이 보안 그룹·NetworkPolicy 로 막히지 않는지도 함께 확인 부탁드립니다.

### 9-4. 인증을 켜야 합니다 (R-8 의 서버판)

로컬에서는 양쪽 다 인증 없이 통했지만 **서버에서는 그대로 두면 안 됩니다.**

| 방향 | 현재 | 서버에서 필요한 것 |
| --- | --- | --- |
| BE → AI | 인증 헤더 없음 | 저희 `/internal/v1/ai/*` 는 `X-AI-Internal-Token` 을 요구합니다. BE 클라이언트가 이 헤더를 보내야 합니다 |
| AI → BE | `/internal/generations/{id}/complete` 가 인증 없이 열려 있음 | 최소한 내부 전용으로 제한하거나 토큰 검증을 붙여 주세요 |

토큰 값은 양 팀 시크릿으로 주입합니다. **발급 주체만 정해 주시면** 저희가 맞추겠습니다.

### 9-5. 타임아웃 — 동기 호출로는 감당되지 않습니다

BE 의 `AI_TIMEOUT_SECONDS` 는 기본 **300초**입니다.

- 상세페이지 1건 생성은 **로컬 Apple Silicon 기준 평균 226초**였습니다 (이미지 생성 포함)
- 서버 GPU 실측치는 **아직 없습니다**
- 장인이 올린 사진이 적어 생성 컷이 많아지면 300초를 넘길 수 있습니다

**요청**: 생성 요청은 **즉시 접수(202)하고 완료 시 콜백**받는 구조로 가 주세요. 계약서 5-1 의 비동기 설계와도 맞고, R-4 에서 말씀드린 "202 안에 FAILED" 문제도 같이 해소됩니다. 지금처럼 동기로 호출하면 서버에서는 타임아웃으로 실패합니다.

### 9-6. 상태 확인 경로

BE 나 인프라에서 AI 서비스 상태를 볼 때 쓰실 수 있습니다. **둘 다 인증 없이** 열려 있습니다.

| 경로 | 의미 |
| --- | --- |
| `GET /health` | 프로세스 살아 있음. 항상 200, 추론 서버를 호출하지 않음 |
| `GET /health/ready` | 추론 준비 완료. 모델 서버 확인 후 200 또는 503 + 사유 |

모델 로딩에 수 분이 걸리므로, **기동 직후 `/health/ready` 가 503 인 것은 정상**입니다. 이 구간에 생성 요청을 보내면 실패합니다.

---

## 저희(AI)가 맡아서 하는 것

R-1 이 해결되면 바로 붙일 수 있도록 아래는 **BE 변경 없이** 저희가 맞추겠습니다.

| # | 내용 |
| --- | --- |
| 1 | `POST /ai/products` 경로 추가 — 지금은 404 입니다 |
| 2 | BE 가 보내는 JSON 본문 수용 (현재는 multipart 를 요구해 422) |
| 3 | 이미지 URL 목록 수용 — BE 가 주는 URL 을 저희가 내려받습니다 |
| 4 | 콜백을 `POST /internal/generations/{generationId}/complete` 에 JSON `{"reactDocument": ...}` 로 전송 (실측으로 200 확인했습니다) |
| 5 | BE 공통 응답 봉투 `{success, status, data}` 수용 |
| 6 | 숫자 ID(`Long`) 수용 |

다만 **생성 이미지를 넘길 방법**만은 저희끼리 정할 수 없습니다. 상세페이지 AI 는 장인이 올린 사진을 먼저 쓰고 **모자란 만큼 이미지를 생성**하는데, BE 콜백은 `reactDocument` 하나만 받습니다. ① BE 가 이미지 업로드 API 를 열어 주시면 저희가 올리고 받은 id 를 문서에 심는 방식을 **권합니다**(이미지 저장·CDN 이 이미 BE 책임이므로). 자세한 선택지는 협의 문서 C-1 에 있습니다.

---

## 재현 방법

이 문서의 모든 내용은 아래로 재현됩니다.

```bash
docker run -d -p 6379:6379 redis:8
docker run -d -e POSTGRES_DB=midam -e POSTGRES_USER=midam -e POSTGRES_PASSWORD=midam \
  -p 5432:5432 pgvector/pgvector:pg17
docker exec <pg> psql -U midam -d midam -c "CREATE EXTENSION IF NOT EXISTS vector;"
ollama pull qwen3:8b

# 챗봇 (:8001)
cd GenAI/chat_bot && pip install -r requirements.txt && python verify_env.py
DATABASE_URL=postgresql://midam:midam@localhost:5432/midam \
  python -m app.ingest.load_products --file data/장인몰_샘플_product.csv \
                                     --artisan-file data/장인몰_샘플_artisan.csv
DATABASE_URL=... uvicorn app.main:app --port 8001

# 상세페이지 (:8002)
cd GenAI/page_generation && uvicorn detail_page_ai.app:app --port 8002

# BE (:8080)
cd backend && ./gradlew bootRun

# 흐름
curl -X POST localhost:8080/dev/setup
curl -X POST "localhost:8080/dev/token?role=USER&memberId=1"
curl -X POST localhost:8080/api/chatbot/sessions -H "Authorization: Bearer <TOKEN>" -d '{}'
curl -X POST localhost:8080/api/chatbot/sessions/<SID>/messages \
  -H "Authorization: Bearer <TOKEN>" -H 'Content-Type: application/json' \
  -d '{"content":"엄마 환갑 선물 고급스러운 걸로 5만원대"}'
```
