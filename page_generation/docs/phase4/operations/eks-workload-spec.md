# EKS 배포 — 인프라팀 요청 답변

- 작성일: 2026-09-16
- 대상 저장소: Team3_EcommerceSystemAI (AI Repository)
- 답변 범위: 인프라팀 요청 1-1 ~ 1-5

> **검증 상태 먼저 말씀드립니다.** 2026-09-18 기준 `deploy/sglang/Dockerfile`은 Mac ARM64 호스트에서 `linux/amd64` 에뮬레이션으로 실제 빌드에 성공했습니다. 최종 이미지의 Docker 로컬 가상 크기는 **16.97 GB (15.81 GiB)**이며, 컨테이너 내부의 SGLang import·앱 import·`DRY_RUN`·FastAPI `/health` smoke test도 통과했습니다. 다만 **GPU에서 두 모델을 실제 적재한 적은 아직 없습니다.** 두 모델이 L40S 한 장에 실제로 올라가는지, 생성·편집 품질과 처리 시간, peak VRAM 및 두 SGLang 프로세스의 합산 host RAM은 첫 AWS GPU 배포에서 확인해야 합니다. 확인 항목은 `docs/phase4/operations/ubuntu-deployment.md` 의 검증 체크리스트에 정리돼 있습니다. 아래 자원 수치 중 이미지 크기는 빌드 실측이고, 모델·VRAM·host RAM 합산값은 명시한 근거에 따른 계산 또는 미검증 추정치입니다.

---

## 1-1. Runtime 구조

**우리 팀이 필요한 GPU 워크로드는 L40S 한 개입니다.** T4/Ollama 워크로드는 사용하지 않습니다.

```
L40S (1장)
└ ai-sglang  (파드 1개, 컨테이너 1개)
   ├ FastAPI :8000          ← 백엔드가 호출하는 엔드포인트
   ├ SGLang 텍스트·비전 서버 :30000  (컨테이너 내부 전용)
   └ SGLang 이미지 확산 서버 :30001  (컨테이너 내부 전용)
```

- **FastAPI `:8000` 은 이 컨테이너가 직접 제공합니다.** 백엔드는 `:8000` 만 호출하면 되고, 30000/30001 은 컨테이너 내부(`127.0.0.1`) 통신이라 Service 로 노출할 필요가 없습니다.
- **멀티컨테이너로 나누지 말아 주세요.** 우리 파이프라인은 SGLang 서버가 두 개(텍스트·비전, 이미지 확산)입니다. NVIDIA device plugin 은 GPU 를 컨테이너 단위로 배타 할당하므로, 컨테이너를 나누면 L40S 한 장을 두 컨테이너가 나눠 쓸 수 없습니다(타임슬라이싱/MPS 를 따로 켜지 않는 한). 그래서 **한 컨테이너에서 세 프로세스**를 띄우는 구조로 만들었습니다.
- 프로세스 관리: `entrypoint.sh` 가 SGLang 두 서버를 백그라운드로 띄우고 FastAPI 를 PID 1 로 실행합니다. 세 프로세스 중 하나라도 죽으면 컨테이너가 종료되어 쿠버네티스가 파드를 재시작합니다.

## 1-2. EKS 배포용 `deploy/sglang/Dockerfile`

| 항목 | 값 |
| --- | --- |
| SGLang Dockerfile | `deploy/sglang/Dockerfile` |
| 진입 스크립트 | `deploy/sglang/entrypoint.sh` |
| 빌드 컨텍스트 | **이 디렉터리(`page_generation/`)** (`docker build -f deploy/sglang/Dockerfile .` 를 `page_generation/` 에서 실행) — `pyproject.toml`, `uv.lock`, `src/`, `web/`, `assets/` 를 복사합니다 |
| Ollama Dockerfile | **작성하지 않았습니다.** 우리는 L40S 한 장만 사용합니다. 필요하시면 추가 작성 가능합니다 |

운영 기준 반영 상태:

| 요구 | 반영 |
| --- | --- |
| 필요한 Dependency 포함 | 베이스 `lmsysorg/sglang:v0.5.19`(CUDA 포함) + `sglang[diffusion]==0.5.19` + `bitsandbytes==0.50.2` + 서비스 의존성(`uv sync --locked`) + Node.js 22 + Playwright Chromium |
| `CMD`/`ENTRYPOINT` | `ENTRYPOINT ["/usr/local/bin/detail-page-ai-entrypoint"]` (`deploy/sglang/entrypoint.sh` 를 설치한 것) |
| FastAPI `:8000` | `EXPOSE 8000 30000 30001`, uvicorn 이 PID 1. **Service 로 노출할 포트는 8000 뿐**이고 30000/30001 은 컨테이너 내부 통신용입니다 |
| Secret 미포함 | 이미지에 토큰·키를 넣지 않았습니다. 전부 런타임 주입 |
| 로그 stdout/stderr | 파일 리다이렉트 없음. 세 프로세스 로그가 모두 표준 출력으로 나갑니다 |
| 컨테이너 내부 영구 저장 금지 | 아래 1-4 의 PVC 절 참고. `VOLUME` 선언 없음 |
| Non-root | `appuser` UID/GID 10001 로 전환 |
| GPU CUDA/Library | SGLang 공식 이미지의 CUDA 런타임 사용 |
| `linux/amd64` | 대상 플랫폼입니다 |

### 1-2-1. 2026-09-18 이미지 검증 실측

| 항목 | 결과 |
| --- | --- |
| 빌드 | `docker buildx build --platform linux/amd64 --load` 성공 |
| 최종 이미지 | 16.97 GB / 15.81 GiB (`docker image inspect` 기준) |
| SGLang 베이스 이미지 | 14.74 GB / 13.73 GiB |
| 이미지에 모델 포함 여부 | 미포함. 모델은 PVC 또는 HF 캐시에 실행 시 준비 |
| 앱만 기동한 유휴 메모리 | 67.33 MiB (FastAPI `/health` 확인 컨테이너) |
| SGLang·Torch·Diffusers import | 약 0.97 GiB peak RSS. 모델 가중치 적재 메모리는 아님 |
| 정적 검증 | 세 Dockerfile `buildx --check` 경고 없음, Compose config 성공 |

이 검증은 NVIDIA GPU가 없는 Mac에서 수행했으므로 실제 CUDA kernel 실행, 모델 적재, peak VRAM 및 생성 요청 E2E를 대체하지 않습니다.

## 1-3. Health Check

FastAPI 에 두 경로를 새로 추가했습니다.

| 경로 | 용도 | 동작 |
| --- | --- | --- |
| `GET /health` | **liveness** | 인증 없이 항상 `200` + `{"status":"ok"}`. 추론 서버를 호출하지 않습니다 |
| `GET /health/ready` | **readiness** | SGLang 두 서버의 `/v1/models` 를 2초 타임아웃으로 확인. 전부 정상이면 `200`, 아니면 `503` + 사유 |

- 두 경로 모두 **인증 토큰이 필요 없습니다.**
- **liveness 를 `/health/ready` 로 잡지 말아 주세요.** 모델 로딩에 수 분이 걸리므로 liveness 가 추론 서버에 묶이면 파드가 계속 재시작됩니다.
- `startupProbe` 를 `/health/ready` 로 두고 `failureThreshold` 를 넉넉히 잡아 주세요. EKS 경로의 정상 기동은 모델 다운로드가 아니라 S3→PVC 동기화, 모델 로딩, GPU 초기화가 끝난 뒤이며, 정확한 시간은 서버 GPU에서 아직 실측하지 않았습니다. S3 동기화가 끝나기 전에 파드가 뜨면 우리 컨테이너가 명확한 오류를 남기고 즉시 종료하므로, 아래 1-4의 initContainer 또는 동기화 Job 완료를 파드 시작 조건으로 묶어 주세요.

## 1-4. 공유 정보

### `deploy/sglang/Dockerfile` 경로
- SGLang: `deploy/sglang/Dockerfile` (+ `deploy/sglang/entrypoint.sh`)
- Ollama: 없음 (사용하지 않음)

### CPU / Memory 권장값

| 항목 | 요청(request) | 상한(limit) | 근거 |
| --- | --- | --- | --- |
| CPU | 3 | 4 | 상세페이지 렌더링에 Chromium, 누끼에 rembg 를 씁니다. 로컬 Apple Silicon 기준선은 1건당 평균 226초였습니다 |
| Memory | **24Gi** | 28Gi | 누끼(rembg) 프로세스 상주 **약 12.9 GiB 실측** + SGLang 두 프로세스의 파이썬/토치 상주분 + Chromium 렌더링 |

> **2026-09-18 갱신.** 앞서 드린 CPU 3/6, Memory 16Gi/28Gi 에서 **Memory request 를
> 16Gi → 24Gi 로, CPU limit 을 6 → 4 로 고쳤습니다.** 아래 실측 때문입니다.

##### 누끼(rembg) 실측 — 2026-09-18 사내 Ubuntu 서버 컨테이너

8 코어 CPU, 500×500 입력 기준입니다.

| 단계 | 시간 | 프로세스 누적 피크 RSS |
| --- | ---: | ---: |
| 세션 로드 | 21.3초 | 2.18 GiB |
| 누끼 1회차 | 22.5초 | 9.22 GiB |
| 2회차 | 33.3초 | **12.90 GiB** |
| 3회차 | 24.1초 | 12.90 GiB |
| 4회차 | 30.5초 | 12.90 GiB |

**2회차에서 12.90 GiB 로 평탄해집니다.** 누수가 아니라 onnxruntime 아레나가 정상
상태에 도달한 것이며, 이후 회차에서 더 늘지 않습니다. 다만 **누끼만으로 프로세스가
약 13 GiB 를 상시 점유**한다는 뜻이라, Memory request 16Gi 로는 스케줄러가 실제
사용량을 반영하지 못합니다. 같은 서버에서 렌더 도중 컨테이너가 `OOMKilled`(exit 137)
로 종료된 것을 확인했습니다(가용 13 GiB 환경).

CPU limit 을 6 에서 4 로 낮춘 것은 `g6e.xlarge` 가 **4 vCPU** 라 6 은 도달할 수 없는
값이기 때문입니다. 오해를 만들지 않도록 노드 용량에 맞췄습니다.

**여전히 미검증인 것**: SGLang 두 서버가 GPU 노드에서 쓰는 **호스트 RAM 은 아직
측정하지 못했습니다.** 위 24Gi 는 누끼 실측 12.9 GiB 에 나머지를 추정해 얹은 값입니다.
첫 배포에서 합산 피크를 측정한 뒤 확정하겠습니다. 위 값은 **L40S 1장짜리 노드가 4 vCPU / 32 GiB(예: `g6e.xlarge`) 라도 스케줄되도록** 잡은 값입니다. 노드가 `g6e.2xlarge`(8 vCPU / 64 GiB) 급이면 CPU request 4~6 으로 올리는 편이 렌더링 처리량에 유리합니다. GPU 오프로딩은 끄고 운영하므로(`--dit-cpu-offload false`, `--text-encoder-cpu-offload false`) 호스트 RAM 으로 가중치가 넘어오지는 않습니다.

### GPU 요구량

| 항목 | 값 |
| --- | --- |
| GPU | `nvidia.com/gpu: 1` (NVIDIA L40S 48GB) |
| 가중치 | 텍스트 19.6 GiB + 이미지 10.2 GiB = 약 29.8 GiB |
| 실제 선점(계산값) | 텍스트 서버가 `--mem-fraction-static 0.50` 으로 약 22.4 GiB 를 KV 캐시 포함 정적 선점 + 이미지 10.2 GiB = 약 32.6 GiB. 가용 44.7 GiB 기준 여유 약 12 GiB. **계산값이며 실측 전입니다** |
| 분할 사용 | 불가. 한 컨테이너가 GPU 한 장을 전부 사용합니다 |

### Secret / Environment Variable 이름

**Secret 으로 주입 (값은 전달하지 않습니다)**

| 환경변수 | 용도 | 필수 | staging Parameter Store 경로 | 등록 주체 |
| --- | --- | --- | --- | --- |
| `AI_INTERNAL_AUTH_TOKEN` | `/internal/v1/ai/*` 호출 인증 토큰 | 예 | `/staging/ai/internal-auth-token` | **생성형 AI 팀 — 등록 완료** (2026-09-22, Version 1) |
| `BACKEND_AUTH_TOKEN` | BE 콜백용 Bearer 토큰 | 예 | `/staging/backend/backend-auth-token` | **BE 팀** (우리는 읽기만) |
| `HF_TOKEN` | Hugging Face 토큰 | 현재 모델은 비게이트라 불필요. 게이트 모델로 바꾸면 필수 | 미등록 | — |

두 토큰은 **서로 다른 값**입니다. 방향이 반대이기 때문입니다.

```
BE  --(AI_INTERNAL_AUTH_TOKEN)-->  AI      X-AI-Internal-Token 헤더
AI  --(BACKEND_AUTH_TOKEN)------>  BE      Authorization: Bearer 헤더
```

`AI_INTERNAL_AUTH_TOKEN` 은 **형식 제약이 없습니다.** 임의 문자열이며
`hmac.compare_digest` 로 상수 시간 비교합니다(`app.py:90-99`).

#### staging Parameter Store 등록 현황 (2026-09-22)

| 파라미터 | Type | KMS 키 | 상태 | 등록 |
| --- | --- | --- | --- | --- |
| `/staging/ai/internal-auth-token` | `SecureString` | `alias/jangin-staging-app` | **등록 완료** (Version 1) | 생성형 AI 팀 |
| `/staging/ai/vector-db/password` | `SecureString` | `alias/jangin-staging-app` | **등록 완료** (Version 1) | 생성형 AI 팀이 **대행** (원 소관: 챗봇 팀) |
| `/staging/ai/vector-db/postgres-password` | `SecureString` | `alias/jangin-staging-app` | **등록 완료** (Version 1) | 생성형 AI 팀이 **대행** (원 소관: 챗봇 팀) |
| `/staging/backend/backend-auth-token` | — | — | **BE 미등록** (2026-09-22 확인) | BE 팀 |

등록 시점에 `/staging/ai` 는 비어 있었으므로 덮어쓴 값이 없습니다. 리전은
`ap-northeast-2` 이고, 값을 바꾸면 파드 재시작이 필요합니다. 값은 생성과 동시에
`put-parameter` 로 전달해 화면·로그에 남기지 않았고, 문자는 URL-safe 라 접속
문자열에서 이스케이프가 필요 없습니다.

> **벡터DB 두 건은 챗봇 팀이 확인해야 할 전제가 있습니다.** 벡터DB 가 **이미 다른
> 비밀번호로 프로비저닝되어 있다면** 파라미터만 바꿔도 DB 의 실제 비밀번호는 바뀌지
> 않습니다. 아직 생성 전이라면 문제가 없습니다. `chat_bot/env.example` 이
> `DB_PASSWORD_FILE=/mnt/secrets-store/password` 로 파라미터를 마운트해 읽으므로
> 하드코딩된 값과 충돌하지는 않습니다.

> **진단 참고**: 이 환경변수가 주입되지 않으면 `/internal/v1/ai/*` 가 **401 이 아니라
> 503** (`AI internal integration is unavailable`)을 반환합니다. 401 은 값이 틀린
> 경우입니다. 파라미터 연결이 빠졌을 때 헷갈리지 않도록 구분해 두었습니다.

**ConfigMap 등으로 주입**

| 이름 | 값(서버 기준) |
| --- | --- |
| `BACKEND_URL` | BE 엔드포인트 (환경별로 다름) |
| `AI_CORS_ORIGINS` | **주입하지 않으셔도 됩니다.** FE 는 BE 를 통해서만 이 서비스에 도달하므로 브라우저가 직접 호출하는 경로가 없고, CORS 는 서버 대 서버 호출에 적용되지 않습니다. 기본값 그대로 둡니다 |
| `LOCAL_TEXT_PROVIDER` / `LOCAL_IMAGE_PROVIDER` / `BACKGROUND_PROVIDER` | `sglang` (이미지 기본값) |
| `LOCAL_TEXT_URL` / `LOCAL_IMAGE_URL` | `http://127.0.0.1:30000` / `http://127.0.0.1:30001` (이미지 기본값) |
| `LOCAL_TEXT_MODEL` / `LOCAL_IMAGE_MODEL` | `qwen-text` / `flux-klein` (SGLang 등록 이름과 일치해야 함) |
| `TEXT_MODEL_PATH` / `IMAGE_MODEL_PATH` | PVC 안의 모델 디렉터리 절대 경로. 예: `/var/lib/detail-page-ai/models/text/qwen3.8-27b-awq-int4`, `/var/lib/detail-page-ai/models/image/flux2-klein-9b-bnb-4bit` |
| `TEXT_MODEL_REVISION` / `IMAGE_MODEL_REVISION` | HF 모드에서만 사용하는 모델 가중치 커밋 고정값. 로컬 모드에서는 `--revision` 을 전달하지 않습니다 |
| `SQLITE_PATH` / `ASSET_STORE_DIR` / `HF_HOME` / `U2NET_HOME` | PVC 경로 (이미지 기본값) |

전체 목록은 `.env.example` 과 `src/detail_page_ai/config.py` 에 있습니다.

### 영구 데이터 — PVC 한 개

컨테이너 내부에 데이터를 남기지 않도록 **모든 영구 경로를 한 마운트 지점 아래로 모았습니다.** PVC 하나만 붙여 주시면 됩니다.

```
/var/lib/detail-page-ai/          ← PVC 마운트 지점 (1개)
├ state.sqlite3                    작업 상태 · BE 전달 outbox
├ assets/                          생성된 이미지 산출물
├ models/text/<model>/              텍스트·비전 모델 가중치
├ models/image/<model>/             이미지 확산 모델 가중치
├ models/huggingface/              HF 모드 fallback·런타임 캐시
├ models/u2net/                    rembg 누끼 모델 약 973 MB
├ models/torch/                    torch 캐시
└ cache/                           SGLang·FlashInfer·Triton 등 런타임 캐시
```

| 항목 | 값 |
| --- | --- |
| 유형 | `gp3`, `ReadWriteOnce` |
| 용량 | **100Gi 권장** (모델 약 30GB + 산출물·캐시) |
| 권한 | UID/GID **10001** 이 쓸 수 있어야 합니다. `securityContext.fsGroup: 10001` 설정 필요 |
| 제약 | `ReadWriteOnce` 라 **단일 파드만 가능**합니다. 파드를 늘리려면 상태를 RDS + S3 로 옮기는 별도 작업이 필요합니다 |

EKS 경로에서는 인프라팀이 S3에서 위 모델 디렉터리로 가중치를 동기화한 뒤 파드를 시작해야 합니다. 우리 컨테이너는 PVC의 로컬 디렉터리만 읽습니다. PVC 마운트 후 모델 디렉터리가 생성되어 있으나 `config.json`이 아직 없으면 로컬 모드의 명확한 오류를 남기고 즉시 종료합니다. 모델 경로 디렉터리 자체가 없으면 HF 모드로 fallback하므로, EKS에서는 네트워크 다운로드에 의존하지 않도록 모델 디렉터리와 파일을 initContainer 또는 선행 Job으로 준비해 주세요.

#### 인프라팀 동기화 대상

| 모델 | 저장소·고정 커밋 | 용도 | 크기 | PVC 배치 경로 |
| --- | --- | --- | --- | --- |
| 텍스트·비전 | `cyankiwi/Qwen3.8-27B-AWQ-INT4` (`6e134bae811fb5adac50ee042ae5f029ac6779aa`) | SGLang 텍스트 서버 | 가중치 19.6 GiB | `models/text/<model>/` (`TEXT_MODEL_PATH`) |
| 이미지 확산 | `circulus/FLUX.2-klein-9B-bnb-4bit` (`58c2804f31af12c8888504b96250010c50b55e44`) | SGLang 확산 서버 | 약 10.2 GiB | `models/image/<model>/` (`IMAGE_MODEL_PATH`) |
| **누끼(rembg)** | **`danielgatis/rembg` 릴리스 `v0.0.0` 의 `BiRefNet-general-epoch_244.onnx`** | **판매 사진 배경 제거** | **973 MB** | **`models/u2net/birefnet-general.onnx`** |

S3 버킷은 `jangin-{env}-s3-models`를 사용하고, 인프라팀이 S3 Gateway Endpoint를 통해 PVC로 동기화합니다. 텍스트·이미지 모델은 별도 디렉터리에 **압축하지 않고 펼친 형태**로 저장해야 하며, `config.json`과 가중치 파일(`*.safetensors`)이 해당 디렉터리 안에 직접 있어야 합니다. 위 예시의 `TEXT_MODEL_PATH`와 `IMAGE_MODEL_PATH`에 PVC 안의 실제 절대 경로를 주입해 주세요.

##### 누끼 모델을 동기화 대상에 넣어 주셔야 하는 이유

rembg 모델은 디렉터리가 아니라 **파일 하나**이고, 파일명이 `birefnet-general.onnx` 여야 합니다. 경로는 `U2NET_HOME` 환경변수가 가리키는 곳으로, 이미지 기본값이 `/var/lib/detail-page-ai/models/u2net` 입니다(별도 주입 불필요).

**이 파일이 없으면 우리 컨테이너가 첫 렌더 요청에서 `github.com` 으로 973 MB를 직접 내려받습니다.** 2026-09-18 사내 Ubuntu 서버 컨테이너 연동 테스트에서 실제로 관측했습니다.

```
Downloading data from 'https://github.com/danielgatis/rembg/releases/download/v0.0.0/
BiRefNet-general-epoch_244.onnx' to file
'/var/lib/detail-page-ai/models/u2net/birefnet-general.onnx'
```

동기화 대상에 넣어 주시면 두 가지가 해결됩니다.

- **런타임 egress가 필요 없습니다.** 넣지 않으시면 노드에서 `github.com` 으로 나가는 경로를 열어 두셔야 합니다.
- **첫 요청이 다운로드를 기다리지 않습니다.** 사내 LAN에서 약 17초였고, 실패하면 그 요청이 실패합니다.

S3에 올리실 때는 릴리스 자산 파일명(`BiRefNet-general-epoch_244.onnx`)이 아니라 **`birefnet-general.onnx` 로 바꿔서** 위 경로에 두셔야 합니다. rembg가 그 이름으로 찾습니다.

모델 서버는 텍스트·비전과 이미지 확산을 **각각 독립적으로** 다음과 같이 판정합니다.

- 지정한 모델 경로가 디렉터리로 존재하면 로컬 모드입니다. 이때 저장소 ID 대신 해당 경로를 사용하고 `--revision`을 전달하지 않으며, 네트워크를 시도하지 않도록 `HF_HUB_OFFLINE=1`로 실행합니다.
- 로컬 모드에서 `config.json`이 없으면 모델 디렉터리가 불완전하다는 명확한 오류 메시지를 표준 출력/오류로 남기고 기동을 중단합니다. 파드가 Ready 상태가 되지 않습니다.
- 지정한 모델 경로가 디렉터리로 존재하지 않으면 HF 모드입니다. 이때 지금의 저장소 ID와 `--revision` 고정 커밋을 사용합니다. EKS 정상 경로에서는 인프라팀의 S3→PVC 동기화가 먼저 완료되어 로컬 모드가 선택되어야 합니다.

### S3 등 AWS Resource 접근 필요 여부

앞선 답변에서는 “S3 등 AWS Resource 접근은 필요 없습니다”라고 말씀드렸으나, S3 사전 업로드 제안에 따라 **모델 확보 방식은 다음과 같이 바뀝니다.**

- 우리 컨테이너는 여전히 AWS 자격이 필요하지 않습니다. `boto3`·AWS CLI 의존성이 없고, 컨테이너에 IAM 역할이나 S3 권한을 부여하지 않습니다.
- 인프라팀이 `jangin-{env}-s3-models`에서 PVC로 두 모델을 동기화하고, 우리는 주입받은 `TEXT_MODEL_PATH`·`IMAGE_MODEL_PATH`의 로컬 디렉터리만 읽습니다. S3 Gateway Endpoint와 `aws s3 sync`의 주체는 인프라팀의 initContainer 또는 선행 Job입니다.
- 이전 답변은 첫 기동 때 Hugging Face에서 약 30GB를 내려받는 전제였지만, EKS 경로에서는 사전 동기화된 PVC를 읽는 전제로 변경되었습니다. 따라서 우리 컨테이너가 S3 또는 Hugging Face 네트워크에 직접 접근할 필요가 없습니다.
- 생성 이미지, SQLite 상태, outbox 및 런타임 캐시는 이전과 같이 `/var/lib/detail-page-ai` 아래 PVC에 저장합니다. **산출물 저장 위치는 변경되지 않았습니다.**

## 1-5. Image 발행 Branch

**`main` push 기준으로 사용하시면 됩니다.** 준비는 끝났습니다.

| 항목 | 값 |
| --- | --- |
| 저장소 | `https://github.com/Jangingmall/GenAI` 의 **`page_generation/`** (AI 파트 모노레포, 비공개) |
| 기본 브랜치 | `main` |
| 소스 경로 | `page_generation/` — 이 워크로드의 전부입니다 |

1. **모노레포의 하위 디렉터리입니다.** 이 워크로드의 소스는 저장소 최상위가 아니라 `page_generation/` 아래에 있습니다. 같은 저장소의 `chat_bot/` 은 추천 챗봇으로 **다른 서비스**이니 이 워크로드에 포함하지 마세요. 따라서 이미지 발행 트리거도 `page_generation/**` 경로 변경으로 좁히는 편이 좋습니다 — 챗봇만 바뀌었을 때 이 이미지가 다시 빌드되지 않도록.
2. **접근 권한이 필요합니다.** 비공개 저장소라 CI 나 인프라팀 계정에 조직 권한을 부여해야 clone 이 됩니다. 필요한 계정을 알려 주세요.
3. **빌드 컨텍스트는 `page_generation/` 디렉터리**입니다. 저장소가 모노레포라 최상위가 아니라 이 하위 디렉터리에서 `docker build -f deploy/sglang/Dockerfile .` 을 실행해 주세요. Dockerfile이 있는 디렉터리(`deploy/sglang/`)만 컨텍스트로 잡으면 빌드가 실패합니다.

변경 런타임 감지는 `page_generation/` 기준으로 `deploy/sglang/`, `src/`, `pyproject.toml`, `uv.lock`, `web/`, `assets/references/` 경로 변경을 트리거로 잡으시면 됩니다. 이 경로들이 이미지에 들어갑니다.

---

## 함께 알아 두셔야 할 사항

1. **이미지가 큽니다.** SGLang 베이스(`lmsysorg/sglang:v0.5.19`)에 `sglang[diffusion]` 과 `bitsandbytes` 를 얹은 것만으로 약 18~22 GB 이고, 여기에 Chromium·Node·서비스 의존성이 더해집니다. ECR 저장 용량, 노드 디스크, 첫 pull 시간을 감안해 주세요.
2. **첫 기동의 모델 다운로드 단계가 EKS 경로에서는 사라집니다.** 인프라팀이 미리 S3에서 PVC로 동기화한 모델 디렉터리를 읽으므로, 컨테이너가 첫 기동에 약 30GB를 직접 받지 않습니다. 동기화 완료, GPU 적재, 두 서버의 Ready 전환 시간은 아직 서버 GPU에서 실측하지 않았으므로 정확한 기동 시간을 단정할 수 없습니다. `startupProbe`는 이 미측정 구간을 반영해 설정해 주세요. 단일 EC2 Compose 경로의 HF 다운로드 전제는 `aws-migration-checklist.md`에 별도로 남아 있습니다.
3. **이미지 모델 라이선스.** 현재 이미지 모델은 FLUX Non-Commercial License 원본을 커뮤니티가 4bit 로 양자화한 가중치를 사용합니다. 상업 운영 전에 라이선스 확인이 필요하다는 점을 기록해 둡니다. 대안은 Apache 2.0 인 `black-forest-labs/FLUX.2-klein-4B` 입니다.
4. **아직 GPU 검증 전입니다.** Colab 스모크 테스트 노트북(`notebooks/colab_sglang_smoke_test.ipynb`)으로 사전 확인이 가능하며, 아직 실행하지 않았습니다.
