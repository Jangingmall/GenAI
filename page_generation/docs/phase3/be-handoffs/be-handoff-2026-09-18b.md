# BE 전달사항 회신 — 2026-09-18

- 수신 문서: 「AI팀 전달사항」 기준일 2026-09-18, 커밋 `8a6df578`
- 회신: 생성형 AI 팀 (상세페이지 생성)

## 요약

| 항목 | 상태 |
| --- | --- |
| 1. `status_url` GET 응답 스키마 | **아래 2절에 정의.** 이미 구현돼 있고 계약만 없었습니다 |
| 2-1. 이미지 리다이렉트 (BE-12) | 확인. 저희 쪽 조치 없음 |
| 2-2. 데드라인 스케줄러 | **확인했고, 이것 때문에 BE-11 결정이 급해졌습니다** (4절) |
| 3. 콜백 경로 재확인 (BE-9) | 확인. 저희가 그 경로로 조립해 보내도록 수정 중입니다 (3절) |

---

## 1. 먼저 알려드릴 함정 — 표기법이 두 군데서 다릅니다

같은 서비스인데 **상태 조회 응답은 snake_case, 콜백 metadata 는 camelCase** 입니다.

| 경로 | 표기 |
| --- | --- |
| `GET /internal/v1/ai/detail-page-jobs/{job_id}` (`status_url`) | `product_id`, `job_id`, `request_id`, `updated_at` |
| AI → BE 콜백 `metadata` | `productId`, `generationId`, `detailPage.reactDocument` |

콜백 쪽은 BE 가 camelCase 로 읽는다고 하셔서 저희가 맞춘 것입니다. 상태 조회는
그대로 snake_case 입니다. **폴링을 붙이실 때 같은 파서를 쓰시면 깨집니다.**

원하시면 상태 조회도 camelCase 로 맞추겠습니다. 다만 이미 쓰고 계신 곳이 있으면
깨지므로, **바꿀지 여부를 알려주세요.** 저희가 임의로 바꾸지 않겠습니다.

---

## 2. `status_url` GET 응답 스키마

```
GET /internal/v1/ai/detail-page-jobs/{job_id}
X-AI-Internal-Token: {AI_INTERNAL_AUTH_TOKEN}
```

`POST` 응답의 `status_url` 은 이 경로를 가리킵니다.

### 응답 본문

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `product_id` | string | 예 | 요청 시 보내신 상품 식별자 |
| `job_id` | string | 예 | 작업 식별자 |
| `request_id` | string | 예 | 요청 추적용 식별자 |
| `status` | string (enum) | 예 | 아래 상태값 |
| `progress` | integer | 예 | 0–100 |
| `updated_at` | string (ISO 8601, UTC) | 예 | 마지막 갱신 시각 |
| `draft` | object \| null | 아니오 | `DRAFT_READY` 이후에만 채워집니다 |
| `result` | object \| null | 아니오 | `COMPLETED` 이후에만 채워집니다 |
| `error` | object \| null | 아니오 | `FAILED` 일 때만 채워집니다 |

### `status` 값

```
QUEUED  ANALYZING  EXTRACTING  GENERATING_BACKGROUNDS  COMPOSING
VERIFYING  RENDERING  DELIVERING  DRAFT_READY  COMPLETED  FAILED
```

`DRAFT_READY` 는 **초안이 준비된 상태이지 완료가 아닙니다.** 4절을 함께 보십시오.

### 실제 응답 예 (진행 중)

```json
{
  "product_id": "fan5",
  "job_id": "7a03cd4c-2931-4d32-9c37-e8345e8ab313",
  "request_id": "3bc9566a-4f91-4929-9df5-a2fb13e3e4ba",
  "status": "ANALYZING",
  "progress": 15,
  "draft": null,
  "result": null,
  "error": null,
  "updated_at": "2026-09-18T06:09:44.077715Z"
}
```

`draft` · `result` 의 내부 구조는 콜백으로 보내는 것과 같은 스키마입니다.
폴링만 하실 거면 **`status` 와 `progress` 만 보셔도 충분합니다.**

### 폴링을 붙이실 때

- 인증 헤더 `X-AI-Internal-Token` 이 필요합니다. 없으면 401 입니다.
- 폴링 간격은 **5초 이상**을 권합니다. 상세페이지 1건이 초안까지 로컬 실측 약
  100–160초 걸립니다. 그보다 잦게 부르셔도 얻는 게 없습니다.
- 폴링은 콜백을 대체하지 않습니다. 저희는 완료 시 콜백을 겁니다.

---

## 3. 콜백 경로 — 저희 쪽 수정 중

정정해 주신 경로를 정본으로 받았습니다.

```
POST /internal/generations/{generationId}/completion
```

**저희 구현이 이 경로를 보내지 못하는 상태였습니다.** 설정값 `BACKEND_URL` 이
단일 주소라 건마다 다른 `{generationId}` 를 경로에 넣지 못했고, 그래서 지난
연동 테스트에서 콜백을 수동으로 보냈습니다.

기저 주소에서 경로를 조립하도록 수정 중이며, 이번 연동 테스트에서 자동 콜백까지
확인하겠습니다. BE 쪽에 필요한 조치는 없습니다.

`Idempotency-Key` 를 `{generationId}` 로 달라고 하신 것도 함께 맞춥니다.

---

## 4. 데드라인 스케줄러와 BE-11 — **결정이 필요합니다**

1861초 데드라인을 넣으셨다는 것은, BE 가 **작업 제출 후 약 31분 안에 콜백이
온다고 가정**하신 것입니다. 저희 설계와 맞지 않는 부분이 있어 말씀드립니다.

### 저희 파이프라인의 현재 흐름

```
작업 접수(202) → 분석 → DRAFT_READY  ← 여기서 멈춥니다
                              ↓
                          승인(approve)
                              ↓
                      렌더 → 콜백 → COMPLETED
```

`DRAFT_READY` 다음은 **승인 단계**이고, 콜백은 승인 뒤에 일어납니다. 지난
연동 테스트에서 BE 가 10분간 `QUEUED` 로 남아 있던 이유가 이것입니다.

### 그래서 생기는 문제

**승인이 사람 손을 거치면 31분을 넘길 수 있습니다.** 장인이 초안을 보고 고치는
시간이니 31분은 넉넉한 시간이 아닙니다. 그 경우 BE 는 실제로는 정상인 작업을
`FAILED` 로 처리합니다.

### 정해 주셔야 할 것

**누가 언제 승인합니까?** 선택지는 셋입니다.

| 안 | 내용 | BE 영향 | AI 영향 |
| --- | --- | --- | --- |
| A | **초안 시점에 콜백**하고, 승인은 BE·FE 쪽에서 | 초안을 받아 저장·표시하는 흐름 필요 | 콜백 시점만 앞당기면 됨 |
| B | 승인을 자동화(초안=최종) | 없음 | 승인 단계 제거 |
| C | 현행 유지 + 데드라인을 사람 검수 시간에 맞게 연장 | 데드라인 값 재조정 | 없음 |

**저희 의견은 A 입니다.** 초안을 만드는 것까지가 AI 의 일이고, 그것을 사람에게
보여주고 승인받는 것은 BE·FE 의 화면에서 일어나는 일이라고 보기 때문입니다.
A 로 가면 31분 데드라인도 저희 생성 시간(약 3분)에만 걸리므로 충분합니다.

B 는 장인이 초안을 고칠 수 없게 되므로 제품 결정이 필요합니다.
C 는 데드라인을 사람 검수 시간만큼(수 시간) 늘려야 해서 안전망 역할을 못 합니다.

**A/B/C 중 무엇으로 갈지 회신 부탁드립니다.** 정해지기 전까지 저희는 현행
흐름을 유지하며, 연동 테스트에서는 승인을 즉시 수행해 확인하겠습니다.

---

## 5. 저희 쪽 진행 상황

| 항목 | 상태 |
| --- | --- |
| 콜백 경로 조립 | 수정 중 |
| `Idempotency-Key` = generationId | 함께 수정 |
| `status_url` 스키마 | 이 문서 2절로 계약 |
| 표기법 통일 | **BE 결정 대기** (1절) |
| 승인·콜백 시점 | **BE 결정 대기** (4절) |
