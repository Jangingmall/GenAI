# BE 팀 요청사항 — 실제 E2E 후속

- 작성일: 2026-09-18
- 대상 BE: `Jangingmall/backend` `develop` / `77e61ae`
- 대상 AI: `Team3_EcommerceSystemAI` `deploy/ubuntu` / `7e72afc`
- 근거: 실제 BE 컨테이너와 AI 프로세스를 기동한 HTTP E2E 재검증

## 1. 테스트 결과

FE 앱 자체 대신 FE가 호출하는 BE API를 동일한 요청으로 재현했습니다.

```text
POST /dev/setup
→ 실제 장인 JWT·상품 ID 발급

POST /api/content/products/1/generations
→ 202 PROCESSING

BE → AI POST /internal/v1/ai/detail-page-jobs
→ 202 QUEUED

AI 작업 상태
→ DRAFT_READY, progress=100

BE 폴링
→ 계속 QUEUED
```

AI 승인 단계는 BE에 연결된 승인 호출이 없어 AI 내부 승인 API를 수동으로 호출해 확인했습니다. 실제 렌더링 뒤 AI가 BE 콜백을 호출했지만 다음 순서로 막혔습니다.

1. BE 기본 multipart 첨부 개수 제한 10개로 `MaxUploadSizeExceededException` / `FileCountLimitExceededException` 500
2. 테스트 컨테이너에서 `SERVER_TOMCAT_MAX_PART_COUNT=50`을 적용하자 콜백이 컨트롤러까지 도달
3. AI 승인 generation ID가 `job UUID-approval-hash` 형식이라 BE의 `Long generationId` 변환에서 400

그 결과 BE 생성 상태는 최종까지 `QUEUED`로 남았습니다.

> 텍스트 모델 서버는 테스트용 HTTP stub을 사용했습니다. AI FastAPI, 작업 저장소, 실제 렌더러, multipart 콜백 호출은 실제 코드로 실행했습니다.

## 2. BE 요청사항

### BE-E2E-1. 승인 흐름을 BE에서 연결해 주세요 — 차단

현재 BE clone의 `src/main/java/com/jangingmall/backend/content/application/GenerationAsyncExecutor.java` 실제 흐름은 AI 작업 제출과 `QUEUED` 저장에서 끝납니다. AI는 초안 생성 후 `DRAFT_READY`에서 승인 대기하므로, 현재 구조에서는 자동으로 최종 콜백이 발생하지 않습니다.

BE에 다음 흐름을 연결해 주세요.

1. AI 작업 상태 조회: `GET /internal/v1/ai/detail-page-jobs/{jobId}`
2. `DRAFT_READY` 초안을 FE에 전달
3. 장인 승인·수정 내용을 BE가 수신
4. 필요하면 AI 초안 저장: `PUT /internal/v1/ai/detail-page-jobs/{jobId}/draft`
5. 최종 승인: `POST /internal/v1/ai/detail-page-renders`
6. AI 콜백 수신 후 BE 상태를 `COMPLETED`로 변경

현재 `/api/content/products/{productId}/contents/{contentId}/approve`는 콘텐츠 상태 변경 API이며 AI 승인 호출과 연결되어 있지 않습니다. 이 API를 확장할지, generation 전용 승인 API를 만들지 정해 주세요.

### BE-E2E-2. generation ID를 숫자 하나로 끝까지 유지해 주세요 — 차단

현재 BE clone의 `src/main/java/com/jangingmall/backend/content/presentation/AiCallbackController.java`는 `@PathVariable Long generationId`를 사용하고 callback 경로는 다음입니다.

```text
POST /internal/generations/{generationId}/completion
```

BE가 AI 작업 제출 metadata의 `options.source_generation_id`에 보낸 BE generation ID를 최초 작업·초안 승인·최종 콜백에서 동일하게 사용해야 합니다. AI 측은 이 값을 보존하고 승인 콜백에도 그대로 사용하는 수정이 반영됐습니다.

확인 요청:

- BE generation ID를 `1`, `2`와 같은 숫자 계약으로 확정
- BE가 작업 제출 시 보낸 `source_generation_id`와 callback path의 ID가 항상 동일한지 확인
- 승인 시 별도의 UUID나 suffix generation ID를 만들지 않도록 계약에 명시

### BE-E2E-3. multipart 첨부 개수와 용량을 AI 계약에 맞춰 주세요 — 차단

AI 콜백은 상세 이미지·섹션 이미지·상품 사진을 여러 multipart file part로 보냅니다. 실제 테스트에서는 총 18개 part가 생성됐고, BE 기본 첨부 개수 제한 10개에서 500이 발생했습니다.

BE 설정을 다음 기준으로 맞춰 주세요.

```yaml
server:
  tomcat:
    max-part-count: 50

spring:
  servlet:
    multipart:
      max-file-size: 10MB
      max-request-size: 120MB
```

정확한 운영 상한을 다르게 정한다면 AI의 `MAX_IMAGE_BYTES`, `MAX_REQUEST_BYTES`, 최대 section/photo 개수와 동일한 수치를 양측 계약에 기록해 주세요.

### BE-E2E-4. AI 상태를 BE generation 상태에 반영해 주세요

현재 AI가 `DRAFT_READY`가 되어도 BE 폴링 응답은 계속 `QUEUED`였습니다. 최소한 다음 상태 매핑이 필요합니다.

| AI 상태 | BE 상태/응답 | 의미 |
|---|---|---|
| `QUEUED`, `ANALYZING`, `EXTRACTING`, `GENERATING_BACKGROUNDS`, `COMPOSING`, `VERIFYING`, `RENDERING`, `DELIVERING` | `PROCESSING` 또는 진행률 포함 상태 | 작업 진행 중 |
| `DRAFT_READY` | 승인 대기 상태 | FE에 초안 노출 필요 |
| `COMPLETED` | `COMPLETED` | 최종 콜백 저장 완료 |
| `FAILED` | `FAILED` | 재시도 가능 여부 포함 |

승인 대기 상태를 기존 BE enum에 추가할지, `PROCESSING`과 별도 response field로 표현할지 결정해 주세요.

### BE-E2E-5. 로컬 E2E와 운영 S3 저장 조건을 명시해 주세요

최종 콜백은 BE의 `ImageStorage`를 통해 상세 이미지·섹션·사진을 저장합니다. 로컬 프로파일에서 S3/MinIO endpoint와 bucket이 없으면 ID·multipart 문제를 해결한 뒤 저장 단계에서 다시 막힐 수 있습니다.

- 로컬 E2E용 MinIO 또는 mock S3 endpoint
- `IMAGE_STORAGE_BUCKET`, `IMAGE_RETURN_BUCKET`, credentials, endpoint
- 운영 S3 bucket 및 권한

위 설정을 로컬 연동 가이드에 추가해 주세요.

## 3. AI 측 반영 완료

BE 코드는 수정하지 않고 AI 레포에서 다음 두 가지를 수정했습니다.

1. BE가 전달한 `options.source_generation_id`를 보존하고, Product BE 작업의 승인 callback generation ID로 재사용
2. BE의 공통 응답 `{success, status, data}`를 `data` 내부 ACK로 unwrap한 뒤 `SAVED`/`ALREADY_SAVED`를 파싱

추가 테스트:

```text
tests/test_backend_client.py
tests/test_service.py
tests/test_draft_flow.py
→ 45 passed
```

BE 승인 흐름과 multipart 설정 반영 뒤 동일한 실제 HTTP E2E를 다시 실행해 `FE API 202 → AI DRAFT_READY → 승인 → AI callback 200 → BE COMPLETED`를 확인해야 합니다.
