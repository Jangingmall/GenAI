# AWS 이관 준비물 및 단계별 체크리스트

작성일: 2026-09-10 · 최종 개정: 2026-09-16 (SGLang 3서비스 구성 확정 및 EKS 현황 정합성 반영)  
대상: 상세페이지 생성 AI 서비스 (`detail-page-ai` 및 SGLang 추론 서버)  
상위 문서: [AWS 이관·검증 가이드](aws-deployment.md)

이 문서는 로컬 Apple Silicon(MLX) 환경에서 검증된 상세페이지 AI 서비스를 AWS 환경으로 이관하기 위해 운영 담당자가 순서대로 밟을 수 있는 실무 체크리스트다. 각 항목은 **(1) 무엇을 준비하는가**, **(2) 없으면 무엇이 막히는가**, **(3) 확인 방법**의 세 가지 필수 요건을 갖추고 있다.

> [!IMPORTANT]
> **확정 운영 경로 및 EKS 현황 명시**:
> - **확정 운영 경로**: 단일 AWS EC2 `g6e.xlarge` (NVIDIA L40S 48GB 1장, Ubuntu) + `docker compose` 기반 3서비스(`detail-page-ai`, `sglang-text`, `sglang-image`) 공존 구성이다.
> - **EKS 현황 (미결정 상태)**: 현재 저장소에는 EKS 전용 산출물(Deployment/Service/PVC 매니페스트, Helm 차트 등)이 전무하며, EKS 배포 경로는 미결정 상태이다. 본 체크리스트의 EKS 관련 항목은 "EKS로 갈 경우의 설계안"에 해당한다.
> - **검증 상태 (과장 금지)**: 로컬 단위 테스트 358개 통과, `docker compose -f deploy/docker-compose.yml config` 유효성, 컨테이너 빌드 확인 등은 완료되었으나, **GPU 에서는 한 번도 실행되지 않았다.** 두 모델 동시 적재, 4-bit 파이프라인 로딩, 편집 품질, 처리 시간 모두 미검증 상태이며 첫 배포 실측이 필수적이다.

---

## 단계 요약 및 종속성

```text
[Phase 1: 클라우드 인프라 & 호스트 환경 준비]
       │
       ▼
[Phase 2: SGLang 추론 서버 스택 & 모델 가중치]
       │
       ▼
[Phase 3: 컨테이너 이미지 빌드 & 정적 자산 패키징]
       │
       ▼
[Phase 4: 호스트 런타임, 스토리지 & 환경변수 주입]
       │  (EKS 전환 시: K8s 매니페스트 & PVC 매핑)
       ▼
[Phase 5: 점진적 E2E 기동 및 네트워크 검증]
       │
       ▼
[Phase 6: 릴리스 품질 게이트 3종 실행 & 첫 GPU 실측]
```

---

## Phase 1. 클라우드 인프라 및 IAM 권한 준비

### 1-1. GPU 인스턴스 쿼터 및 인스턴스 확보
- **무엇을 준비하는가**: AWS EC2 `g6e.xlarge` (NVIDIA L40S 48GB VRAM) 인스턴스 1대. (EKS 전환 시 GPU 관리형 노드 그룹 또는 Karpenter NodePool 필요).
- **없으면 무엇이 막히는가**: 텍스트 27B AWQ(약 22.4GB 선점)와 FLUX.2 Klein 9B 4-bit(약 10.2GB)를 단일 GPU에 상주시키지 못해 OOM이 발생하거나 배포 자체가 불가능함 (g4dn T4 16GB, g5 A10G 24GB는 VRAM 부족으로 불가).
- **확인 방법**:
  ```bash
  aws service-quotas get-service-quota \
    --service-code ec2 \
    --quota-code L-DB2E81BA \
    --query "ServiceQuota.Value" # G and VT on-demand vCPU quota 확인 (최소 4 vCPU 필요)
  ```

### 1-2. 모델 가중치 보관 및 다운로드 캐시
- **무엇을 준비하는가**:
  - **단일 EC2 Compose 경로**: 이름 있는 도커 볼륨 `huggingface-cache` (`/root/.cache/huggingface`)를 사용해 Hugging Face에서 모델을 1회 다운로드하고 캐싱합니다. 이 경로는 기존처럼 저장소 ID와 고정 `--revision`을 사용합니다.
  - **EKS 경로**: 인프라팀이 S3 버킷 `jangin-{env}-s3-models`에서 PVC로 모델을 사전 동기화하고, VPC 내 S3 Gateway Endpoint를 사용합니다. 애플리케이션 컨테이너에는 AWS CLI·boto3·IAM 권한을 넣지 않습니다. `TEXT_MODEL_PATH`와 `IMAGE_MODEL_PATH`에 PVC의 펼쳐진 모델 디렉터리 절대 경로를 주입합니다.
- **없으면 무엇이 막히는가**: EC2 Compose에서 볼륨 캐시가 비어 있으면 HF 다운로드가 다시 발생합니다. EKS에서 S3→PVC 동기화가 끝나지 않아 모델 디렉터리가 생성된 채 `config.json`이 없으면 로컬 모드가 명확한 오류를 남기고 종료합니다. 모델 디렉터리 자체가 없으면 HF 모드로 fallback하지만, EKS에서는 네트워크 다운로드를 전제로 하지 않으므로 initContainer 또는 선행 Job으로 동기화를 완료해야 합니다. 두 경로 모두 첫 GPU 실측 전까지 정확한 기동 시간은 확정하지 않습니다.
- **확인 방법**:
  ```bash
  docker volume inspect huggingface-cache
  ```
  EKS에서는 `TEXT_MODEL_PATH`·`IMAGE_MODEL_PATH` 각각에 `config.json`과 `*.safetensors`가 직접 존재하는지, 압축이 풀린 별도 디렉터리인지 확인합니다.

### 1-3. 호스트 GPU 런타임 및 이미지 빌드 환경
- **무엇을 준비하는가**: Ubuntu 22.04/24.04 LTS 호스트, NVIDIA 공식 드라이버 (550 권장), Docker Engine 및 NVIDIA Container Toolkit.
- **없으면 무엇이 막히는가**: 컨테이너 내부에서 GPU 디바이스 인식 불가로 SGLang 추론 서버 기동 실패.
- **확인 방법**:
  ```bash
  docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
  ```

---

## Phase 2. SGLang 추론 서빙 스택 및 모델 가중치 준비

### 2-1. 텍스트·비전 분석 모델 포팅 (`sglang-text`)
- **무엇을 준비하는가**:
  - 모델: `cyankiwi/Qwen3.8-27B-AWQ-INT4` (19.60 GiB), 고정 커밋 `6e134bae811fb5adac50ee042ae5f029ac6779aa`.
  - 이미지: `lmsysorg/sglang:v0.5.19`.
  - **단일 EC2 Compose(HF 모드) 구동**: `python3 -m sglang.launch_server --model-path cyankiwi/Qwen3.8-27B-AWQ-INT4 --revision 6e134bae811fb5adac50ee042ae5f029ac6779aa --served-model-name qwen-text --host 0.0.0.0 --port 30000 --mem-fraction-static 0.50 --context-length 8192 --trust-remote-code`.
  - **EKS(S3→PVC 로컬 모드) 구동**: `TEXT_MODEL_PATH=/var/lib/detail-page-ai/models/text/qwen3.8-27b-awq-int4` 같은 PVC 디렉터리를 `--model-path`로 사용하고 `--revision`은 전달하지 않습니다. `HF_HUB_OFFLINE=1`로 네트워크 접근을 차단하며, 디렉터리 안의 `config.json`과 `*.safetensors`를 먼저 확인합니다.
- **없으면 무엇이 막히는가**: 비전 및 텍스트 멀티모달 분석 서비스 기동 실패 또는 VRAM OOM 발생.
- **확인 방법**:
  ```bash
  curl -sS http://127.0.0.1:30000/v1/models | jq '.data[0].id' # "qwen-text" 확인
  ```

### 2-2. 이미지 모델 서빙 및 클라이언트 규약 (`sglang-image`)
- **무엇을 준비하는가**:
  1. 모델: `circulus/FLUX.2-klein-9B-bnb-4bit` (약 10.2 GiB, 트랜스포머 4.36 + 텍스트 인코더 5.66 + VAE 0.16 GiB), 고정 커밋 `58c2804f31af12c8888504b96250010c50b55e44`.
  2. 커스텀 이미지 빌드: `deploy/docker/sglang-diffusion.Dockerfile` (`lmsysorg/sglang:v0.5.19` 베이스에 `sglang[diffusion]==0.5.19` 및 `bitsandbytes==0.50.2` 설치).
  3. **단일 EC2 Compose(HF 모드) 구동**: `sglang serve --model-path circulus/FLUX.2-klein-9B-bnb-4bit --revision 58c2804f31af12c8888504b96250010c50b55e44 --served-model-name flux-klein --host 0.0.0.0 --port 30001 --num-gpus 1 --dit-cpu-offload false --text-encoder-cpu-offload false`.
  4. **EKS(S3→PVC 로컬 모드) 구동**: `IMAGE_MODEL_PATH=/var/lib/detail-page-ai/models/image/flux2-klein-9b-bnb-4bit` 같은 PVC 디렉터리를 `--model-path`로 사용하고 `--revision`은 전달하지 않습니다. `HF_HUB_OFFLINE=1`로 실행하며, `config.json`이 없으면 명확한 오류 후 기동을 중단합니다. 텍스트 서버와 이미지 서버는 이 판정을 각각 독립적으로 수행합니다.
  5. 클라이언트 규약 호환: `src/local_detail_page_ai/clients.py`의 `sglang` provider가 JSON `POST /v1/images/generations` 및 multipart `POST /v1/images/edits`를 직접 호출하므로 별도 프록시 불필요 (해소됨).
- **없으면 무엇이 막히는가**: 확산 생성 및 in-context 편집 실패로 상품 연출 컷 및 배경 생성 전건 실패.
- **라이선스 사실 기록**: 원본 `black-forest-labs/FLUX.2-klein-9B`는 FLUX Non-Commercial License이다. 채택된 `circulus/FLUX.2-klein-9B-bnb-4bit`는 커뮤니티 양자화본이며 관리자 결정으로 채택되었다. 상업 운영 전 BFL 라이선스 범위 확인이 필요하다(사실만 기록). 대안은 Apache 2.0 라이선스의 `black-forest-labs/FLUX.2-klein-4B`이다.
- **확인 방법**:
  ```bash
  curl -sS http://127.0.0.1:30001/v1/models | jq '.data[0].id' # "flux-klein" 확인
  ```

---

## Phase 3. 컨테이너 이미지 빌드 및 정적 자산 패키징

### 3-1. 레이아웃 원형 카탈로그(`detail-page-layouts.json`) 복사 확인 — [해소됨]
- **무엇을 준비하는가**: `deploy/Dockerfile` 빌드 시 `assets/references/detail-page-layouts.json`이 컨테이너 이미지 내부 `/app/assets/references/detail-page-layouts.json`에 정상 복사되도록 레이어가 반영되어 있음.
  ```dockerfile
  COPY assets/references/detail-page-layouts.json ./assets/references/detail-page-layouts.json
  ```
- **없으면 무엇이 막히는가**: `src/detail_page_ai/layout_archetypes.py`가 카탈로그 파일을 찾지 못해 `LAYOUT_ARCHETYPES`가 빈 리스트(`[]`)로 초기화되고, 레이아웃 원형 주입이 비활성화되어 블록 다양성 게이트(`check_plan_diversity.py`) 판정이 고정형으로 퇴행함.
- **확인 방법**:
  ```bash
  docker run --rm detail-page-ai:latest python -c "
  from detail_page_ai.layout_archetypes import LAYOUT_ARCHETYPES
  assert len(LAYOUT_ARCHETYPES) >= 20, f'Catalog empty! Count: {len(LAYOUT_ARCHETYPES)}'
  print('Layout archetypes loaded:', len(LAYOUT_ARCHETYPES))
  "
  ```

### 3-2. Playwright Chromium 런타임 의존성 패키징
- **무엇을 준비하는가**: `deploy/Dockerfile`에 정의된 대로 `python:3.13-slim` 베이스 위에 Node.js 및 Chromium 브라우저 바이너리가 정상 설치되어야 함.
- **없으면 무엇이 막히는가**: 사용자 승인 후 4단계 최종 상세페이지 PNG 렌더(`render_detail_page.mjs`) 단계에서 Chromium 프로세스 기동 실패로 500 에러 발생.
- **확인 방법**:
  ```bash
  docker run --rm detail-page-ai:latest node scripts/runtime/render_detail_page.mjs --help
  ```

### 3-3. SGLang 확산 서버 커스텀 이미지 빌드
- **무엇을 준비하는가**: `deploy/docker/sglang-diffusion.Dockerfile`을 빌드하여 `local/sglang-diffusion:0.5.19` 이미지를 생성.
  ```bash
  docker build -f deploy/docker/sglang-diffusion.Dockerfile -t local/sglang-diffusion:0.5.19 .
  ```
- **없으면 무엇이 막히는가**: 공식 `lmsysorg/sglang:v0.5.19` 이미지에는 diffusion 패키지와 bitsandbytes가 기본 포함되어 있지 않아 `sglang-image` 컨테이너 기동 실패.
- **확인 방법**:
  ```bash
  docker run --rm local/sglang-diffusion:0.5.19 python3 -c "import sglang, bitsandbytes; print('SGLang diffusion ready')"
  ```

---

## Phase 4. 호스트 런타임, 스토리지 및 환경변수 주입

### 4-1. 영속성 볼륨 (Docker 볼륨 `detail-page-ai-data` / EKS 전환 시 gp3 EBS PVC)
- **무엇을 준비하는가**: Docker 이름 있는 볼륨 `detail-page-ai-data` 마운트 (`/var/lib/detail-page-ai`). (EKS 설계 시 `gp3` 스토리지 클래스 기반 **100Gi 권장** ReadWriteOnce EBS PVC; 모델 가중치만 약 30GB(텍스트 19.6 GiB + 이미지 10.2 GiB)이며 작업 산출물·런타임 캐시를 고려해 100Gi 권장).
- **없으면 무엇이 막히는가**: 컨테이너/파드 재시작 또는 장애 시 SQLite 작업 DB(`state.sqlite3`), 생성 이미지 에셋(`assets/`), rembg 누끼 모델 가중치(`models/u2net`)가 유실되어 미완료 작업 복구 및 outbox 재전송이 실패함.
- **확인 방법**:
  ```bash
  docker volume inspect detail-page-ai-data
  ```

### 4-2. 환경변수 정본 매핑 (`.env` 파일 / EKS 전환 시 ConfigMap & Secret)
- **무엇을 준비하는가**: `src/detail_page_ai/config.py`의 `Settings` 및 `.env.example` 정본에 부합하는 환경변수 등록.
  - SGLang 연동: `LOCAL_TEXT_PROVIDER=sglang`, `LOCAL_IMAGE_PROVIDER=sglang`, `BACKGROUND_PROVIDER=sglang`, `LOCAL_TEXT_URL=http://sglang-text:30000`, `LOCAL_IMAGE_URL=http://sglang-image:30001`, `LOCAL_TEXT_MODEL=qwen-text`, `LOCAL_IMAGE_MODEL=flux-klein`.
  - **단일 EC2 Compose(HF 모드)** 모델 버전 고정: `TEXT_MODEL_REVISION=6e134bae811fb5adac50ee042ae5f029ac6779aa`, `IMAGE_MODEL_REVISION=58c2804f31af12c8888504b96250010c50b55e44`.
  - **EKS(S3→PVC 로컬 모드)** 모델 경로: `TEXT_MODEL_PATH=/var/lib/detail-page-ai/models/text/qwen3.8-27b-awq-int4`, `IMAGE_MODEL_PATH=/var/lib/detail-page-ai/models/image/flux2-klein-9b-bnb-4bit`. 이 모드에서는 `--revision`을 적용하지 않으며, 어떤 커밋의 가중치를 올렸는지는 S3 동기화 산출물과 위 고정 SHA를 기준으로 인프라팀이 관리합니다.
  - 인증/보안: `AI_INTERNAL_AUTH_TOKEN`, `BACKEND_URL`, `BACKEND_AUTH_TOKEN`, `AI_CORS_ORIGINS`.
- **없으면 무엇이 막히는가**:
  - `AI_INTERNAL_AUTH_TOKEN` 누락 시: 모든 `/internal/v1/ai/*` 호출이 401 Unauthorized로 차단.
  - `BACKEND_URL` / `BACKEND_AUTH_TOKEN` 누락 시: 승인 후 BE로의 outbox 배달이 중단됨.
  - `AI_CORS_ORIGINS` 미설정 시: 판매자 센터 웹 브라우저에서 CORS 차단 발생.
- **확인 방법**:
  ```bash
  # .env 주요 변수 설정 상태 확인
  grep -E "LOCAL_TEXT_PROVIDER|LOCAL_IMAGE_PROVIDER|TEXT_MODEL_REVISION|IMAGE_MODEL_REVISION" .env
  ```

---

## Phase 5. 점진적 E2E 기동 및 네트워크 검증 (0단계 ~ 6단계)

운영 배포 시 단계를 건너뛰지 않고 아래 순서로 검증을 통과해야 한다.

| 단계 | 검증 대상 | 확인 명령 | 성공 기준 | 실패 시 원인 분리 |
|---|---|---|---|---|
| **0단계** | 애플리케이션 컨테이너 기본 기동 | `curl -sS http://<host>:8000/health` | HTTP 200 수신 (`{"status":"ok"}`) | 포트 포워딩, 방화벽 또는 프로세스 크래시 |
| **1단계** | SGLang 추론 서버 엔드포인트 도달 | `curl -sS http://127.0.0.1:30000/v1/models`<br>`curl -sS http://127.0.0.1:30001/v1/models` | `qwen-text`, `flux-klein` 모델 ID JSON 수신 | 추론 컨테이너 미기동 또는 GPU 할당 오류 |
| **2단계** | 텍스트 분석 및 Draft 생성 | 상품 이미지 1장 업로드 후 `GET .../jobs/<job_id>` 폴링 | status가 `DRAFT_READY`로 전이 | `sglang-text` 응답 타임아웃 또는 JSON 파싱 오류 |
| **3단계** | 이미지 생성 및 합성 | 2단계 완료 후 `photos/` 내 파일 생성 확인 | `hero`, `packshot`, `lifestyle`, `detail` 생성 | 확산 모델 VRAM OOM 또는 호출 규약 오류 |
| **4단계** | 최종 상세페이지 PNG 렌더 | 승인 API (`POST .../approve`) 호출 | status가 `COMPLETED` 및 `detail_page.png` 생성 | Node.js / Playwright Chromium 라이브러리 누락 |
| **5단계** | BE outbox 전달 | BE API 및 DB 조회 | BE에 `AiBeProductPersistRequest` 수신 확인 | `BACKEND_URL` 오설정 또는 인증 토큰 오류 |
| **6단계** | 장애 복구 검증 | `docker compose -f deploy/docker-compose.yml restart detail-page-ai` | 재기동 후 `state.sqlite3` 유지 및 미완료 작업 복구 | 도커 볼륨 미마운트 (임시 컨테이너 파일시스템 사용) |

---

## Phase 6. 배포 전 릴리스 품질 게이트 3종 실행 및 첫 GPU 실측

운영 배포 직전, 스테이징 환경에서 파일럿 6건(또는 샘플 10건)을 실행하고 아래 3개 게이트 검증 스크립트를 모두 통과(`exit code 0`)해야 최종 릴리스가 승인된다.

### 6-1. 컷아웃 보존율 회귀 게이트
- **실행 명령**:
  ```bash
  python scripts/check_cutout_fidelity.py --pilot-dir generated/evaluation/<pilot-dir>
  ```
- **합격 기준**: 6개 카테고리 전건 보존율 80% 이상 및 `심각 손실 [FAIL]` 0건.

### 6-2. 레이아웃 계획 다양성 게이트
- **실행 명령**:
  ```bash
  python scripts/check_plan_diversity.py --pilot-dir generated/evaluation/<pilot-dir>
  ```
- **합격 기준**: 카테고리 간 블록 구성 다양성 확보 (고정된 단일 시퀀스 반복 퇴행 없음).

### 6-3. 씬 분기 방향 커버리지 게이트
- **실행 명령**:
  ```bash
  python scripts/check_scene_direction_coverage.py --pilot-dir generated/evaluation/<pilot-dir>
  ```
- **합격 기준**: 공예/비공예 및 제품 특성에 맞는 씬 디렉션이 올바르게 매핑되어 `MISSING` 0건.

> [!NOTE]
> **품질 게이트 목록 변경 안내**:  
> 사진 정책 개편(참고용 워터마크 영구 제거, `product_generated` 메타데이터 구분)에 따라 과거의 `scripts/check_reference_label.py`는 삭제되었으며 품질 게이트 대상에서 영구 제외되었다.

### 6-4. 첫 GPU 배포 실측 체크리스트 (검증 상태 과장 금지)

> [!IMPORTANT]
> **GPU 미실행 사실 명시**:  
> 본 프로젝트는 단위 테스트 358개 통과 및 CPU 컨테이너 정상 동작을 확인했으나, **GPU 에서는 한 번도 실행되지 않았다.**  
> 첫 배포 인스턴스에서 아래 6개 항목을 실측하여 배포 보고서에 수치를 기입해야 한다:
> - [ ] **1. SGLang 2프로세스 동시 상주**: `g6e.xlarge` (L40S 48GB)에서 `sglang-text`와 `sglang-image` 동시 기동 시 OOM 없이 정상 기동
> - [ ] **2. 4-bit 파이프라인 로딩 시간**: bitsandbytes 4-bit 양자화된 FLUX.2 Klein 9B 파이프라인의 GPU 메모리 로딩 완료 시간 측정
> - [ ] **3. VRAM 점유량 실측**: 정적 선점 후 여유 버퍼가 예상대로 약 12 GiB 수준으로 유지되는지 `nvidia-smi` 실측
> - [ ] **4. 텍스트·비전 분석 처리 시간**: Qwen3.8-27B-AWQ-INT4의 이미지 분석 및 JSON 출력 지연 시간 측정
> - [ ] **5. 이미지 생성·편집 레이턴시**: FLUX.2 Klein 9B 4-bit의 생성 및 multipart 편집 처리 시간 실측
> - [ ] **6. E2E 1건 전체 처리 시간**: 로컬 베이스라인(건당 약 226초) 대비 AWS GPU 환경에서의 1건 완료 시간 확정

---

## 미결정 항목 및 승인 담당자 매트릭스

아래 항목은 AI 서비스 개발팀 단독으로 결정할 수 없으며, 인프라 이관 전 유관 조직의 승인이 완료되어야 한다.

| 항목 | 결정 필요 내용 | 승인/결정 담당 조직 | 상태 |
|---|---|---|---|
| **GPU 인스턴스 타입** | `g6e.xlarge` (L40S 48GB; 온디맨드 기준 시간당 약 $1.8 [미검증 참고값 — 리전·계약·시점별 상이, 인프라팀 확인 필요]) 도입 및 상주 아키텍처 승인 | 인프라 / FinOps 팀 | 결정 필요 (실제 단가·할인 옵션 검증이 승인 조건에 포함됨) |
| **EKS 전환 여부 및 매니페스트 구축** | 현재 확정된 단일 호스트 Docker Compose 운영 대비 EKS 전환 필요성 검토 및 매니페스트/파드 분할 아키텍처 수립 | 인프라 / DevOps 팀 | 미결정 상태 (현재 EKS 전용 매니페스트 전무) |
| **FLUX 모델 상업 라이선스 확인** | 원본 FLUX.2-klein-9B의 Non-Commercial 라이선스 조건과 커뮤니티 양자화본(`circulus/FLUX.2-klein-9B-bnb-4bit`)의 상업 서비스 허용 범위 확인 | 관리자 / 법무팀 | 확인 필요 (필요 시 Apache 2.0 라이선스의 FLUX.2-klein-4B 대안 전환 검토) |
| **BE 엔드포인트** | 운영/스테이징 `BACKEND_URL` 및 서비스 계정 토큰 | 상품 백엔드(BE) 팀 | 결정 필요 |
| **프런트엔드 도메인** | `AI_CORS_ORIGINS`에 등록할 판매자 센터 정식 도메인 목록 | 프런트엔드(FE) 팀 | 결정 필요 |
| **다중 파드 확장 여부** | 1단계: 단일 호스트(Docker Compose) / 단일 파드 유지 vs 2단계: RDS(PostgreSQL)+S3 전환 | 아키텍처 / 프로젝트 PM | 1단계 확정, 2단계 로드맵 수립 필요 |
