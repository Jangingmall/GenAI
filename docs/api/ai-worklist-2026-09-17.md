# AI 작업 목록 — 2026-09-17

- 범위: 이 저장소에서 생성형 AI 팀이 고칠 항목
- 근거: [`be-ai-integration-negotiation.md`](be-ai-integration-negotiation.md)의 A 항목과 [`be-request-2026-09-17.md`](be-request-2026-09-17.md)의 「저희(AI)가 맡아서 하는 것」
- `docs/evaluation/`은 시점 기록이므로 수정하지 않습니다.

> **차단:** `/ai/products`의 응답 형식은 BE 회신([D-1](open-decisions-2026-09-17.md#d-1-post-aiproducts-응답)) 전에는 구현할 수 없습니다. 지금 BE는 그 응답을 완성된 `react_document`로 저장하므로, 접수 응답(`{"job_id":...}`)을 먼저 반환하면 오류 없이 잘못된 데이터가 저장됩니다.

## 설계 결함 — BE의 응답 형식과 무관하게 정리할 것

| ID | 원문 항목 | 현재 근거 | 닿는 파일 | 작업 |
| --- | --- | --- | --- | --- |
| AI-D1 | A-4 콜백 경로·형식 | `backend_url`을 그대로 클라이언트 URL로 넘기고(`factory.py:131-138`), `BackendProductClient`가 그 URL로 바로 multipart POST를 합니다(`backend_client.py:86-100,157-180`). | `src/detail_page_ai/config.py:62-66`, `src/local_detail_page_ai/factory.py:131-138`, `src/detail_page_ai/backend_client.py:86-196` | 콜백 엔드포인트 경로를 조립할 수 있도록 계약된 경로와 요청 형식을 정리합니다. 최종 경로는 D-1·D-2 합의와 맞춥니다. |
| AI-D2 | A-5 ACK 스키마 경직 | BE ACK 모델이 `generation_id`, `product_id`, `status`, `saved_at`만 받고(`dto.py:571-575`), `BeToAiPersistAckDto`와 응답 envelope가 `extra="forbid"`입니다(`ai_dto.py:28-31,134-138`). | `src/detail_page_ai/ai_dto.py:28-31,134-138`, `src/detail_page_ai/dto.py:571-575`, `src/detail_page_ai/backend_client.py:172-190` | BE 공통 포맷 `{success, status, data}`를 받아들이고 내부 ACK로 변환합니다. 알 수 없는 응답은 계속 오류로 처리하되 현재의 flat ACK만 허용하지 않습니다. |
| AI-D3 | A-3 이미지 바이트만 수용 | 현재 BE 전달이 `files`의 바이트 multipart입니다(`backend_client.py:106-155`). 생성 이미지 전달 방법은 BE 콜백이 `reactDocument`만 받는 C-1 쟁점입니다. | `src/detail_page_ai/backend_client.py:106-155`, `src/detail_page_ai/config.py:62-66`, `src/detail_page_ai/dto.py:504-565` | D-2에서 정한 방식에 따라 이미지 URL 목록·BE 업로드 ID·콜백 확장 중 확정된 계약을 수용합니다. D-2 회신 전에는 구현을 확정하지 않습니다. |

## BE 계약에 맞추는 작업

| ID | 원문 항목 | 현재 근거 | 닿는 파일 | 작업·의존성 |
| --- | --- | --- | --- | --- |
| AI-1 | A-1 생성 요청 경로 | 현재 public 경로는 `app.py:214-218`의 `/api/v1/ai/detail-page-jobs`, 내부 경로는 `app.py:325-329`의 `/internal/v1/ai/detail-page-jobs`입니다. | `src/detail_page_ai/app.py:214-266,325-380` | `POST /ai/products` 경로를 추가합니다. 단, 어떤 응답을 반환할지는 **D-1 회신 전 차단**입니다. |
| AI-2 | A-2 요청 형식 | 현재 내부 생성 요청은 `UploadFile`·`File`과 `metadata`·`Form`을 받습니다(`app.py:330-346`). 메타데이터 모델도 별도로 검증합니다(`ai_dto.py:34-46`). | `src/detail_page_ai/app.py:330-364`, `src/detail_page_ai/ai_dto.py:34-46` | BE가 보내는 JSON 본문 `{generationId, productId, images[], productName, howMade, careTips}`를 수용하도록 요청 DTO와 엔드포인트를 맞춥니다. |
| AI-3 | A-6 ID 타입 | Product BE 경계 DTO의 `product_id`가 현재 문자열입니다(`ai_dto.py:39,76,87,117,131`; `dto.py:504-505`). | `src/detail_page_ai/ai_dto.py:34-46,73-95,114-132`, `src/detail_page_ai/dto.py:504-505` | BE의 `Long`을 숫자 ID로 수용하고, 상태·승인·저장 요청의 ID를 같은 타입으로 전달합니다. |
| AI-4 | 힌트 필드명 매핑 | AI 모델은 `product_name`, `making_method`, `care_guide`를 사용합니다(`fe_dto.py:61-80`, `dto.py:118-140`). 현재 app 입력도 snake_case 이름입니다(`app.py:219-249`). | `src/detail_page_ai/app.py:219-249`, `src/detail_page_ai/fe_dto.py:61-80`, `src/detail_page_ai/dto.py:118-140` | BE 계약의 `productName`↔`product_name`, `howMade`↔`making_method`, `careTips`↔`care_guide`를 명시적 alias/변환으로 매핑합니다. |

## D-4 이후 후속 — 원문 A-7

동기화 API는 세 주체의 경로 합의 뒤에 처리합니다. 원문은 결정 1·2가 확정되면 `POST /ai/products/sync`, `PUT`/`DELETE /ai/products/{id}` 추가 여부를 정하도록 되어 있습니다. 챗봇 라우팅(BE-3)과 [D-4](open-decisions-2026-09-17.md#d-4-post-aiproducts-경로-의미)를 먼저 확정합니다.

닿는 파일: `src/detail_page_ai/app.py:214-266,325-380`, `src/detail_page_ai/ai_dto.py:34-46,49-70`.

---

## 주체별 문서

- [BE 인계 목록](be-handoff-2026-09-17.md)
- [양측 합의 필요 사항](open-decisions-2026-09-17.md)
