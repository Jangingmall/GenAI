# BE 팀 인계 — 2026-09-17

- 보내는 곳: 생성형 AI 팀 (상세페이지 생성)
- 근거: [`../../internal/be-request-2026-09-17.md`](../../internal/be-request-2026-09-17.md)와 `docs/evaluation/`의 시점 기록
- 범위: BE 코드·설정만 고치면 되는 항목

> **차단 항목은 BE-1과 BE-2입니다.** BE-1이 막혀 있으면 BE는 어떤 AI 서비스와도 통신하지 못하고, BE-2는 `202 Accepted` 안에 `FAILED`가 들어가는 원인을 함께 해결해야 합니다.

## 한눈에 보기

| 번호 | 제목 | 급함 |
| --- | --- | :---: |
| **BE-1** | `HttpClient`를 HTTP/1.1로 고정 | **차단** |
| **BE-2** | `@Async` 자기 호출 수정 — R-4 흡수 | **차단** |
| BE-3 | 상품 동기화를 챗봇으로 라우팅 | 높음 |
| BE-4 | 콘텐츠 생성 실패 재시도 구현 확인 | 중간 |
| BE-5 | 계약서 5-3과 코드 중 정본 확정 | 중간 |
| BE-6 | 로컬 가이드의 `.env` 미동작 | 낮음 |
| BE-7 | `AI_SGLANG_URL`·`AI_OLLAMA_URL` 이름 정리 | 중간 |
| BE-8 | AWS 주소·포트 및 콜백 주소 설정 | 높음 |

## BE-1. `HttpClient`를 HTTP/1.1로 고정해 주세요 (R-1)

### 증상

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

### 근거

BE가 만드는 본문을 **그대로** 챗봇에 직접 보내면 정상 동작합니다.

```
POST http://localhost:8001/ai/chat
{"session_id":"...","message":"엄마 환갑 선물 고급스러운 걸로 5만원대","history":[]}

→ 200
{"reply":"5만 원대 환갑 선물로 3점을 골랐어요...","intent":"gift_recommendation",
 "product_ids":[42,105,427],"suggestions":[...]}
```

소켓에서 기록한 실제 요청 바이트는 다음과 같습니다.

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

본문은 정상적으로 실려 있습니다. 문제는 **`Upgrade: h2c` / `Connection: Upgrade`**입니다. `HttpClient.newBuilder()`는 기본값이 HTTP/2이고, 평문 HTTP에서는 h2c 업그레이드를 시도합니다. AI 서비스들이 쓰는 uvicorn(h11)은 HTTP/1.1만 말하므로 본문이 애플리케이션에 전달되지 않습니다.

고칠 파일:

| 파일 | 행 |
| --- | --- |
| `chatbot/infrastructure/RestAiChatClient.java` | 33 |
| `content/infrastructure/RestAiContentClient.java` | 33 |

### 요청

두 파일 모두 다음과 같이 고쳐 주세요.

```java
// 현재
HttpClient.newBuilder().connectTimeout(timeout).build()

// 요청
HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1).connectTimeout(timeout).build()
```

저희가 BE를 로컬에서 위와 같이 고치고 다시 빌드·기동했을 때 챗봇 추천이 끝까지 동작했습니다. 이 변경은 BE 저장소에서 해주셔야 하며, 저희 쪽에서 우회할 방법이 없습니다.

## BE-2. `@Async` 자기 호출을 프록시 경유로 수정해 주세요 (R-11, R-4 흡수)

### 증상

`POST /api/content/products/{id}/generations`가 `202 Accepted`를 주는데 본문 `status`가 이미 `FAILED`입니다. AI 호출이 동기로 일어나 즉시 실패한 뒤 202로 감싸집니다.

### 근거

`GenerationService.java:45`가 같은 클래스의 `executeAsync(:73)`를 직접 호출합니다.

```java
ContentGeneration saved = generationRepository.save(generation);
executeAsync(saved.getId(), command);   // ← 같은 클래스 내부 호출

@Async
public void executeAsync(Long generationId, GenerationCommand.Request command) { ... }
```

Spring의 `@Async`는 프록시로 동작하므로 같은 빈 안에서 자기 메서드를 부르면 애노테이션이 무효가 됩니다. `@EnableAsync`는 `global/config/AsyncConfig.java:6`에 정상 선언돼 있어 설정 문제가 아닙니다. 이것이 R-4의 원인입니다.

실패했을 때만의 문제가 아닙니다. AI가 정상 동작하면 이 호출은 성공할 때까지 요청 스레드를 붙잡습니다. 상세페이지 1건은 초안까지만 저희 측정에서 **160초**였습니다.

### 요청

호출을 다른 빈으로 빼거나 `ApplicationEventPublisher`를 쓰는 등 **프록시를 거치게** 만들어 진짜 비동기로 분리해 주세요. R-4와 같은 원인이므로 하나의 수정으로 처리해 주세요.

## BE-3. 상품 동기화를 챗봇 쪽으로 보내 주세요 (R-2)

### 증상

- 같은 질의를 챗봇에 직접 보내면 `product_ids: [42, 105, 427]`을 돌려줍니다.
- 같은 질의를 BE를 통해 보내면(R-1 패치 후) `reply`·`intent`·`suggestions`는 정상인데 `products`는 **빈 배열**입니다.

### 근거

이 테스트에서는 챗봇 색인이 샘플 CSV 기준 **832건**, BE 로컬 DB는 `/dev/setup`이 만든 **1건**이었습니다. 상품 동기화가 도착하는 곳이 잘못돼 있습니다.

- `RestAiContentClient.java:64,78,92` — `syncProduct`, `updateProduct`, `deleteProduct`가 모두 `ollamaUrl`(= **상세페이지 서버**)로 갑니다.
- 필요한 곳은 추천 색인을 가진 챗봇입니다.

### 요청

동기화 3종을 `AI_SGLANG_URL`(챗봇)로 보내 주세요. 상세페이지 생성만 `AI_OLLAMA_URL`로 가면 됩니다.

## BE-4. 콘텐츠 생성 실패 시 재시도를 구현·확인해 주세요 (R-5)

### 증상

계약서 3-6은 "최대 2회 재시도"인데 로그에는 **1회 호출 후 즉시 실패**로 남았습니다.

### 근거

실측 로그입니다. 챗봇 쪽 `RestAiChatClient`에는 재시도가 있지만 콘텐츠 생성 경로에는 확인되지 않습니다.

### 요청

콘텐츠 생성 실패 시 계약서 3-6의 최대 2회 재시도가 실제로 구현돼 있는지 확인하고, 없으면 구현해 주세요.

## BE-5. 계약서 5-3과 코드 중 정본을 확정해 주세요 (R-6)

### 증상

계약서 5-3은 출력이 블록 배열(`{order, tag, text, imageUrl}`)인데 `AiCallbackController`는 `reactDocument`를 받습니다.

### 근거

`AiCallbackRequest.java:10`의 현재 코드가 `reactDocument`를 받는 것을 확인했습니다.

### 요청

어느 쪽이 정본인지 확정해 주세요. 저희는 **코드 기준(`reactDocument`)**으로 맞추겠습니다.

## BE-6. 로컬 가이드의 `.env`를 동작하게 해 주세요 (R-7)

### 증상

`AI_로컬_연동_가이드` 1장이 루트 `.env`로 `AI_OLLAMA_URL`을 설정하라고 하지만 Spring이 값을 읽지 않고 기본값으로 호출합니다.

### 근거

`build.gradle`에 dotenv 의존성이 없어 Spring이 루트 `.env`를 읽지 않습니다. AI 팀이 로컬 재현할 때 처음 걸리는 지점입니다.

### 요청

가이드를 고치거나 dotenv를 추가해 주세요.

## BE-7. `AI_SGLANG_URL`·`AI_OLLAMA_URL` 이름을 실제 용도에 맞춰 주세요 (R-10)

### 증상

BE의 두 설정은 엔진 이름을 쓰고 있는데 실제 엔진과 정확히 반대입니다.

### 근거

| BE 변수 | BE가 연결한 서비스 | 그 서비스가 실제로 쓰는 엔진 |
| --- | --- | --- |
| `AI_SGLANG_URL` | 챗봇 (`GenAI/chat_bot`) | **Ollama** (`app/config.py:43,47` — `OLLAMA_HOST`, `gemma2:9b`) |
| `AI_OLLAMA_URL` | 상세페이지 (`GenAI/page_generation`) | **SGLang** (`deploy/sglang/Dockerfile:42-43`) |

### 요청

용도 기준 이름을 권합니다.

```
AI_CHAT_URL      → 챗봇        (POST /ai/chat)
AI_CONTENT_URL   → 상세페이지   (POST /ai/products 등)
```

엔진은 나중에 바뀔 수 있지만 용도는 바뀌지 않습니다. 이름을 바꾸기 어렵다면 최소한 주석과 가이드 문서에 어느 서비스인지 명시해 주세요.

## BE-8. AWS 배포 주소·포트와 콜백용 BE 주소를 설정해 주세요 (R-9 일부)

### 증상

로컬의 `localhost` 주소와 서버의 주소·포트가 다릅니다. 서버에서는 챗봇과 상세페이지의 주소를 각각 넣어야 하고, 상세페이지 AI가 완료 후 BE를 호출할 내부 주소도 필요합니다.

### 근거

서버 설정 기준은 다음과 같습니다.

| 설정 | 로컬 재현값 | **서버** |
| --- | --- | --- |
| 챗봇 | `http://localhost:8001` | 챗봇 서비스 주소 — **챗봇 팀 확인 필요** |
| 상세페이지 | `http://localhost:8002` | **`:8000`**의 상세페이지 서비스 주소 |

- 로컬 재현에서 쓴 `8001`·`8002`는 BE 기본값에 맞추려고 저희가 임시로 띄운 포트입니다.
- **두 AI 서비스 모두 기본 포트가 `8000`**입니다. 한 호스트에 둘을 같이 올리면 포트가 충돌하므로 한쪽을 다른 포트로 띄우고 그 값을 BE 설정에 넣어야 합니다.
- 쿠버네티스처럼 파드가 분리되면 둘 다 `8000`이어도 문제없습니다. BE는 `http://<서비스명>:8000` 형태로 잡으면 됩니다.
- 컨테이너 안에서 SGLang이 `30000`·`30001`을 쓰지만 내부 전용이라 BE가 알 필요도, 노출할 필요도 없습니다.

상세페이지 AI가 생성 완료 뒤 BE를 호출할 때는 서버의 BE 내부 주소가 필요합니다.

| AI 설정 | 채울 값 |
| --- | --- |
| `BACKEND_URL` | BE 콜백 엔드포인트 **전체 URL** (환경별) |
| `BACKEND_AUTH_TOKEN` | 저희가 BE 호출 시 `Authorization: Bearer`에 넣을 토큰 |

### 요청

개발·스테이징·운영 각각의 BE 내부 주소를 알려 주세요. AI 파드에서 BE로 나가는 통신이 보안 그룹·NetworkPolicy로 막히지 않는지도 함께 확인 부탁드립니다.

### 운영 참고 — 상태 확인 경로

| 경로 | 의미 |
| --- | --- |
| `GET /health` | 프로세스 살아 있음. 항상 200, 추론 서버를 호출하지 않음 |
| `GET /health/ready` | 추론 준비 완료. 모델 서버 확인 후 200 또는 503 + 사유 |

모델 로딩에 수 분이 걸리므로 기동 직후 `/health/ready`가 503인 것은 정상입니다. 이 구간에 생성 요청을 보내면 실패합니다.

---

## 나머지 문서

- [AI 작업 목록](ai-worklist-2026-09-17.md)
- [양측 합의 필요 사항](open-decisions-2026-09-17.md)
