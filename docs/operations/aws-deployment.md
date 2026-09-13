# AWS 이관·검증 가이드 (상세페이지 AI)

작성일: 2026-09-10 (개정 2판) · 대상: 상세페이지 생성 AI 서비스 (`ai-service` 및 추론 서빙)  
체크리스트: [AWS 이관 준비물 및 단계별 체크리스트](aws-migration-checklist.md)

이 문서는 로컬 Apple Silicon(MLX) 환경에서 검증된 상세페이지 생성 파이프라인을 AWS EKS GPU 노드로 이관하여 **1건 end-to-end 생성 및 릴리스 품질 게이트 통과까지 검증**하는 종합 운영 가이드다.

> [!NOTE]
> **성능 수치 기준선 (로컬 베이스라인 vs AWS)**:  
> 본 문서의 실측 수치는 2026-09-10 Apple Silicon MLX 환경(M-series 통합 메모리, `Qwen3.8-27B-4bit` 18.2GB + `flux2-klein-9b-4bit` 9.5GB) 기준선이다. 6건 파일럿 실행 시 이미지 생성을 포함하여 **약 27분(1건당 평균 약 226초)**이 소요되었다.  
> 이는 **AWS 인프라의 성능 수치가 아니며 로컬 개발 기준선**이다. AWS GPU(L40S 등)에서의 실제 처리 속도와 레이턴시는 CUDA 포팅 및 실측 후 확정한다.

---

## 1. 구성 요소와 포트

| 구성 요소 | 포트 | 런타임/기술 스택 | 역할 | 현재 상태 |
|---|---|---|---|---|
| **ai-service** | **8000** | Python 3.13, FastAPI, Node.js/Chromium, SQLite | Job 접수, 상태 머신, Draft 생성, React 문서 조립, PNG 렌더, 상품 BE outbox 배달 | 컨테이너화 준비 완료 (`Dockerfile` 존재) |
| **추론 서버** | **11234** (필요 시 11235) | vLLM + Diffusers / MLX Serve 호환 프록시 | 텍스트·비전 분석 + 배경 및 연출 컷 생성 | **Apple Silicon 전용 (MLX Serve)** → CUDA 재포팅 필요 |

ai-service는 추론 서버를 `LOCAL_TEXT_URL`과 `LOCAL_IMAGE_URL` 두 환경변수로만 참조한다. 추론 서버의 백엔드를 무엇으로 교체하든 애플리케이션 클라이언트가 기대하는 규약만 충족하면 핵심 비즈니스 로직 코드는 변경되지 않는다.

---

## 2. 지금 그대로는 뜨지 않는다 — 핵심 제약과 갭 4가지

AWS 배포 전 반드시 해결되어야 하는 기술적 격차는 다음과 같다.

### 갭 1. Apple Silicon 전용 MLX Serve 종속성
- **현상**: MLX Serve는 macOS/Apple Silicon 전용 프레임워크로, AWS EC2 Linux CUDA 환경에서는 바이너리 자체가 실행되지 않는다.
- **해결 방안**: 텍스트 분석은 **vLLM**, 이미지는 **Diffusers** 기반 커스텀 서빙 컨테이너로 교체해야 한다.

### 갭 2. 가중치 포맷 불일치
- **현상**: 로컬 가중치인 `ddalcu/Qwen3.8-27B-MLX-Serve-4bit`(18.2GB) 및 `mlx-community/flux2-klein-9b-4bit`(9.5GB)는 MLX 전용 포맷이다.
- **해결 방안**: 텍스트는 AWQ 또는 GPTQ 4-bit, 이미지는 safetensors 또는 bitsandbytes 4-bit 가중치를 새로 확보하여 S3에 적재해야 한다.

### 갭 3. 클라이언트 이미지 편집 호출 규약 불일치 (핵심 제약)
- **현상**: 초기 문서에는 multipart `/v1/images/edits`로 기술되었으나, 현재 실제 코드([clients.py](../../src/local_detail_page_ai/clients.py#L214-L247))는 편집 요청 시 **단일 JSON 엔드포인트**인 `POST {LOCAL_IMAGE_URL}/v1/images/generations`를 호출한다:
  ```json
  {
    "model": "flux2-klein-9b",
    "prompt": "...",
    "size": "1024x1024",
    "mode": "edit",
    "steps": 4,
    "strength": 0.30,
    "image": "<base64_encoded_source_image>"
  }
  ```
  - `steps`: FLUX.2 Klein 증류(distilled) 모델 특성에 맞춰 기본값이 4로 설정되어 전달된다.
  - `strength`: FLUX.2 in-context edit 모드에서 지원되지 않아 모델이 무시하지만 JSON 스키마에는 포함된다.
- **영향**: 표준 OpenAI API나 일반 Diffusers 서빙은 `/v1/images/generations`에서 `mode: "edit"`나 `image` base64 필드를 파싱하지 않는다.
- **해결 방안**:
  1. **(권장) 서빙 프록시 어댑터 배치**: Diffusers 앞단에 경량 FastAPI 프록시를 두어 위 JSON 규약을 받아 in-context image-to-image 파이프라인으로 매핑.
  2. **클라이언트 어댑터 확장**: `src/local_detail_page_ai/clients.py`에 표준 Diffusers/ComfyUI 규격을 지원하는 신규 클라이언트를 추가.

### 갭 4. 컨테이너 빌드 시 필수 정적 자산 누락
- **현상**: [layout_archetypes.py](../../src/detail_page_ai/layout_archetypes.py#L14-L16)는 `assets/references/detail-page-layouts.json`(20종 상세페이지 원형 카탈로그)을 로드하여 모델 프롬프트에 주입한다. 그러나 현재 [Dockerfile](../../Dockerfile#L32-L34)은 `src/`와 렌더 스크립트만 복사하고 `assets/`를 복사하지 않는다.
- **영향**: 컨테이너 실행 시 카탈로그 파일을 찾지 못해 `load_layout_catalog()`가 빈 리스트(`[]`)를 반환하며, 레이아웃 원형 주입이 비활성화되어 페이지 구성 다양성이 퇴행한다.
- **해결 방안**: `Dockerfile`에 `COPY assets/references/detail-page-layouts.json ./assets/references/detail-page-layouts.json` 레이어를 추가해야 한다.

---

## 3. 이관 준비물 및 체크리스트 연계

상세한 준비 절차와 검증 방법은 [AWS 이관 준비물 및 단계별 체크리스트](aws-migration-checklist.md)에 기술되어 있으며, 요약은 다음과 같다:

1. **클라우드 인프라**: EC2 `g6e.xlarge` (L40S 48GB) 인스턴스 쿼터, EKS 노드 그룹, S3 Gateway Endpoint.
2. **모델 가중치**: S3 버킷에 Qwen3.8-27B(AWQ/GPTQ 4-bit) 및 FLUX.2 Klein 9B(safetensors) 적재.
3. **컨테이너 이미지**: `assets/references/detail-page-layouts.json` 복사를 포함하여 ECR에 빌드 및 푸시.
4. **스토리지**: 단일 파드용 EBS PVC (최소 20Gi gp3, ReadWriteOnce) 마운트 (`/var/lib/detail-page-ai`).
5. **환경변수/보안**: `AI_INTERNAL_AUTH_TOKEN`, `BACKEND_PRODUCT_URL`, `BACKEND_AUTH_TOKEN`, `AI_CORS_ORIGINS` 주입.

---

## 4. 이관 경로 두 가지

### A안 — 전체 이관 (최종 목표)

단일 GPU 노드에 파드 1개(또는 같은 노드 내 파드 2개)로 배치한다.

```text
[ai-service :8000]  --HTTP-->  [text-infer :11234]   vLLM (Qwen3.8 27B AWQ 4bit)
        |            --HTTP-->  [image-infer :11235]  Diffusers + Edit JSON 프록시 (FLUX.2 Klein 9B)
        +-- EBS PVC (sqlite: state.sqlite3, assets/)
```

- **동일 노드 배치 필수**: 텍스트 분석 및 이미지 생성(페이지당 7~8회, base64 수 MB)이 빈번하므로 네트워크 대역폭 비용과 지연을 방지하기 위해 로컬 loopback 통신을 유지한다.
- **이미지 서빙 동시성 1**: 디퓨전 모델은 VRAM 스파이크가 크므로 인스턴스 내부 큐를 두고 동시성 1로 순차 처리한다.
- **모델 상주 (Always Resident)**: 요청마다 가중치를 로드하면 5분 이상 지연되므로 메모리에 상주시키며, readiness probe는 모델 가중치 로드 완료를 기준으로 설정한다.

### B안 — 분리 검증 (권장 선행 단계)

CUDA 추론 서버 포팅 작업과 병행하여 **AWS 애플리케이션 인프라 구간을 먼저 검증**하는 경로다.

- `ai-service`만 EKS에 먼저 올리고, `LOCAL_TEXT_URL` / `LOCAL_IMAGE_URL`을 외부 테스트 GPU 인스턴스(또는 Colab/GCP)로 향하게 한다.
- 컨테이너 기동, Node/Chromium 렌더, EBS 영속화, 보안 그룹, 상품 BE outbox 배달까지 **모델 이외의 전 과정을 선행 확정**하여 위험을 분리한다.

---

## 5. 컨테이너 이미지 규격

### ai-service 컨테이너 (`Dockerfile`)

| 항목 | 사양 / 설정값 | 비고 |
|---|---|---|
| 베이스 이미지 | `python:3.13-slim` | GPU 미사용 (CPU 전용 파이프라인) |
| 시스템 런타임 | Node.js, npm, Chromium 브라우저 바이너리 | `npx playwright install --with-deps chromium` |
| 파이썬 라이브러리 | fastapi, httpx, pillow, pydantic-settings, python-multipart, uvicorn | `pyproject.toml` 기반 |
| 정적 자산 복사 | `src/`, `scripts/runtime/render_detail_page.mjs`, `assets/references/detail-page-layouts.json` | **layouts.json 누락 방지 필수** |
| 실행 계정 | `appuser` (UID 10001, GID 10001) | 비root 보안 계정 |
| 볼륨 마운트 | `/var/lib/detail-page-ai` | SQLite 및 Asset 저장 디렉터리 |
| 진입점 / 헬스체크 | `serve-ai` (포트 8000) | `GET /api/v1/ai/detail-page-jobs/does-not-exist` (404 응답 확인) |

### 추론 서버 컨테이너

| 항목 | 사양 / 설정값 |
|---|---|
| 베이스 이미지 | `nvidia/cuda:12.4.1-runtime-ubuntu22.04` |
| 텍스트 추론 엔진 | vLLM (OpenAI 호환 `/v1/chat/completions` 지원) |
| 이미지 추론 엔진 | Diffusers + MLX JSON 호환 프록시 (포트 11235 또는 11234 멀티엔드포인트) |
| 예상 이미지 크기 | 약 10~14GB (가중치 제외) |

---

## 6. GPU 사이징 및 VRAM 예산

| 항목 | 예상 VRAM | 비고 |
|---|---:|---|
| Qwen3.8-27B 4-bit 가중치 | ~16GB | AWQ 또는 GPTQ 4-bit |
| FLUX.2 Klein 9B fp16 가중치 | ~18GB | bnb-4bit 적용 시 ~10GB 수준으로 감소 가능 |
| KV 캐시 및 런타임 활성화 버퍼 | ~8~10GB | `max_model_len` 제한 적용 시 |
| **최소 요구 VRAM** | **~42~44GB** | **권장 인스턴스: `g6e.xlarge` (L40S 48GB)** |

> [!WARNING]
> **VRAM 고갈 방지 (`max_model_len` 제한)**:  
> Qwen3.8의 기본 컨텍스트 길이(174k)를 그대로 두면 vLLM이 VRAM의 대부분을 KV 캐시로 선할당하여 FLUX.2 모델이 로드되지 못하고 OOM이 발생한다. 상품 분석은 수천 토큰으로 충분하므로 vLLM 실행 시 반드시 `--max-model-len 8192` 및 `--gpu-memory-utilization 0.45` 수준으로 상한을 지정해야 한다.

---

## 7. 모델 가중치 배포 (S3)

```text
s3://jangin-{env}-s3-models/
  detail-page/
    text/qwen3.8-27b-awq/         # AWQ 4-bit safetensors
    image/flux2-klein-9b-fp16/    # FLUX.2 Klein 9B safetensors
```

- **S3 Gateway VPC Endpoint**: Hugging Face 허브 직접 다운로드는 NAT Gateway 데이터 처리 비용(GB당 약 $0.059 [미검증 참고값 — 리전·계약·시점별 상이, 인프라팀 확인 필요])이 발생하므로, VPC 내부 엔드포인트를 통해 무료로 고속 다운로드한다.
- **초기화 Init 컨테이너**: 파드 기동 시 init 컨테이너가 S3에서 인스턴스 로컬 스토리지(`/mnt/models` 또는 emptyDir)로 가중치를 동기화한 후 추론 서버를 구동한다.

---

## 8. 상태(state) 처리 및 영속성 ([persistence.py](../../src/detail_page_ai/persistence.py))

ai-service는 파일 기반의 두 가지 영속성 저장소를 사용한다.

| 환경변수 | 기본값 | 저장 내용 |
|---|---|---|
| `SQLITE_PATH` | `.local/detail-page-ai/state.sqlite3` | `detail_page_jobs` (작업 상태/임대), `detail_page_outbox` (BE 배달 큐) |
| `ASSET_STORE_DIR` | `.local/detail-page-ai/assets` | 원본 및 생성된 이미지 바이너리 |

### 단일 파드 + EBS PVC (1단계 운영 아키텍처)
- `gp3` EBS PVC (`ReadWriteOnce`)를 `/var/lib/detail-page-ai`에 마운트하여 두 경로를 모두 영속화한다.
- **장애 복구 흐름**:
  1. 파드 크래시 또는 노드 재배치 시 새 파드가 동일 EBS 볼륨을 재마운트한다.
  2. 기동 시 `recover_interrupted()`가 호출되어 만료된 lease를 가진 작업(`QUEUED`, `ANALYZING`, `COMPOSING` 등)을 감지하고 상태를 `QUEUED`로 리셋하여 처음부터 안전하게 재실행한다.
  3. `SQLiteDeliveryOutbox` 백그라운드 루프가 미전송(`PENDING`, `RETRYING`) 상태인 outbox 이벤트를 상품 BE로 자동 재전송한다.

### 수평 확장(HPA / 다중 파드) 제약 사항 (2단계 과제)
- **EBS 한계**: EBS 볼륨은 단일 노드/단일 파드에만 마운트(`ReadWriteOnce`)할 수 있어 파드 레플리카를 2개 이상으로 늘릴 수 없다.
- **EFS(NFS) 불가**: SQLite 파일을 EFS 네트워크 공유 스토리지에 올릴 경우, 다중 파드 동시 트랜잭션 시 파일 락 불안정 및 데이터베이스 손상(Corruption)이 발생한다.
- **해결 로드맵**: 추후 트래픽 증가로 인한 다중 파드 수평 확장이 필요할 경우, `JobRepository` 및 `DeliveryOutbox`를 **PostgreSQL(RDS/Aurora)** 백엔드로 전환하고 `AssetStore`를 **S3**로 교체해야 한다.

---

## 9. 환경변수 정본 표 ([config.py](../../src/detail_page_ai/config.py) `Settings` 1:1 대조)

아래 표는 현재 코드베이스의 `Settings` 정의와 완전히 일치하는 환경변수 정본이다.

| 환경변수명 (Alias) | 타입 및 허용값 | 기본값 | AWS EKS 설정 지침 |
|---|---|---|---|
| `ANALYSIS_PROVIDER` | `local` | `local` | `local` 유지 (외부 클라우드 API 호출 차단) |
| `LOCAL_TEXT_PROVIDER` | `mlx`, `ollama` | `mlx` | `mlx` 유지 (vLLM의 OpenAI 호환 API 사용 시 `mlx` 클라이언트 인터페이스 공유) |
| `LOCAL_TEXT_URL` | 문자열 (URL) | `http://127.0.0.1:11234` | **환경에 맞게 변경** (같은 파드면 유지, 분리 시 서비스 URL) |
| `LOCAL_TEXT_MODEL` | 문자열 | `ddalcu/Qwen3.8-27B-MLX-Serve-4bit` | **반드시 변경** (CUDA 포팅 모델 식별자, 예: `Qwen/Qwen2.5-VL-7B-Instruct-AWQ`) |
| `LOCAL_TEXT_TIMEOUT` | float (초) | `300.0` | 유지 (복잡 이미지 분석 대비 300초) |
| `LOCAL_IMAGE_PROVIDER` | `none`, `mlx` | `mlx` | `mlx` (이미지 생성 활성화 시) 또는 `none` (생성 비활성화 시) |
| `LOCAL_IMAGE_URL` | 문자열 (URL) | `http://127.0.0.1:11234` | **환경에 맞게 변경** (이미지 서버 분리 시 `:11235` 등) |
| `LOCAL_IMAGE_MODEL` | 문자열 | `mlx-community/flux2-klein-9b-4bit` | **반드시 변경** (CUDA 포팅 모델 식별자, 예: `flux2-klein-9b`) |
| `LOCAL_IMAGE_TIMEOUT` | float (초) | `300.0` | 유지 (디퓨전 생성 타임아웃 300초) |
| `PRODUCT_PHOTO_GENERATION` | `source` | `source` | `source` 유지 (원본 제품 픽셀 보존 불변 원칙) |
| `BACKGROUND_PROVIDER` | `none`, `mlx` | `mlx` | `mlx` 또는 `none` |
| `PRODUCT_PHOTO_SHOTS` | 콤마 구분 문자열 | `hero,packshot,detail,lifestyle` | 유지 (`hero,packshot,detail,lifestyle,scale` 중 구성) |
| `SOURCE_PHOTO_VARIATION_THRESHOLD` | int (1~12) | `4` | 유지 (디테일 컷 변형 생성 기준치) |
| `DETAIL_PAGE_RENDERER` | `html` | `html` | `html` 유지 (Playwright HTML 렌더러) |
| `BACKEND_PRODUCT_URL` | 문자열 (URL) 또는 None | `None` | **반드시 설정** (상품 BE 내부 엔드포인트 URL) |
| `BACKEND_AUTH_TOKEN` | 문자열 또는 None | `None` | **반드시 설정** (상품 BE 호출용 Bearer 토큰, Secret 주입) |
| `BACKEND_TIMEOUT_SECONDS` | float (초) | `60.0` | 유지 |
| `AI_INTERNAL_AUTH_TOKEN` | 문자열 또는 None | `None` | **반드시 설정** (`/internal/v1/ai/*` 보안 인증 토큰, Secret 주입) |
| `DETAIL_PAGE_TEMPLATE_PATH` | 문자열 (경로) 또는 None | `None` | 템플릿 이미지 사용 시에만 지정 |
| `MAX_IMAGE_BYTES` | int (바이트) | `10485760` (10MB) | 유지 |
| `REQUIRE_DECODABLE_IMAGES` | bool | `True` | 유지 (이미지 디코딩 무결성 검증) |
| `MAX_SOURCE_IMAGES` | int (1~50) | `12` | 유지 |
| `MAX_REQUEST_BYTES` | int (바이트) | `125829120` (120MB) | 유지 |
| `MAX_PENDING_GENERATIONS` | int | `100` | 대기 큐 크기 |
| `MAX_DELIVERY_ATTEMPTS` | int (1~100) | `8` | outbox 재시도 횟수 상한 |
| `ENABLE_LEGACY_DEMO_API` | bool | `False` | `False` 유지 |
| `AI_CORS_ORIGINS` | 콤마 구분 문자열 | `http://127.0.0.1:4173,...` | **반드시 변경** (운영/스테이징 판매자 센터 도메인 지정) |
| `PROMPT_VERSION` | 문자열 | `local-mlx-qwen-flux-v1` | **변경 권장** (예: `aws-cuda-qwen-flux-v1` - provenance 추적용) |
| `ASSET_STORE_DIR` | 문자열 (디렉터리) | `.local/detail-page-ai/assets` | **반드시 변경** (PVC 마운트 경로: `/var/lib/detail-page-ai/assets`) |
| `SQLITE_PATH` | 문자열 (파일 경로) | `.local/detail-page-ai/state.sqlite3` | **반드시 변경** (PVC 마운트 경로: `/var/lib/detail-page-ai/state.sqlite3`) |
| `RESPONSE_ASSET_MODE` | `base64`, `url`, `both` | `base64` | 유지 |
| `CRAFT_CONFIDENCE_THRESHOLD` | float (0.0~1.0) | `0.65` | 유지 (공예 분류 신뢰도 임계치) |

---

## 10. 네트워크 및 보안 그룹

| 트래픽 방향 | 포트 | 출발지/목적지 | 프로토콜 | 용도 |
|---|---|---|---|---|
| **Inbound** | **8000** | K8s Ingress / ALB / API Gateway | HTTP | ai-service API (판매자 웹 FE 및 상품 BE 요청 수신) |
| **Internal** | **11234 / 11235** | `127.0.0.1` (Pod Local) | HTTP | ai-service → vLLM / Diffusers 추론 호출 (노드 외부 노출 차단) |
| **Outbound** | **443** | 상품 BE 서비스 엔드포인트 | HTTPS | 승인 완료 산출물 outbox 배달 |
| **Outbound** | **443** | AWS S3 Gateway Endpoint | HTTPS | 초기 기동 시 모델 가중치 다운로드 |

---

## 11. 단계별 검증 절차 및 릴리스 품질 게이트

배포 검증은 **(A) 점진적 인프라 도달 검증**과 **(B) 자동화된 릴리스 품질 게이트 검증**의 2단계로 수행된다.

### (A) 점진적 인프라 도달 검증 (0단계 ~ 6단계)

- **0단계 (컨테이너 기본 기동)**:
  ```bash
  curl -sS http://<host>:8000/api/v1/ai/detail-page-jobs/does-not-exist
  # HTTP 404 수신 시 프로세스 정상 기동 및 포트 개방 확인
  ```
- **1단계 (추론 서버 도달)**:
  ```bash
  curl -sS http://127.0.0.1:11234/v1/models
  # 텍스트 및 이미지 모델 식별자 반환 확인
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
- **6단계 (파드 장애 복구)**:
  - `kubectl delete pod <ai-service-pod>` 실행 후, 재기동된 파드가 기존 `state.sqlite3`를 인식하고 작업을 정상 유지하는지 확인.

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

---

## 12. 아직 결정되지 않은 것 (미결정 목록 및 승인 주체)

개발팀 단독으로 결정할 수 없으며 유관 조직과 합의가 필요한 항목들이다:

| 항목 | 결정 필요 내용 | 결정/승인 주체 | 현 상태 및 리스크 |
|---|---|---|---|
| **GPU 인스턴스 승인** | EC2 `g6e.xlarge` (L40S 48GB; 온디맨드 기준 시간당 약 $1.8 [미검증 참고값 — 리전·계약·시점별 상이, 인프라팀 확인 필요]) 예산 및 온디맨드 쿼터 할당 | **인프라 / FinOps 팀** | 결정 필요 (미승인 시 T4/A10G로 강제되어 OOM 발생; 실제 단가 검증이 승인 조건에 포함됨) |
| **S3 모델 버킷 권한** | 가중치 저장소 버킷명, IAM 권한 및 EKS IRSA 매핑 정책 | **클라우드 보안 / 인프라 팀** | 미확정 시 파드 기동 불가 |
| **상품 BE 엔드포인트** | 운영/스테이징 `BACKEND_PRODUCT_URL` 주소 및 인증 시크릿 발급 | **상품 백엔드(BE) 팀** | 미확정 시 outbox 배달 불가 |
| **프런트엔드 오리진** | `AI_CORS_ORIGINS`에 등록할 정식 웹 서비스 도메인 목록 | **프런트엔드(FE) 팀** | 미확정 시 브라우저 CORS 차단 |
| **추론 어댑터 프록시 배포** | Diffusers 앞단에 MLX Serve JSON edit 규약 프록시 컨테이너를 sidecar로 둘지 여부 | **AI 서빙 엔지니어** | 기술 방식 확정 필요 |
| **다중 파드 확장 시점** | 1단계(단일 파드 + EBS PVC) 운영 후 RDS(PostgreSQL) + S3 이관 시점 | **프로젝트 PM / 아키텍트** | 트래픽 목표치에 따라 로드맵 수립 필요 |

---

## 13. 알려진 제약 및 참고 문서

- **체크포인트 부재**: 현재 파이프라인은 작업 중간 체크포인트가 없어 파드 크래시 시 해당 job은 처음(`QUEUED`)부터 다시 실행된다 (건당 약 3~4분 소모).
- **이미지 생성 해상도**: 현재 1024×1024 정사각형 고정으로 생성된 후 Pillow로 크롭하여 상세페이지 폭(774px)에 합성된다.
- **참고 문서 목록**:
  - 이관 실무 체크리스트: [AWS 이관 준비물 체크리스트](aws-migration-checklist.md)
  - 서빙 스택 검토: [로컬 MLX Serve 서빙 운영 검토](sglang-vllm-fit.md)
  - 메모리 산정 보고서: [로컬 모델 서버 메모리 예상치](server-memory-estimate.md)
  - 로컬 런타임 가이드: [로컬 LLM 상세페이지 경로](local-llm.md)
