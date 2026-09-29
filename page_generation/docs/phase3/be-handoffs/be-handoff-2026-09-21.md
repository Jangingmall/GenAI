# BE 요청 — 2026-09-21

- 근거: [`be-ai-integration-test-2026-09-21.md`](../runs/be-ai-integration-test-2026-09-21.md)
- 대상 커밋: `Jangingmall/backend` `origin/develop` `0e7a1a0`
- 회신: 생성형 AI 팀 (상세페이지 생성)

## 먼저 좋은 소식

**BE 를 거쳐 넣은 첫 연동 테스트에서 BE → AI 구간이 전부 이어졌습니다.**

| 단계 | 결과 |
| --- | --- |
| 생성 요청 | **202** `generationId=1` · `PROCESSING` |
| BE → AI 제출 | **202** `jobId` 발급 |
| 이미지 fetch | 정상 |
| AI 분석 | `DRAFT_READY` |
| 콜백 경로 바인딩 | 통과 |
| 콜백 metadata 파싱 | 통과 (`productId`, `detailPage.reactDocument`) |
| 콜백 generation 조회 | 통과 |

`@Async` 수정이 동작합니다. 202 안에 `FAILED` 가 들어 있던 현상은 사라졌습니다.

### 앞서 드린 우려 하나를 저희가 정정합니다

지난 회신에서 **"BE 의 `generationId` 는 `Long` 인데 저희는 UUID 를 보냅니다"** 라고
말씀드렸는데, **틀렸습니다. 이미 맞습니다.**

BE 가 `options.source_generation_id` 로 자기 ID 를 보내 주고 계시고
(`RestAiContentClient.java:172`), 저희가 그 값을 그대로 씁니다. 이번 실행에서
`generation_id = 1` 로 확인했고 콜백 URL 도
`/internal/generations/1/completion` 으로 정확히 조립됐습니다.

앞선 400 은 **저희가 BE 를 거치지 않고 저희 엔드포인트를 직접 호출하면서 그 필드를
빠뜨린 탓**이었습니다. 저희 테스트 방식의 문제였지 BE 계약의 문제가 아니었습니다.
혼선을 드려 죄송합니다.

---

## 요청 1 — 콜백이 S3 버킷을 요구해 로컬에서 끝까지 갈 수 없습니다

콜백이 BE 핸들러 안쪽까지 들어가 조회까지 통과한 뒤 다음으로 끝났습니다.

```
GlobalExceptionHandler : Unhandled exception
java.lang.IllegalStateException: 공개 이미지 S3 버킷이 설정되지 않았습니다.
```

- 위치: `S3ImageStorage.java:89`
- 설정 키: `IMAGE_UPLOAD_BUCKET`
- `local` 프로파일 기본값이 빈 문자열입니다 (`application.yml:52`)

**저희 쪽에서 고칠 것은 없습니다.** 다만 이 상태에서는 **로컬이나 CI 에서 콜백이
성공하는 것을 누구도 확인할 수 없습니다.** 저장 단계 직전까지만 검증됩니다.

부탁드릴 것은 둘 중 하나입니다.

| 방안 | 내용 |
| --- | --- |
| A | `local` 프로파일에서 MinIO 같은 대체 스토리지를 붙여 주세요 |
| B | 버킷이 없을 때는 이미지 업로드를 건너뛰고 `reactDocument` 만 저장하도록 해 주세요 |

**B 를 권합니다.** 연동 테스트의 목적은 계약 확인이고, 이미지가 실제로 S3 에
올라가는지는 배포 환경에서 확인할 일이기 때문입니다. A 는 로컬 구성이 하나 더
늘어납니다.

## 요청 2 — 설정 누락이 500 으로 나갑니다

위 예외가 **500 Internal Server Error** 로 돌아옵니다. 저희 입장에서는
**"우리 페이로드가 잘못됐다"와 "BE 설정이 비어 있다"가 구분되지 않습니다.**

이번에도 처음에는 저희 직렬화를 의심하고 한참을 뒤졌습니다.

설정 누락은 요청의 잘못이 아니므로 **503** 이 더 맞고, 본문에 어떤 설정이
비었는지 한 줄 남겨 주시면 저희가 바로 압니다. 같은 맥락에서 지난 회신에 적은
**없는 경로에 404 대신 500 이 나가는 것**도 아직 그대로입니다.

---

## 아직 회신을 기다리는 것 — 승인·콜백 시점 (BE-11)

[`be-handoff-2026-09-18b.md`](be-handoff-2026-09-18b.md) 4절에서 A/B/C 로 여쭌
항목입니다. **이번 테스트에서 실제로 문제가 됐습니다.**

저희는 `DRAFT_READY` 에서 멈추고 승인을 기다립니다. 그동안 BE 는 `QUEUED` 입니다.

```
GET /api/content/products/1/generations/1
{"generationId":1,"productId":1,"status":"QUEUED","completedAt":null}
```

**1861초가 지나면 이 작업은 정상인데도 `FAILED` 가 됩니다.** 사람이 초안을 보고
고치는 시간이 31분을 넘기면 그렇게 됩니다.

저희 의견은 여전히 **A(초안 시점에 콜백하고 승인은 BE·FE 에서)** 입니다.

## 관측된 차이 — 폴링을 하고 계십니다

전달사항 문서에는 "`statusUrl` 폴링 없이 콜백과 데드라인 스케줄러로만 완료를
처리한다"고 되어 있었는데, 실제로는 BE 컨테이너가 저희
`/internal/v1/ai/detail-page-jobs/{job_id}` 를 주기적으로 조회했습니다.
데드라인 스케줄러도 정상 동작했습니다(저희 컨테이너가 죽자
`AI 상태 조회 실패 … No route to host` 를 남겼습니다).

문제는 아닙니다. 다만 저희가 드린 **`status_url` 응답 스키마가 선택 항목이 아니라
이미 쓰이고 있는 계약**이라는 뜻이라, 표기법 차이를 다시 짚어 드립니다.

| 경로 | 표기 |
| --- | --- |
| 상태 조회 (`status_url`) | **snake_case** — `product_id`, `job_id`, `updated_at` |
| 콜백 metadata | **camelCase** — `productId`, `detailPage.reactDocument` |

같은 파서를 쓰시면 깨집니다. 상태 조회도 camelCase 로 맞출까요? 이미 쓰고 계신
곳이 있으면 깨지므로 **저희가 임의로 바꾸지 않겠습니다.** 알려 주세요.

---

## 저희 쪽 남은 한계 (참고)

승인·렌더 단계는 사내 테스트 서버에서 완주하지 못했습니다. 누끼(rembg)가 CPU 에서
약 12.9 GiB 를 쓰는데 그 서버 가용 메모리가 13 GiB 라 컨테이너가 죽습니다.
GPU 노드에서는 `onnxruntime-gpu` 로 옮기도록 이미지에 반영했으나 저희에게 GPU 가
없어 확인하지 못했습니다. **BE 와는 무관한 저희 쪽 사정**이며, 첫 AWS 배포에서
확인할 항목입니다.
