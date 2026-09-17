# 3자 로컬 연동 로그 — 2026-09-17

세 서비스를 모두 로컬에 띄우고 FE 역할의 요청을 BE 에 넣어 흐름을 따라간 기록이다. **BE 는 저장소 원본 상태(패치 없음)** 로 실행했다.

| 파일 | 내용 |
| --- | --- |
| `be-ai-2026-09-17.log` | BE 가 AI 를 호출한 결과 (AI 호출 관련 행만 추출) |
| `chatbot-2026-09-17.log` | 챗봇이 받은 요청 |
| `pagegen-2026-09-17.log` | 상세페이지 서비스가 받은 요청 |
| `transcript-2026-09-17.log` | FE 역할로 보낸 요청과 받은 응답 전문 |

## 구성

| 서비스 | 포트 | 상태 |
| --- | --- | --- |
| BE (Spring, `1e04949`) | 8080 | JDK 25 · Redis 8 · H2 인메모리 |
| 챗봇 (`GenAI/chat_bot`) | 8001 | pgvector · Ollama `qwen3:8b` · bge-m3 · 장인 52명/상품 832건 적재 |
| 상세페이지 (`GenAI/page_generation`) | 8002 | `LOCAL_IMAGE_PROVIDER=none` |

기동 직후 세 서비스 모두 정상 응답했다 (`BE=200 chatbot=200 pagegen=200`).

## 흐름별 결과

| 흐름 | 결과 |
| --- | --- |
| A. 챗봇 세션 생성 | **201** 정상 |
| B. 챗봇 메시지 전송 | 201 이지만 본문은 폴백 — `"현재 AI 추천을 이용할 수 없습니다"`, `intent: null`, `products: []` |
| C. 상세페이지 생성 요청 | **202** 이지만 본문 `status` 가 이미 `FAILED` |
| D-1. AI → BE 콜백 (우리 multipart) | **HTTP 500**, `retryable=True` |
| D-2. AI → BE 콜백 (BE 기대 JSON) | **200**, generation 이 `COMPLETED` 로 전이 |

## 발견된 문제

1. **BE → 챗봇: 422 → 400 → 400.** BE 가 HTTP/2 업그레이드(`Upgrade: h2c`)를 붙여 보내 uvicorn 이 본문을 앱에 넘기지 않는다. 재시도 2회는 연결이 깨져 프로토콜 오류가 된다.
2. **BE → 상세페이지: 404.** `POST /ai/products` 경로가 이 서비스에 없다.
3. **AI → BE: 500.** 우리가 multipart 로 보내는데 BE 콜백은 JSON `{reactDocument}` 만 받는다. 500 이라 우리 쪽은 재시도 대상으로 오판한다.
4. **202 안에 `FAILED`.** 동기 호출이 즉시 실패한 뒤 202 로 감싸진다.
5. **콘텐츠 생성은 재시도가 없다.** 챗봇 호출은 3회 시도했지만 콘텐츠 생성은 1회 호출 후 즉시 실패로 끝났다.

각 문제의 원인과 요청 사항은 [`../../api/be-request-2026-09-17.md`](../../api/be-request-2026-09-17.md) 에 정리했다. 원시 HTTP 캡처를 포함한 분석은 [`../three-service-integration-test-2026-09-17.md`](../three-service-integration-test-2026-09-17.md) 에 있다.
