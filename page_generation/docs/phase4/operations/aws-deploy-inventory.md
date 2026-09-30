# AWS 배포 반입 목록 (Deploy Inventory)

작성일: 2026-09-17  
대상 서비스: 상세페이지 생성 AI 서비스 (`detail-page-ai` + SGLang 텍스트/이미지 통합 파이프라인)  
상위 문서: [`docs/phase4/operations/eks-workload-spec.md`](eks-workload-spec.md), [`docs/phase4/operations/aws-migration-checklist.md`](aws-migration-checklist.md)

> [!WARNING]
> **필독 검증 상태 (과장 금지)**
> - **서버 GPU에서는 아직 한 번도 실행되지 않았습니다.**
> - `deploy/sglang/Dockerfile`(SGLang + CUDA)은 **아직 빌드된 적이 없습니다.** (서비스 이미지 `deploy/Dockerfile`만 2026-09-17에 Linux 환경에서 빌드·기동을 확인했습니다. 이 둘을 혼동하지 마세요.)
> - 본 문서의 CPU·메모리·VRAM 수치는 실측값이 아닌 **미검증 추정치/계산값**이며, 첫 GPU 배포 시 실측을 거쳐 확정해야 합니다.

---

## 0. 배포 반입 총괄 요약

배포 시 **무엇을, 어디에, 누가** 올려야 하는지 한눈에 정리한 총괄 표입니다.

| 번호 | 항목 | 무엇을 (반입 대상) | 어디에 (배포 대상) | 담당 | 상태 |
| ---: | --- | --- | --- | :---: | :---: |
| 1 | **컨테이너 이미지** | 단일 통합 이미지 (FastAPI :8000 + SGLang 30000/30001) | AWS ECR | 우리 / 인프라팀 | 미검증 |
| 2 | **모델 가중치** | 텍스트(Qwen 27B) 및 이미지(FLUX 9B) 가중치 디렉터리 | S3 (`jangin-{env}-s3-models`) → PVC | 인프라팀 / 우리 | 회신 대기 |
| 3 | **영구 볼륨** | PVC 1개 (`gp3`, 100Gi, `ReadWriteOnce`) | `/var/lib/detail-page-ai` (K8s PVC) | 인프라팀 | 회신 대기 |
| 4 | **시크릿 (Secret)** | `BACKEND_AUTH_TOKEN`, `AI_INTERNAL_AUTH_TOKEN` (2개) | K8s Secret | BE팀 / 인프라팀 | 회신 대기 |
| 5 | **설정값 (ConfigMap)** | `TEXT_MODEL_PATH`, `IMAGE_MODEL_PATH`, `BACKEND_URL` 등 | K8s ConfigMap / Env | 인프라팀 / 우리 | 회신 대기 |
| 6 | **워크로드 자원** | GPU L40S 1장 (`nvidia.com/gpu: 1`), CPU 3~6, RAM 16~28Gi | K8s Deployment resources | 인프라팀 / 우리 | 미검증 |
| 7 | **프로브 (Probe)** | liveness (`/health`), readiness/startup (`/health/ready`) | K8s Pod Spec (무인증) | 우리 / 인프라팀 | 준비됨 |
| 8 | **네트워크** | BE 콜백 주소 연동, S3 Gateway Endpoint, 8000 Service 노출 | VPC / K8s Service | 인프라팀 / BE팀 | 회신 대기 |
| 9 | **이미지 발행 (CI)** | `main` push 시 `page_generation/**` 트리거 ECR 빌드/푸시 | GitHub Actions 파이프라인 | 인프라팀 / 우리 | 회신 대기 |

---

## 1. 컨테이너 이미지 (Container Image)

| 항목 | 상세 사양 | 대상 위치 | 담당 | 상태 | 비고 |
| --- | --- | --- | :---: | :---: | --- |
| **빌드 소스** | [`deploy/sglang/Dockerfile`](../../../deploy/sglang/Dockerfile) | GitHub 저장소 | 우리 | 준비됨 | CUDA + SGLang + FastAPI 단일 통합 정의 |
| **진입 스크립트** | [`deploy/sglang/entrypoint.sh`](../../../deploy/sglang/entrypoint.sh) | 컨테이너 내부 `/usr/local/bin` | 우리 | 준비됨 | SGLang 2서버 백그라운드 + FastAPI PID 1 감독 |
| **빌드 컨텍스트** | `page_generation/` (모노레포 하위 디렉터리) | CI / 빌드 머신 | 인프라팀 / 우리 | 준비됨 | `docker build -f deploy/sglang/Dockerfile .` |
| **레지스트리** | AWS ECR (`{account_id}.dkr.ecr.{region}.amazonaws.com/...`) | AWS ECR | 인프라팀 | 회신 대기 | ECR 리포지토리 생성 및 푸시 권한 필요 |
| **프로세스 구조** | 단일 파드/단일 컨테이너 내 3개 프로세스 공존 | K8s Pod 1개 | 우리 | 미검증 | L40S GPU 배타 할당 공유를 위해 단일 컨테이너 필수 |
| **노출 포트** | FastAPI `:8000` (Service 노출), SGLang `30000`, `30001` (내부) | K8s Service | 인프라팀 | 준비됨 | 30000/30001은 `127.0.0.1` 루프백 통신 전용 |
| **빌드 이력 주의** | `deploy/sglang/Dockerfile`은 **아직 빌드된 적 없음** | - | - | 미검증 | `deploy/Dockerfile`(CPU 전용)만 Linux 빌드 검증됨 |

---

## 2. 모델 가중치 (Model Weights — S3 사전 업로드)

> **확정 사양 (S3 사전 업로드 방식)**:
> - 인프라팀이 S3(`jangin-{env}-s3-models`) → PVC 동기화를 담당합니다 (initContainer 또는 Job의 `aws s3 sync`, VPC S3 Gateway Endpoint 경유로 NAT 트래픽 미경유).
> - 우리 컨테이너는 PVC의 로컬 디렉터리만 읽습니다. 애플리케이션 컨테이너에는 AWS CLI·boto3·IAM 권한이 **불필요**합니다.
> - 로컬 디렉터리 모드에서는 SGLang의 `--revision` 플래그가 적용되지 않으므로, **어느 커밋의 가중치인지는 S3 업로드 시점에서 관리·보장**해야 합니다.

| 모델 구분 | HuggingFace 원본 저장소 | 고정 커밋 | 가중치 크기 | 포맷 및 반입 위치 | 담당 | 상태 |
| --- | --- | --- | --- | --- | :---: | :---: |
| **텍스트·비전 분석** | `cyankiwi/Qwen3.8-27B-AWQ-INT4` | `6e134bae811fb5adac50ee042ae5f029ac6779aa` | 19.6 GiB | `config.json` + `*.safetensors` 디렉터리<br>→ S3 `.../qwen3.8-27b-awq/` | 인프라팀 | 회신 대기 |
| **이미지 확산 생성** | `circulus/FLUX.2-klein-9B-bnb-4bit` | `58c2804f31af12c8888504b96250010c50b55e44` | 약 10.2 GiB | `config.json` + `*.safetensors` 디렉터리<br>→ S3 `.../flux.2-klein-9b-bnb/` | 인프라팀 | 회신 대기 |
| **동기화 방식** | initContainer / Job 기반 `aws s3 sync` | - | 총 ~30 GiB | S3 Gateway Endpoint 경유 동기화 | 인프라팀 | 회신 대기 |
| **라이선스 확인** | FLUX Non-Commercial 원본 커뮤니티 4bit | - | - | 상업 운영 전 라이선스 범위 확인 필요 (대안: Apache 2.0 `FLUX.2-klein-4B`) | 인프라팀 / BE팀 | 확인 필요 |

---

## 3. 영구 볼륨 (Persistent Volume Claim)

컨테이너 재시작 시 모델 재다운로드를 방지하고 산출물/상태를 보존하기 위해 단일 PVC를 마운트합니다.

| 속성 | 확정 사양 | 담당 | 상태 | 비고 |
| --- | --- | :---: | :---: | --- |
| **PVC 개수 / 타입** | 1개 / `gp3`, `ReadWriteOnce` | 인프라팀 | 회신 대기 | 단일 파드 전용 |
| **권장 용량** | **100Gi** | 인프라팀 | 회신 대기 | 모델 ~30GiB + U2Net ~1GiB + 캐시/산출물 여유 |
| **마운트 경로** | `/var/lib/detail-page-ai` | 인프라팀 / 우리 | 준비됨 | 컨테이너 내부 공통 베이스 경로 |
| **권한 설정** | `securityContext.fsGroup: 10001` | 인프라팀 | 회신 대기 | Non-root `appuser`(UID/GID 10001) 쓰기 권한 필수 |

### PVC 하위 디렉터리 구조
```text
/var/lib/detail-page-ai/          ← 단일 PVC 마운트 지점
├ state.sqlite3                    작업 상태 및 BE 전달 outbox DB
├ assets/                          생성된 이미지 산출물 및 중간 자산
├ models/                          모델 가중치 디렉터리 (S3 sync 대상)
│  ├ huggingface/                  (로컬 다운로드 fallback 시 허브 캐시)
│  ├ u2net/                        rembg 누끼 모델 (~973 MB)
│  └ torch/                        torch 캐시
└ cache/                           런타임 캐시 (SGLang, FlashInfer, Triton, CUDA)
```

---

## 4. 시크릿 (K8s Secrets)

K8s Secret으로 안전하게 주입하며, 이미지나 저장소 코드에 절대 포함하지 않습니다.

| 시크릿 키 이름 | 필수 여부 | 용도 | 담당 | 상태 | 비고 |
| --- | :---: | --- | :---: | :---: | --- |
| `BACKEND_AUTH_TOKEN` | **예** | BE 콜백 호출 시 Bearer 인증 토큰 | BE팀 / 인프라팀 | 회신 대기 | BE와 사전 협의된 공유 토큰 |
| `AI_INTERNAL_AUTH_TOKEN` | **예** | `/internal/v1/ai/*` 호출 검증 공유 토큰 (`X-AI-Internal-Token`) | BE팀 / 인프라팀 | 회신 대기 | BE가 AI 호출 시 헤더로 전달 |
| `HF_TOKEN` | **불필요** | Hugging Face Hub 다운로드 토큰 | - | **불필요** | **S3 사전 업로드 방식에서는 주입 불필요** |

---

## 5. 설정값 (ConfigMap / Environment Variables)

| 환경 변수명 | 값 (서버/EKS 배포 기준) | 주입 방식 | 담당 | 상태 |
| --- | --- | :---: | :---: | :---: |
| `TEXT_MODEL_PATH` | PVC 내 절대 경로 (예: `/var/lib/detail-page-ai/models/qwen3.8-27b-awq`) | ConfigMap | 인프라팀 / 우리 | 회신 대기 |
| `IMAGE_MODEL_PATH` | PVC 내 절대 경로 (예: `/var/lib/detail-page-ai/models/flux.2-klein-9b-bnb`) | ConfigMap | 인프라팀 / 우리 | 회신 대기 |
| `BACKEND_URL` | BE 엔드포인트 URL (환경별 내부 도메인/서비스 주소) | ConfigMap | BE팀 / 인프라팀 | 회신 대기 |
| `TEXT_SERVED_MODEL_NAME` | `qwen-text` | 기본값 (생략 가능) | 우리 | 준비됨 |
| `IMAGE_SERVED_MODEL_NAME` | `flux-klein` | 기본값 (생략 가능) | 우리 | 준비됨 |
| `LOCAL_TEXT_PROVIDER` | `sglang` | 기본값 (생략 가능) | 우리 | 준비됨 |
| `LOCAL_IMAGE_PROVIDER` | `sglang` | 기본값 (생략 가능) | 우리 | 준비됨 |
| `LOCAL_TEXT_URL` | `http://127.0.0.1:30000` | 기본값 (생략 가능) | 우리 | 준비됨 |
| `LOCAL_IMAGE_URL` | `http://127.0.0.1:30001` | 기본값 (생략 가능) | 우리 | 준비됨 |
| `TEXT_MEM_FRACTION` | `0.50` (VRAM 정적 선점률) | ConfigMap / 기본값 | 우리 | 준비됨 |
| `TEXT_CONTEXT_LENGTH` | `16384` | ConfigMap / 기본값 | 우리 | 준비됨 (2026-09-30 8192→16384, 분석 입력 9307토큰) |
| `AI_CORS_ORIGINS` | 주입 불필요 (BE 서버 간 통신이므로 기본값 유지) | - | - | 준비됨 |

---

## 6. 워크로드 자원 (Workload Resources — 추정치)

> [!IMPORTANT]
> 아래 수치는 **미검증 추정치 및 계산값**입니다. 첫 배포에서 실제 부하를 측정한 뒤 확정해야 합니다.

| 자원 구분 | 요청 (Requests) | 상한 (Limits) | 추정 근거 | 담당 | 상태 |
| --- | :---: | :---: | --- | :---: | :---: |
| **GPU** | `nvidia.com/gpu: 1` | `nvidia.com/gpu: 1` | NVIDIA L40S 48GB VRAM 1장 배타 사용 | 인프라팀 | 미검증 |
| **VRAM** | 약 32.6 GiB (계산값) | 48 GiB | 텍스트 선점 22.4 GiB (0.50) + 이미지 10.2 GiB (여유 약 12 GiB) | 우리 | 미검증 |
| **CPU** | `3` | `6` | Playwright Chromium 렌더링 + rembg CPU 추론 (`g6e.xlarge` 4 vCPU 기준) | 인프라팀 | 미검증 |
| **메모리** | `16Gi` | `28Gi` | SGLang 2서버 Python/PyTorch 상주분 + 로딩 버퍼 + 렌더링 (`g6e.xlarge` 32GiB 기준) | 인프라팀 | 미검증 |

- 노드 인스턴스: `g6e.xlarge`(4 vCPU / 32 GiB / L40S 1장)에서 스케줄링 가능하도록 설계됨.
- 노드가 `g6e.2xlarge`(8 vCPU / 64 GiB) 급인 경우 CPU request를 4~6으로 상향하면 렌더링 처리량 향상에 유리함.

---

## 7. 헬스체크 프로브 (Probes)

두 프로브 모두 **인증 토큰이 필요하지 않습니다.**

| 프로브 종류 | 대상 엔드포인트 | 기대 응답 | 검사 내용 및 설정 주의 | 담당 | 상태 |
| --- | --- | :---: | --- | :---: | :---: |
| **livenessProbe** | `GET /health` | `200 OK`<br>`{"status":"ok"}` | FastAPI 프로세스 생존 확인. **추론 서버를 확인하지 않음.** `/health/ready`로 설정 절대 금지. | 우리 / 인프라팀 | 준비됨 |
| **readinessProbe** | `GET /health/ready` | `200 OK`<br>`{"status":"ok", ...}` | SGLang 2서버(`/v1/models`) 2초 타임아웃 헬스체크. 미준비 시 `503 Service Unavailable`. | 우리 / 인프라팀 | 준비됨 |
| **startupProbe** | `GET /health/ready` | `200 OK` | 파드 초기 기동 및 모델 GPU 적재 완료 대기. `failureThreshold`를 넉넉히 설정 필요. | 인프라팀 | 준비됨 |

---

## 8. 네트워크 및 엔드포인트 (Network & Endpoints)

| 통신 방향 | 출발지 / 목적지 | 프로토콜 / 포트 | 노출 필요 여부 | 담당 | 상태 |
| --- | --- | :---: | :---: | :---: | :---: |
| **인바운드** | BE → AI Pod | HTTP / `:8000` | **Service 노출 필요** (Private K8s Service) | 인프라팀 | 회신 대기 |
| **내부 루프백** | FastAPI → SGLang Text | HTTP / `:30000` | 노출 불필요 (`127.0.0.1` 컨테이너 내부 통신) | 우리 | 준비됨 |
| **내부 루프백** | FastAPI → SGLang Image | HTTP / `:30001` | 노출 불필요 (`127.0.0.1` 컨테이너 내부 통신) | 우리 | 준비됨 |
| **아웃바운드 (콜백)** | AI Pod → BE | HTTP(S) / `BACKEND_URL` | VPC 내부 사설망 통신 (작업 완료 multipart 전달) | BE팀 / 인프라팀 | 회신 대기 |
| **아웃바운드 (S3 sync)** | initContainer → S3 | HTTPS / `:443` | **VPC S3 Gateway Endpoint** 경유 (NAT 게이트웨이 미경유) | 인프라팀 | 회신 대기 |

---

## 9. 이미지 빌드 및 배포 파이프라인 (CI/CD)

| 항목 | 사양 / 설정값 | 담당 | 상태 | 비고 |
| --- | --- | :---: | :---: | --- |
| **소스 저장소** | `https://github.com/Jangingmall/GenAI` | 우리 / 인프라팀 | 준비됨 | AI 파트 비공개 모노레포 |
| **발행 브랜치** | `main` | 인프라팀 | 준비됨 | `main` 브랜치 push 기준 |
| **트리거 경로** | `page_generation/**` | 인프라팀 | 회신 대기 | `chat_bot/` 등 타 서비스 변경 시 재빌드 방지 |
| **빌드 컨텍스트** | `page_generation/` 최상위 | 인프라팀 | 회신 대기 | `docker build -f deploy/sglang/Dockerfile .` |
| **접근 권한** | 비공개 모노레포 읽기 권한 | 인프라팀 / 관리자 | 회신 대기 | CI 러너 또는 인프라 계정에 조직 권한 부여 필요 |
