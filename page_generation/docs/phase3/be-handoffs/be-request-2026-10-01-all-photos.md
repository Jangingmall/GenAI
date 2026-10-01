# BE 요청 — 판매자 사진 전체 전송 · 렌더 자동 요청(#105) 확인 결과

- 작성: 2026-10-01 · 생성형 AI 팀 (상세페이지 생성)
- BE 대조 기준: `Jangingmall/backend` `develop` `2ed3603` (2026-10-01, #105·#106 포함)
- 확인 방법: AI 서비스·로컬 모델·렌더러는 실제 코드로 실행했다. BE 쪽은 `RestAiContentClient` 의 요청을 같은 필드·헤더로 재현했고, BE 콜백은 테스트 수신기로 받았다. **실제 BE 컨테이너와의 연동 테스트는 아니다**
- 입력: 전주 합죽선 · 매화선, 판매자 입력 3개(상품명·제작 과정·관리 방법), 판매자 사진 5장 (CDN 과 같은 가로 1280 WebP 로 변환)

---

## 요약

| # | 내용 | BE 조치 |
| --- | --- | --- |
| 1 | #105 의 렌더 자동 요청·재요청이 AI 와 맞는지 확인했습니다 | **불필요** — 그대로 동작합니다 |
| 2 | 판매자 사진을 **첫 장만** 보내고 있습니다 | **요청** — 나머지 사진도 `product_images` 로 보내 주세요 |

---

## 1. 렌더 자동 요청(#105) — 확인 완료

`AiRenderApprovalAsyncExecutor` → `RestAiContentClient.approveRender` 와 같은 요청을 보냈습니다.
상태 응답의 `draft.draft` 를 그대로 담은 multipart `metadata`, 헤더·본문 멱등성 키 `render-{generationId}` 입니다.

| 호출 | BE 가 기대하는 응답 | AI 응답 |
| --- | --- | --- |
| 첫 렌더 요청 | 200 | **200** `COMPLETED` (로컬 176~214초) |
| 렌더 중 재요청 (스케줄러 재시도) | 409 + `Approval is already in progress` → 정상 처리 | **409, 같은 문구** (즉시) |
| 완료 후 재요청 | 오류 없음 | **200**, 저장된 같은 결과 |
| 완료 콜백 | 1회 | **1회** (재요청으로 다시 콜백하지 않음) |
| 콜백 파일명 | `{generationId}-photo-{NN}-{photo_id}` 로 사진 ID 추출 | `17-photo-05-detail-02.png` 형식으로 보냄 — 일치 |

- 9/29 전달 문서에서 "BE 는 승인을 재시도하지 않아 409 를 받을 일이 없다"고 적었는데, #105 부터는 재요청하며 409 를 정상으로 처리합니다. 위 표대로 맞습니다
- 렌더가 BE 타임아웃(300초)을 넘겨도 BE 의 다음 재요청은 409 를 받고, 결과는 콜백으로 따로 저장됩니다

## 2. 요청 — 판매자 사진 전체 전송

### 지금

`RestAiContentClient.submitJob` → `fetchFirstImage(images, …)` 가 **`images.getFirst()` 한 장만** 내려받아 `product_image` 로 보냅니다.
판매자가 사진을 여러 장 올려도 AI 는 첫 장만 받습니다.

### 요청

나머지 사진도 같은 요청에 **`product_images` 파트로 반복**해서 보내 주세요. 계약([`../api/be-fe-ai-integration-spec.md`](../api/be-fe-ai-integration-spec.md) 4.1, [`../api/ai-dto-contract.md`](../api/ai-dto-contract.md))에 이미 있는 필드입니다.

```text
POST /internal/v1/ai/detail-page-jobs   (multipart/form-data)
  metadata         지금과 같음
  product_image    첫 번째 사진 (지금과 같음)
  product_images   두 번째 사진
  product_images   세 번째 사진
  …
```

| 항목 | 값 |
| --- | --- |
| 파트 이름 | `product_images` — 같은 이름을 사진 수만큼 반복 (`body.add("product_images", …)` 여러 번) |
| 각 파트 Content-Type | 지금 `product_image` 와 같이 `sniffImage` 로 판별한 `image/png`·`image/jpeg`·`image/webp` |
| 최대 장수 | `product_image` 포함 **12장** (넘으면 413) |
| 크기 | 장당 **10MB**, 합계 **120MB** (넘으면 413) |
| 순서 | 첫 장이 대표 사진. **AI 는 상품 분석(문구)에 첫 장만 쓰므로** 대표 사진을 첫 장으로 유지해 주세요 |

- 추가 사진 중 일부를 내려받지 못한 경우: 첫 장만 받으면 상세페이지는 만들 수 있으니, **실패한 추가 사진만 빼고 제출**하는 것을 권합니다. 작업 전체를 실패시킬지는 BE 에서 정해 주세요
- 승인(`detail-page-renders`) 요청에는 사진을 다시 보낼 필요가 없습니다. AI 가 접수 때 받은 사진을 저장해 씁니다

### 보내면 달라지는 것 (같은 상품·같은 입력으로 비교)

| 항목 | 지금 (사진 1장) | 5장 전송 시 |
| --- | --- | --- |
| 상세페이지에 쓰인 판매자 실제 사진 | 1장 (나머지는 그 사진을 자르거나 AI 생성) | **5장** — 대표·패키지·디테일·사용 장면·추가 사진에 실제 사진 |
| AI 생성 사진 | 5장 | 5장 (1장은 미사용) |
| 렌더 시간 (로컬) | 214초 | 176초 |
| BE 콜백 파트 수 | 18개 (상품 사진 8) | 19개 (상품 사진 9, 미사용 1장은 보내지 않음 — `product_photo_06` 번호가 비어 있음) |

- BE `application.yml` 의 `max-part-count: 50`·`max-request-size: 120MB` 안에 들어갑니다 (5장 시험 콜백 합계 9.4MB). 12장은 시험하지 않았습니다
- 미사용 사진은 콜백에서 빠져 `product_photo_NN` 번호가 이어지지 않을 수 있습니다. 사진 ID는 파일명(`{generationId}-photo-{NN}-{photo_id}`)으로 읽으므로 BE 처리에는 영향이 없습니다

## 3. AI 쪽 후속 (BE 조치 아님)

여러 장을 받았을 때 AI 가 맞춰야 할 점이 시험에서 보였습니다. AI 팀이 처리합니다.

- 상품 분석이 첫 장만 봅니다. 사진마다 모습이 다르면 문구와 사진이 어긋날 수 있습니다
- 실제 사진이 충분해도 AI 생성 사진을 같은 수만큼 만듭니다
