# BE 팀에 드리는 요청 — 2026-09-17

- 보내는 곳: 생성형 AI 팀 (상세페이지 생성)
- 근거: `docs/evaluation/three-service-integration-test-2026-09-17.md` — 세 서비스를 모두 로컬에 띄워 측정한 기록
- 함께 보실 것: `docs/api/be-ai-integration-negotiation.md` — 항목별 연동 협의

## 요약

BE · 챗봇(`GenAI/chat_bot`) · 상세페이지(`GenAI/page_generation`) 세 서비스를 로컬에서 실제로 기동해 붙여 봤습니다.

**BE 가 AI 서비스에 HTTP 요청 본문을 전달하지 못하고 있습니다.** 계약이 틀린 것이 아니라 HTTP 프로토콜 문제이며, **BE 코드 한 줄**이면 해결됩니다. 저희가 로컬에서 고쳐 **동작까지 확인**했습니다.

이 문제 때문에 지금은 챗봇 추천이 항상 폴백 문구로 나가고, 상세페이지 연동도 같은 이유로 막힙니다.

---

## 요청 1 — `HttpClient` 를 HTTP/1.1 로 고정해 주세요 (가장 급함)

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

## 요청 2 — 상품 동기화를 챗봇 쪽으로 보내 주세요

실측 두 가지를 나란히 놓습니다.

- 같은 질의를 **챗봇에 직접** 보내면 `product_ids: [42, 105, 427]` 을 돌려줍니다
- 같은 질의를 **BE 를 통해** 보내면(요청 1 패치 후) `reply`·`intent`·`suggestions` 는 정상인데 `products` 는 **빈 배열**입니다

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

## 요청 3 — 확인 부탁드리는 것들

| # | 내용 | 근거 |
| --- | --- | --- |
| 3-1 | **202 안에 이미 `FAILED` 가 들어옵니다.** `POST /api/content/products/{id}/generations` 가 `202 Accepted` 를 주는데 본문 `status` 가 `FAILED` 였습니다. AI 호출이 동기로 일어나 즉시 실패한 뒤 202 로 감싸집니다. 계약서 5-1 의 비동기가 의도라면 호출을 분리해 주세요 | 실측 |
| 3-2 | **콘텐츠 생성 실패 시 재시도가 없습니다.** 계약서 3-6 은 "최대 2회 재시도"인데 로그에는 1회 호출 후 즉시 실패로 남았습니다. (챗봇 쪽 `RestAiChatClient` 에는 재시도가 있습니다) | 실측 |
| 3-3 | **문서와 코드가 다릅니다.** 계약서 5-3 은 출력이 블록 배열(`{order, tag, text, imageUrl}`)인데 `AiCallbackController` 는 `reactDocument` 를 받습니다. 저희는 **코드 기준**으로 맞추겠습니다 | `AiCallbackRequest.java:10` |
| 3-4 | **`.env` 가 동작하지 않습니다.** `AI_로컬_연동_가이드` 1장이 루트 `.env` 로 `AI_OLLAMA_URL` 을 설정하라고 하는데, `build.gradle` 에 dotenv 의존성이 없어 Spring 이 읽지 않고 기본값으로 호출합니다. AI 팀이 로컬 재현할 때 처음 걸리는 지점입니다 | 실측 |
| 3-5 | **양방향 인증을 정해야 합니다.** 저희 `/internal/v1/ai/*` 는 `X-AI-Internal-Token` 을 요구하는데 BE 클라이언트는 인증 헤더를 보내지 않습니다. 반대로 BE 의 `/internal/generations/{id}/complete` 도 인증 없이 열려 있습니다. 토큰 발급 주체도 함께 정해 주세요 | 코드 |

---

## 저희(AI)가 맡아서 하는 것

요청 1 이 해결되면 바로 붙일 수 있도록 아래는 **BE 변경 없이** 저희가 맞추겠습니다.

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
