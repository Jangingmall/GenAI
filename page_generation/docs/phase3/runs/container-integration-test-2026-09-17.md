# 컨테이너 연동 테스트 — 2026-09-17

> 이 문서는 2026-09-17 시점 기록이다. 이후 상태가 바뀌어도 이 문서는 고치지 않는다.

- 환경: Ubuntu 서버(사내 LAN, x86_64 · 8코어 · RAM 15GB · **GPU 없음** · Docker 29.6.2)
- 대상: `page_generation`(`04c1387`) · `Jangingmall/backend`(`1e04949`)
- 앞선 테스트와의 차이: **두 서비스를 프로세스가 아니라 컨테이너로 올려** 도커 네트워크로 붙였다.

## 이번에 처음 확인된 것

### 이미지가 실제로 빌드된다

지금까지 모든 문서에 "이 Dockerfile 은 아직 빌드하지 않았다"고 적어 왔다. **이번에 처음 빌드했다.**

| 이미지 | 빌드 | 크기 |
| --- | --- | ---: |
| `deploy/Dockerfile` (상세페이지 서비스) | 성공 | **4.99 GB** |
| `backend/Dockerfile --target local` (BE) | 성공 | 619 MB |

`deploy/sglang/Dockerfile`(SGLang + CUDA)은 이 서버에 GPU 가 없어 빌드·실행하지 않았다. **여전히 미빌드다.**

### 컨테이너 런타임 성질

| 확인 | 결과 |
| --- | --- |
| 컨테이너 상태 | `Up (healthy)` — Dockerfile 의 `HEALTHCHECK` 가 실제로 동작 |
| 실행 사용자 | `appuser` (비 root) |
| 내부 포트 | **8000** — 로컬 재현에서 쓰던 8002 는 호스트 매핑일 뿐이다 |
| 서비스 디스커버리 | `AI_OLLAMA_URL=http://dp-ai:8000` 으로 컨테이너 이름 해석 동작 |
| `GET /health` | 200 |
| `GET /health/ready` | 모델 서버 없으면 503 + 사유, 연결되면 200 |

### 연동 결과는 프로세스 때와 같다

```
BE 컨테이너 : AI 콘텐츠 생성 실패 generationId=1
              reason=404 Not Found: {"detail":"Not Found"}
AI 컨테이너 : 172.26.0.4 - "POST /ai/products HTTP/1.1" 404 Not Found
```

**실행 방식을 컨테이너로 바꿔도 달라지지 않는다.** 문제는 계약이지 배포 형태가 아니다.

---

## BE 코드를 더 읽어 확인한 문제 두 가지

### 1. `@Async` 가 동작하지 않는다 — 자기 호출이라 프록시를 우회한다

`GenerationService.java:45` 가 같은 클래스의 `executeAsync`(`:73`)를 **직접 호출**한다.

```java
ContentGeneration saved = generationRepository.save(generation);
executeAsync(saved.getId(), command);   // ← 같은 클래스 내부 호출
...
@Async
public void executeAsync(Long generationId, GenerationCommand.Request command) { ... }
```

Spring 의 `@Async` 는 프록시를 통해 동작한다. **같은 빈 안에서 자기 메서드를 부르면 프록시를 거치지 않아 애노테이션이 무효**가 되고 요청 스레드에서 그대로 실행된다. `@EnableAsync` 는 `global/config/AsyncConfig.java:6` 에 정상적으로 선언돼 있으므로 설정 문제가 아니다.

이것이 앞서 관측한 **"202 Accepted 안에 이미 `FAILED` 가 들어 있는"** 현상의 원인이다. AI 호출이 응답 직렬화 전에 끝나 버린다.

**영향은 실패했을 때만이 아니다.** AI 가 정상 동작하면 이 호출은 **성공할 때까지 요청 스레드를 붙잡는다.** 상세페이지 1건 생성은 이번 측정에서 초안까지만 160초였다. FE 와 BE 가 그 시간 동안 함께 대기하게 된다.

### 2. `/ai/products` 의 응답 본문을 그대로 react_document 로 저장한다

`GenerationService.java:77-89`:

```java
String reactDocumentJson = aiContentClient.requestGeneration(...);
generation.complete(reactDocumentJson);
contentService.storeReactDocument(new ContentCommand.StoreReactDocument(..., reactDocumentJson, ...));
```

BE 는 `POST /ai/products` 의 **동기 응답 본문이 완성된 react_document 라고 가정**한다. 검증 없이 문자열 그대로 저장한다.

그런데 같은 BE 에 **콜백 경로도 있다**(`POST /internal/generations/{id}/complete`, `AiCallbackRequest.java:10`). 완료 처리 경로가 **둘**이고, 실제로 도는 것은 동기 경로다.

**이것이 우리 구현을 막는다.** `/ai/products` 를 만들 때 무엇을 반환해야 하는지가 정해지지 않는다.

- BE 가 지금 구조를 유지하면 → 우리는 **react_document 를 동기 응답으로** 돌려줘야 하고, 호출이 수 분간 블로킹된다
- BE 가 `@Async` 를 고치고 콜백을 쓰면 → 우리는 **202 를 즉시 반환**하고 완료 시 콜백해야 한다

지금 상태에서 우리가 202 접수 응답을 돌려주면, BE 는 그 **접수 응답 JSON(`{"job_id":...}`)을 react_document 로 저장**한다. 오류 없이 잘못된 데이터가 들어간다.

---

## 챗봇은 컨테이너로 올릴 수 없다

`Jangingmall/GenAI` 의 `chat_bot/` 에 **Dockerfile 이 없다.** 저장소 전체에도 없다(`page_generation/` 제외). 인프라팀이 요청한 "런타임별 Dockerfile" 기준으로 챗봇은 아직 배포 가능한 형태가 아니다. 이번 테스트에서 챗봇은 컨테이너로 올리지 못했다.

## 이 서버에 대해

사내 LAN 의 이 Ubuntu 서버는 **배포 대상이 아니다.** GPU 가 없고 RAM 이 15GB 라 27B 텍스트 모델과 FLUX 를 올릴 수 없다. 연동·회귀 테스트용이다. 실제 배포 대상은 AWS 다(`docs/phase4/operations/ubuntu-deployment.md:3` — EC2 `g6e.xlarge`, L40S 48GB).

이번 파이프라인 실행은 GPU 가 없어 **Mac 의 MLX(Qwen3.8-27B)를 LAN 으로 연결해** 돌렸다. 서버에서 `192.168.75.24:11234` 로 도달했고 초안까지 160초가 걸렸다.

## 재현

```bash
docker network create itest-net
docker run -d --name redis --network itest-net redis:8
docker build -f deploy/Dockerfile -t detail-page-ai:itest .
docker run -d --name dp-ai --network itest-net -p 8002:8000 \
  -e LOCAL_TEXT_PROVIDER=mlx -e LOCAL_TEXT_URL=http://<모델서버>:11234 \
  -e LOCAL_IMAGE_PROVIDER=none -e AI_INTERNAL_AUTH_TOKEN=<토큰> \
  -v dp-data:/var/lib/detail-page-ai detail-page-ai:itest

cd backend && docker build --target local -t jangingmall-be:itest .
docker run -d --name be --network itest-net -p 8080:8080 \
  -e SPRING_PROFILES_ACTIVE=local -e SPRING_DATA_REDIS_HOST=redis \
  -e AI_OLLAMA_URL=http://dp-ai:8000 jangingmall-be:itest
```
