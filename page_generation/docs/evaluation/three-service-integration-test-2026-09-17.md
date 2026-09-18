# 3자 연동 테스트 (BE · 챗봇 · 상세페이지) — 2026-09-17

> 이 문서는 2026-09-17 시점 기록이다. 이후 상태가 바뀌어도 이 문서는 고치지 않는다.

- 대상: `Jangingmall/backend`(`1e04949`) · `Jangingmall/GenAI` `chat_bot/`(`7440a0a`) · 같은 저장소 `page_generation/`(이 서비스)
- 방법: 세 서비스를 모두 로컬에서 실제로 기동해 FE 역할의 요청을 BE 에 넣고 흐름을 따라갔다.
- 가장 큰 발견: **BE 가 AI 서비스에 본문을 전달하지 못한다.** 계약 문제가 아니라 HTTP 프로토콜 문제이며, 한 줄로 고쳐 검증까지 마쳤다.

## 구성

| 서비스 | 포트 | 기동 조건 |
| --- | --- | --- |
| BE (Spring) | 8080 | JDK 25, Redis 8(docker), local 프로필 H2 인메모리 |
| 챗봇 (`chat_bot`) | 8001 | Python 3.14, PostgreSQL 17 + pgvector(docker), Ollama `qwen3:8b`, 임베딩 `BAAI/bge-m3` |
| 상세페이지 (`page_generation`) | 8002 | `LOCAL_IMAGE_PROVIDER=none` |

챗봇은 `verify_env.py` 전 항목 통과 후 샘플 CSV 로 **장인 52명 / 상품 832건**을 적재했다.

---

## 발견 1 — BE 의 HTTP/2 업그레이드 때문에 본문이 전달되지 않는다 (치명)

### 증상
BE 를 통해 챗봇에 메시지를 보내면 폴백 문구만 돌아왔다.

```
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

### 계약 문제가 아님을 먼저 갈랐다
BE 가 만드는 본문을 그대로 챗봇에 직접 보내면 **정상 동작**한다.

```
POST http://localhost:8001/ai/chat
{"session_id":"...","message":"엄마 환갑 선물 고급스러운 걸로 5만원대","history":[]}
→ 200
{"reply":"5만 원대 환갑 선물로 3점을 골랐어요...","intent":"gift_recommendation",
 "product_ids":[42,105,427],"suggestions":[...]}
```

### 원인 — 원시 요청을 잡아 확인
BE 가 실제로 보내는 바이트를 소켓에서 그대로 기록했다.

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

본문은 chunked 로 실려 있다. 그러나 **`Upgrade: h2c` / `Connection: Upgrade` 가 붙어 있어** uvicorn(h11)이 이를 프로토콜 업그레이드 요청으로 처리하고 본문을 애플리케이션에 넘기지 않는다. 그래서 FastAPI 는 "본문 없음"으로 422 를 반환하고, 그 뒤 연결 상태가 깨져 재시도는 `Invalid HTTP request received` 가 된다.

원인은 `HttpClient.newBuilder()` 가 **기본값 HTTP/2** 라는 점이다. 평문 HTTP 에서는 h2c 업그레이드를 시도하는데 uvicorn 은 HTTP/1.1 만 말한다.

- `RestAiChatClient.java:33`
- `RestAiContentClient.java:33` — **같은 패턴이라 상세페이지 연동도 동일하게 깨진다**

### 수정과 검증
BE 를 로컬에서 한 줄 고쳐 다시 빌드·기동했다.

```java
HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1).connectTimeout(timeout).build()
```

결과 — BE 를 통한 챗봇 추천이 끝까지 동작한다.

```
POST /api/chatbot/sessions/{id}/messages   {"content":"엄마 환갑 선물 고급스러운 걸로 5만원대"}
→ 201
reply: "5만 원대에서 고급스러운 환갑 선물로 3점을 골랐어요. 분청 다완과 분청 찻잔은
        전통 분청 기법으로 만든 작품이고, 치자염 파우치는 자연염색으로 만든 상품입니다."
intent: "gift_recommendation"
suggestions: ["분청 재질 상품","흰색 상품","여주 지역 장인"]
```

> 이 수정은 **BE 저장소에서 해야 한다.** 우리 쪽에서 할 수 있는 일이 아니며, 고치기 전에는 어떤 AI 서비스도 BE 와 통신할 수 없다.

---

## 발견 2 — 상세페이지 경로는 여전히 없다

HTTP/1.1 패치 후에도 결과는 같다.

```
POST /api/content/products/1/generations → 202 Accepted, 본문 status "FAILED"
BE 로그: reason=404 Not Found
상세페이지 로그: "POST /ai/products HTTP/1.1" 404 Not Found
```

BE 는 `AI_OLLAMA_URL`(기본 `:8002`)로 `POST /ai/products` 를 호출하는데 이 서비스에는 그 경로가 없다. 협의 문서 A-1 항목이며 우리가 맞추기로 한 부분이다.

---

## 발견 3 — 챗봇이 돌려준 `product_ids` 가 BE 상품과 맞지 않는다

챗봇은 `product_ids: [42, 105, 427]` 을 반환했지만 BE 응답의 `products` 는 **빈 배열**이었다.

- 챗봇 색인: 자체 CSV 에서 적재한 **832건**
- BE 로컬 DB: `/dev/setup` 이 만든 **1건**

BE 는 받은 id 로 자기 DB 에서 상품 카드를 조립하므로, 두 쪽 상품 집합이 다르면 추천이 화면에 뜨지 않는다. 이 테스트 환경의 데이터 차이이기도 하지만, **운영에서도 BE 의 상품 동기화가 챗봇에 도달해야만 해소된다.** 현재 BE 는 상품 동기화를 상세페이지 서버(`AI_OLLAMA_URL`)로 보내고 있어 챗봇 색인은 채워지지 않는다(`RestAiContentClient.java:64,78,92`). 협의 문서 결정 2-1 항목이다.

---

## 발견 4 — 적재 스크립트가 `.env` 를 읽지 않는다 (사소)

`app/ingest/load_products.py:574` 는 `DATABASE_URL` 환경변수 또는 내장 기본값만 본다. `.env` 의 `DB_USER` 등을 쓰지 않아 기본 사용자 `User` 로 접속을 시도하고 인증에 실패한다. `DATABASE_URL` 을 직접 지정해야 적재된다. 챗봇 README 4장 절차만 따르면 여기서 막힌다.

---

## 요약

| # | 내용 | 고칠 쪽 |
| --- | --- | --- |
| 1 | HTTP/2 업그레이드로 본문 미전달 — **모든 AI 연동이 막힘** | **BE** (한 줄, 검증 완료) |
| 2 | `POST /ai/products` 경로 없음 | 상세페이지(우리) |
| 3 | 챗봇 색인과 BE 상품 집합 불일치 — 동기화가 잘못된 서비스로 감 | BE·챗봇 합의 |
| 4 | 적재 스크립트가 `.env` 미사용 | 챗봇 |

발견 1을 고치면 챗봇 연동은 **바로 동작한다**(검증함). 상세페이지 연동은 발견 1 수정 + 우리 쪽 경로 구현이 함께 있어야 한다.

## 재현

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
```
