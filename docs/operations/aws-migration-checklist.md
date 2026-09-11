# AWS 이관 준비물 및 단계별 체크리스트

작성일: 2026-09-10  
대상: 상세페이지 생성 AI 서비스 (`ai-service` 및 로컬 추론 서버)  
상위 문서: [AWS 이관·검증 가이드](aws-deployment.md)

이 문서는 로컬 Apple Silicon(MLX) 환경에서 검증된 상세페이지 AI 서비스를 AWS EKS GPU 환경으로 이관하기 위해 운영 담당자가 순서대로 밟을 수 있는 실무 체크리스트다. 각 항목은 **(1) 무엇을 준비하는가**, **(2) 없으면 무엇이 막히는가**, **(3) 확인 방법**의 세 가지 필수 요건을 갖추고 있다.

---

## 단계 요약 및 종속성

```text
[Phase 1: 클라우드 인프라 & 권한]
       │
       ▼
[Phase 2: CUDA 모델 가중치 & 추론 서버 스택]
       │
       ▼
[Phase 3: 컨테이너 이미지 빌드 & 자산 패키징]
       │
       ▼
[Phase 4: K8s 매니페스트, 스토리지 & 환경변수]
       │
       ▼
[Phase 5: 점진적 E2E 기동 및 네트워크 검증]
       │
       ▼
[Phase 6: 릴리스 품질 게이트 4종 및 승인]
```

---

## Phase 1. 클라우드 인프라 및 IAM 권한 준비

### 1-1. GPU 인스턴스 쿼터 및 노드 그룹 확보
- **무엇을 준비하는가**: AWS EC2 `g6e.xlarge` (NVIDIA L40S 48GB VRAM) 인스턴스 1대 및 EKS GPU 관리형 노드 그룹(또는 Karpenter NodePool).
- **없으면 무엇이 막히는가**: 텍스트 27B 4-bit(약 16GB)와 FLUX.2 Klein 9B fp16(약 18GB)를 단일 노드에 상주시키지 못해 OOM이 발생하거나 배포 자체가 불가능함. (g4dn T4 16GB, g5 A10G 24GB는 VRAM 부족으로 불가).
- **확인 방법**:
  ```bash
  aws service-quotas get-service-quota \
    --service-code ec2 \
    --quota-code L-DB2E81BA \
    --query "ServiceQuota.Value" # G and VT on-demand vCPU quota 확인 (최소 4 vCPU 필요)
  kubectl get nodes -l nvidia.com/gpu.present=true -o wide
  ```

### 1-2. S3 버킷 및 Gateway VPC Endpoint
- **무엇을 준비하는가**: 모델 가중치 보관용 S3 버킷(`s3://jangin-{env}-s3-models/`)과 VPC 내 S3 Gateway Endpoint.
- **없으면 무엇이 막히는가**: 컨테이너 기동 시 Hugging Face 직접 다운로드로 인해 NAT Gateway 데이터 처리 비용(GB당 약 $0.059 [미검증 참고값 — 리전·계약·시점별 상이, 인프라팀 확인 필요], 모델당 ~27GB 기준)이 매번 발생하며 기동 시간이 크게 지연됨.
- **확인 방법**:
  ```bash
  aws ec2 describe-vpc-endpoints \
    --filters "Name=service-name,Values=com.amazonaws.$(aws configure get region).s3" \
    --query "VpcEndpoints[0].State" # 'available' 출력 확인
  aws s3 ls s3://jangin-{env}-s3-models/detail-page/
  ```

### 1-3. ECR 레지스트리 및 빌드/푸시 권한
- **무엇을 준비하는가**: `detail-page-ai-service` ECR 프라이빗 리포지토리 및 CI/CD 워크스페이스용 IAM 푸시 권한.
- **없으면 무엇이 막히는가**: 빌드된 애플리케이션 컨테이너 이미지를 EKS 노드에서 pull할 수 없음.
- **확인 방법**:
  ```bash
  aws ecr describe-repositories --repository-names detail-page-ai-service
  ```

---

## Phase 2. CUDA 모델 가중치 및 추론 서빙 스택 준비

### 2-1. 텍스트 분석 모델 포팅 (Qwen3.8-27B AWQ/GPTQ)
- **무엇을 준비하는가**: 현재 MLX 4-bit(`ddalcu/Qwen3.8-27B-MLX-Serve-4bit`) 가중치를 CUDA vLLM에서 구동 가능한 AWQ 또는 GPTQ 4-bit 포맷으로 변환 또는 허브에서 확보하여 S3에 업로드.
- **없으면 무엇이 막히는가**: vLLM이 MLX 전용 4-bit 가중치를 읽지 못해 텍스트 추론 서버 기동 실패 (`ModuleNotFoundError` or weight format mismatch).
- **확인 방법**:
  ```bash
  vllm serve /models/qwen3.8-27b-awq --port 11234 --max-model-len 8192 &
  curl -sS http://127.0.0.1:11234/v1/models | jq '.data[0].id'
  ```

### 2-2. 이미지 모델 포팅 및 규약 호환 어댑터 (FLUX.2 Klein 9B)
- **무엇을 준비하는가**:
  1. `mlx-community/flux2-klein-9b-4bit`를 대체할 safetensors / bitsandbytes 4-bit 가중치.
  2. **핵심 규약 어댑터**: 현재 클라이언트(`src/local_detail_page_ai/clients.py:214-247`)는 편집 요청 시 multipart `/v1/images/edits`가 아니라 **JSON `POST /v1/images/generations` (`mode: "edit"`, `image: "<base64>"`, `steps: 4`, `strength: 0.30`)**를 전송함. Diffusers 또는 ComfyUI 기반 서빙 앞에 이 JSON 규약을 수신해 in-context diffusion 파이프라인으로 전달하는 FastAPI 래퍼 프록시를 준비해야 함.
- **없으면 무엇이 막히는가**: 일반적인 OpenAI 호환 이미지 서버는 `/v1/images/generations`에서 `mode: "edit"`나 `image` base64 필드를 파싱하지 못하고 422 Unprocessable Entity 에러를 반환하여 상세페이지의 활용 장면 및 디테일 컷 생성이 전건 실패함.
- **확인 방법**:
  ```bash
  # In-context edit JSON 규약 호환 확인
  curl -sS -X POST http://127.0.0.1:11234/v1/images/generations \
    -H "Content-Type: application/json" \
    -d '{"model":"flux2","prompt":"test","size":"1024x1024","mode":"edit","steps":4,"strength":0.3,"image":"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="}' \
    | jq '.data[0].b64_json' | head -c 50
  ```

---

## Phase 3. 컨테이너 이미지 빌드 및 정적 자산 패키징

### 3-1. 레이아웃 원형 카탈로그(`detail-page-layouts.json`) 복사 누락 방지
- **무엇을 준비하는가**: `Dockerfile` 빌드 시 `assets/references/detail-page-layouts.json`이 컨테이너 이미지 내부 `/app/assets/references/detail-page-layouts.json`에 복사되도록 Dockerfile 레이어 추가.
  ```dockerfile
  # Dockerfile 필수 추가 라인
  COPY assets/references/detail-page-layouts.json ./assets/references/detail-page-layouts.json
  ```
- **없으면 무엇이 막히는가**: `src/detail_page_ai/layout_archetypes.py:14-16`가 카탈로그 파일을 찾지 못해 `LAYOUT_ARCHETYPES`가 빈 리스트(`[]`)로 초기화됨. 결과적으로 레이아웃 원형 주입이 비활성화되어 60건 평가 시 블록 다양성 게이트(`check_plan_diversity.py`) 판정이 고정형으로 퇴행함.
- **확인 방법**:
  ```bash
  docker run --rm <image-tag> python -c "
  from detail_page_ai.layout_archetypes import LAYOUT_ARCHETYPES
  assert len(LAYOUT_ARCHETYPES) >= 20, f'Catalog empty! Count: {len(LAYOUT_ARCHETYPES)}'
  print('Layout archetypes loaded:', len(LAYOUT_ARCHETYPES))
  "
  ```

### 3-2. Playwright Chromium 런타임 의존성 패키징
- **무엇을 준비하는가**: `Dockerfile`에 정의된 대로 `python:3.13-slim` 베이스 위에 Node.js 및 Chromium 브라우저 바이너리가 정상 설치되어야 함.
- **없으면 무엇이 막히는가**: 사용자 승인 후 4단계 최종 상세페이지 PNG 렌더(`render_detail_page.mjs`) 단계에서 Chromium 프로세스 기동 실패로 500 에러 발생.
- **확인 방법**:
  ```bash
  docker run --rm <image-tag> node scripts/runtime/render_detail_page.mjs --help
  ```

---

## Phase 4. Kubernetes 매니페스트, 스토리지 및 환경변수 주입

### 4-1. 영속성 볼륨 (EBS PVC ReadWriteOnce)
- **무엇을 준비하는가**: `gp3` 스토리지 클래스 기반 EBS PVC (최소 20Gi 이상). 마운트 경로: `/var/lib/detail-page-ai`.
- **없으면 무엇이 막히는가**: 파드 재시작 또는 노드 장애 시 SQLite 데이터베이스(`state.sqlite3`)와 생성 이미지 에셋(`assets/`)이 유실되어 진행 중인 job 복구 및 outbox 재전송이 영구 실패함.
- **확인 방법**:
  ```bash
  kubectl get pvc detail-page-ai-pvc -o jsonpath='{.status.phase}' # 'Bound' 확인
  ```

### 4-2. 환경변수 정본 매핑 (ConfigMap & Secret)
- **무엇을 준비하는가**: `src/detail_page_ai/config.py`의 `Settings` 정본에 부합하는 ConfigMap 및 Secret 등록.
- **없으면 무엇이 막히는가**:
  - `AI_INTERNAL_AUTH_TOKEN` 누락 시: 모든 `/internal/v1/ai/*` 호출이 401 Unauthorized로 차단.
  - `BACKEND_PRODUCT_URL` / `BACKEND_AUTH_TOKEN` 누락 시: 승인 후 상품 BE로의 outbox 배달이 중단됨.
  - `AI_CORS_ORIGINS` 미설정 시: 프런트엔드 브라우저에서 CORS 차단 발생.
- **확인 방법**:
  ```bash
  kubectl get secret detail-page-ai-secrets -o jsonpath='{.data.AI_INTERNAL_AUTH_TOKEN}' | base64 -d
  kubectl get configmap detail-page-ai-config -o yaml
  ```

---

## Phase 5. 점진적 E2E 기동 및 네트워크 검증 (0단계 ~ 6단계)

운영 배포 시 단계를 건너뛰지 않고 아래 순서로 검증을 통과해야 한다.

| 단계 | 검증 대상 | 확인 명령 | 성공 기준 | 실패 시 원인 분리 |
|---|---|---|---|---|
| **0단계** | 컨테이너 프로세스 및 포트 | `curl -sS http://<host>:8000/api/v1/ai/detail-page-jobs/does-not-exist` | HTTP 404 수신 | 포트 포워딩, 보안 그룹 또는 프로세스 크래시 |
| **1단계** | 추론 서버 엔드포인트 도달 | `curl -sS http://127.0.0.1:11234/v1/models` | 모델 ID 목록 JSON 수신 | 추론 컨테이너 미기동 또는 loopback 차단 |
| **2단계** | 텍스트 분석 및 Draft 생성 | 상품 이미지 1장 업로드 후 `GET .../jobs/<job_id>` 폴링 | status가 `DRAFT_READY`로 전이 | vLLM 응답 타임아웃 또는 JSON 파싱 오류 |
| **3단계** | 이미지 생성 및 합성 | 2단계 완료 후 `photos/` 내 파일 생성 확인 | `hero`, `packshot`, `lifestyle`, `detail` 생성 | 이미지 모델 VRAM OOM 또는 edit 호출 규약 불일치 |
| **4단계** | 최종 상세페이지 PNG 렌더 | 승인 API (`POST .../approve`) 호출 | status가 `COMPLETED` 및 `detail_page.png` 생성 | Node.js / Playwright Chromium 라이브러리 누락 |
| **5단계** | 상품 BE outbox 전달 | 상품 BE API 및 DB 조회 | 상품 BE에 `AiBeProductPersistRequest` 수신 확인 | `BACKEND_PRODUCT_URL` 오설정 또는 인증 토큰 오류 |
| **6단계** | 장애 복구 (파드 재기동) | `kubectl delete pod <ai-service-pod>` | 재기동 후 `state.sqlite3` 유지 및 lease 재청구 | EBS PVC 미마운트 (임시 컨테이너 파일시스템 사용) |

---

## Phase 6. 배포 전 릴리스 품질 게이트 4종 실행

운영 배포 직전, 스테이징 환경에서 파일럿 6건(또는 샘플 10건)을 실행하고 아래 4개 게이트 검증 스크립트를 모두 통과(`exit code 0`)해야 최종 릴리스가 승인된다.

### 6-1. 참고용 라벨 도달 검증 게이트
- **실행 명령**:
  ```bash
  python scripts/check_reference_label.py --pilot-dir generated/evaluation/<pilot-dir>
  ```
- **합격 기준**: 생성된 모든 이미지(`product_generated=True`)의 React 문서 및 HTML에 `참고용` 문구가 100% 도달하고, 원본 컷에는 오표기가 전혀 없어야 함 (`all_passed: true`).

### 6-2. 컷아웃 보존율 회귀 게이트
- **실행 명령**:
  ```bash
  python scripts/check_cutout_fidelity.py --pilot-dir generated/evaluation/<pilot-dir>
  ```
- **합격 기준**: 6개 카테고리 전건 보존율 80% 이상 및 `심각 손실 [FAIL]` 0건.

### 6-3. 레이아웃 계획 다양성 게이트
- **실행 명령**:
  ```bash
  python scripts/check_plan_diversity.py --pilot-dir generated/evaluation/<pilot-dir>
  ```
- **합격 기준**: 카테고리 간 블록 구성 다양성 확보 (고정된 단일 시퀀스 반복 퇴행 없음).

### 6-4. 씬 분기 방향 커버리지 게이트
- **실행 명령**:
  ```bash
  python scripts/check_scene_direction_coverage.py --pilot-dir generated/evaluation/<pilot-dir>
  ```
- **합격 기준**: 공예/비공예 및 제품 특성에 맞는 씬 디렉션이 올바르게 매핑되어 `MISSING` 0건.

---

## 미결정 항목 및 승인 담당자 매트릭스

아래 항목은 AI 서비스 개발팀 단독으로 결정할 수 없으며, 인프라 이관 전 유관 조직의 승인이 완료되어야 한다.

| 항목 | 결정 필요 내용 | 승인/결정 담당 조직 | 상태 |
|---|---|---|---|
| **GPU 인스턴스 타입** | `g6e.xlarge` (L40S 48GB; 온디맨드 기준 시간당 약 $1.8 [미검증 참고값 — 리전·계약·시점별 상이, 인프라팀 확인 필요]) 도입 및 상주 아키텍처 승인 | 인프라 / FinOps 팀 | 결정 필요 (실제 단가·할인 옵션 검증이 승인 조건에 포함됨) |
| **S3 모델 저장소** | 모델 가중치 전용 S3 버킷 명칭, 리전 및 접근 IAM Role | 클라우드 보안 / 인프라 팀 | 결정 필요 |
| **상품 BE 엔드포인트** | 운영/스테이징 `BACKEND_PRODUCT_URL` 및 서비스 계정 토큰 | 상품 백엔드(BE) 팀 | 결정 필요 |
| **프런트엔드 도메인** | `AI_CORS_ORIGINS`에 등록할 판매자 센터 정식 도메인 목록 | 프런트엔드(FE) 팀 | 결정 필요 |
| **다중 파드 확장 여부** | 1단계: 단일 파드(EBS PVC) 유지 vs 2단계: RDS(PostgreSQL)+S3 전환 | 아키텍처 / 프로젝트 PM | 1단계 확정, 2단계 로드맵 수립 필요 |
