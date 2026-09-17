# BE ↔ AI 연동 협의 요청

> 이 문서는 주체별로 다음 세 문서로 갈라졌습니다. 아래 본문은 이력 보존을 위해 그대로 남겨 둡니다.
>
> - [BE 팀 인계](be-handoff-2026-09-17.md)
> - [AI 작업 목록](ai-worklist-2026-09-17.md)
> - [양측 합의 필요 사항](open-decisions-2026-09-17.md)

- 보내는 곳: 생성형 AI 팀
- 받는 곳: BE 팀
- 작성일: 2026-09-17
- 근거: `docs/evaluation/be-integration-test-2026-09-17.md` (실제 두 서비스를 띄워 측정한 기록)

## 요약

2026-09-17 에 `Jangingmall/backend` (`1e04949`) 를 받아 로컬에서 실제로 띄우고 AI 서비스와 붙여 봤습니다. **현재 두 시스템은 어느 방향으로도 연결되지 않습니다.**

- BE → AI: `POST /ai/products` 가 **404**. 생성이 즉시 `FAILED` 로 끝납니다.
- AI → BE: 우리가 보내는 multipart 를 BE 가 **500** 으로 거부합니다.

다만 **`react_document` 는 양쪽이 이미 같은 것을 씁니다.** BE 콜백에 JSON `{"reactDocument": {...}}` 로 보내면 **200 이고 generation 이 `COMPLETED` 로 넘어가는 것까지 확인**했습니다. 형식 문제는 대부분 우리가 맞추면 됩니다.

**형식보다 먼저 정할 것이 있습니다.** 코드로 해결되는 문제가 아니라 제품 결정입니다.

---

## 먼저 결정할 것 2가지

### 결정 1. AI 가 이미지를 생성합니다 — BE 계약서와 다릅니다

**AI 팀 결정: 생성합니다.** 이 항목은 저희 쪽에서 확정했고, BE 계약서와 다르다는 점을 알려 드립니다.

| | 내용 |
| --- | --- |
| BE 계약서 5-4 | "이미지 직접 생성 없음 — 장인이 업로드한 사진을 블록에 배치" |
| **AI 실제 동작** | 장인이 올린 사진을 **먼저** 역할에 배정하고, **채우지 못한 역할과 보조 컷(활용 장면·디테일)을 생성**합니다 |

상세페이지는 대표 컷·패키지샷·디테일·활용 장면을 필요로 하는데 장인이 그만큼 올리지 않는 경우가 많습니다. 그래서 **제공 사진을 우선 쓰되 모자란 만큼 채우는** 방식입니다. 장인이 올린 사진은 한 장도 버리지 않습니다.

- 생성 컷은 `product_generated=true` 와 `asset_mode`(`generated_scene` / `generated_view`)로 **구분해 전달**합니다. 상품 사실의 근거로 쓰지 않으며, 화면에 별도 '참고용' 표시는 붙이지 않습니다.
- 생성 장수는 설정(`MAX_GENERATED_PHOTOS`, 기본 5)으로 조절되며, **`0` 으로 두면 생성을 전혀 하지 않습니다.**

> **BE 팀 확인 요청**: 계약서 5-4 를 현재 동작에 맞게 고칠지, 아니면 생성을 끄는 쪽(`MAX_GENERATED_PHOTOS=0`)으로 갈지 회신 부탁드립니다. 끄는 것은 설정 한 줄이라 언제든 되돌릴 수 있습니다. 다만 **생성을 유지한다면 아래 C-1(생성 이미지를 어떻게 넘길지)을 반드시 먼저 정해야 합니다.**

### 결정 2. 추천 챗봇은 별도 서비스입니다 — 확인 완료

추천 챗봇은 **`Jangingmall/GenAI` 저장소의 `chat_bot/`** 에 있습니다. 이 저장소(상세페이지 생성)와는 **다른 서비스**이며, 통합은 나중 단계입니다.

따라서 BE 의 두 URL 설정은 **그대로 두는 것이 맞습니다.**

| BE 설정 | 가리킬 서비스 | 제공 |
| --- | --- | --- |
| `AI_SGLANG_URL` | `GenAI/chat_bot` | `POST /ai/chat`, `GET /ai/health` |
| `AI_OLLAMA_URL` | **이 저장소 (상세페이지 생성)** | 상세페이지 생성 |

> 앞서 저희가 "AI 서비스는 하나이니 두 URL 을 합쳐 달라"고 적었던 부분은 **철회합니다.** 서비스가 둘이 맞습니다.

### 결정 2-1. `POST /ai/products` 가 세 곳에서 서로 다른 뜻입니다 — 정리가 필요합니다

같은 경로를 세 곳이 다르게 씁니다.

| 주체 | `POST /ai/products` 의 의미 | 본문 |
| --- | --- | --- |
| BE `RestAiContentClient.java:54` | **상세페이지 생성 요청** | `{generationId, productId, images[], productName, howMade, careTips}` |
| `GenAI/chat_bot` `app/main.py:112` | **추천 색인용 상품 upsert** | `{artisan, product}` |
| BE 계약서 5-3 | 상품 게시 시점 **동기화** | `{artisan, product}` |

여기서 두 가지 문제가 나옵니다.

1. **BE 는 상품 동기화를 `AI_OLLAMA_URL`(= 상세페이지 서버)로 보냅니다**(`RestAiContentClient.java:64,78,92`). 그런데 그 데이터가 실제로 필요한 곳은 **추천 색인을 가진 챗봇**입니다. 지금 설정대로면 챗봇은 상품 동기화를 영영 받지 못하고, 추천에 상품이 노출되지 않습니다.
2. **챗봇에는 `/ai/products/sync` 가 없습니다.** 챗봇은 upsert 를 `POST /ai/products` 로 받습니다. BE 가 부르는 `/ai/products/sync` 와 경로가 다릅니다.

**제안**: 상품 동기화 3종(`sync`, `PUT`, `DELETE`)은 **챗봇 서비스(`AI_SGLANG_URL`)로 보내고**, 상세페이지 생성만 `AI_OLLAMA_URL` 로 보내 주세요. 경로 이름은 세 팀이 한 번에 맞추는 편이 낫습니다. 저희는 어느 쪽으로 정하든 따르겠습니다.

---

## 항목별 분류

### A. 우리(AI)가 맞추겠습니다 — BE 변경 불필요

| # | 항목 | 현재 | 맞출 방향 |
| --- | --- | --- | --- |
| A-1 | 생성 요청 경로 | AI 는 `POST /internal/v1/ai/detail-page-jobs` | **`POST /ai/products` 를 AI 에 추가**합니다 (`RestAiContentClient.java:54`) |
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
| B-1 | 상품 동기화를 받는 쪽 | BE 가 상품 동기화 3종을 `ollamaUrl`(상세페이지 서버)로 보냅니다 (`RestAiContentClient.java:64,78,92`) | 위 **결정 2-1** 참고. 동기화는 추천 색인을 가진 **챗봇 서비스**로 가야 합니다. 두 URL 설정 자체는 그대로 두시면 됩니다 |
| B-2 | `.env` 미동작 | 가이드 1장이 루트 `.env` 로 `AI_OLLAMA_URL` 을 설정하라고 하지만 `build.gradle` 에 dotenv 의존성이 없어 Spring 이 읽지 않습니다. 기본값으로 호출됐습니다 | 가이드를 고치거나 dotenv 를 추가해 주세요. AI 팀이 로컬 재현할 때 첫 번째로 걸립니다 |
| B-3 | 실패 시 재시도 | 계약서 3-6 은 "최대 2회 재시도" 인데, BE 로그에는 **1회 호출 후 즉시 실패**로 남았습니다 | 재시도가 구현돼 있는지 확인 부탁드립니다 |
| B-4 | 202 안의 FAILED | `POST .../generations` 가 `202 Accepted` 를 주는데 본문 `status` 가 이미 `FAILED` 였습니다. AI 호출이 동기로 일어나 즉시 실패한 뒤 202 로 감싸집니다 | 비동기(계약서 5-1)가 의도라면 호출을 분리해 주세요. FE 가 202 를 성공으로 오인합니다 |
| B-5 | 문서와 코드 불일치 | 계약서 5-3 은 출력이 블록 배열(`{order, tag, text, imageUrl}`)인데, `AiCallbackController` 는 `reactDocument` 를 받습니다 (`AiCallbackRequest.java:10`) | **어느 쪽이 정본입니까?** 저희는 코드 기준(`reactDocument`)으로 맞추겠습니다 |

### C. 합의가 필요합니다

| # | 항목 | 쟁점 |
| --- | --- | --- |
| **C-1** | **생성 이미지를 어떻게 넘깁니까 — 가장 급한 항목** | AI 가 이미지를 생성하기로 확정됐습니다(결정 1). 그런데 **넘길 방법이 없습니다.** BE 콜백은 `reactDocument` 하나만 받고(`AiCallbackRequest.java:10`), 현재 AI 는 이미지 바이트를 multipart 로 보냅니다. 셋 중 하나를 정해 주세요 — ① BE 가 이미지 업로드 API 를 열고 AI 가 그리로 올린 뒤 받은 `imageId` 를 `reactDocument` 에 심는다 ② AI 가 S3 에 직접 올리고 URL 을 심는다(현재 AI 는 AWS SDK 의존성이 없어 추가 작업이 필요합니다) ③ 콜백 본문을 확장해 이미지를 함께 받는다. **저희는 ①을 권합니다** — 이미지 저장·CDN 은 이미 BE 책임이고(계약서 5-5), AI 에 S3 권한을 새로 주지 않아도 됩니다 |
| C-2 | 계약서 5-4 수정 여부 | 위 결정 1. 계약서를 현재 동작에 맞출지, 생성을 끌지(`MAX_GENERATED_PHOTOS=0`) |
| C-3 | `/ai/products` 경로 정리 | 위 결정 2-1. BE·상세페이지·챗봇 세 곳이 같은 경로를 다르게 씁니다 |
| C-4 | **인증** | AI 의 `/internal/v1/ai/*` 는 `X-AI-Internal-Token` 을 요구합니다(없으면 401). BE 클라이언트는 인증 헤더를 보내지 않습니다. 반대로 BE 의 `/internal/generations/{id}/complete` 도 인증 없이 열려 있었습니다. **양방향 내부 호출 인증을 어떻게 할지** 정해야 합니다. 토큰 발급 주체도 함께 정해 주세요 |
| C-5 | **처리 시간과 타임아웃** | BE 는 `AI_TIMEOUT_SECONDS` 기본 300초입니다. 상세페이지 1건 생성은 로컬 Apple Silicon 기준 **평균 226초**였고, 서버 GPU 실측은 아직 없습니다. 이미지 생성을 포함하면 300초를 넘길 수 있습니다. 폴링 구조라면 AI 는 요청을 즉시 접수(202)하고 완료 시 콜백하는 편이 안전합니다 |

---

## 저희가 제안하는 순서

1. **C-1 회신 — 생성 이미지를 어떻게 넘길지.** 가장 급합니다. 이것이 정해져야 A-4 콜백 구현을 시작할 수 있습니다
2. **결정 2-1 회신 — 상품 동기화를 어디로 보낼지와 `/ai/products` 경로 정리**
3. **C-4 인증 방식 합의** — 구현 전에 정해야 양쪽 다 한 번에 끝납니다
4. AI 가 A-1 ~ A-6 구현 → 로컬에서 재연동 테스트
5. B-1 ~ B-5 BE 쪽 수정
6. C-5 타임아웃은 서버 GPU 실측 이후 확정

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

- 상세페이지 생성 파이프라인과 `react_document` 조립은 구현·테스트 완료 (테스트 362개 통과)
- 사진 배정은 **장인이 올린 사진을 먼저 역할에 배정**하고 모자란 만큼만 생성합니다. 올린 사진은 한 장도 버리지 않습니다
- 서버 배포 구성(SGLang, L40S ×1)은 정의 완료, **GPU 에서는 아직 한 번도 실행되지 않았습니다**
- 추천 챗봇은 이 저장소에 없습니다. `Jangingmall/GenAI` 의 `chat_bot/` 이 담당하며 통합은 나중 단계입니다
