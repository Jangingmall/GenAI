# AWS 이관·검증 가이드 (상세페이지 AI)

작성일: 2026-09-10 · 최종 개정: 2026-09-16 (SGLang 3서비스 구성 확정 및 EKS 현황 정합성 반영)  
대상: 상세페이지 생성 AI 서비스 (`detail-page-ai` 및 SGLang 추론 서빙)  
체크리스트: [AWS 이관 준비물 및 단계별 체크리스트](aws-migration-checklist.md)

이 문서는 로컬 Apple Silicon(MLX) 환경에서 검증된 상세페이지 생성 파이프라인을 AWS 환경으로 이관하여 **1건 end-to-end 생성 및 릴리스 품질 게이트 통과까지 검증**하는 종합 운영 가이드다.

> [!IMPORTANT]
> **현재 확정 운영 경로와 EKS 현황 (정본 사실 기록)**:
> 1. **확정된 운영 경로**: 단일 호스트(AWS EC2 `g6e.xlarge`, 1x NVIDIA L40S 48GB, Ubuntu) + `docker compose` 기반 3개 서비스(`detail-page-ai`, `sglang-text`, `sglang-image`) 공존 구성이다.
> 2. **EKS 현황 (미결정 상태)**: 현재 저장소에는 EKS 전용 산출물(Deployment/Service/PVC 매니페스트, Helm 차트, ECR 푸시 스크립트 등)이 전무하며, EKS 배포 경로는 아직 확정되지 않은 **미결정 상태**이다. 본 문서의 EKS 관련 서술(단일 파드 + EBS PVC, HPA 제약 등)은 **"EKS로 갈 경우의 설계안"**으로 정리·보존한다.
> 3. **검증 상태 (과장 금지)**: 로컬 단위 테스트 358개 통과, `docker compose config` 유효성, `detail-page-ai` 서비스 컨테이너 arm64 빌드·기동·healthy 확인 및 amd64 빌드 확인은 완료되었다. 그러나 **GPU 에서는 한 번도 실행되지 않았다.** 두 모델 동시 적재, 4-bit 파이프라인 로딩, 편집 품질, 처리 시간 모두 미검증 상태이며 첫 배포 실측을 통해 확인해야 한다.

> [!NOTE]
> **성능 수치 기준선 (로컬 베이스라인 vs AWS)**:  
> 본 문서의 실측 수치는 2026-09-10 Apple Silicon MLX 환경(M-series 통합 메모리, `Qwen3.8-27B-4bit` 18.2GB + `flux2-klein-9b-4bit` 9.5GB) 기준선이다. 6건 파일럿 실행 시 이미지 생성을 포함하여 **약 27분(1건당 평균 약 226초)**이 소요되었다.  
> 이는 **AWS 인프라의 성능 수치가 아니며 로컬 개발 기준선**이다. AWS GPU(L40S 등)에서의 실제 처리 속도와 레이턴시는 첫 배포 실측 후 확정한다.

---

## 1. 구성 요소와 포트

| 구성 요소 | 포트 | 런타임/기술 스택 | 역할 | 현재 상태 |
|---|---|---|---|---|
| **detail-page-ai** | **8000** | Python 3.13, FastAPI, Node.js/Chromium, SQLite | Job 접수, 상태 머신, Draft 생성, React 문서 조립, PNG 렌더, 상품 BE outbox 배달 | 컨테이너화 준비 완료 (`Dockerfile`, CPU 전용) |
| **sglang-text** | **30000** | `lmsysorg/sglang:v0.5.19`, Python 3, CUDA | 텍스트·비전 멀티모달 분석 (`cyankiwi/Qwen3.8-27B-AWQ-INT4`, 공개명 `qwen-text`) | SGLang SRT 서버 확정 (GPU 분할: mem-fraction-static 0.50) |
| **sglang-image** | **30001** | `local/sglang-diffusion:0.5.19` (`sglang[diffusion]` + `bitsandbytes`), CUDA | 이미지 생성 및 in-context 편집 (`circulus/FLUX.2-klein-9B-bnb-4bit`, 공개명 `flux-klein`) | SGLang 확산 서버 확정 (GPU 분할: VRAM 약 10.2 GiB 상주) |

- **단일 GPU 공유**: 두 SGLang 프로세스가 단일 L40S 48GB GPU를 분할하여 동시 상주한다.
- **클라이언트 연결**: `detail-page-ai`는 `LOCAL_TEXT_URL=http://sglang-text:30000` 및 `LOCAL_IMAGE_URL=http://sglang-image:30001`로 각 추론 서버를 호출한다.
- **로컬 개발 경로 분리**: Apple Silicon MLX Serve 경로(`LOCAL_*_PROVIDER=mlx`, `127.0.0.1:11234`)는 로컬 Mac 개발용으로 코드베이스에 유지되며, 서버 운영 경로와 분리된다.

---

## 2. 지금 그대로는 뜨지 않는다 — 핵심 제약과 갭 4가지 현황

초기 로컬 MLX 환경에서 식별되었던 4대 기술적 갭의 해소 상태와 근거는 다음과 같다.

### 갭 1. Apple Silicon 전용 MLX Serve 종속성 — [해소됨]
- **초기 현상**: MLX Serve는 macOS/Apple Silicon 전용 프레임워크로, AWS EC2 Linux CUDA 환경에서는 바이너리가 실행되지 않았다.
- **해소 상태 및 근거**: Linux CUDA 호환 SGLang v0.5.19 서빙 스택으로 전면 교체 확정되었다. 텍스트 분석용 `sglang-text`(포트 30000)와 이미지 생성·편집용 `sglang-image`(포트 30001)를 Docker Compose로 구성 완료했다.
- **남은 확인 사항**: 로컬 Compose 설정 검증은 완료되었으나, **GPU 환경에서 실제로 컨테이너를 기동한 이력은 없다.** 첫 배포 시 L40S 인스턴스에서의 실기동 및 VRAM 분할 동작을 확인해야 한다.

### 갭 2. 가중치 포맷 불일치 — [해소됨]
- **초기 현상**: 로컬 가중치(`ddalcu/Qwen3.8-27B-MLX-Serve-4bit`, `mlx-community/flux2-klein-9b-4bit`)는 MLX 전용 포맷이었다.
- **해소 상태 및 근거**: CUDA 및 SGLang에서 지원하는 양자화 가중치를 채택하고 커밋을 영구 고정했다:
  - 텍스트: `cyankiwi/Qwen3.8-27B-AWQ-INT4` (19.60 GiB, 고정 커밋 `6e134bae811fb5adac50ee042ae5f029ac6779aa`)
  - 이미지: `circulus/FLUX.2-klein-9B-bnb-4bit` (약 10.2 GiB, 고정 커밋 `58c2804f31af12c8888504b96250010c50b55e44`)
  - 모델은 이름 있는 도커 볼륨 `huggingface-cache`(`/root/.cache/huggingface`)에 1회 다운로드되어 캐싱된다.
- **라이선스 사실 기록**: 원본 `black-forest-labs/FLUX.2-klein-9B`는 FLUX Non-Commercial License이다. 채택된 `circulus/FLUX.2-klein-9B-bnb-4bit`는 커뮤니티 양자화본이며 **관리자 결정으로 채택**되었다. 상업 운영 전 BFL 라이선스 범위 확인이 필요하다(사실만 기록). 대안은 Apache 2.0 라이선스의 `black-forest-labs/FLUX.2-klein-4B`이다.

### 갭 3. 클라이언트 이미지 편집 호출 규약 불일치 — [해소됨]
- **초기 현상**: MLX Serve 클라이언트는 이미지 편집 요청 시 비표준 JSON 규약(`POST /v1/images/generations`에 `mode: "edit"`, `image: "<base64>"`)을 사용하여 일반 Diffusers/OpenAI 호환 서버에서 파싱 에러(422)가 발생할 위험이 있었다.
- **해소 상태 및 근거**: `src/local_detail_page_ai/clients.py`에 `sglang` provider 구현을 완료했다 (`LOCAL_IMAGE_PROVIDER=sglang`, `BACKGROUND_PROVIDER=sglang`):
  - 생성: `POST /v1/images/generations` (JSON: `model`, `prompt`, `size`, `response_format=b64_json`, `num_inference_steps` 등)
  - 편집: `POST /v1/images/edits` (**multipart/form-data**, `image` 필드로 소스 이미지 전송). SGLang 핸들러에 필드가 없는 `strength`는 전송하지 않음.
  - SGLang 네이티브 엔드포인트와 규약이 일치하므로 Diffusers 앞단의 별도 프록시 어댑터 배치가 불필요해졌다.

### 갭 4. 컨테이너 빌드 시 필수 정적 자산 누락 — [해소됨]
- **초기 현상**: `assets/references/detail-page-layouts.json`(25종 상세페이지 원형 카탈로그)이 `Dockerfile` 복사 대상에서 누락되어 컨테이너 실행 시 레이아웃 카탈로그가 빈 리스트(`[]`)로 초기화될 위험이 있었다.
- **해소 상태 및 근거**: `Dockerfile`에 `COPY assets/references/detail-page-layouts.json ./assets/references/detail-page-layouts.json` 레이어가 정상 추가되어 컨테이너 빌드 시 25종 레이아웃 원형이 정상 포함됨을 확인했다.

---

## 3. 이관 준비물 및 체크리스트 연계

상세한 준비 절차와 검증 방법은 [AWS 이관 준비물 및 단계별 체크리스트](aws-migration-checklist.md)에 기술되어 있으며, 요약은 다음과 같다:

1. **클라우드 인프라**: EC2 `g6e.xlarge` (L40S 48GB 1장) 온디맨드 인스턴스 쿼터 승인 및 인스턴스 생성.
2. **호스트 환경**: Ubuntu 22.04/24.04 LTS, NVIDIA 드라이버 (550 권장), Docker Engine 및 NVIDIA Container Toolkit.
3. **모델 가중치**: Hugging Face 허브에서 고정 커밋 기반으로 다운로드되어 볼륨 `huggingface-cache`에 1회 캐싱 (`HF_TOKEN` 설정 가능).
4. **컨테이너 이미지**: `detail-page-ai` 애플리케이션 이미지 및 `local/sglang-diffusion:0.5.19` 확산 서버 이미지 빌드.
5. **스토리지**: 도커 볼륨 `detail-page-ai-data` 마운트 (`/var/lib/detail-page-ai`).
6. **환경변수/보안**: `.env.example`을 기반으로 `LOCAL_TEXT_PROVIDER=sglang`, `LOCAL_IMAGE_PROVIDER=sglang`, `AI_INTERNAL_AUTH_TOKEN`, `BACKEND_PRODUCT_URL`, `BACKEND_AUTH_TOKEN`, `AI_CORS_ORIGINS` 설정.

---

## 4. 운영 및 이관 경로

### 확정 운영 경로: 단일 g6e.xlarge + Docker Compose (단일 호스트 공존)

현재 프로젝트에서 확정 및 검증된 운영 경로는 단일 AWS EC2 `g6e.xlarge` 인스턴스 상에서 Docker Compose로 3개 서비스를 구동하는 방식이다.

```text
[Host: AWS EC2 g6e.xlarge (1x NVIDIA L40S 48GB, Ubuntu)]
  ├── [detail-page-ai :8000] (FastAPI, Playwright Chromium, SQLite) -- CPU 전용
  │     ├── HTTP --> [sglang-text :30000]   (Qwen3.8-27B AWQ INT4, VRAM 50% 선점)
  │     └── HTTP --> [sglang-image :30001]  (FLUX.2-klein-9B bnb-4bit, VRAM ~10.2GB 상주)
  ├── 볼륨: detail-page-ai-data (/var/lib/detail-page-ai - state.sqlite3, assets/)
  └── 볼륨: huggingface-cache (/root/.cache/huggingface - 모델 가중치 1회 다운로드 캐시)
```

- **동일 호스트 내부 통신**: 텍스트 분석 및 이미지 생성/편집(페이지당 수 회, 대용량 base64 및 multipart 통신)이 빈번하므로 Docker 브릿지 네트워크 내에서 통신하여 네트워크 비용 및 지연을 최소화한다.
- **GPU 분할 상주**: 단일 L40S(48GB) GPU를 두 SGLang 프로세스가 나눠 쓴다 (`sglang-text`는 `--mem-fraction-static 0.50`, `sglang-image`는 `--dit-cpu-offload false --text-encoder-cpu-offload false`).
- **서비스 기동 종속성**: `docker-compose.yml`에서 `detail-page-ai`는 `sglang-text`와 `sglang-image`의 `service_healthy`를 `depends_on`으로 대기한 후 기동된다.

---

### EKS 로 갈 경우의 설계안 (현재 미결정 상태)

> [!IMPORTANT]
> **EKS 현황 사실 명시 (4가지 기술 차이)**:  
> 현재 저장소에는 EKS 전용 산출물(Deployment/Service/PVC 매니페스트, Helm 차트, ECR 푸시 스크립트 등)이 전무하며, EKS 배포 경로는 **미결정 상태**이다.  
> EKS로 전환하기 위해서는 다음 4가지 핵심 차이점이 반드시 해결되어야 한다:
> 1. **K8s probe 매핑 (Dockerfile HEALTHCHECK 무시)**: K8s는 Dockerfile의 `HEALTHCHECK` 지시자를 무시하므로 매니페스트에 probe를 직접 정의해야 한다. 현재 FastAPI에는 전용 헬스체크 엔드포인트(`GET /health`, readiness용 `GET /health/ready`, 200 OK)가 이미 구현되어 있으므로 K8s의 `httpGet` probe로 바로 매핑할 수 있다.
> 2. **GPU 1장·2파드 분할 불가**: 표준 K8s NVIDIA device plugin은 컨테이너 단위 배타적 GPU 할당을 수행하므로, GPU 1장을 2개 파드가 나눠 쓸 수 없다. 단일 노드에서 구동하려면 GPU 타임슬라이싱/MPS 설정이 필요하거나, 두 SGLang 추론 프로세스를 단일 파드 내 멀티 컨테이너/통합 스크립트로 묶는 파드 설계가 필요하다.
> 3. **모델 캐시 스토리지 전환**: 도커 볼륨 `huggingface-cache`를 K8s 환경에 맞게 PVC(ReadWriteMany 또는 대용량 EBS)나 S3 동기화 init 컨테이너 방식으로 전환해야 한다.
> 4. **추론 서빙 규격 최신화**: 초기 설계서에 서술되었던 레거시 서빙 규격(vLLM + Diffusers 프록시) 대신 본 문서의 SGLang 2프로세스 규격으로 매니페스트를 작성해야 한다.

#### EKS 설계안: 단일 파드 + EBS PVC 구성 (EKS 전환 시 검토안)
- EKS GPU 노드 그룹에 단일 파드 형태로 배치 (위 제약 2에 따라 GPU 1장을 공유하기 위해 단일 파드 내 멀티 컨테이너 또는 통합 런처 배치).
- 영속성: `gp3` EBS PVC (`ReadWriteOnce`)를 `/var/lib/detail-page-ai`에 마운트하여 `state.sqlite3`와 생성 에셋을 영속화.
- 장애 복구: 파드 크래시 시 새 파드가 동일 EBS 볼륨을 마운트하고, `recover_interrupted()`가 미완료 작업을 `QUEUED`로 리셋하며, `SQLiteDeliveryOutbox` 루프가 미전송 이벤트를 상품 BE로 자동 재전송.

#### EKS 다중 파드(HPA) 수평 확장 시 제약 사항 및 해결 로드맵
- **EBS 한계**: EBS 볼륨은 `ReadWriteOnce`이므로 여러 노드의 파드 레플리카가 동시에 마운트할 수 없다.
- **EFS(NFS) 불가**: SQLite 파일을 EFS 네트워크 파일시스템에 마운트하면 동시 트랜잭션 시 파일 락 충돌로 DB가 손상된다.
- **해결 로드맵**: 추후 트래픽 증가로 인한 다중 파드 수평 확장이 필요할 경우, `JobRepository` 및 `DeliveryOutbox`를 **PostgreSQL(RDS/Aurora)**로 전환하고, `AssetStore`를 **S3**로 교체해야 한다.

---

## 5. 컨테이너 이미지 규격

### (1) ai-service 컨테이너 (`Dockerfile`)

| 항목 | 사양 / 설정값 | 비고 |
|---|---|---|
| 베이스 이미지 | `python:3.13-slim` | GPU 미사용 (CPU 전용 파이프라인) |
| 시스템 런타임 | Node.js, npm, Chromium 브라우저 바이너리 | `npx playwright install --with-deps chromium` |
| 패키지 관리 | `ghcr.io/astral-sh/uv:0.11.4` | `uv sync --locked --no-dev` |
| 정적 자산 복사 | `src/`, `web/`, `scripts/runtime/render_detail_page.mjs`, `assets/references/detail-page-layouts.json` | **layouts.json 정적 자산 포함 완료** |
| 실행 계정 | `appuser` (UID 10001, GID 10001) | 비root 보안 계정 |
| 볼륨 마운트 | `/var/lib/detail-page-ai` | SQLite 작업 DB 및 Asset 저장 디렉터리 |
| 진입점 | `serve-ai` (포트 8000) | `exec python -c "from detail_page_ai.app import run; run()"` |
| Dockerfile 헬스체크 | `GET /health` (200 OK, readiness: `GET /health/ready`) | Docker 런타임 및 K8s httpGet probe 호환 |

### (2) 추론 서버 컨테이너 (SGLang 2프로세스 확정 규격)

추론 서버는 과거 서술되었던 vLLM 및 Diffusers 별도 프록시 방식이 아니라, **SGLang 공식 이미지를 기반으로 2개 추론 서버 프로세스를 단일 GPU에 공존시키는 규격**으로 확정되었다.

| 구분 | 텍스트·비전 추론 서버 (`sglang-text`) | 이미지 생성·편집 확산 서버 (`sglang-image`) |
|---|---|---|
| **컨테이너 이미지** | `lmsysorg/sglang:v0.5.19` (공식 허브 이미지) | `local/sglang-diffusion:0.5.19` (커스텀 빌드) |
| **빌드 파일/방법** | 공식 이미지 직접 pull | `docker/sglang-diffusion.Dockerfile`<br>베이스: `lmsysorg/sglang:v0.5.19`<br>설치: `pip install sglang[diffusion]==0.5.19 bitsandbytes==0.50.2` |
| **추론 대상 모델** | `cyankiwi/Qwen3.8-27B-AWQ-INT4` | `circulus/FLUX.2-klein-9B-bnb-4bit` |
| **가중치 크기** | 19.60 GiB | 약 10.2 GiB (트랜스포머 4.36 + 텍스트 인코더 5.66 + VAE 0.16 GiB) |
| **고정 커밋 (Revision)** | `6e134bae811fb5adac50ee042ae5f029ac6779aa` | `58c2804f31af12c8888504b96250010c50b55e44` |
| **공개 모델명 (`--served-model-name`)** | `qwen-text` | `flux-klein` |
| **서비스 포트** | **30000** | **30001** |
| **기동 명령어 및 주요 인자** | `python3 -m sglang.launch_server`<br>`--model-path cyankiwi/Qwen3.8-27B-AWQ-INT4`<br>`--revision 6e134bae811fb5adac50ee042ae5f029ac6779aa`<br>`--served-model-name qwen-text`<br>`--host 0.0.0.0 --port 30000`<br>`--mem-fraction-static 0.50`<br>`--context-length 8192`<br>`--trust-remote-code` | `sglang serve`<br>`--model-path circulus/FLUX.2-klein-9B-bnb-4bit`<br>`--revision 58c2804f31af12c8888504b96250010c50b55e44`<br>`--served-model-name flux-klein`<br>`--host 0.0.0.0 --port 30001`<br>`--num-gpus 1`<br>`--dit-cpu-offload false`<br>`--text-encoder-cpu-offload false` |
| **헬스체크 엔드포인트** | `GET http://127.0.0.1:30000/v1/models` (200 OK) | `GET http://127.0.0.1:30001/v1/models` (200 OK)<br>*(주의: 확산 서버에는 `/health` 엔드포인트 없음)* |
| **주요 런타임 옵션 사유** | `--mem-fraction-static 0.50`: 48GB 중 약 24GB를 텍스트 모델 가중치(19.6 GiB) 및 8192 컨텍스트 KV 캐시 풀로 선점하여 확산 모델 VRAM 여유 보장 | `--dit-cpu-offload false --text-encoder-cpu-offload false`: SGLang 기본값인 CPU 오프로드를 꺼서 4-bit 텍스트 인코더를 GPU에 상주시키고 호스트 RAM 압박 방지 |

---

## 6. GPU 사이징 및 VRAM 예산

| 항목 | 점유 VRAM | 산출 근거 및 비고 |
|---|---:|---|
| `sglang-text` 가중치 및 KV 캐시 선점 | 약 22.35~24.0 GiB | `cyankiwi/Qwen3.8-27B-AWQ-INT4` 가중치 19.60 GiB, `--mem-fraction-static 0.50`, 8192 컨텍스트 풀 |
| `sglang-image` 가중치 및 파이프라인 | 약 10.20 GiB | `circulus/FLUX.2-klein-9B-bnb-4bit` (트랜스포머 4.36 + 텍스트 인코더 5.66 + VAE 0.16 GiB) |
| 순수 가중치 합계 | 약 29.80 GiB | 텍스트 가중치(19.60 GiB) + 이미지 파이프라인 가중치(10.20 GiB) |
| **정적 점유 합계 (선점+가중치)** | **약 32.55 GiB** | 텍스트 선점(22.35 GiB) + 이미지 가중치(10.20 GiB) 기준 (44.70 GiB 중 약 72.8% 점유) |
| **동적 여유 버퍼 (런타임 활성화 버퍼)** | **약 12.15 GiB** | 이미지 생성 스파이크 및 텍스트 활성화 텐서 처리용 여유 공간 |
| **권장 인스턴스** | **EC2 `g6e.xlarge`** | **NVIDIA L40S 48GB 1장 (물리 48GB, 실가용 약 44.70 GiB)** |

> [!NOTE]
> **호스트 RAM 압박 해소**:  
> 확산 서버에서 CPU 오프로드를 끄고(`--dit-cpu-offload false --text-encoder-cpu-offload false`) GPU에 파이프라인을 전량 상주시키므로, `g6e.xlarge`의 호스트 시스템 메모리(32 GiB)에 대용량 가중치가 오프로드되어 발생하는 스왑 및 OOM 위험이 없다.

> [!WARNING]
> **FLUX 모델 라이선스 사실 확인 필요**:  
> 원본 `black-forest-labs/FLUX.2-klein-9B` 모델은 FLUX Non-Commercial License가 적용된다. 현재 채택된 `circulus/FLUX.2-klein-9B-bnb-4bit`는 그 커뮤니티 양자화본이며 **관리자 결정으로 채택**되었다. 상업 배포 전 BFL 라이선스 허용 범위를 확인할 필요가 있다(사실만 기록, 권고 금지). 상업 이용이 보장되는 공식 대안은 Apache 2.0 라이선스의 `black-forest-labs/FLUX.2-klein-4B` (가중치 7.22 GiB)이다.

---

## 7. 모델 가중치 배포 및 캐싱

### Docker Compose 환경 (현재 확정 경로)
- **Hugging Face 허브 직접 1회 다운로드**:
  - 컨테이너 최초 기동 시 각 SGLang 프로세스가 `--model-path` 및 `--revision`에 지정된 저장소에서 모델을 직접 다운로드한다.
  - 도커 이름 있는 볼륨 `huggingface-cache` (`/root/.cache/huggingface`)에 캐시되므로 컨테이너가 재시작되어도 재다운로드가 발생하지 않는다.
  - **가중치 버전 고정**: `.env`의 `TEXT_MODEL_REVISION`(`6e134bae811fb5adac50ee042ae5f029ac6779aa`) 및 `IMAGE_MODEL_REVISION`(`58c2804f31af12c8888504b96250010c50b55e44`)을 통해 저장소 커밋이 고정되어 일관된 바이너리를 보장한다.
  - **사설 저장소 인증**: 필요 시 `HF_TOKEN` 환경변수로 Hugging Face 토큰을 주입한다 (현재 채택된 두 모델은 공개 저장소이므로 공백 가능).

### EKS 환경 전환 시 (설계안)
- **S3 모델 저장소 및 S3 Gateway VPC Endpoint**:
  - 클러스터 환경에서는 모델 가중치를 S3 버킷(`s3://jangin-{env}-s3-models/detail-page/`)에 사전 적재한 후, S3 Gateway Endpoint를 통해 무료·고속으로 init 컨테이너에서 노드 스토리지로 동기화하는 구조를 취한다.

---

## 8. 상태(state) 처리 및 영속성 ([persistence.py](../../src/detail_page_ai/persistence.py))

ai-service는 파일 기반의 두 가지 영속성 저장소를 사용한다.

| 환경변수 | 기본값 | 컨테이너 배포 경로 | 저장 내용 |
|---|---|---|---|
| `SQLITE_PATH` | `.local/detail-page-ai/state.sqlite3` | `/var/lib/detail-page-ai/state.sqlite3` | `detail_page_jobs` (작업 상태/임대), `detail_page_outbox` (BE 배달 큐) |
| `ASSET_STORE_DIR` | `.local/detail-page-ai/assets` | `/var/lib/detail-page-ai/assets` | 원본 및 생성된 이미지 바이너리 |
| `U2NET_HOME` | (내장 기본값) | `/var/lib/detail-page-ai/models/u2net` | rembg 누끼 모델 가중치 (`birefnet-general.onnx`, 약 973MB) |

- **Docker 볼륨 마운트**: `detail-page-ai-data` 볼륨을 `/var/lib/detail-page-ai`에 마운트하여 컨테이너 재기동 후에도 작업 DB, 생성 이미지, 누끼 모델 가중치를 유지한다.
- **장애 복구 흐름**:
  1. 서비스 크래시 또는 컨테이너 재시작 시 기동 단계에서 `recover_interrupted()`가 호출된다.
  2. 만료된 임대(lease)를 가진 작업(`QUEUED`, `ANALYZING`, `COMPOSING` 등)을 감지하여 상태를 `QUEUED`로 안전하게 리셋하고 재실행한다.
  3. 백그라운드 태스크 `SQLiteDeliveryOutbox` 루프가 미전송(`PENDING`, `RETRYING`) 상태인 outbox 이벤트를 상품 BE로 자동 재전송한다.

---

## 9. 환경변수 정본 표 ([config.py](../../src/detail_page_ai/config.py) 및 [.env.example](../../.env.example) 1:1 대조)

### (1) 애플리케이션 환경변수 (`src/detail_page_ai/config.py` `Settings` 1:1 대조)

아래 표는 현재 코드베이스의 `Settings` 정의 및 `.env.example`과 일치하는 애플리케이션 환경변수 정본이다.

| 환경변수명 (Alias) | 타입 및 허용값 | 기본값 | 배포 설정 권장값 | 비고 |
|---|---|---|---|---|
| `ANALYSIS_PROVIDER` | `local` | `local` | `local` | 외부 클라우드 API 호출 차단 |
| `LOCAL_TEXT_PROVIDER` | `mlx`, `ollama`, `sglang` | `mlx` | `sglang` | SGLang 추론 클라이언트 활성화 (로컬 개발 시 `mlx`) |
| `LOCAL_TEXT_URL` | 문자열 (URL) | `http://127.0.0.1:11234` | `http://sglang-text:30000` | Compose 서비스 `sglang-text` 포트 30000 |
| `LOCAL_TEXT_MODEL` | 문자열 | `ddalcu/Qwen3.8-27B-MLX-Serve-4bit` | `qwen-text` | SGLang `--served-model-name`과 1:1 일치 필수 |
| `LOCAL_TEXT_TIMEOUT` | float (초) | `300.0` | `300.0` | 복잡 이미지 및 텍스트 분석 타임아웃 |
| `LOCAL_IMAGE_PROVIDER` | `none`, `mlx`, `sglang` | `mlx` | `sglang` | SGLang 확산 클라이언트 활성화 (비활성화 시 `none`) |
| `LOCAL_IMAGE_URL` | 문자열 (URL) | `http://127.0.0.1:11234` | `http://sglang-image:30001` | Compose 서비스 `sglang-image` 포트 30001 |
| `LOCAL_IMAGE_MODEL` | 문자열 | `mlx-community/flux2-klein-9b-4bit` | `flux-klein` | SGLang `--served-model-name`과 1:1 일치 필수 |
| `LOCAL_IMAGE_TIMEOUT` | float (초) | `300.0` | `300.0` | 확산 이미지 생성 타임아웃 |
| `PRODUCT_PHOTO_GENERATION` | `source` | `source` | `source` | 원본 제품 픽셀 보존 원칙 (`source` 고정) |
| `BACKGROUND_PROVIDER` | `none`, `mlx`, `sglang` | `mlx` | `sglang` | 배경판 생성 제공자 |
| `PRODUCT_PHOTO_SHOTS` | 콤마 구분 문자열 | `hero,packshot,detail,lifestyle` | `hero,packshot,detail,lifestyle` | 생성 대상 사진 역할 목록 |
| `SOURCE_PHOTO_VARIATION_THRESHOLD` | int (1~12) | `4` | `4` | 원본 사진 추가 컷 파생 임계값 |
| `DETAIL_PAGE_RENDERER` | `html` | `html` | `html` | Playwright HTML 렌더러 (`html` 고정) |
| `BACKEND_PRODUCT_URL` | 문자열 (URL) 또는 None | `None` | **반드시 설정** | 상품 BE 내부 수신 URL (예: `http://product-backend:8080/...`) |
| `BACKEND_AUTH_TOKEN` | 문자열 또는 None | `None` | **반드시 설정** | 상품 BE 호출용 Bearer 토큰 (Secret 관리) |
| `BACKEND_TIMEOUT_SECONDS` | float (초) | `60.0` | `60.0` | 상품 BE 호출 타임아웃 |
| `AI_INTERNAL_AUTH_TOKEN` | 문자열 또는 None | `None` | **반드시 설정** | BE가 AI 호출 시 검증하는 `X-AI-Internal-Token` |
| `DETAIL_PAGE_TEMPLATE_PATH` | 문자열 또는 None | `None` | `None` | 커스텀 템플릿 경로 (미지정 시 내장 템플릿 사용) |
| `MAX_IMAGE_BYTES` | int (바이트) | `10485760` (10MB) | `10485760` | 단일 입력 이미지 최대 크기 |
| `REQUIRE_DECODABLE_IMAGES` | bool | `True` | `True` | 이미지 디코딩 무결성 검증 강제 여부 |
| `MAX_SOURCE_IMAGES` | int (1~50) | `12` | `12` | 요청당 최대 소스 이미지 수 |
| `MAX_REQUEST_BYTES` | int (바이트) | `125829120` (120MB) | `125829120` | 전체 요청 본문 최대 크기 |
| `MAX_PENDING_GENERATIONS` | int | `100` | `100` | 최대 대기 생성 작업 수 |
| `MAX_DELIVERY_ATTEMPTS` | int (1~100) | `8` | `8` | Outbox 배달 최대 재시도 횟수 |
| `ENABLE_LEGACY_DEMO_API` | bool | `False` | `False` | 운영 환경 레거시 데모 API 비활성화 권장 |
| `AI_CORS_ORIGINS` | 콤마 구분 문자열 | `http://127.0.0.1:4173,...` | **반드시 설정** | 운영/스테이징 판매자 센터 웹 도메인 |
| `PROMPT_VERSION` | 문자열 | `local-mlx-qwen-flux-v1` | `local-sglang-qwen-flux-v1` | 프롬프트 템플릿 버전 식별자 |
| `ASSET_STORE_DIR` | 문자열 (디렉터리) | `.local/detail-page-ai/assets` | `/var/lib/detail-page-ai/assets` | 볼륨 영속화 디렉터리 경로 |
| `SQLITE_PATH` | 문자열 (파일 경로) | `.local/detail-page-ai/state.sqlite3` | `/var/lib/detail-page-ai/state.sqlite3` | 볼륨 영속화 SQLite DB 경로 |
| `RESPONSE_ASSET_MODE` | `base64`, `url`, `both` | `base64` | `base64` | 결과 상세페이지 에셋 반환 방식 |
| `CRAFT_CONFIDENCE_THRESHOLD` | float (0.0~1.0) | `0.65` | `0.65` | 공예 리서치 수행 신뢰도 임계치 |

### (2) SGLang 추론 인프라 및 Docker Compose 환경변수 ([.env.example](../../.env.example) 대조)

| 환경변수명 | 기본 설정값 | 설명 |
|---|---|---|
| `SGLANG_IMAGE` | `lmsysorg/sglang:v0.5.19` | SGLang 공식 베이스 Docker 이미지 태그 |
| `SGLANG_VERSION` | `0.5.19` | SGLang 버전 (확산 빌드 시 사용) |
| `TEXT_MODEL_PATH` | `cyankiwi/Qwen3.8-27B-AWQ-INT4` | 텍스트/비전 추론 모델 가중치 저장소 (Hugging Face) |
| `TEXT_MODEL_REVISION` | `6e134bae811fb5adac50ee042ae5f029ac6779aa` | 텍스트 모델 가중치 버전 커밋 고정값 |
| `TEXT_SERVED_MODEL_NAME` | `qwen-text` | 텍스트 추론 서버 공개 모델명 (`--served-model-name`) |
| `TEXT_MEM_FRACTION` | `0.50` | 텍스트 서버 정적 VRAM 선점 비율 (48GB 중 약 24GB 할당) |
| `TEXT_CONTEXT_LENGTH` | `8192` | 텍스트 모델 최대 컨텍스트 길이 (KV 캐시 상한) |
| `IMAGE_MODEL_PATH` | `circulus/FLUX.2-klein-9B-bnb-4bit` | 이미지 확산 추론 모델 가중치 저장소 (Hugging Face) |
| `IMAGE_MODEL_REVISION` | `58c2804f31af12c8888504b96250010c50b55e44` | 이미지 모델 가중치 버전 커밋 고정값 |
| `IMAGE_SERVED_MODEL_NAME` | `flux-klein` | 이미지 추론 서버 공개 모델명 (`--served-model-name`) |
| `HF_TOKEN` | (선택적 공백) | Hugging Face 토큰 (비공개/게이트 모델 다운로드 시 필요) |
| `U2NET_HOME` | `/var/lib/detail-page-ai/models/u2net` | rembg 누끼 모델 (`birefnet-general.onnx`) 캐시 볼륨 경로 |

---

## 10. 네트워크 및 보안 그룹

| 트래픽 방향 | 포트 | 출발지/목적지 | 프로토콜 | 용도 |
|---|---|---|---|---|
| **Inbound** | **8000** | ALB / API Gateway / 웹 프런트엔드 | HTTP | `detail-page-ai` API (판매자 웹 FE 및 상품 BE 요청 수신) |
| **Internal** | **30000** | `127.0.0.1` (Host) 또는 Compose 네트워크 (`sglang-text`) | HTTP | `detail-page-ai` → `sglang-text` 텍스트·비전 분석 호출 (외부 노출 불필요) |
| **Internal** | **30001** | `127.0.0.1` (Host) 또는 Compose 네트워크 (`sglang-image`) | HTTP | `detail-page-ai` → `sglang-image` 확산 생성·편집 호출 (외부 노출 불필요) |
| **Outbound** | **443** | 상품 BE 서비스 엔드포인트 | HTTPS | 승인 완료 산출물 outbox 배달 |
| **Outbound** | **443** | Hugging Face 허브 (`huggingface.co`) | HTTPS | 초기 기동 시 모델 가중치 1회 다운로드 |

---

## 11. 단계별 검증 절차 및 릴리스 품질 게이트

배포 검증은 **(A) 점진적 인프라 도달 검증**, **(B) 자동화된 릴리스 품질 게이트 3종 실행**, **(C) 첫 GPU 배포 실측 체크리스트**의 3단계로 수행된다.

### (A) 점진적 인프라 도달 검증 (0단계 ~ 6단계)

- **0단계 (애플리케이션 컨테이너 기본 기동)**:
  ```bash
  curl -sS http://<host>:8000/health
  # HTTP 200 ({"status":"ok"}) 수신 시 FastAPI 프로세스 정상 기동 및 포트 개방 확인 (readiness: /health/ready)
  ```
- **1단계 (SGLang 추론 서버 도달)**:
  ```bash
  # 텍스트·비전 추론 서버 확인 (qwen-text 반환)
  curl -sS http://127.0.0.1:30000/v1/models | jq '.data[0].id'
  
  # 이미지 확산 추론 서버 확인 (flux-klein 반환)
  curl -sS http://127.0.0.1:30001/v1/models | jq '.data[0].id'
  ```
- **2단계 (텍스트 분석 및 Draft 생성)**:
  ```bash
  curl -sS -X POST http://<host>:8000/api/v1/ai/detail-page-jobs \
    -H "Authorization: Bearer <AI_INTERNAL_AUTH_TOKEN>" \
    -F "image=@sample.jpg" -F "product_name=백자 달항아리"
  # status: DRAFT_READY 전이 확인
  ```
- **3단계 (이미지 생성 및 컷아웃 합성)**:
  - `photos/` 내에 `hero.png`, `packshot.png`, `lifestyle.png` 등이 생성되었는지 확인.
- **4단계 (PNG 렌더링)**:
  ```bash
  curl -sS -X POST http://<host>:8000/api/v1/ai/detail-page-jobs/<job_id>/approve \
    -H "Authorization: Bearer <AI_INTERNAL_AUTH_TOKEN>"
  # status: COMPLETED 및 detail_page.png 생성 확인
  ```
- **5단계 (상품 BE outbox 전달)**:
  - 상품 BE 로그 및 DB에서 `AiBeProductPersistRequest` 수신 확인.
- **6단계 (장애 복구 검증)**:
  - `docker compose restart detail-page-ai` 실행 후, 재기동된 서비스가 볼륨 내 `state.sqlite3`를 인식하고 미완료 작업을 정상 재개하는지 확인.

### (B) 자동화 릴리스 품질 게이트 3종 실행

실제 운영 배포 전 스테이징 환경에서 파일럿 평가를 수행하고 아래 3개 게이트를 순차 실행한다:

```bash
# 파일럿 또는 샘플 실행 (예: 6건 또는 60건 전체)
python scripts/run_eval_pilot.py --all --output-dir generated/evaluation/aws-staging-run

# 1. 컷아웃 보존율 회귀 게이트
python scripts/check_cutout_fidelity.py --pilot-dir generated/evaluation/aws-staging-run

# 2. 레이아웃 계획 다양성 게이트
python scripts/check_plan_diversity.py --pilot-dir generated/evaluation/aws-staging-run

# 3. 씬 방향 커버리지 진단 게이트
python scripts/check_scene_direction_coverage.py --pilot-dir generated/evaluation/aws-staging-run
```

- 모든 게이트 스크립트가 `exit code 0` ([PASS])을 반환해야 프로덕션 배포가 승인된다.
- **참고**: 사진 정책 변경(참고용 워터마크 영구 제거, `product_generated` 메타데이터 구분)에 따라 과거의 `scripts/check_reference_label.py`는 삭제되었으며 품질 게이트 목록에서 제외되었다.

### (C) 첫 GPU 배포 실측 체크리스트 (검증 상태 과장 금지)

> [!IMPORTANT]
> **GPU 미실행 사실 명시**:  
> 현재 코드베이스는 로컬 CPU/macOS 환경에서 358개 테스트를 통과하고 컨테이너 빌드를 마쳤으나, **실제 GPU 환경에서는 한 번도 실행된 적이 없다.**  
> 첫 GPU 배포 시 아래 항목들을 반드시 실측하여 기록해야 한다:
> - [ ] **두 모델 동시 상주 적재**: L40S 48GB에서 `sglang-text`와 `sglang-image` 동시 기동 시 OOM 없이 정상 기동되는지 확인
> - [ ] **4-bit 파이프라인 로딩 시간**: bitsandbytes 4-bit 양자화된 FLUX.2 Klein 9B 파이프라인 로딩 성공 여부 및 소요 시간
> - [ ] **VRAM 점유율 실측**: 정적 선점 후 여유 버퍼가 예상대로 약 12 GiB 수준으로 유지되는지 `nvidia-smi` 실측
> - [ ] **텍스트·비전 분석 처리 시간**: Qwen3.8-27B-AWQ-INT4의 이미지 분석 및 JSON 출력 레이턴시 측정
> - [ ] **이미지 생성·편집 처리 시간**: FLUX.2 Klein 9B bnb-4bit의 생성(JSON) 및 편집(multipart) 품질과 1건당 소요 시간
> - [ ] **End-to-End 전체 소요 시간**: 1건당 처리 시간이 로컬 기준선(평균 226초) 대비 어느 수준인지 실측 확정

---

## 12. 아직 결정되지 않은 것 (미결정 목록 및 승인 주체)

개발팀 단독으로 결정할 수 없으며 유관 조직과 합의가 필요한 항목들이다:

| 항목 | 결정 필요 내용 | 결정/승인 주체 | 현 상태 및 리스크 |
|---|---|---|---|
| **GPU 인스턴스 승인** | EC2 `g6e.xlarge` (L40S 48GB; 온디맨드 기준 시간당 약 $1.8 [미검증 참고값 — 리전·계약·시점별 상이, 인프라팀 확인 필요]) 예산 및 온디맨드 쿼터 할당 | **인프라 / FinOps 팀** | 결정 필요 (미승인 시 T4/A10G로 강제되어 OOM 발생; 실제 단가 검증이 승인 조건에 포함됨) |
| **EKS 전환 여부 및 매니페스트 구축** | 현재 확정된 Docker Compose 운영 대비 EKS 전환 필요성 검토 및 K8s 매니페스트/GPU 분할 아키텍처 수립 | **인프라 / DevOps 팀** | 미결정 상태 (현재 EKS 전용 매니페스트 전무) |
| **FLUX 모델 상업 라이선스 확인** | 원본 FLUX.2-klein-9B의 Non-Commercial 라이선스 조건과 채택된 커뮤니티 4bit 양자화본의 상업 서비스 허용 범위 확인 | **관리자 / 법무팀** | 확인 필요 (필요 시 Apache 2.0 라이선스의 FLUX.2-klein-4B 대안 전환 검토) |
| **상품 BE 엔드포인트** | 운영/스테이징 `BACKEND_PRODUCT_URL` 주소 및 인증 시크릿 발급 | **상품 백엔드(BE) 팀** | 미확정 시 outbox 배달 불가 |
| **프런트엔드 오리진** | `AI_CORS_ORIGINS`에 등록할 정식 웹 서비스 도메인 목록 | **프런트엔드(FE) 팀** | 미확정 시 브라우저 CORS 차단 |
| **다중 호스트/파드 확장 시점** | 1단계(단일 호스트 Docker Compose / 단일 파드) 운영 후 RDS(PostgreSQL) + S3 이관 시점 | **프로젝트 PM / 아키텍트** | 트래픽 목표치에 따라 로드맵 수립 필요 |

---

## 13. 알려진 제약 및 참고 문서

- **체크포인트 부재**: 현재 파이프라인은 작업 중간 체크포인트가 없어 서비스 크래시 시 해당 job은 처음(`QUEUED`)부터 다시 실행된다 (건당 약 3~4분 소모).
- **이미지 생성 해상도**: 현재 1024×1024 정사각형 고정으로 생성된 후 Pillow로 크롭하여 상세페이지 폭(774px)에 합성된다.
- **참고 문서 목록**:
  - Ubuntu 배포 가이드: [Ubuntu 서버 배포 가이드 (SGLang 3서비스 구성)](ubuntu-deployment.md)
  - 이관 실무 체크리스트: [AWS 이관 준비물 체크리스트](aws-migration-checklist.md)
  - 서빙 스택 검토: [SGLang 서빙 조사 보고서](sglang-serving-research.md) 및 [로컬 MLX Serve 서빙 운영 검토](sglang-vllm-fit.md)
  - 메모리 산정 보고서: [로컬 모델 서버 메모리 예상치](server-memory-estimate.md)
  - 로컬 런타임 가이드: [로컬 LLM 상세페이지 경로](local-llm.md)
