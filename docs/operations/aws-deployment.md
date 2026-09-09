# AWS 이관·검증 가이드 (상세페이지 AI)

작성일: 2026-09-09 · 대상: 상세페이지 생성 AI 서비스 (챗봇 제외)

이 문서는 로컬 Apple Silicon에서 동작 중인 상세페이지 파이프라인을 AWS EKS GPU 노드에
올려 **1건 end-to-end 생성까지 확인**하는 것을 목표로 한다. 아래 수치는 2026-09-09 로컬
실측이며, 추정치는 추정이라고 표시했다.

## 1. 구성 요소와 포트

| 구성 | 포트 | 역할 | 현재 상태 |
|---|---|---|---|
| ai-service (FastAPI) | **8000** | job 접수·상태·draft·승인, React 문서 조립, PNG 렌더, BE 전달 | 동작 |
| 추론 서버 | **11234** | 텍스트 분석 + 이미지 생성 (OpenAI 호환) | **Apple Silicon 전용 (MLX Serve)** |

ai-service는 추론 서버를 `LOCAL_TEXT_URL` / `LOCAL_IMAGE_URL` 두 환경변수로만 참조한다.
**추론 서버를 무엇으로 바꾸든 OpenAI 호환 계약(`/v1/models`, `/v1/chat/completions`,
`/v1/images/edits`)만 지키면 애플리케이션 코드는 바뀌지 않는다.** 이관 리스크를 이 경계
안에 가두는 것이 이 설계의 핵심이다.

## 2. 지금 그대로는 뜨지 않는다 — 갭 3가지

정직하게 먼저 적는다. 아래 세 가지가 해결되기 전에는 EKS에서 파이프라인이 완주하지 않는다.

1. **MLX Serve는 Apple Silicon 전용이다.** CUDA 노드에서 실행되지 않는다. 텍스트는 vLLM,
   이미지는 diffusers 기반 서버로 대체해야 한다.
2. **가중치 포맷이 MLX 4bit다.** `ddalcu/Qwen3.8-27B-MLX-Serve-4bit`(18.2GB),
   `mlx-community/flux2-klein-9b-4bit`(9.5GB)는 CUDA 스택에서 읽지 못한다.
   AWQ/GPTQ(텍스트), safetensors 또는 bitsandbytes 4bit(이미지)로 다시 확보해야 한다.
3. **`Dockerfile`이 없다.** 컨테이너화가 착수되지 않았다.

## 3. 이관 경로 두 가지

### A안 — 전체 이관 (최종 목표)

파드 하나에 컨테이너 3개, 또는 노드 하나에 파드 2개.

```text
[ai-service :8000]  --HTTP-->  [text-infer :11234]   vLLM, Qwen3.8 27B (AWQ/GPTQ 4bit)
        |            --HTTP-->  [image-infer :11235]  diffusers FastAPI, Flux2 Klein 9B
        +-- EBS PVC (sqlite, asset store)
```

- 텍스트와 이미지 추론을 **같은 노드**에 둔다. 이미지 응답이 base64 2~3MB이고 페이지당
  7~8회 오가므로 노드 경계를 넘기면 그대로 비용·지연이 된다.
- 이미지 서버는 **동시성 1 + 요청 큐**로 둔다. diffusion은 배칭 이득이 적고 VRAM 스파이크로
  OOM이 나기 쉽다. 상세페이지는 비동기 job이라 큐잉이 자연스럽다.
- 두 모델을 **상주**시킨다. 요청마다 로드하면 job마다 수 분이 붙는다. 대신 readiness probe를
  **모델 로드 완료 기준**으로 걸어야 로드 중인 파드로 트래픽이 가지 않는다.

### B안 — 분리 검증 (권장 선행 단계)

CUDA 재포팅 결과를 기다리지 않고 **AWS 쪽 절반을 먼저 검증**하는 경로다.

- ai-service만 EKS에 올리고, `LOCAL_TEXT_URL` / `LOCAL_IMAGE_URL`을 Colab/GCP에 띄운 추론
  서버로 향하게 한다.
- 이렇게 하면 컨테이너 기동, 환경변수, EBS 영속화, 보안 그룹, BE 전달(outbox)까지
  **모델과 무관한 구간을 먼저 확정**할 수 있다.
- 인프라가 지적한 "모델과 인프라를 동시에 처음 켜는" 위험을 이 단계에서 제거한다.

## 4. 컨테이너 이미지 규격

### ai-service

| 항목 | 값 |
|---|---|
| 베이스 | `python:3.13-slim` (CUDA 불필요 — GPU를 직접 쓰지 않는다) |
| 런타임 의존 | fastapi, uvicorn, httpx, pillow, pydantic-settings, python-multipart |
| 추가 런타임 | **Node.js + Playwright Chromium** — 최종 PNG 렌더가 `scripts/runtime/render_detail_page.mjs`를 subprocess로 실행한다 |
| 예상 크기 | **약 1.5~2GB** (Chromium이 대부분, 추정) |
| 진입점 | `serve-ai` → `uvicorn detail_page_ai.app:app --host 0.0.0.0 --port 8000` |

> Chromium을 빼면 이미지가 300MB 수준으로 줄지만 승인 후 PNG 산출이 불가능해진다.
> PNG를 별도 렌더 워커로 분리하는 선택지가 있으나 이번 검증 범위에서는 한 컨테이너에 둔다.

### 추론 서버

| 항목 | 값 |
|---|---|
| 베이스 | `nvidia/cuda:12.x-runtime-ubuntu22.04` |
| 텍스트 | vLLM + Qwen3.8 27B (AWQ 또는 GPTQ 4bit) |
| 이미지 | PyTorch + diffusers + Flux2 Klein 9B |
| 예상 크기 | **약 8~12GB** (가중치 제외, 추정) |

## 5. GPU 사이징

| 항목 | 추정 |
|---|---|
| 텍스트 27B 4bit 가중치 | ~16GB |
| Flux2 Klein 9B fp16 | ~18GB |
| KV 캐시·활성화 | 나머지 |
| **필요 인스턴스** | **g6e (L40S 48GB)** |

**g4dn(T4 16GB)에는 올라가지 않는다.** 4bit를 이미 적용한 상태에서 가중치만 27.7GB다.

모델 컨텍스트가 174k라 기본값으로 두면 KV 캐시가 VRAM을 잠식한다. 상세페이지 분석은
이미지 1장 + 힌트로 수천 토큰이면 충분하므로 **`max_model_len`을 실제 사용량으로 제한**해야
한다. 이 설정을 놓치면 이미지 모델이 올라갈 자리가 없어진다.

## 6. 모델 가중치 배포 (S3)

```text
s3://jangin-{env}-s3-models/
  detail-page/
    text/qwen3.8-27b-<quant>/     # AWQ 또는 GPTQ, 용량 재산정 필요
    image/flux2-klein-9b-<fmt>/   # safetensors 또는 bnb-4bit
```

HuggingFace 직접 다운로드는 NAT Gateway를 경유해 GB당 $0.059가 붙는다. 현재 MLX 기준
27.7GB이면 회당 약 $1.63, 11일 매일이면 약 $18이다. S3 Gateway Endpoint를 타면 무료다.
**단 CUDA 재포팅 후 양자화 포맷이 바뀌면 용량이 달라지므로, 최종 용량은 재포팅 확정 후 산정한다.**

## 7. 상태(state) 처리 — 반드시 확인할 것

ai-service는 두 곳에 **로컬 파일로 상태를 쓴다.**

| 환경변수 | 기본값 | 내용 |
|---|---|---|
| `SQLITE_PATH` | `.local/detail-page-ai/state.sqlite3` | job, lease, outbox |
| `ASSET_STORE_DIR` | `.local/detail-page-ai/assets` | 원본·생성 이미지 자산 |

**컨테이너 기본 상태로 두면 파드 재시작 시 진행 중 job과 미전송 outbox가 사라진다.**
EBS PVC를 붙여 두 경로를 영속화하거나, S3 백엔드로 바꾸는 작업이 필요하다.
Spot 인스턴스를 쓴다면 이 영속화가 전제 조건이다.

## 8. 환경변수 (AWS에서 반드시 설정)

| 변수 | 값 | 비고 |
|---|---|---|
| `LOCAL_TEXT_URL` | `http://127.0.0.1:11234` | 추론 서버 주소. B안에서는 외부 주소 |
| `LOCAL_IMAGE_URL` | `http://127.0.0.1:11234` | 이미지 서버를 분리하면 `:11235` |
| `LOCAL_TEXT_MODEL` | CUDA 재포팅 후 모델 ID | 현재 `ddalcu/Qwen3.8-27B-MLX-Serve-4bit` |
| `LOCAL_IMAGE_MODEL` | 〃 | 현재 `mlx-community/flux2-klein-9b-4bit` |
| `AI_INTERNAL_AUTH_TOKEN` | **필수** | `/internal/v1/ai/*` 접근 토큰 |
| `BACKEND_PRODUCT_URL` | 상품 BE 주소 | outbox 전달 대상 |
| `BACKEND_AUTH_TOKEN` | 상품 BE 토큰 | |
| `AI_CORS_ORIGINS` | FE 오리진 | 기본값은 로컬 전용 |
| `SQLITE_PATH` / `ASSET_STORE_DIR` | PVC 마운트 경로 | 7절 참고 |
| `PROMPT_VERSION` | `local-mlx-qwen-flux-v1` | 산출물 provenance 기록에 쓰임 |

전체 목록은 `.env.example`을 따른다. 외부 모델 API 키는 **없다** — 운영 경로에 외부 모델
호출이 존재하지 않는다.

## 9. 네트워크 / 보안 그룹

| 방향 | 포트 | 대상 |
|---|---|---|
| 인바운드 | 8000 | ai-service. FE와 상품 BE가 호출 |
| 내부 | 11234 (필요 시 11235) | 추론 서버. 같은 파드면 loopback이라 규칙 불필요 |
| 아웃바운드 | 443 | 상품 BE 전달, S3(Gateway Endpoint 경유) |

추론 포트는 현재 `127.0.0.1` 바인딩이다. 추론을 별도 파드로 분리할 때만 인바운드 규칙이
추가로 필요하다.

## 10. 검증 절차

각 단계는 **실패 시 원인을 분리할 수 있도록** 배치했다. 앞 단계를 건너뛰지 않는다.

### 0단계 — 컨테이너 기동 (모델 불필요)

```bash
curl -sS http://<host>:8000/api/v1/ai/detail-page-jobs/does-not-exist
```
404 계열 응답이 오면 프로세스·포트·보안 그룹이 정상이다. 연결 거부면 인프라 문제이지
모델 문제가 아니다.

### 1단계 — 추론 서버 도달

```bash
curl -sS http://127.0.0.1:11234/v1/models
```
텍스트·이미지 모델 ID가 모두 보여야 한다. **컨테이너 샌드박스가 loopback을 막는 경우가
있으니 ai-service 컨테이너 안에서 실행**한다.

### 2단계 — 분석까지 (텍스트 모델만)

이미지 1장으로 job을 등록하고 `DRAFT_READY`까지 폴링한다.

```bash
curl -sS -X POST http://<host>:8000/api/v1/ai/detail-page-jobs \
  -F "image=@sample.jpg" -F "product_name=테스트 상품"
curl -sS http://<host>:8000/api/v1/ai/detail-page-jobs/<job_id>
```

여기까지 성공하면 텍스트 추론·React 문서 조립·저장소가 정상이다.
상태는 `QUEUED → ANALYZING → EXTRACTING → ... → DRAFT_READY` 순으로 움직인다.

### 3단계 — 이미지 생성까지

2단계에서 `GENERATING_BACKGROUNDS` / `COMPOSING`을 통과했는지 확인한다. 페이지당 이미지
생성 호출이 7~8회이므로 이 구간이 가장 오래 걸린다. 로컬 실측은 건당 전체 263~361초이며,
**GPU에서는 이미지 구간이 크게 줄어들 것으로 예상하나 실측 전까지는 미확정**이다.

### 4단계 — 승인 후 PNG

승인 API를 호출해 `RENDERING`을 통과시킨다. 여기서 실패하면 원인은 모델이 아니라
**Node/Playwright Chromium 누락**일 가능성이 가장 높다.

### 5단계 — BE 전달

`BACKEND_PRODUCT_URL`을 설정한 상태에서 `DELIVERING`까지 확인한다. outbox는 선저장 후
전송이므로, BE가 일시적으로 죽어도 재시작 후 재전송된다.

### 6단계 — 재시작 복구

파드를 강제 종료하고 다시 띄운다. PVC가 제대로 붙어 있으면 진행 중이던 job의 lease가
만료된 뒤 재청구되고, 미전송 outbox가 재전송된다. **7절의 영속화가 빠져 있으면 이 단계에서
드러난다.**

## 11. 알려진 제약

- **진행 중 생성 작업에는 체크포인트가 없다.** 파드가 죽으면 그 job은 처음부터 재실행되며
  건당 약 5분이 버려진다. 모델 상주 구조에서는 재로드 시간이 추가된다.
- 이미지 생성은 현재 **1024×1024 정사각형 고정**이다. 상세페이지 캔버스는 774 폭의 세로
  형태라 생성물을 잘라 쓴다. diffusers로 이관하면 종횡비를 열 수 있다.
- 사람 검수는 아직 실행되지 않았다. 자동 게이트(`scripts/check_cutout_fidelity.py`,
  `scripts/check_scene_direction_coverage.py`) 결과만 존재한다.

## 참고

- 서빙 스택 검토: [로컬 MLX Serve 서빙 운영 검토](sglang-vllm-fit.md)
- 런타임 아키텍처: [runtime-architecture.html](../architecture/runtime-architecture.html)
- 평가 실행 기록: [파일럿 리포트](../evaluation/pilot-report-2026-09-09.md)
