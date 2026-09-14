# Ubuntu 서버 배포 가이드 (상세페이지 AI — SGLang 3서비스 구성)

- **대상 인프라**: AWS EC2 `g6e.xlarge` (1x NVIDIA L40S 48GB, 4 vCPU, 32GB RAM, 1x 250GB NVMe SSD)
- **대상 브랜치**: `deploy/ubuntu`
- **대상 구성**: Docker Compose 기반 3개 서비스 단일 호스트 공존
  - `detail-page-ai`: FastAPI 애플리케이션 (CPU 전용, 포트 8000)
  - `sglang-text`: SGLang SRT 텍스트/비전 추론 서버 (Qwen3.8-27B-AWQ-INT4, 포트 30000, 공개명 `qwen-text`)
  - `sglang-image`: SGLang 확산 이미지 생성/편집 서버 (FLUX.2-klein-4B, 포트 30001, 공개명 `flux-klein`)
- **대상 플랫폼**: `linux/amd64` (Ubuntu 22.04 LTS / 24.04 LTS)

이 문서는 Ubuntu GPU 서버(`g6e.xlarge`)에서 단일 NVIDIA L40S(48GB) GPU를 공유하여 텍스트 및 이미지 추론 서버를 SGLang으로 동시에 구동하고, 상세페이지 AI 서비스를 안정적으로 배포·운영하기 위한 절차를 설명합니다.

---

## 1. 서버 준비

### 1.1 시스템 및 디스크 요구 사양
- **인스턴스 사양**: AWS EC2 `g6e.xlarge`
  - GPU: 1x NVIDIA L40S (48 GB GDDR6 with ECC, Ada Lovelace sm89)
  - vCPU / RAM: 4 vCPU / 32 GiB RAM
  - 로컬 스토리지: 1x 250 GB NVMe SSD (Instance Store)
- **디스크 여유 공간 (권장 최소 150GB 이상)**:
  - SGLang 베이스 이미지 (`lmsysorg/sglang:v0.5.19`) 및 확산 빌드 이미지: 약 18~22 GB
  - Qwen3.8-27B-AWQ-INT4 모델 가중치: 약 19.6 GiB (공식 FP8 대안 선택 시 28.8 GiB)
  - FLUX.2-klein-4B 모델 가중치: 약 7.2 GiB (Diffusers 전체 구성 시 ~22 GiB)
  - rembg 누끼 모델 (`birefnet-general.onnx`): 약 973 MB
  - 생성된 산출물(`assets/`) 및 SQLite 작업 DB (`state.sqlite3`): 수 GB 이상
- **[권장] NVMe 인스턴스 스토어 캐시 마운트**:
  `g6e.xlarge`의 250GB 로컬 NVMe SSD는 EBS 대비 I/O 속도가 월등하므로, Hugging Face 모델 캐시 볼륨 또는 Docker 데이터 디렉터리로 마운트하여 기동 및 모델 로딩 시간을 대폭 단축할 수 있습니다.
  ```bash
  # NVMe 인스턴스 스토어 포맷 및 마운트 (인스턴스 최초 기동 시)
  sudo mkfs.ext4 -E nodiscard /dev/nvme1n1
  sudo mkdir -p /mnt/nvme-cache
  sudo mount -o noatime /dev/nvme1n1 /mnt/nvme-cache
  sudo chmod 777 /mnt/nvme-cache
  ```

### 1.2 NVIDIA 드라이버 및 Container Toolkit 설치
SGLang 컨테이너 및 CUDA 12.9/13.0 지원을 위해 호스트 드라이버는 **535 이상(권장 550 이상 또는 570)**이 요구됩니다.

```bash
# 1. 패키지 인덱스 갱신 및 필수 유틸리티 설치
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg ubuntu-drivers-common

# 2. NVIDIA 공식 드라이버 설치 (550 권장)
sudo apt-get install -y nvidia-driver-550
# 드라이버 모듈 적재 (필요 시 서버 재부팅: sudo reboot)
nvidia-smi

# 3. Docker Engine 및 Compose Plugin 설치
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER

# 4. NVIDIA Container Toolkit 설치
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# 5. Docker GPU 런타임 검증
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

---

## 2. 코드 받기

저장소를 복제하고 Ubuntu 배포 브랜치(`deploy/ubuntu`)로 이동합니다.

```bash
git clone <저장소_URL> Team3_EcommerceSystemAI
cd Team3_EcommerceSystemAI
git checkout deploy/ubuntu
```

---

## 3. `.env` 환경변수 작성

`.env.example` 파일을 복사하여 실제 서버 환경에 맞춘 `.env` 파일을 생성합니다.

```bash
cp .env.example .env
chmod 600 .env  # 비밀값이 포함되므로 권한 제한
```

### 3.1 주요 설정값 점검

| 환경변수명 | 기본값 / 설정 예시 | 설명 및 변경 필요 여부 |
| :--- | :--- | :--- |
| **`SGLANG_IMAGE`** | `lmsysorg/sglang:v0.5.19` | SGLang 공식 컨테이너 베이스 이미지 |
| **`SGLANG_VERSION`** | `0.5.19` | SGLang Diffusion 이미지 빌드에 적용할 SGLang 패키지 버전 |
| **`TEXT_MODEL_PATH`** | `cyankiwi/Qwen3.8-27B-AWQ-INT4` | 텍스트 모델 가중치 체크포인트 경로 (HF 다운로드 대상) |
| **`TEXT_SERVED_MODEL_NAME`**| `qwen-text` | 텍스트 서버 공개 모델명 (`--served-model-name`) |
| **`TEXT_MEM_FRACTION`** | `0.50` | 텍스트 VRAM 정적 할당 비율 (**인스턴스에서 측정 후 확정**) |
| **`TEXT_CONTEXT_LENGTH`**| `8192` | KV 캐시 상한 제어를 위한 컨텍스트 길이 |
| **`IMAGE_MODEL_PATH`** | `black-forest-labs/FLUX.2-klein-4B` | 이미지 모델 체크포인트 경로 (**Apache 2.0 라이선스**) |
| **`IMAGE_SERVED_MODEL_NAME`**| `flux-klein` | 확산 서버 공개 모델명 (`--served-model-name`, 클라이언트 요청 model과 일치 필수) |
| **`IMAGE_PERFORMANCE_MODE`**| `memory` | VRAM 절약 모드 활성화 |
| **`HF_TOKEN`** | `""` | Hugging Face 토큰 (4B는 비게이트라 불필요, 비공개 저장소 시 필요) |
| **`LOCAL_TEXT_PROVIDER`**| `sglang` | 텍스트 클라이언트 구현체 (FastAPI 앱 연동) |
| **`LOCAL_TEXT_URL`** | `http://sglang-text:30000` | SGLang 텍스트 컨테이너 주소 |
| **`LOCAL_TEXT_MODEL`** | `qwen-text` | 클라이언트 텍스트 모델명 (`TEXT_SERVED_MODEL_NAME`과 100% 일치) |
| **`LOCAL_IMAGE_PROVIDER`**| `sglang` | 이미지 클라이언트 구현체 |
| **`LOCAL_IMAGE_URL`** | `http://sglang-image:30001` | SGLang 확산 컨테이너 주소 |
| **`LOCAL_IMAGE_MODEL`** | `flux-klein` | 클라이언트 이미지 모델명 (`IMAGE_SERVED_MODEL_NAME`과 100% 일치) |
| **`BACKGROUND_PROVIDER`**| `sglang` | 연출 컷/배경판 생성 제공자 |
| **`AI_INTERNAL_AUTH_TOKEN`**| (난수 문자열) | Product BE 호출 인증 토큰 (`openssl rand -hex 32`로 **반드시 설정**) |
| **`BACKEND_AUTH_TOKEN`**| (토큰 문자열) | Product BE 콜백 전송 인증 토큰 (**반드시 설정**) |
| **`BACKEND_PRODUCT_URL`**| `http://backend:8080` | 산출물 수신 Product BE URL (**반드시 설정**) |

---

## 4. 서비스 기동 및 상태 확인

### 4.1 서비스 빌드 및 기동
Docker Compose를 통해 이미지를 빌드하고 3개 서비스를 백그라운드(`-d`) 모드로 실행합니다.

```bash
docker compose up -d --build
```
> [!NOTE]
> `sglang-image` 서비스는 공식 SGLang 이미지에 `sglang[diffusion]` 확산 의존성을 사전에 포함하기 위해 [`docker/sglang-diffusion.Dockerfile`](../../docker/sglang-diffusion.Dockerfile)을 빌드하여 `local/sglang-diffusion:0.5.19` 이미지를 생성합니다.

### 4.2 컨테이너 기동 순서 및 헬스체크 의존성
- `sglang-text`와 `sglang-image` 서비스가 먼저 기동되어 Hugging Face 가중치를 다운로드하고 GPU VRAM에 로드합니다.
- 각 SGLang 서비스는 내부 모델 등록이 완료되면 OpenAI 호환 엔드포인트인 `GET /v1/models`에서 HTTP 200을 반환합니다.
- `detail-page-ai`는 `depends_on: {condition: service_healthy}` 설정에 따라 **두 SGLang 서비스가 `GET /v1/models` 정상 응답(healthy)을 반환한 후에만 기동**되므로 부팅 중 연결 실패(Connection Refused)가 발생하지 않습니다.
- 최초 실행 시 모델 다운로드(약 27GB)에 5~15분가량 소요될 수 있으므로 `start_period: 600s`(10분)가 부여되어 있습니다.

### 4.3 서비스 상태 확인
```bash
docker compose ps
```

출력 예시 (모든 서비스가 healthy 상태):
```text
NAME              IMAGE                          COMMAND                  SERVICE          CREATED          STATUS                    PORTS
detail-page-ai    team3_ecommercesystemai        "serve-ai"               detail-page-ai   15 minutes ago   Up 5 minutes (healthy)    0.0.0.0:8000->8000/tcp
sglang-image      local/sglang-diffusion:0.5.19  "sglang serve ..."       sglang-image     15 minutes ago   Up 15 minutes (healthy)   0.0.0.0:30001->30001/tcp
sglang-text       lmsysorg/sglang:v0.5.19        "python3 -m sglang..."   sglang-text      15 minutes ago   Up 15 minutes (healthy)   0.0.0.0:30000->30000/tcp
```

### 4.4 로그 모니터링
```bash
# 텍스트 서버 로그 확인
docker compose logs -f sglang-text

# 확산 서버 로그 확인
docker compose logs -f sglang-image

# 메인 AI 서비스 로그 확인
docker compose logs -f detail-page-ai
```

---

## 5. rembg 누끼 모델 동작 및 볼륨 캐시

### 5.1 모델 캐시 동작
상품 사진 누끼(Background Removal) 작업 시 `rembg`는 `birefnet-general.onnx`(약 973MB)를 다운로드합니다.
Dockerfile 및 compose의 `U2NET_HOME=/var/lib/detail-page-ai/models/u2net` 설정에 따라 영구 볼륨(`detail-page-ai-data`)에 저장되므로 컨테이너를 재시작해도 다시 다운로드하지 않습니다.

### 5.2 사설망 사전 적재 절차
인터넷이 차단된 폐쇄망 환경의 경우 호스트에서 모델 파일을 미리 볼륨에 주입합니다:
```bash
# 1. 모델 다운로드
curl -L -o birefnet-general.onnx https://github.com/danielgatis/rembg/releases/download/v0.0.0/birefnet-general.onnx

# 2. 볼륨으로 파일 복사 및 권한(appuser uid: 10001) 부여
docker run --rm \
  -v detail-page-ai-data:/target \
  -v $(pwd):/source \
  alpine sh -c "
    mkdir -p /target/models/u2net && \
    cp /source/birefnet-general.onnx /target/models/u2net/birefnet-general.onnx && \
    chown -R 10001:10001 /target/models
  "
```

---

## 6. 추론 서버 구성: SGLang 단일 GPU 공존 아키텍처

### 6.1 공존 구조
`g6e.xlarge`는 물리 GPU 1장(NVIDIA L40S 48GB)을 탑재하고 있습니다. SGLang은 프로세스당 1개 모델을 서빙하므로, 동일 GPU 0번에 텍스트(`sglang-text`, 포트 30000)와 이미지 확산(`sglang-image`, 포트 30001) 컨테이너 2개를 띄워 공존시킵니다.

```
+-------------------------------------------------------------------------+
|                  AWS EC2 g6e.xlarge (Host RAM: 32 GiB)                  |
|                                                                         |
|  +-------------------------------------------------------------------+  |
|  |                     NVIDIA L40S VRAM (48 GB)                      |  |
|  |                                                                   |  |
|  | [ sglang-text (SRT) ]            [ sglang-image (Diffusion) ]     |  |
|  |  Port: 30000                      Port: 30001                     |  |
|  |  Qwen3.8-27B-AWQ-INT4 (19.6 GiB)  FLUX.2-klein-4B (7.2 GiB)       |  |
|  |  정적 풀 선점: ~24.0 GiB (0.50)    동적 할당: ~14.0 GiB (Denoising) |  |
|  |  (가중치 + KV 캐시 풀)            (메모리 모드, pin-cpu)          |  |
|  |                                                                   |  |
|  | <------------- 공유 오버헤드: CUDA Context (~2 GiB) ------------> |  |
|  +-------------------------------------------------------------------+  |
|                                     ^                                   |
|                                     | Compose Network                   |
|                        +---------------------------+                    |
|                        |  detail-page-ai (Port 8000)|                    |
|                        |  FastAPI + Playwright (CPU) |                   |
|                        +---------------------------+                    |
+-------------------------------------------------------------------------+
```

### 6.2 SGLang Compose 검수 결함 3건과 해결 조치 (근거 문서 및 URL)

정적 compose 문법 검사(`docker compose config`)만으로는 드러나지 않는 실제 런타임 기동 결함 3건을 공식 문서 기반으로 진단하고 해결했습니다.

#### 1) 공식 SGLang 이미지 내 확산(Diffusion) 기능 부재
- **근거**: [SGLang Diffusion 공식 설치 문서](https://docs.sglang.io/docs/sglang-diffusion/installation.md)
  > *"The standard SGLang image does not include diffusion extras by default. Install with `pip install 'sglang[diffusion]'`..."*
- **결함**: 공식 `lmsysorg/sglang:v0.5.19` 이미지는 LLM 전용이어서 `diffusers` 등 확산 의존성이 누락되어 있으며, `sglang serve` 실행 시 확산 모듈을 로드하지 못하고 종료됩니다.
- **해결 조치**: 컨테이너 기동 시마다 매번 pip을 설치하는 위험을 피하기 위해, 전용 Dockerfile인 [`docker/sglang-diffusion.Dockerfile`](../../docker/sglang-diffusion.Dockerfile)을 추가했습니다. 베이스 이미지 위에 동일 버전의 `sglang[diffusion]==${SGLANG_VERSION}`(의존성 23개 포함)을 사전 빌드하여 컨테이너 이미지화합니다.

#### 2) 클라이언트 요청의 `model` 파라미터와 서버 모델명 불일치 거부
- **근거**: [SGLang Diffusion OpenAI API 규약](https://docs.sglang.io/docs/sglang-diffusion/api/openai_api.md)
  > *"The request's `model` parameter must match `--served-model-name`..."*
- **결함**: 확산 서버는 `--served-model-name flux-klein`으로 띄웠으나, 클라이언트(`detail-page-ai`)가 가중치 체크포인트 경로인 `black-forest-labs/FLUX.2-klein-4B`를 `model` 값으로 보내면 확산 서버가 모델을 찾지 못하고 HTTP 400/404로 요청을 거부합니다.
- **해결 조치**: 다운로드 체크포인트 경로(`TEXT_MODEL_PATH`, `IMAGE_MODEL_PATH`)와 공개 서비스 모델명(`TEXT_SERVED_MODEL_NAME=qwen-text`, `IMAGE_SERVED_MODEL_NAME=flux-klein`)을 명확히 분리하고, 클라이언트의 `LOCAL_TEXT_MODEL`/`LOCAL_IMAGE_MODEL`이 공개 서비스 모델명을 그대로 참조하도록 단일화했습니다.

#### 3) 확산 서버 `/health` 엔드포인트 부재로 인한 기동 정지(Hang)
- **근거**: [SGLang Diffusion API 엔드포인트 명세](https://docs.sglang.io/docs/sglang-diffusion/api/openai_api.md)
  > *"Diffusion server endpoints: `GET /v1/models`, `GET /v1/models/{model_name}`, `GET /server_info`..."*
- **결함**: 확산 서버 명세에는 `/health` 엔드포인트가 공식 제공되지 않으므로, `/health` 헬스체크를 지정할 경우 `sglang-image` 컨테이너가 영원히 `unhealthy` 상태에 머물러 `detail-page-ai`가 기동되지 않습니다.
- **해결 조치**: 두 SGLang 서비스 모두 OpenAI 표준 규격인 `GET /v1/models`를 Python 표준 라이브러리(`urllib.request`)로 호출하는 헬스체크로 전환하여 컨테이너 환경의 도구(curl 등) 유무와 무관하게 확실한 준비 완료 상태를 검증합니다.

---

### 6.3 모델 라이선스 판정 및 주의사항

#### 1) FLUX.2-klein-9B의 상업적 사용 불가 판정
- **라이선스**: **FLUX Non-Commercial License (FLUX NCL)**
- **공식 근거**: [Black Forest Labs 공식 블로그](https://bfl.ai/blog/flux2-klein-towards-interactive-visual-intelligence)
  > *"Note: The 'FLUX [dev] Non-Commercial License' has been renamed to 'FLUX Non-Commercial License' and will apply to the 9B Klein models. No material changes have been made to the license. License: FLUX NCL"*
- **판정**: 이커머스 상품 상세페이지를 제작하여 고객에게 제공하는 본 서비스는 명백한 상업적 운영이므로, 별도의 BFL 엔터프라이즈 라이선스 계약 없이는 **FLUX.2-klein-9B를 프로덕션 기본값으로 채택할 수 없습니다.** 또한 9B는 Hugging Face 게이트 저장소(`gated: auto`)로 접근이 차단되어 있습니다.

#### 2) FLUX.2-klein-4B 채택 근거
- **라이선스**: **Apache 2.0 License** (상업적 이용 및 재배포 완벽 허용)
- **공식 근거**:
  > *"FLUX.2 [klein] 4B: Fully open under Apache 2.0. Built for local development, edge deployment, and production use... Open weights available for commercial use under the Apache 2.0 license."*
- **기술적 이점**: 비게이트 저장소(`gated: False`)로 `HF_TOKEN` 없이 다운로드 가능하며, 4-step Rectified Flow 증류 모델로서 단일 GPU에서 1초 미만 추론이 가능합니다. VRAM 요구량이 가중치 7.22 GiB(FP8 3.8 GiB)에 불과하여 L40S 48GB를 텍스트 모델과 분할해 쓰기에 최적입니다.

> [!WARNING]
> **[확인 필요·결정 필요 — 관리자 결정 사항]**  
> 현재 로컬 Mac 개발 환경에서 사용 중인 `mlx-community/flux2-klein-9b-4bit` 역시 BFL FLUX.2-klein-9B의 4bit 양자화 변환본이므로, **원천 라이선스인 FLUX Non-Commercial License의 적용 대상**입니다. 로컬 개발 환경 역시 라이선스 리스크를 제거하기 위해 4B 기반 MLX 모델로 교체할 것인지 관리자의 확인 및 결정이 필요합니다.

---

### 6.4 텍스트 모델 기본값 선정 근거

| 모델 ID | 양자화 | 가중치 크기 | 비전 지원 | 채택 여부 및 선정 근거 |
| :--- | :--- | :--- | :--- | :--- |
| **`cyankiwi/Qwen3.8-27B-AWQ-INT4`** | AWQ INT4 | **19.60 GiB** | 지원 | **[1순위 기본값]**: 가중치가 19.6 GiB로 작아 48GB 중 `--mem-fraction-static 0.50`(~24 GiB) 설정만으로 KV 캐시를 충분히 확보하면서 확산 모델에 21 GiB 이상의 여유분을 제공함. |
| **`Qwen/Qwen3.8-27B-FP8`** | 공식 FP8 | **28.77 GiB** | 지원 | **[대안 후보]**: Alibaba 공식 FP8 체크포인트로 L40S 텐서코어 가속에 최적이나, 가중치만으로 48GB의 60%를 점유하여 확산 모델과의 공존 여유가 12GB 미만으로 매우 타이트함. |
| **`Qwen/Qwen3.8-27B`** | 원본 BF16 | **51.77 GiB** | 지원 | **[배제]**: 48GB VRAM 단독 적재도 불가능하므로 공존 불가. |

---

### 6.5 메모리 비율 하한 계산 및 확정 원칙

- **물리적 가중치 하한(Lower Bound)**:
  - `cyankiwi/Qwen3.8-27B-AWQ-INT4`: $19.60\text{ GiB} / 48\text{ GiB} \approx 0.408$ (약 41%)
  - 순수 가중치만 올리는 데 최소 41%가 필요하므로, `--mem-fraction-static`은 0.41 미만으로 설정할 수 없습니다.
  - 여기에 컨텍스트 8192 토큰 처리를 위한 최소 KV 캐시 풀(약 4~5 GiB)을 확보하기 위해 **초기 설정값으로 `0.50` (약 24.0 GiB)**을 권장합니다.
- **확산 모델 여유 공간**:
  - 총 48 GiB - 텍스트 정적 선점 24 GiB - 이중 CUDA Context 오버헤드 2 GiB = **약 22 GiB 동적 여유분**.
  - FLUX 4B 가중치(7.22 GiB) + 1024x1024 Denoising 피크 메모리(12~14 GiB)를 안정적으로 수용할 수 있습니다.
- **확정 원칙**:
  수치 계산상의 추정이므로, **반드시 실제 인스턴스 기동 후 아래 체크리스트를 측정하여 최종 확정**해야 합니다.

---

### 6.6 첫 배포 측정 체크리스트 (운영자 기입 표)

첫 배포 시 아래 표의 측정 항목을 순서대로 확인하고 실측값을 기록하여 인프라 파라미터를 최종 확정합니다.

| 번호 | 점검 및 측정 항목 | 기대 기준 | 실측값 / 상태 | 판정 |
| :---: | :--- | :--- | :--- | :---: |
| 1 | `docker/sglang-diffusion.Dockerfile` 빌드 성공 | `sglang[diffusion]` 0.5.19 설치 완료 | [ &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ] | [ ] Pass / [ ] Fail |
| 2 | `sglang-text` 및 `sglang-image` `GET /v1/models` 헬스체크 통과 | HTTP 200 반환 및 healthy 전환 | [ &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ] | [ ] Pass / [ ] Fail |
| 3 | 클라이언트 모델명 일치 검증 (`qwen-text`, `flux-klein`) | 400/404 거부 없이 정상 요청 접수 | [ &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ] | [ ] Pass / [ ] Fail |
| 4 | 유휴(Idle) 상태 `nvidia-smi` 메모리 점유<br>- 텍스트 서버 (`sglang-text`)<br>- 확산 서버 (`sglang-image`)<br>- 총 점유량 / 총 VRAM | <br>~24.0 GiB 내외<br>~7.5 GiB 내외<br>< 33.0 GiB / 48 GiB | <br>[ &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ] GiB<br>[ &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ] GiB<br>[ &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ] GiB | [ ] Pass / [ ] Fail |
| 5 | 텍스트 서버 긴 프롬프트(상품설명+이미지) 분석 시 KV 캐시 여유 | OOM 없이 200 반환, 로그 상 KV 부족 없음 | [ &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ] | [ ] Pass / [ ] Fail |
| 6 | 1024x1024 해상도 이미지 생성/편집 시 순간 피크 VRAM | 전체 VRAM 46 GiB 이하 유지 | [ &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ] GiB | [ ] Pass / [ ] Fail |
| 7 | 이중 CUDA Context 드라이버 고정 오버헤드 | 프로세스당 ~1 GiB 내외 | [ &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ] GiB | [ ] Pass / [ ] Fail |
| 8 | 단일 상품 상세페이지 한 건 생성 총 소요 시간 (E2E) | 분석 + 생성 + 누끼 + 렌더링 총합 | [ &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ] 초 | [ ] Pass / [ ] Fail |

---

## 7. 동작 확인 및 API 검증

### 7.1 SGLang 서버 직접 호출 점검

#### 1) 텍스트 모델 서버 (`http://localhost:30000`)
```bash
# 1. 헬스 상태 확인 (OpenAI 모델 목록 반환 확인)
curl -sS http://localhost:30000/v1/models | jq .

# 2. 간단한 텍스트/비전 분석 요청 테스트 (등록된 qwen-text 모델명 사용)
curl -sS -X POST http://localhost:30000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen-text",
    "messages": [
      {"role": "user", "content": "안녕하세요! 간단히 자기소개해 주세요."}
    ],
    "temperature": 0.1
  }' | jq .
```

#### 2) 이미지 확산 모델 서버 (`http://localhost:30001`)
```bash
# 1. 헬스 상태 확인 (OpenAI 모델 목록 반환 확인)
curl -sS http://localhost:30001/v1/models | jq .

# 2. 이미지 생성 테스트 (등록된 flux-klein 모델명 사용, 1024x1024, 4-step)
curl -sS -X POST http://localhost:30001/v1/images/generations \
  -H "Content-Type: application/json" \
  -d '{
    "model": "flux-klein",
    "prompt": "Modern luxury ceramic tea cup on a minimal wooden table, studio lighting, highly detailed",
    "size": "1024x1024",
    "n": 1,
    "response_format": "b64_json"
  }' | jq -r '.data[0].b64_json' | head -c 50
```

### 7.2 애플리케이션 한 건 생성 E2E 테스트 (`POST /internal/v1/ai/detail-page-jobs`)

메인 애플리케이션을 통해 상품 이미지 접수 및 전체 파이프라인 처리를 검증합니다.

```bash
# 1. 테스트용 1x1 이미지 생성
echo -n "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==" | base64 -d > sample_product.png

# 2. AI 작업 접수 요청
INTERNAL_TOKEN=$(grep '^AI_INTERNAL_AUTH_TOKEN=' .env | cut -d '=' -f2)

curl -X POST http://localhost:8000/internal/v1/ai/detail-page-jobs \
  -H "X-AI-Internal-Token: ${INTERNAL_TOKEN}" \
  -H "Idempotency-Key: sglang-e2e-$(date +%s)" \
  -F "product_image=@sample_product.png;type=image/png" \
  -F 'metadata={
    "product_id": "test-sglang-001",
    "idempotency_key": "sglang-run-001",
    "template_id": "default-long-detail-page",
    "locale": "ko-KR",
    "user_hints": {
      "product_name": "도자기 수제 머그컵",
      "making_method": "전통 백자 물레 성형 기법",
      "care_guide": "식기세척기 사용 가능, 부드러운 스펀지로 세척하세요."
    }
  }'
```

- **기대 응답 (HTTP 202 Accepted)**:
  ```json
  {
    "product_id": "test-sglang-001",
    "job_id": "job-...",
    "request_id": "...",
    "status": "QUEUED",
    "status_url": "/internal/v1/ai/detail-page-jobs/job-...",
    "created_at": "..."
  }
  ```

### 7.3 작업 진행 상태 조회 (`GET /internal/v1/ai/detail-page-jobs/{job_id}`)
```bash
curl -X GET http://localhost:8000/internal/v1/ai/detail-page-jobs/<발급받은_JOB_ID> \
  -H "X-AI-Internal-Token: ${INTERNAL_TOKEN}"
```
상태 전이 확인: `QUEUED` → `ANALYZING` → `EXTRACTING` → `RENDERING` → `COMPLETED`.

---

## 8. 운영 및 유지보수

### 8.1 서비스 중지 및 재기동
```bash
# 전체 서비스 안전 중지 (볼륨 데이터 보존)
docker compose down

# 서비스 재기동
docker compose up -d
```

### 8.2 서비스 업데이트
```bash
git checkout deploy/ubuntu
git pull
docker compose up -d --build
```

### 8.3 데이터 백업 및 복원
모든 영구 데이터는 `detail-page-ai-data` 볼륨에 저장되어 있습니다.

- **데이터 백업**:
  ```bash
  mkdir -p backups
  docker run --rm \
    -v detail-page-ai-data:/data \
    -v $(pwd)/backups:/backup \
    alpine tar czf /backup/detail_page_ai_backup_$(date +%Y%m%d_%H%M%S).tar.gz -C /data .
  ```
- **데이터 복원**:
  ```bash
  docker compose down
  docker run --rm \
    -v detail-page-ai-data:/data \
    -v $(pwd)/backups:/backup \
    alpine sh -c "cd /data && rm -rf * && tar xzf /backup/<백업파일명>.tar.gz"
  docker compose up -d
  ```
