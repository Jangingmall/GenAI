# Phase 4 모델 카드 및 운영 가이드

- 작성일: 2026-09-22
- 대상: `Team3_EcommerceSystemAI` 상세페이지 AI 파이프라인
- 사실 기준: 저장소의 운영 문서, 평가 기록, 배포 파일, 소스 설정을 직접 대조했다. 저장소에서 확인하지 못한 값은 `확인하지 않음` 또는 `확인 필요`로 표시했다.

## 1. 모델 카드

### 카드 1. 배포 텍스트·비전 모델

| 항목 | 저장소에서 확인한 내용 |
| --- | --- |
| 저장소 / 고정 커밋 | `cyankiwi/Qwen3.8-27B-AWQ-INT4` / `6e134bae811fb5adac50ee042ae5f029ac6779aa` |
| 크기·양자화 | 가중치 **19.6 GiB**. AWQ W4A16 / INT4로 기록되어 있다. |
| 파이프라인 역할 | 상품 이미지를 분석하고 상품 프로필·한국어 카피를 만드는 텍스트·비전 추론. SGLang 공개 모델명은 `qwen-text`다. |
| 실행 환경 | EKS 단일 `ai-sglang` 컨테이너의 SGLang 텍스트 서버. NVIDIA L40S 1장, `127.0.0.1:30000`, `--mem-fraction-static 0.50`, 컨텍스트 길이 8192. |
| 라이선스 | 저장소 문서와 `.env.example`에 **Apache 2.0 기반**으로 기록되어 있다. 이 문서에서 Hugging Face 원문 라이선스 페이지를 별도로 재확인하지는 않았다. |
| 알려진 한계 | GPU에서 실제 가중치 적재·생성 E2E, peak VRAM, 두 SGLang 프로세스의 합산 host RAM은 아직 확인하지 않았다. 로컬 모드에서 모델 디렉터리가 생성됐지만 `config.json`이 없으면 기동이 중단된다. |

### 카드 2. 배포 이미지 확산 모델

| 항목 | 저장소에서 확인한 내용 |
| --- | --- |
| 저장소 / 고정 커밋 | `circulus/FLUX.2-klein-9B-bnb-4bit` / `58c2804f31af12c8888504b96250010c50b55e44` |
| 크기·양자화 | 약 **10.2 GiB**: transformer 4.36 GiB, text encoder 5.66 GiB, VAE 0.16 GiB. transformer와 text encoder는 bitsandbytes 4bit NF4, double quant, bfloat16 연산으로 기록되어 있다. |
| 파이프라인 역할 | 제품 원본을 대체하지 않는 배경·활용 장면·추가 디테일 컷 생성 및 원본 참고 편집. 서비스 공개 모델명은 `flux-klein`이다. |
| 실행 환경 | 같은 EKS 컨테이너의 SGLang diffusion 서버. NVIDIA L40S 1장, `127.0.0.1:30001`, `--dit-cpu-offload false`, `--text-encoder-cpu-offload false`. `sglang[diffusion]==0.5.19`와 `bitsandbytes==0.50.2`가 이미지에 설치된다. |
| 라이선스 | 원본 `black-forest-labs/FLUX.2-klein-9B`는 저장소 문서상 FLUX Non-Commercial License(FLUX NCL)다. 채택 저장소는 그 커뮤니티 양자화본이며 자체 라이선스 표기는 확인하지 못했다. 상업 운영에 허용되는 범위는 **확인 필요**다. |
| 알려진 한계 | 실제 GPU 적재·VRAM·처리시간은 미검증이다. 생성 자산은 `GENERATED` 연출 슬롯으로 취급하며 상품 사실의 대표 근거로 사용하지 않는다. |

### 카드 3. 누끼 모델

| 항목 | 저장소에서 확인한 내용 |
| --- | --- |
| 저장소 / 버전 | `danielgatis/rembg` 릴리스 `v0.0.0`의 `BiRefNet-general-epoch_244.onnx`; 애플리케이션 모델명은 `birefnet-general`. 고정 커밋 SHA는 **없음**(릴리스 버전만 기록). Python 패키지는 `rembg==2.0.69`로 고정되어 있다. |
| 크기·양자화 | ONNX 모델 파일 **973 MB**. 양자화 방식은 저장소에서 확인하지 않음. |
| 파이프라인 역할 | 판매 원본 사진에서 배경을 제거하고 원본 RGB 기반의 packshot·detail 자산을 만든다. 실패 시 원본/폴백 경로가 사용된다. |
| 실행 환경 | FastAPI와 같은 애플리케이션 프로세스에서 lazy-load된다. `U2NET_HOME=/var/lib/detail-page-ai/models/u2net`, 파일명은 `birefnet-general.onnx`다. EKS CUDA 이미지에는 `onnxruntime-gpu==1.29.0`, CPU 이미지에는 `onnxruntime==1.29.0`이 설치된다. |
| 라이선스 | rembg 패키지와 BiRefNet 가중치의 라이선스를 이 저장소 문서에서 확인하지 못했다. **확인 필요**. |
| 알려진 한계 | 2026-09-18 Ubuntu 실측에서 프로세스 누적 RSS가 2회차에 **12.90 GiB**까지 올라간 뒤 평탄화됐다. 가용 메모리 13 GiB 환경에서는 렌더 중 `OOMKilled`(exit 137)가 관측됐다. CUDA provider 선택 자체는 코드에 있으나 실제 GPU 전환은 확인하지 않았다. |

### 카드 4. 로컬 개발 모델 쌍

로컬 개발 용도는 텍스트·비전과 이미지 확산 두 저장소를 하나의 MLX Serve 인스턴스에서 사용하므로, 모델별 사실을 별도 행으로 구분한다.

| 항목 | 로컬 텍스트·비전 | 로컬 이미지 확산 |
| --- | --- | --- |
| 저장소 / 고정 커밋 | `ddalcu/Qwen3.8-27B-MLX-Serve-4bit` / 고정 커밋 **없음** | `mlx-community/flux2-klein-9b-4bit` / 고정 커밋 **없음** |
| 크기·양자화 | 4-bit MLX 모델. 2026-09-17 파이프라인 기록에서 resident **18.2 GB**로 기록됐지만, 가중치 파일 크기와 peak는 별도 측정되지 않았다. | 4-bit MLX 모델. 운영 문서에 **9.5 GB**로 기재되어 있으나, 이 문서에서 별도 resident 측정은 확인하지 않았다. |
| 파이프라인 역할 | 상품 이미지 분석·비전 질의·한국어 상품 카피 생성. | 배경·활용 장면·디테일 연출 컷 생성. 제품 원본 픽셀 보존 역할은 하지 않는다. |
| 실행 환경 | Apple Silicon Mac의 MLX Serve, `http://127.0.0.1:11234`. | 같은 포트 `11234`. **동시 적재가 아니라 2단계 교체다** — 아래 참고. |
| 라이선스 | 이 저장소의 평가·운영 기록에서 해당 커뮤니티 저장소의 라이선스를 확인하지 못했다. **확인 필요**. | 이 저장소의 평가·운영 기록에서 해당 커뮤니티 저장소의 라이선스를 확인하지 못했다. **확인 필요**. |
| 알려진 한계 | 로컬 MLX resident 메모리·p95는 장비별로 측정해야 한다. 평가 기록은 안전성 및 파이프라인 실측이지 상용 게시 승인 기록이 아니다. | 1024px 생성 메모리·p95·품질의 정량 승인은 미완료다. 생성 자산은 상품 사실의 근거가 아니다. |

#### 로컬 개발에서 두 모델은 동시에 뜨지 않는다

Apple Silicon Mac 의 메모리로는 27B 텍스트 모델(resident 18.2 GB)과 FLUX(8.9 GB)를
**함께 올릴 수 없다.** 실제로 시도하면 다음이 나온다.

```
Insufficient memory: needs ~11.0 GB free but only 9.2 GB is available
```

그래서 로컬 종단 실행은 **같은 포트 `11234` 에 모델을 번갈아 올리는 2단계**로 한다.

| 단계 | 올리는 모델 | 수행 |
| --- | --- | --- |
| 1 | `Qwen3.8-27B-MLX-Serve-4bit` | 작업 접수 → 분석 → `DRAFT_READY` |
| 2 | `flux2-klein-9b-4bit` | 승인·렌더 → 사진 생성 → 최종 산출물 |

사진 생성은 분석 단계가 아니라 **렌더 단계**에서 일어난다. 끝나면 텍스트 모델로
되돌려 놓는다.

**배포(L40S 48GB)에서는 이 제약이 없을 것으로 보지만 실측하지 않았다.** 두 모델이
한 장에 실제로 올라가는지는 첫 GPU 배포에서 확인할 항목이다.

## 2. 운영 가이드

### 2.1 배포 형상

EKS 기준 배포 형상은 L40S 1장을 쓰는 **단일 파드·단일 컨테이너**다. `deploy/sglang/Dockerfile`은 세 프로세스를 한 컨테이너에 넣고, `deploy/sglang/entrypoint.sh`가 SGLang 두 서버를 백그라운드로 시작한 뒤 FastAPI를 foreground/PID 1로 실행한다.

| 프로세스 | 포트 | 외부 노출 | 역할 |
| --- | ---: | --- | --- |
| FastAPI | 8000 | Service가 노출하는 유일한 포트 | Product BE가 호출하는 AI API |
| SGLang 텍스트·비전 | 30000 | 컨테이너 내부 `127.0.0.1` | `qwen-text` 분석 |
| SGLang 이미지 확산 | 30001 | 컨테이너 내부 `127.0.0.1` | `flux-klein` 생성·편집 |

Dockerfile에는 `EXPOSE 8000 30000 30001`이 있으나 30000/30001은 내부 통신용이다. SGLang 자식 프로세스가 종료되면 entrypoint watcher가 FastAPI와 다른 자식도 종료해 컨테이너가 재시작되게 한다.

### 2.2 자원 요구: 실측과 추정 구분

| 자원 | 권장 request | 권장 limit | 근거와 상태 |
| --- | ---: | ---: | --- |
| CPU | 3 | 4 | Chromium 렌더링과 rembg를 고려한 운영 사양. 4 vCPU인 `g6e.xlarge`에 맞춘 값이다. |
| Memory | 24 Gi | 28 Gi | rembg 프로세스 12.90 GiB는 실측. 나머지와 SGLang host RAM을 더한 24/28 Gi는 추정 사양이며, SGLang 두 프로세스의 합산 host RAM은 미측정이다. |
| GPU | `nvidia.com/gpu: 1` | - | NVIDIA L40S 48GB. 가용 44.7 GiB 기준의 배포 문서 값이다. |

GPU 메모리 계산은 실측이 아니다. 텍스트 19.6 GiB + 이미지 10.2 GiB = 약 29.8 GiB이고, 텍스트 `--mem-fraction-static 0.50`의 약 22.4 GiB와 이미지 10.2 GiB를 합쳐 약 32.6 GiB를 선점할 것이라는 계산값이다. 실제 모델 적재, peak VRAM, 생성 E2E는 GPU 배포에서 확인해야 한다.

Mac ARM64에서 `linux/amd64` 에뮬레이션으로 EKS Dockerfile 빌드와 import/DRY_RUN/`/health` smoke test는 통과했고 최종 이미지 크기는 **16.97 GB (15.81 GiB)**였다. 이 결과는 GPU kernel 실행이나 가중치 적재를 검증한 결과가 아니다.

### 2.3 모델 준비: S3에서 PVC로 동기화

EKS에서는 인프라팀이 S3 버킷 `jangin-{env}-s3-models`에서 PVC로 모델을 동기화한다. 애플리케이션 컨테이너에는 AWS CLI·boto3·IAM 권한을 넣지 않으며, S3 Gateway Endpoint를 통한 initContainer 또는 선행 Job이 담당한다.

| 대상 | PVC 위치 | 준비 규칙 |
| --- | --- | --- |
| 텍스트·비전 | `models/text/<model>/`에 펼친 디렉터리, `TEXT_MODEL_PATH`로 지정 | `config.json`과 `*.safetensors`가 디렉터리 바로 아래에 있어야 한다. |
| 이미지 확산 | `models/image/<model>/`에 펼친 디렉터리, `IMAGE_MODEL_PATH`로 지정 | `config.json`과 `*.safetensors`가 디렉터리 바로 아래에 있어야 한다. |
| 누끼 | `models/u2net/birefnet-general.onnx` | 릴리스 자산명을 그대로 쓰지 말고 `birefnet-general.onnx`로 저장한다. |

`TEXT_MODEL_PATH` 또는 `IMAGE_MODEL_PATH`가 디렉터리이면 entrypoint는 로컬 모드로 판단하고 `--revision`을 생략하며 `HF_HUB_OFFLINE=1`로 실행한다. 디렉터리는 있으나 `config.json`이 없으면 “S3 동기화가 끝나기 전에 파드가 뜬 것일 수 있다”는 오류를 남기고 즉시 종료한다. 디렉터리 자체가 없으면 HF 저장소 ID와 고정 revision을 사용하므로, EKS에서는 동기화 완료를 파드 시작 조건으로 묶어야 한다.

누끼 파일이 없으면 첫 렌더 요청 때 `github.com`에서 약 973 MB를 내려받는다. 폐쇄망에서는 이 파일을 PVC에 선적재해야 한다.

### 2.4 환경변수와 주입 위치

아래 표의 alias는 `src/detail_page_ai/config.py`에서 직접 확인한 `Settings` 필드 기준이다. `TEXT_*`, `IMAGE_*`, `U2NET_HOME`, `HF_TOKEN`은 Settings alias가 아니라 배포 파일·SGLang·rembg가 사용하는 런타임 변수다.

#### Secret

| 변수 | 실제 용도 |
| --- | --- |
| `AI_INTERNAL_AUTH_TOKEN` | Product BE가 AI 내부 API를 호출할 때 검증하는 토큰 (`ai_internal_auth_token`) |
| `BACKEND_AUTH_TOKEN` | AI가 Product BE로 콜백할 때 쓰는 Bearer 토큰 (`backend_auth_token`) |
| `HF_TOKEN` | Hugging Face 접근 토큰. 현재 배포 모델은 문서상 비게이트라 필수는 아니지만, 게이트 모델로 바꾸면 필요하다. |

#### ConfigMap 또는 일반 런타임 설정

| 변수 | `Settings` alias / 기본값 | 운영 의미 |
| --- | --- | --- |
| `BACKEND_URL` | `backend_url` / `None` | BE 수신 주소. 운영에서는 설정하지 않으면 outbox 배달이 보류된다. |
| `BACKEND_CALLBACK_PATH` | `backend_callback_path` / `/internal/generations/{generation_id}/completion` | BE 콜백 경로 |
| `LOCAL_TEXT_PROVIDER` | `local_text_provider` / `mlx` | EKS는 `sglang` |
| `LOCAL_TEXT_URL` | `local_text_url` / `http://127.0.0.1:11234` | EKS는 `http://127.0.0.1:30000` |
| `LOCAL_TEXT_MODEL` | `local_text_model` / `ddalcu/Qwen3.8-27B-MLX-Serve-4bit` | EKS는 `qwen-text` |
| `LOCAL_IMAGE_PROVIDER` | `local_image_provider` / `mlx` | EKS는 `sglang`; `none`이면 readiness에서 이미지 서버를 제외한다. |
| `LOCAL_IMAGE_URL` | `local_image_url` / `http://127.0.0.1:11234` | EKS는 `http://127.0.0.1:30001` |
| `LOCAL_IMAGE_MODEL` | `local_image_model` / `mlx-community/flux2-klein-9b-4bit` | EKS는 `flux-klein` |
| `BACKGROUND_PROVIDER` | `background_provider` / `mlx` | EKS는 `sglang` |
| `AI_CORS_ORIGINS` | `cors_origins` / `http://127.0.0.1:4173,http://localhost:4173` | 실제 FE 도메인이 브라우저에서 직접 호출하는 구성인지 확인해 조정한다. |
| `ASSET_STORE_DIR` | `asset_store_dir` / `.local/detail-page-ai/assets` | EKS PVC의 `/var/lib/detail-page-ai/assets` |
| `SQLITE_PATH` | `sqlite_path` / `.local/detail-page-ai/state.sqlite3` | EKS PVC의 `/var/lib/detail-page-ai/state.sqlite3` |

배포 프로세스용으로는 `TEXT_MODEL_PATH`, `TEXT_MODEL_REVISION`, `TEXT_SERVED_MODEL_NAME`, `TEXT_MEM_FRACTION`, `TEXT_CONTEXT_LENGTH`, `IMAGE_MODEL_PATH`, `IMAGE_MODEL_REVISION`, `IMAGE_SERVED_MODEL_NAME`, `U2NET_HOME`도 주입·관리한다. EKS 기본 경로는 `/var/lib/detail-page-ai` 아래 PVC다. 비밀값은 Dockerfile에 넣지 않는다.

### 2.5 헬스체크

| 경로 | 성격 | 실제 동작 |
| --- | --- | --- |
| `GET /health` | liveness | 추론 서버를 호출하지 않고 항상 `200`과 `{"status":"ok"}`를 반환한다. |
| `GET /health/ready` | readiness | 설정된 텍스트 서버와 이미지 서버의 `/v1/models`를 각각 2초 timeout으로 조회한다. 모두 정상이면 `200`, 하나라도 실패하면 `503`과 component별 사유를 반환한다. 이미지 provider가 `none`이면 이미지 검사를 만들지 않는다. |

liveness에 `/health/ready`를 사용하면 모델 로딩 중 readiness 실패가 파드 재시작으로 이어질 수 있다. Docker `HEALTHCHECK`는 `/health`를 사용하고, Kubernetes에서는 liveness와 분리해 `startupProbe`/readiness에 `/health/ready`를 사용한다. 서버 GPU에서 모델 동기화·적재·ready 전환 시간은 아직 실측하지 않았다.

### 2.6 기동 순서와 실패 모드

1. entrypoint가 두 모델 경로가 로컬 디렉터리인지 확인한다.
2. 로컬 디렉터리인데 `config.json`이 없으면 검증 단계에서 실패한다.
3. 검증을 통과하면 SGLang 텍스트 서버(30000), 이미지 서버(30001)를 백그라운드로 시작한다.
4. FastAPI를 `serve-ai`로 foreground/PID 1에 올린다.
5. watcher가 두 자식과 PID 1을 감시한다. 텍스트/이미지 서버가 죽으면 오류 로그를 남기고 컨테이너를 실패 종료한다.

따라서 S3→PVC 동기화 전에 파드가 시작되어 모델 디렉터리만 생긴 경우, API가 살아 있는 것처럼 보이기 전에 entrypoint 오류로 종료된다. 모델 파일이 모두 준비된 뒤 파드를 시작하거나 initContainer/선행 Job 완료를 의존 조건으로 둔다.

### 2.7 로그에서 확인할 것

누끼 세션을 처음 만들 때 다음 로그를 찾는다.

```text
rembg ONNX Runtime providers: available=[...] selected=[...]
```

`CUDAExecutionProvider`가 사용 가능하면 선택 목록은 `CUDAExecutionProvider`와 `CPUExecutionProvider` 순서가 되고, 아니면 CPU만 선택된다. 이 로그가 실제 provider 선택을 확인하는 저장소 내 신호다. 컨테이너는 프로세스 로그를 파일로 리다이렉트하지 않고 stdout/stderr로 보낸다.

### 2.8 알려진 운영 제약과 미검증 항목

| 항목 | 현재 확인 결과 |
| --- | --- |
| PVC | `gp3`, `ReadWriteOnce`, 권장 100Gi, UID/GID 10001 쓰기 권한 필요. RWO라 단일 파드만 가능하며 다중 파드는 RDS+S3 이관이 별도 필요하다. |
| 렌더·누끼 메모리 | rembg 누적 RSS 12.90 GiB 실측. SGLang host RAM 합산은 미측정이므로 Memory 24/28Gi는 확정값이 아니다. |
| GPU 실행 | Docker 이미지 빌드와 정적 smoke test는 Mac에서 통과했지만, L40S에서 두 모델을 실제 적재·생성한 실행은 확인하지 않았다. |
| 누끼 CUDA 전환 | 코드와 GPU용 onnxruntime 설치는 확인했지만, 실제 `CUDAExecutionProvider` 선택 및 성능은 확인하지 않았다. |
| 기동 시간·처리량 | 모델 동기화, GPU 적재, ready 전환 시간과 p95 처리시간은 확인하지 않았다. |
| EKS 매니페스트 | 저장소 운영 기록상 EKS 전용 매니페스트는 확인하지 않았다. 현재 문서는 컨테이너와 운영 절차 기준이다. |
| 라이선스 | 배포 Qwen은 저장소 문서상 Apache 2.0 기반. 배포 FLUX의 상업 이용 범위, rembg/BiRefNet, 로컬 MLX 두 모델의 라이선스는 각각 확인 필요다. |

## 3. 근거 파일

- 배포 구조·자원·PVC·모델 동기화: [`docs/operations/eks-workload-spec.md`](../../operations/eks-workload-spec.md)
- 모델 라이선스·양자화·VRAM 계산: [`docs/operations/sglang-serving-research.md`](../../operations/sglang-serving-research.md), [`docs/operations/ubuntu-deployment.md`](../../operations/ubuntu-deployment.md)
- 환경변수 alias: [`src/detail_page_ai/config.py`](../../../src/detail_page_ai/config.py), [`.env.example`](../../../.env.example)
- 기동·모델 경로 오류·포트: [`deploy/sglang/entrypoint.sh`](../../../deploy/sglang/entrypoint.sh), [`deploy/sglang/Dockerfile`](../../../deploy/sglang/Dockerfile)
- 헬스체크: [`src/detail_page_ai/app.py`](../../../src/detail_page_ai/app.py)
- 누끼 provider·모델명·로그: [`src/detail_page_ai/source_photos.py`](../../../src/detail_page_ai/source_photos.py)
- 로컬 모델과 실측 기록: [`docs/operations/local-llm.md`](../../operations/local-llm.md), [`docs/evaluation/pipeline-run-2026-09-17.md`](../../evaluation/pipeline-run-2026-09-17.md), [`docs/evaluation/pilot-report-2026-09-09.md`](../../evaluation/pilot-report-2026-09-09.md)
