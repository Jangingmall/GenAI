# BE ↔ AI 연동 테스트 — 2026-09-21

> 이 문서는 2026-09-21 시점 기록이다. 이후 상태가 바뀌어도 이 문서는 고치지 않는다.

- 환경: 사내 Ubuntu 서버 `192.168.75.208` (x86_64 · 8코어 · RAM 15GB · **GPU 없음**) · 전부 **컨테이너**
- AI: `Team3_EcommerceSystemAI` `c39595d` → 이미지 `dp-ai:v5` (4.97GB)
- BE: `Jangingmall/backend` `origin/develop` `0e7a1a0` → 이미지 `be:v5` (619MB)
- 텍스트 모델: Mac 의 MLX `Qwen3.8-27B` 를 LAN(`192.168.75.24:11234`)으로 연결
- 이미지 생성: 끔 (`LOCAL_IMAGE_PROVIDER=none`)
- 앞선 테스트와의 차이: **BE 를 거쳐** 요청을 넣었다. 지금까지는 우리 엔드포인트를 직접 호출했다.

## 결론

**BE → AI 구간은 전부 이어진다.** AI → BE 콜백은 BE 안까지 도달했고, BE 가 받은
이미지를 S3 에 올리는 단계에서 멈췄다. **설정 문제이고 계약 문제가 아니다.**

```
FE 역할 → BE 생성 요청(202) → BE → AI 작업 제출(202)
       → AI 분석(DRAFT_READY) → [승인 대기]
       → 콜백 → BE 경로·파싱·조회 통과 → BE S3 업로드에서 실패
```

## 이어진 것

| 단계 | 결과 |
| --- | --- |
| BE 생성 요청 `POST /api/content/products/1/generations` | **202** `generationId=1`, `PROCESSING` |
| BE → AI 제출 `POST /internal/v1/ai/detail-page-jobs` | **202** `jobId=a0bcdbe7-…` |
| BE 이미지 fetch | 정상 (네트워크 안 URL) |
| AI 분석 | **DRAFT_READY**, progress 100 |
| BE 의 status 폴링 | 동작 (BE 가 우리 `status_url` 을 주기적으로 조회) |
| BE 데드라인 스케줄러 | 동작 (AI 컨테이너가 죽자 `AI 상태 조회 실패 … No route to host` 기록) |
| 콜백 경로 바인딩 | 통과 (`/internal/generations/1/completion`) |
| 콜백 metadata 파싱 | 통과 (`productId`, `detailPage.reactDocument` 모두 읽힘) |
| 콜백 generation 조회 | 통과 (id=1 레코드 존재) |
| BE 이미지 S3 업로드 | **실패** — 아래 참고 |

### `@Async` 수정이 동작한다

BE 응답이 `202` + `PROCESSING` 이다. 이전에는 202 안에 이미 `FAILED` 가 들어 있었다.

```
c.j.b.c.i.RestAiContentClient   : AI 콘텐츠 생성 job 제출 generationId=1 productId=1
c.j.b.c.a.GenerationAsyncExecutor: AI job 제출 완료 generationId=1 jobId=a0bcdbe7-…
```

### generationId 가 양쪽에서 맞는다 — 이전 보고를 정정한다

**앞서 "BE 의 generationId 는 Long 인데 우리는 UUID 를 보낸다"고 보고한 것은 틀렸다.**

BE 는 자기 `generationId` 를 `options.source_generation_id` 로 보낸다.

```java
// RestAiContentClient.java:172
new GenerationOptions(generationId.toString())
// record GenerationOptions(@JsonProperty("source_generation_id") String sourceGenerationId)
```

우리 코드는 그것을 받아 그대로 쓴다.

```python
# service.py:203-207
generation_id = (
    resolved_options.source_generation_id
    if product_id is not None and resolved_options.source_generation_id
    else str(uuid.uuid4())
)
```

이번 실행에서 확인한 값은 `generation_id: 1` 로, BE 의 숫자 ID 와 일치한다.
콜백 URL 도 `/internal/generations/1/completion` 으로 정확히 조립됐다.

이전에 400(`Type mismatch: generationId`)이 났던 것은 **내가 BE 를 거치지 않고
우리 엔드포인트를 직접 호출하면서 `options.source_generation_id` 를 넣지 않아
UUID 가 생성된 탓**이다. 테스트 방식의 문제였지 계약 불일치가 아니었다.

## 막힌 것

### 1. BE 콜백이 S3 버킷을 요구한다

콜백은 BE 핸들러 안쪽까지 들어갔고 마지막에 다음으로 끝났다.

```
GlobalExceptionHandler : Unhandled exception
java.lang.IllegalStateException: 공개 이미지 S3 버킷이 설정되지 않았습니다.
```

`S3ImageStorage.java:89` 이고, 설정 키는 `IMAGE_UPLOAD_BUCKET` 이다. `local`
프로파일의 기본값이 빈 문자열이라 로컬에서는 콜백이 끝까지 성공할 수 없다.

**우리 쪽에서 고칠 것은 없다.** 로컬·CI 에서 콜백까지 검증하려면 BE 가 버킷을
설정하거나 MinIO 같은 대체재를 붙여야 한다. 이 항목은 BE 에 요청한다.

곁들여, 이 예외가 **500** 으로 나간다. 설정 누락이라 502/503 계열이 더 맞고,
지금은 우리 쪽에서 "우리 페이로드가 잘못됐나" 와 구분되지 않는다.

### 2. 렌더가 이 서버에서 완주하지 못한다 — 우리 쪽 한계

승인·렌더 요청을 넣으면 AI 컨테이너가 `Exit 137` 로 죽는다. 누끼(rembg)가
CPU 로 돌면서 프로세스가 약 12.9 GiB 를 점유하는데, 이 서버의 가용 메모리가
13 GiB 라 Chromium 까지 얹히면 넘어간다. 세 번 시도해 세 번 모두 같은 결과였다.

측정값은 [`eks-workload-spec.md`](../operations/eks-workload-spec.md) 1-4 절에 있다.
`deploy/sglang/Dockerfile` 은 `onnxruntime-gpu` 로 바꿔 두었으므로 **GPU 노드에서는
이 경로가 VRAM 으로 옮겨간다.** 다만 GPU 가 없어 확인하지 못했다.

**이 서버는 렌더 검증용으로 적합하지 않다.** 연동 계약 검증에는 충분하다.

### 3. 승인 주체가 아직 정해지지 않았다 (BE-11)

우리는 `DRAFT_READY` 에서 멈추고 승인을 기다린다. 그동안 BE 는 `QUEUED` 로 남는다.

```
GET /api/content/products/1/generations/1
{"generationId":1,"productId":1,"status":"QUEUED","completedAt":null}
```

BE 의 1861초 데드라인이 지나면 이 작업은 `FAILED` 로 처리된다. 회신 문서
[`be-handoff-2026-09-18b.md`](../operations/be-handoff-2026-09-18b.md) 4절의
A/B/C 중 하나를 정해야 한다.

## 관측된 차이 — BE 는 실제로 폴링한다

BE 전달사항 문서에는 "`statusUrl` 폴링 없이 콜백과 데드라인 스케줄러로만 완료를
처리한다"고 되어 있었으나, 실제로는 BE 컨테이너(`172.27.0.4`)가 우리
`/internal/v1/ai/detail-page-jobs/{job_id}` 를 주기적으로 조회했다.

문제는 아니지만, 우리가 드린 `status_url` 응답 스키마 회신이 문서상 선택 항목이
아니라 **이미 쓰이고 있는 계약**이라는 뜻이다.

## 재현

```bash
docker network create it5
docker run -d --name rd5 --network it5 redis:8
docker run -d --name imgsrv5 --network it5 -v ~/it5:/usr/share/nginx/html:ro nginx:alpine

docker build -f page_generation/deploy/Dockerfile -t dp-ai:v5 page_generation
docker run -d --name dp5 --network it5 -p 8005:8000 \
  -e LOCAL_TEXT_PROVIDER=mlx -e LOCAL_TEXT_URL=http://<모델서버>:11234 \
  -e LOCAL_IMAGE_PROVIDER=none -e BACKGROUND_PROVIDER=none \
  -e AI_INTERNAL_AUTH_TOKEN=<토큰> \
  -e BACKEND_URL=http://be5:8080 -e BACKEND_AUTH_TOKEN=<토큰> dp-ai:v5

cd backend && docker build --target local -t be:v5 .
docker run -d --name be5 --network it5 -p 8085:8080 \
  -e SPRING_PROFILES_ACTIVE=local -e SPRING_DATA_REDIS_HOST=rd5 \
  -e AI_CONTENT_URL=http://dp5:8000 \
  -e AI_INTERNAL_AUTH_TOKEN=<토큰> -e BACKEND_AUTH_TOKEN=<토큰> be:v5

curl -X POST localhost:8085/dev/setup          # 장인·상품·토큰 생성
curl -X POST localhost:8085/api/content/products/1/generations \
  -H "Authorization: Bearer <TOKEN>" -H 'Content-Type: application/json' \
  -d '{"images":["http://imgsrv5/fan.jpg"],"productName":"초충도 부채 세트", ...}'
```

`BACKEND_URL` 은 **기저 주소**다. 콜백 경로는
`/internal/generations/{generation_id}/completion` 으로 우리가 조립한다.
