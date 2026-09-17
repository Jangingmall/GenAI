# BE ↔ AI 연동 협의 요청

- 보내는 곳: 생성형 AI 팀
- 받는 곳: BE 팀
- 작성일: 2026-09-17
- 근거: `docs/evaluation/be-integration-test-2026-09-17.md` (실제 두 서비스를 띄워 측정한 기록)

## 요약

2026-09-17 에 `Jangingmall/backend` (`1e04949`) 를 받아 로컬에서 실제로 띄우고 AI 서비스와 붙여 봤습니다. **현재 두 시스템은 어느 방향으로도 연결되지 않습니다.**

- BE → AI: `POST /ai/products` 가 **404**. 생성이 즉시 `FAILED` 로 끝납니다.
- AI → BE: 우리가 보내는 multipart 를 BE 가 **500** 으로 거부합니다.

다만 **`react_document` 는 양쪽이 이미 같은 것을 씁니다.** BE 콜백에 JSON `{"reactDocument": {...}}` 로 보내면 **200 이고 generation 이 `COMPLETED` 로 넘어가는 것까지 확인**했습니다. 형식 문제는 대부분 우리가 맞추면 됩니다.

**형식보다 먼저 정해야 할 것이 두 가지 있습니다.** 이건 코드로 해결되는 문제가 아니라 제품 결정입니다.

---

## 먼저 결정할 것 2가지

### 결정 1. AI 가 이미지를 생성합니까?

| | 내용 |
| --- | --- |
| BE 계약서 5-4 | "이미지 직접 생성 없음 — 장인이 업로드한 사진을 블록에 배치" |
| 현재 AI 구현 | FLUX 로 활용 장면·디테일 컷을 **생성**하고, rembg 로 배경을 제거한 컷을 만듭니다 |

**이건 형식 차이가 아니라 기능 범위 차이입니다.** 어느 쪽으로 정하느냐에 따라 아래 항목 절반의 답이 바뀝니다.

- **생성한다면**: AI 가 만든 새 이미지를 어디에 저장하고 어떻게 전달할지 정해야 합니다. 현재 AI 는 이미지 바이트를 multipart 로 보내고, BE 콜백은 `reactDocument` 하나만 받습니다. 저장 위치(BE S3 업로드 API / AI 가 직접 S3 / 다른 방법)가 비어 있습니다.
- **생성하지 않는다면**: AI 는 업로드 사진을 배치하고 문구만 만듭니다. 이미지 파이프라인(FLUX·rembg)은 이 연동에서 빠집니다. 전달할 것이 `reactDocument` 뿐이라 **연동이 크게 단순해집니다.**

> AI 팀 의견: 계약서대로 **이미지 생성 없이** 시작하고, 생성 컷은 합의 후 별도 단계로 붙이는 편이 빠릅니다. 지금 막힌 지점 대부분이 "새로 만든 이미지를 어떻게 넘기느냐"에서 나옵니다.

### 결정 2. 추천 챗봇(`POST /ai/chat`)은 누가 만듭니까?

BE 는 `AI_SGLANG_URL` 로 `POST /ai/chat` 을 호출하도록 돼 있고(`AiProperties.java`, 계약서 4장), 계약서는 임베딩(BGE-M3/KURE-v1)·하이브리드 검색(Vector+BM25+RRF)·인증 등급 가중 랭킹을 전제합니다.

**이 저장소에는 챗봇이 없습니다.** 상세페이지 생성만 구현돼 있습니다. 챗봇을 누가 언제 만드는지, 별도 서비스인지 확인 부탁드립니다. 현재로서는 `/ai/chat` 호출은 계속 404 입니다.

---

## 항목별 분류

### A. 우리(AI)가 맞추겠습니다 — BE 변경 불필요

| # | 항목 | 현재 | 맞출 방향 |
| --- | --- | --- | --- |
| A-1 | 생성 요청 경로 | AI 는 `POST /internal/v1/ai/detail-page-jobs` | **`POST /ai/products` 를 AI 에 추가**합니다 (`RestAiContentClient.java:53`) |
| A-2 | 요청 형식 | AI 가 multipart 요구 → BE JSON 에 422 | **JSON 수용**. BE 가 보내는 `{generationId, productId, images[], productName, howMade, careTips}` 그대로 받습니다 |
| A-3 | 이미지 전달 | AI 가 바이트 multipart 기대 | **URL 목록 수용**. BE 가 주는 이미지 URL 을 AI 가 내려받습니다 |
| A-4 | 콜백 경로·형식 | AI 가 단일 URL 로 multipart POST | **`POST /internal/generations/{generationId}/complete` 에 JSON `{"reactDocument": ...}`** 로 보냅니다 (실측 200 확인) |
| A-5 | 콜백 응답 파싱 | AI 가 `{generation_id, product_id, status, saved_at}` 만 허용, 추가 필드 거부 | **BE 공통 포맷 `{success, status, data}` 를 받아들이도록** 고칩니다 |
| A-6 | ID 타입 | AI 는 문자열 | **숫자 ID 수용**. BE 의 `Long` 을 그대로 받습니다 |
| A-7 | 동기화 API | 없음 | 결정 1·2 확정 후 `POST /ai/products/sync`, `PUT`/`DELETE /ai/products/{id}` 추가 여부를 정합니다 |

A-1 ~ A-6 은 **BE 코드를 하나도 바꾸지 않아도** 되는 항목입니다.

### B. BE 쪽 확인·수정이 필요합니다

| # | 항목 | 실측 내용 | 요청 |
| --- | --- | --- | --- |
| B-1 | AI 서버 주소 | BE 가 콘텐츠 생성을 `ollamaUrl`(기본 `http://localhost:8002`)로 호출 (`application.yml:146`) | **AI 서비스는 하나이고 포트는 `8000`** 입니다. 인프라 구성상 GPU 워크로드를 하나(L40S ×1)만 씁니다. `AI_SGLANG_URL`·`AI_OLLAMA_URL` 을 같은 주소로 두거나 단일 설정으로 합쳐 주세요 |
| B-2 | `.env` 미동작 | 가이드 1장이 루트 `.env` 로 `AI_OLLAMA_URL` 을 설정하라고 하지만 `build.gradle` 에 dotenv 의존성이 없어 Spring 이 읽지 않습니다. 기본값으로 호출됐습니다 | 가이드를 고치거나 dotenv 를 추가해 주세요. AI 팀이 로컬 재현할 때 첫 번째로 걸립니다 |
| B-3 | 실패 시 재시도 | 계약서 3-6 은 "최대 2회 재시도" 인데, BE 로그에는 **1회 호출 후 즉시 실패**로 남았습니다 | 재시도가 구현돼 있는지 확인 부탁드립니다 |
| B-4 | 202 안의 FAILED | `POST .../generations` 가 `202 Accepted` 를 주는데 본문 `status` 가 이미 `FAILED` 였습니다. AI 호출이 동기로 일어나 즉시 실패한 뒤 202 로 감싸집니다 | 비동기(계약서 5-1)가 의도라면 호출을 분리해 주세요. FE 가 202 를 성공으로 오인합니다 |
| B-5 | 문서와 코드 불일치 | 계약서 5-3 은 출력이 블록 배열(`{order, tag, text, imageUrl}`)인데, `AiCallbackController` 는 `reactDocument` 를 받습니다 (`AiCallbackRequest.java:8-11`) | **어느 쪽이 정본입니까?** 저희는 코드 기준(`reactDocument`)으로 맞추겠습니다 |

### C. 합의가 필요합니다

| # | 항목 | 쟁점 |
| --- | --- | --- |
| C-1 | **이미지 생성 여부** | 위 결정 1. 계약서 5-4 와 현재 AI 구현이 다릅니다 |
| C-2 | **생성 이미지 저장 위치** | C-1 이 "생성한다" 로 정해질 때만 필요합니다. AI 가 만든 이미지를 BE S3 업로드 API 로 넘길지, AI 가 직접 저장할지. 현재 AI 서비스는 AWS SDK 의존성이 없고 산출물을 로컬 볼륨에 둡니다 |
| C-3 | **챗봇 담당** | 위 결정 2 |
| C-4 | **인증** | AI 의 `/internal/v1/ai/*` 는 `X-AI-Internal-Token` 을 요구합니다(없으면 401). BE 클라이언트는 인증 헤더를 보내지 않습니다. 반대로 BE 의 `/internal/generations/{id}/complete` 도 인증 없이 열려 있었습니다. **양방향 내부 호출 인증을 어떻게 할지** 정해야 합니다. 토큰 발급 주체도 함께 정해 주세요 |
| C-5 | **처리 시간과 타임아웃** | BE 는 `AI_TIMEOUT_SECONDS` 기본 300초입니다. 상세페이지 1건 생성은 로컬 Apple Silicon 기준 **평균 226초**였고, 서버 GPU 실측은 아직 없습니다. 이미지 생성을 포함하면 300초를 넘길 수 있습니다. 폴링 구조라면 AI 는 요청을 즉시 접수(202)하고 완료 시 콜백하는 편이 안전합니다 |

---

## 저희가 제안하는 순서

1. **결정 1·2 회신** (이미지 생성 여부, 챗봇 담당) — 나머지가 여기 달려 있습니다
2. **C-4 인증 방식 합의** — 구현 전에 정해야 양쪽 다 한 번에 끝납니다
3. AI 가 A-1 ~ A-6 구현 → 로컬에서 재연동 테스트
4. B-1 ~ B-4 BE 쪽 수정
5. C-5 타임아웃은 서버 GPU 실측 이후 확정

## 재현 방법

이 문서의 모든 수치는 아래로 재현됩니다.

```bash
# BE (JDK 25 필요)
docker run -d -p 6379:6379 redis:8
AI_OLLAMA_URL=http://localhost:8000 ./gradlew bootRun

# AI
uvicorn detail_page_ai.app:app --port 8000

# 흐름
curl -X POST localhost:8080/dev/setup
curl -X POST localhost:8080/api/content/products/1/generations \
  -H "Authorization: Bearer <ARTISAN_TOKEN>" -H 'Content-Type: application/json' \
  -d '{"images":["..."],"productName":"...","howMade":"...","careTips":"..."}'
```

## 참고 — 현재 AI 서비스 상태

- 상세페이지 생성 파이프라인과 `react_document` 조립은 구현·테스트 완료 (테스트 358개 통과)
- 서버 배포 구성(SGLang, L40S ×1)은 정의 완료, **GPU 에서는 아직 한 번도 실행되지 않았습니다**
- 추천 챗봇은 구현돼 있지 않습니다
