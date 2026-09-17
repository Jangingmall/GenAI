# SGLang 서빙 운영 조사 보고서: 가중치·라이선스·동일 GPU 공존 방안

- **작성일**: 2026-09-14
- **대상 인프라**: AWS EC2 `g6e.xlarge` (NVIDIA L40S 48GB 1장, Ubuntu 22.04/24.04 LTS)
- **대상 워크로드**: 텍스트/비전 분석(`Qwen3.8-27B`) 및 이미지 생성/편집(`FLUX.2-klein`) SGLang 서빙
- **문서 목적**: 동일 GPU 내 텍스트/확산 SGLang 2개 프로세스 기동을 위한 docker-compose 작성 및 배포 기반 자료 제공

---

## 결론 요약 (Executive Summary)

### 1. 추천 모델 ID 후보
| 구분 | 기본 채택 모델 (관리자 결정) | 대안 (상업 라이선스 완전 개방 대안) |
| :--- | :--- | :--- |
| **텍스트/비전 모델** | **`cyankiwi/Qwen3.8-27B-AWQ-INT4`** (19.60 GiB, Apache 2.0 기반) 또는<br>**`Qwen/Qwen3.8-27B-FP8`** (공식 FP8, 28.77 GiB) | `Qwen/Qwen3.8-27B` (원본 BF16, 51.77 GiB) -> **48GB VRAM 단독 적재도 불가능하므로 배제** |
| **이미지 확산 모델** | **`circulus/FLUX.2-klein-9B-bnb-4bit`**<br>(전체 약 10.2 GiB: 트랜스포머 4.36 GiB + 텍스트 인코더 5.66 GiB + VAE 0.16 GiB, GPU 상주) | **`black-forest-labs/FLUX.2-klein-4B`** (Apache 2.0, 7.22 GiB / FP8 3.80 GiB) -> 상업 운영 완전 허용 라이선스 대안 |

### 2. 라이선스 판정
- **`circulus/FLUX.2-klein-9B-bnb-4bit`**: **상업적 사용 제한 (FLUX Non-Commercial License, FLUX NCL 대상 커뮤니티 양자화본)**. 원본 FLUX.2-klein-9B의 커뮤니티 4bit(bnb nf4) 양자화본으로, 관리자 결정으로 기본 채택되었습니다. 상업 운영 시 BFL 상업 라이선스 확인이 필요합니다. 비게이트 저장소(`gated: False`)로 토큰 없이 다운로드 가능합니다.
- **`black-forest-labs/FLUX.2-klein-4B`**: **상업적 사용 가능 (Apache 2.0 License)**. 비게이트 저장소(`gated: False`)로 토큰 없이 자유롭게 다운로드 가능하며 상업 운영이 허용되는 오픈 대안입니다.

### 3. 권장 SGLang Docker 이미지 태그
- **공식 이미지**: `lmsysorg/sglang:v0.5.19` (또는 최신 검증 빌드 `lmsysorg/sglang:dev` / `lmsysorg/sglang:v0.5.19-cu129`)
- **CUDA 환경**: Host Driver >= 535 (권장 >= 550), 컨테이너 내부 CUDA 12.9 / 13.0 지원.
- **L40S 및 FP8 지원**: L40S(Ada Lovelace, Compute Capability 8.9)는 4세대 Tensor Core를 통해 FP8(E4M3, E5M2)을 하드웨어 레벨에서 네이티브 지원하며, SGLang 런타임 및 커널이 sm89를 완벽 지원합니다.

### 3-1. SGLang 0.5.19 9B 4bit(bnb) 소스 지원 근거 및 CPU 오프로드 비활성화
- **pre-quantized 4-bit 지원**: SGLang 0.5.19 소스(`sglang/multimodal_gen/runtime/layers/quantization/bitsandbytes.py`)의 `BitsAndBytesConfig`는 "pre-quantized bitsandbytes 4-bit checkpoints"를 직접 지원합니다.
- **단위 테스트 검증 근거**:
  - `test/unit/test_transformer_quant.py`: Hugging Face config의 bitsandbytes nf4 양자화 설정을 올바르게 해석함을 검증.
  - `test/unit/test_text_encoder_loader.py`: 표준 bitsandbytes 텍스트 인코더는 transformers로 위임 로드하며, `test_bitsandbytes_native_load_requires_resident_encoder`에서 **텍스트 인코더의 GPU 상주(resident)가 필수**임을 명시하고 있습니다.
- **Dockerfile 커스텀 빌드 이유**: `bitsandbytes`는 SGLang 공식 패키징의 `test` extra에만 선언되어 있어 `sglang[diffusion]` 설치 시 기본 누락됩니다. 따라서 `docker/sglang-diffusion.Dockerfile`에서 `bitsandbytes==0.50.2`를 사전 설치합니다.
- **CPU 오프로드 해제 (`--dit-cpu-offload false --text-encoder-cpu-offload false`) 이유**:
  - SGLang 0.5.19 `server_args.py`의 `_adjust_offload` 함수는 확산 작업 기동 시 사용자가 명시하지 않으면 `dit_cpu_offload`와 `text_encoder_cpu_offload`를 자동으로 `True`로 켭니다.
  - 이는 bitsandbytes 4bit 텍스트 인코더의 GPU 상주 조건(`test_bitsandbytes_native_load_requires_resident_encoder`)과 정면 충돌하므로 두 플래그를 모두 `false`로 명시해야 합니다.
  - 또한 전체 가중치(~10.2 GiB)가 GPU 44.7 GiB 내에 완전히 상주하므로, CPU 오프로드를 완전히 꺼서 호스트 시스템 RAM(32 GiB)의 압박 및 OOM Killer 위험을 원천 차단합니다.
- **대안 양자화 비교 (4B / FP8 / nvfp4)**:
  - **4B (Apache 2.0)**: 상업 운영 시 라이선스 완전 개방이 필요한 경우의 안전한 오픈 대안 (`black-forest-labs/FLUX.2-klein-4B`).
  - **FP8**: L40S(sm89) 텐서코어에서 가속 가능하나 9B FP8 단일 파일(8.79 GiB) 등은 텍스트 인코더 포함 시 용량이 증가함.
  - **nvfp4 (NVIDIA FP4)**: NVIDIA Blackwell 아키텍처(sm100) 전용이므로 L40S(Ada Lovelace, sm89)에서는 하드웨어 지원이 불가능하여 실행 불가.

### 4. 두 프로세스 기동 명령 초안 (단일 GPU 공존)

> [!IMPORTANT]
> **VRAM 계산 기준 및 비율 하한 명시**:  
> NVIDIA L40S 48GB의 실제 가용 바이너리 용량은 **44.70 GiB**($48 \times 10^9 \text{ bytes} \div 1024^3$)입니다.  
> 아래 `--mem-fraction-static` 비율은 텍스트 가중치 크기에서 역산한 **물리적 최소 하한(Lower Bound)** 기준의 초안이며, 최종 최적값은 인스턴스 부하 측정을 통해 확정해야 합니다.  
> 배포 계약에 따라 포트는 **텍스트 30000 (`sglang-text`)**, **이미지 30001 (`sglang-image`)**을 사용합니다.

#### [안 1: 기본 채택 구성 — AWQ/INT4 텍스트 + FLUX 9B bnb-4bit (관리자 결정)]
텍스트 모델은 가중치가 19.60 GiB인 AWQ-INT4 모델을 채택하고, 확산 모델은 9B를 4bit(bitsandbytes nf4)로 양자화한 전체 파이프라인(`circulus/FLUX.2-klein-9B-bnb-4bit`, 약 10.2 GiB)을 채택하여 트랜스포머와 텍스트 인코더를 모두 GPU에 상주시키는 구성입니다.
- **텍스트 가중치 역산 하한**: $19.60 \div 44.70 \approx 0.438$ (최소 43.8% 필요)
- **텍스트 정적 할당 초안**: `--mem-fraction-static 0.50` (약 22.35 GiB 선점 $\rightarrow$ 가중치 19.60 GiB + KV 캐시 풀 약 2.75 GiB)
- **확산 모델 VRAM**: 트랜스포머 4.36 GiB + 텍스트 인코더 5.66 GiB + VAE 0.16 GiB $\approx$ **10.18 GiB**
- **GPU 여유분**: $44.70 - (22.35 + 10.18) = \mathbf{12.17\text{ GiB}}$ (피크 활성화 및 2개 CUDA Context 수용)
- **호스트 RAM**: 오프로드가 없어 시스템 RAM 32 GiB에 압박이 없음.

```bash
# [프로세스 1: 텍스트/비전 추론 서버 - 서비스명: sglang-text]
# VRAM 44.7 GiB 중 50% (22.35 GiB) 정적 할당, 포트 30000
python3 -m sglang.launch_server \
  --model-path cyankiwi/Qwen3.8-27B-AWQ-INT4 \
  --served-model-name qwen-text \
  --host 0.0.0.0 \
  --port 30000 \
  --mem-fraction-static 0.50 \
  --context-length 8192 \
  --trust-remote-code

# [프로세스 2: 이미지 생성/편집 서버 - 서비스명: sglang-image]
# 전체 4bit 파이프라인 GPU 상주 (오프로드 제외), 포트 30001
sglang serve \
  --model-path circulus/FLUX.2-klein-9B-bnb-4bit \
  --served-model-name flux-klein \
  --host 0.0.0.0 \
  --port 30001 \
  --num-gpus 1 \
  --dit-cpu-offload false \
  --text-encoder-cpu-offload false
```

#### [안 2: 대안 초안 — FP8 텍스트 유지 시 + FLUX 4B FP8 결합]
공식 `Qwen/Qwen3.8-27B-FP8` 가중치를 유지할 경우, 가중치(28.77 GiB) 적재를 위해 텍스트 서버의 정적 할당 비율을 대폭 높여야 하며 확산 모델 가중치 또한 FP8로 경량화해야 합니다.
- **텍스트 가중치 역산 하한**: $28.77 \div 44.70 \approx 0.644$ (최소 64.4% 필요)
- **텍스트 정적 할당 초안**: `--mem-fraction-static 0.68` (약 30.40 GiB 선점 $\rightarrow$ 가중치 28.77 GiB + 최소 KV 캐시 약 1.63 GiB)
- **확산 모델 잔여 VRAM**: $44.70 - 30.40 = \mathbf{14.30\text{ GiB}}$
- **확산 모델 선택 주의사항**: FLUX 4B BF16(7.22 GiB) 적재 시 남는 동적 여유가 약 7.08 GiB뿐이라 이중 CUDA Context(~2GB) 감안 시 Denoising 중 OOM 위험이 매우 큽니다. 따라서 FP8 텍스트 유지 시에는 확산 모델로 **`black-forest-labs/FLUX.2-klein-4b-fp8` (3.80 GiB)**를 결합해야 약 **10.50 GiB**의 안전 여유가 확보됩니다.

```bash
# [프로세스 1: 텍스트/비전 추론 서버 (FP8) - 서비스명: sglang-text]
python3 -m sglang.launch_server \
  --model-path Qwen/Qwen3.8-27B-FP8 \
  --served-model-name qwen-vl \
  --host 0.0.0.0 \
  --port 30000 \
  --mem-fraction-static 0.68 \
  --context-length 8192 \
  --trust-remote-code

# [프로세스 2: 이미지 생성/편집 서버 (FP8) - 서비스명: sglang-image]
sglang serve \
  --model-path black-forest-labs/FLUX.2-klein-4b-fp8 \
  --served-model-name sglang-image \
  --host 0.0.0.0 \
  --port 30001 \
  --num-gpus 1 \
  --performance-mode memory \
  --pin-cpu-memory
```

### 5. 인스턴스에서 측정해야 할 항목 (측정 전 추정 불가 항목)
1. **텍스트 서버 `--mem-fraction-static` 실측 최적화**: 가중치 하한(AWQ 43.8%, FP8 64.4%) 대비 실제 서비스 트래픽(동시 요청 수, 이미지 토큰 수) 수용에 필요한 KV 캐시 크기를 실측하여 최적 정적 할당 비율 확정.
2. **확산 서버 Peak Dynamic VRAM**: FLUX 4B(BF16 7.22 GiB 또는 FP8 3.80 GiB)가 1024x1024 해상도 4-step Denoising 및 VAE Decode 수행 시 발생하는 Activation Peak VRAM 실측 (추정치 ~8~14 GiB).
3. **이중 CUDA Context 및 런타임 드라이버 오버헤드**: 동일 GPU 0번에서 2개 프로세스가 동시에 CUDA context를 초기화할 때 발생하는 고정 오버헤드 (프로세스당 약 0.7~1.2 GiB, 총 ~2 GiB) 실측.
4. **API 호환성 레이어(클라이언트 어댑터)**: 기존 `src/local_detail_page_ai/clients.py`의 `MlxServeImageClient`가 전송하는 비표준 JSON 포맷(`POST /v1/images/generations` with `mode: "edit"`)을 SGLang diffusion 표준 OpenAI 엔드포인트(`POST /v1/images/edits` multipart)로 연결할 프록시/어댑터 필요 여부.

---

## 1. 텍스트 모델 가중치 조사 (Qwen3.8-27B)

### 1.1 Hugging Face 공식 및 양자화 가중치 현황

로컬 환경(`ddalcu/Qwen3.8-27B-MLX-Serve-4bit`)은 Apple Silicon 통합 메모리(MLX) 전용 포맷이므로 CUDA SGLang에서 직접 로드할 수 없습니다. Hugging Face에서 실제 확인된 CUDA 지원 Qwen3.8-27B 가중치 목록은 다음과 같습니다.

| 모델 저장소 ID | 양자화 형식 | 가중치 파일 크기 (GiB) | 이미지 입력(Vision) 지원 여부 | 라이선스 | 비고 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`Qwen/Qwen3.8-27B`** | 원본 BF16 | **51.77 GiB** (55.59 GB) | **지원** (`image-text-to-text`) | Apache 2.0 | 원본 가중치. 48GB VRAM 단일 GPU에 적재 불가 |
| **`Qwen/Qwen3.8-27B-FP8`** | 공식 FP8 | **28.77 GiB** (30.89 GB) | **지원** (`image-text-to-text`) | Apache 2.0 | Alibaba 공식 FP8 체크포인트. L40S 네이티브 호환 |
| **`cyankiwi/Qwen3.8-27B-AWQ-INT4`** | AWQ W4A16 | **19.60 GiB** (21.04 GB) | **지원** (`image-text-to-text`) | Apache 2.0 기반 | 커뮤니티 양자화. 멀티모달 비전 인코더 보존 |
| **`mattbucci/Qwen3.8-27B-AWQ`** | AWQ W4A16 | **17.44 GiB** (18.73 GB) | **지원** (`image-text-to-text`) | Apache 2.0 기반 | 최소 용량 W4A16 변형 |
| **`RedHatAI/Qwen3.8-27B-INT4`** | INT4 | **18.14 GiB** (19.47 GB) | **지원** (`image-text-to-text`) | Apache 2.0 기반 | RedHat 엔지니어링 검증 INT4 |

- **출처**:
  - `Qwen/Qwen3.8-27B`: https://huggingface.co/Qwen/Qwen3.8-27B
  - `Qwen/Qwen3.8-27B-FP8`: https://huggingface.co/Qwen/Qwen3.8-27B-FP8
  - `cyankiwi/Qwen3.8-27B-AWQ-INT4`: https://huggingface.co/cyankiwi/Qwen3.8-27B-AWQ-INT4
  - `mattbucci/Qwen3.8-27B-AWQ`: https://huggingface.co/mattbucci/Qwen3.8-27B-AWQ

### 1.2 비전(Vision) 입력 지원 여부 확인 근거
공식 모델 카드(`Qwen/Qwen3.8-27B/README.md`)에 따르면 Qwen3.8-27B는 별도의 텍스트 전용 모델이 아닌 **"Causal Language Model with Vision Encoder"** 구조의 네이티브 비전-언어 모델(VLM)입니다:
> *"Qwen3.8-27B brings these advances to a compact, deployment-friendly dense model: a native vision-language model that understands images and videos... pipeline_tag: image-text-to-text"*

입력 토크나이저 및 비전 전처리 설정(`preprocessor_config.json`, `video_preprocessor_config.json`)을 내장하고 있어 상품 이미지 고해상도 인식을 네이티브로 지원합니다.

### 1.3 가중치 선택 분석 (L40S 48GB 제약)
- **원본 BF16 (51.77 GiB)**: 가중치 파일 크기만으로도 L40S의 전체 VRAM(48 GB = 44.7 GiB)을 초과하므로 1장에서는 기동 자체가 불가능합니다.
- **공식 FP8 (`Qwen/Qwen3.8-27B-FP8`, 28.77 GiB)**: L40S 4세대 텐서 코어의 FP8 하드웨어 가속을 100% 활용할 수 있습니다. 단, 단독으로 28.77 GiB를 점유하므로 48GB GPU를 확산 모델과 공유하려면 확산 모델의 VRAM 점유율이 15 GiB 이하로 통제되어야 합니다.
- **AWQ-INT4 (`cyankiwi/Qwen3.8-27B-AWQ-INT4`, 19.60 GiB)**: 가중치 점유가 약 19.6 GiB로 낮아져, 두 모델 공존 시 가장 넉넉한 VRAM 여유분(~24 GiB)을 확보할 수 있습니다.

---

## 2. 이미지 모델 가중치와 라이선스 조사 (FLUX.2-klein)

### 2.1 기본 채택 모델: FLUX.2-klein-9B-bnb-4bit (관리자 결정)
- **저장소 ID**: `circulus/FLUX.2-klein-9B-bnb-4bit`
  - URL: https://huggingface.co/circulus/FLUX.2-klein-9B-bnb-4bit
- **가중치 및 파이프라인 구성**:
  - Diffusers `Flux2KleinPipeline` 전체 구성 (단일 safetensors가 아닌 전체 파이프라인).
  - **트랜스포머 (DiT)**: 약 **4.36 GiB**
  - **텍스트 인코더 (Qwen3ForCausalLM)**: 약 **5.66 GiB**
  - **VAE**: 약 **0.16 GiB**
  - **총 가중치 크기**: 약 **10.18 GiB** (~10.2 GiB)
  - 로컬 Mac 환경의 `mlx-community/flux2-klein-9b-4bit`(9.5 GB)와 동일한 성격의 4bit 경량화 파이프라인.
- **양자화 형식**:
  - 트랜스포머와 텍스트 인코더 모두 `quantization_config`에 bitsandbytes 4bit (`bnb_4bit_quant_type: nf4`, `bnb_4bit_use_double_quant: true`, compute dtype `bfloat16`)가 적용되어 사전 양자화됨.
- **게이트 저장소 여부 및 다운로드**:
  - 비게이트 저장소(`gated: False`), Hugging Face 토큰 불필요(익명 다운로드 가능).
- **라이선스 사실**:
  - 원본 모델인 `black-forest-labs/FLUX.2-klein-9B`는 FLUX Non-Commercial License(FLUX NCL) 대상입니다.
  - 본 저장소는 해당 원본 모델의 커뮤니티 양자화본입니다(저장소 카드 별도 라이선스 미표기).
  - 관리자 결정으로 기본 채택되었으며, 상업 운영 시 BFL 상업 라이선스 확인이 필요합니다(판단·권고 없이 사실만 기록).

### 2.2 원본 FLUX.2-klein-9B 및 공식 FP8 현황 (참고)
- **공식 저장소 ID**: `black-forest-labs/FLUX.2-klein-9B`
  - URL: https://huggingface.co/black-forest-labs/FLUX.2-klein-9B
- **가중치 파일 크기**:
  - 단일 체크포인트 파일(`flux-2-klein-9b.safetensors`): **16.91 GiB** (18.16 GB)
  - 전체 Diffusers 저장소(Qwen3 8B text encoder 15.26 GiB + DiT 16.91 GiB + VAE 0.35 GiB): **49.26 GiB** (52.89 GB)
  - 공식 FP8 단일 파일(`black-forest-labs/FLUX.2-klein-9b-fp8`): **8.79 GiB** (9.44 GB)
- **라이선스**: **FLUX Non-Commercial License (FLUX NCL)**
- **게이트 저장소 여부 및 토큰**: **게이트 저장소임 (`gated: auto`)**, HF_TOKEN 필수.

### 2.3 대안 비교: FLUX.2-klein-4B (상업 오픈 대안)
- **공식 저장소 ID**: `black-forest-labs/FLUX.2-klein-4B`
  - URL: https://huggingface.co/black-forest-labs/FLUX.2-klein-4B
- **가중치 파일 크기**:
  - 단일 체크포인트 파일(`flux-2-klein-4b.safetensors`): **7.22 GiB** (7.75 GB)
  - 전체 Diffusers 저장소: **22.11 GiB** (23.74 GB)
  - 공식 FP8 단일 파일(`black-forest-labs/FLUX.2-klein-4b-fp8`): **3.80 GiB** (4.08 GB)
- **라이선스**: **Apache 2.0 License** (상업적 이용 및 재배포 완벽 허용)
- **게이트 저장소 여부 및 다운로드 토큰**:
  - 게이트 여부: **비게이트 (`gated: False`)**, HF 토큰 불필요.
- **성능 및 기능**:
  - 4B 모델 역시 4-step Rectified Flow 증류 아키텍처로 빠른 생성/편집을 지원하며, 상업 라이선스 완전 개방이 필요한 경우 즉시 교체 가능한 검증된 대안입니다.

### 2.4 양자화 형식 비교 및 nvfp4 제약 (Blackwell 전용)
- **bitsandbytes 4bit (bnb nf4)**: SGLang 0.5.19에서 pre-quantized 4-bit 체크포인트를 네이티브 지원. 트랜스포머와 텍스트 인코더 모두 GPU 상주 시 안정적으로 구동.
- **FP8 (E4M3/E5M2)**: Ada Lovelace(L40S, sm89)의 4세대 텐서코어에서 네이티브 하드웨어 가속 지원.
- **nvfp4 (NVIDIA FP4)**: NVIDIA Blackwell 아키텍처(Compute Capability 10.0 / sm100) 전용 양자화 형식입니다. L40S(sm89)에는 하드웨어 차원의 nvfp4 텐서코어가 존재하지 않아 실행이 불가능하므로, L40S 단일 GPU 공존을 위한 4bit 양자화는 bitsandbytes nf4를 채택합니다.

---

## 3. SGLang 설치 형태 및 환경 지원

### 3.1 공식 Docker 이미지 및 권장 태그
- **Docker Hub 저장소**: `lmsysorg/sglang` (URL: https://hub.docker.com/r/lmsysorg/sglang)
- **권장 안정 태그**: `lmsysorg/sglang:v0.5.19` (또는 `v0.5.19-cu129`, `v0.5.19-cu130`)
- **최신 개발 태그**: `lmsysorg/sglang:dev` (또는 `nightly-dev-cu13-...`)
- **출처**: https://github.com/sgl-project/sglang/blob/main/docker/Dockerfile

### 3.2 CUDA 버전 요구사항
- 컨테이너 기본 이미지: Ubuntu 24.04 기반 `nvidia/cuda:13.0.3-cudnn-devel-ubuntu24.04` 또는 CUDA 12.9
- 호스트 요구사항: NVIDIA Driver 버전 535 이상(CUDA 12.2+ 호환), 권장 드라이버 550 또는 570 이상.
- NVIDIA Container Toolkit(`nvidia-docker2`) 설치 필수.

### 3.3 확산 모델(Diffusion) 지원 포함 여부 및 설치 방법
- **공식 Docker 이미지**: SGLang의 공식 Dockerfile 빌드 기본값은 `ARG BUILD_TYPE=all`이며, 이는 `sglang[diffusion]` 의존성(`diffusers==0.37.0`, `cache-dit`, `opencv-python-headless`, `msgpack`, `runai_model_streamer` 등)을 사전에 포함합니다.
- **호스트 직접 설치 또는 가상환경 설치 시**:
  ```bash
  pip install --upgrade pip
  pip install "sglang[diffusion]" --prerelease=allow
  # 또는 소스 설치:
  pip install -e "python[diffusion]"
  ```
- **출처**: https://raw.githubusercontent.com/sgl-project/sglang/main/docs/docs/sglang-diffusion/installation.mdx

### 3.4 L40S GPU (Ada Lovelace, sm89) 및 FP8 가속 지원
- **Compute Capability 8.9 (sm89) 지원**: NVIDIA L40S는 4세대 Tensor Core를 내장하여 FP8(E4M3 및 E5M2) 포맷 연산을 하드웨어 차원에서 네이티브 실행합니다.
- **SGLang 프레임워크 지원**: FlashInfer, Triton, CUTLASS 커널이 sm89 아키텍처에 컴파일되어 있어 L40S에서 FP8 추론 시 정밀도 손실 없이 메모리 대역폭을 2배, 연산 속도를 대폭 향상시킵니다.

---

## 4. 단일 GPU 내 2개 SGLang 프로세스 공존 방안

SGLang은 단일 프로세스에서 텍스트와 확산 모델을 동시에 서빙하는 단일 파이프라인을 지원하지 않으므로, 동일 GPU 0번에 2개의 프로세스를 띄워야 합니다.

### 4.1 메모리 제어 파라미터 분석

#### 1) 텍스트 추론 서버 (SGLang SRT)
- **`--mem-fraction-static` (핵심)**:
  - SRT 엔진이 전체 물리 GPU 메모리 중 가중치와 정적 KV 캐시 풀로 미리 선점(pre-allocate)할 비율을 지정합니다.
  - **L40S 48GB 실제 VRAM 용량**: $48 \times 10^9 \text{ bytes} \div 1024^3 = \mathbf{44.70\text{ GiB}}$.
  - **가중치 크기에서 역산한 최소 하한**:
    - `Qwen3.8-27B-FP8` (28.77 GiB) 사용 시: $28.77 \div 44.70 \approx \mathbf{0.644}$ (최소 64.4%가 가중치 자체로만 필요). 최소 KV 캐시 풀을 포함하려면 **`--mem-fraction-static 0.68`** 이상이어야 모델이 뜸. (이 경우 확산 모델 잔여 VRAM은 14.30 GiB로 제한됨).
    - `cyankiwi/Qwen3.8-27B-AWQ-INT4` (19.60 GiB) 사용 시: $19.60 \div 44.70 \approx \mathbf{0.438}$ (최소 43.8% 필요). KV 캐시 풀(약 2.75 GiB)을 감안해 **`--mem-fraction-static 0.50`** 설정 가능. (이 경우 확산 모델 잔여 VRAM은 22.35 GiB로 여유로움).
  - **공존 시 필수 조치**: SGLang 기본값(`0.88`~`0.90`)을 방치하면 약 40GB 이상을 선점하여 확산 프로세스가 기동 즉시 `CUDA OOM`으로 강제 종료되므로 반드시 명시적으로 제한해야 함.
  - **보조 파라미터**: `--context-length 8192` (또는 16384)를 지정하여 지나친 KV 캐시 할당을 억제.

#### 2) 확산 추론 서버 (SGLang Diffusion / multimodal_gen)
- 확산 서버는 정적 풀 할당 인자(`--mem-fraction-static`)를 사용하지 않고 PyTorch 기본 동적 할당자(Dynamic Allocator)를 사용합니다.
- **메모리 제어 및 오프로드 설정 인자**:
  - `--num-gpus 1`: 단일 GPU 지정.
  - `--dit-cpu-offload false`, `--text-encoder-cpu-offload false`: **9B bnb-4bit 채택 시 필수 지정**. SGLang 0.5.19 bitsandbytes 4bit 텍스트 인코더는 GPU 상주가 필수(`test_bitsandbytes_native_load_requires_resident_encoder`)이며, SGLang 기본 오프로드 활성화 동작(`server_args.py _adjust_offload`)을 끄고 호스트 시스템 RAM(32 GiB) 압박 및 OOM Killer 위험을 원천 차단합니다.
  - *(참고)*: 과거 FP8 가중치 검토 시 언급되었던 `--performance-mode memory` 및 `--pin-cpu-memory` 플래그는 9B bnb-4bit 구성에서 제거되었으며, CPU 오프로드를 끄는 명시적 옵션(`--dit-cpu-offload false --text-encoder-cpu-offload false`)으로 대체되었습니다.
- **출처**: https://raw.githubusercontent.com/sgl-project/sglang/main/docs/docs/sglang-diffusion/deployment_cookbook.mdx

### 4.2 44.70 GiB VRAM 순수 가중치 하한(Lower Bound) 계산 및 비교

> [!WARNING]
> 아래 계산은 L40S의 실제 가용 VRAM인 **44.70 GiB**($48 \times 10^9 \text{ bytes} \div 1024^3$)를 기준으로 **순수 모델 가중치 파일 크기의 물리적 하한(Lower Bound)**만을 합산한 것입니다.  
> 실제 런타임에는 **CUDA Context 오버헤드(각 프로세스당 ~1GB, 총 ~2GB)**, **텍스트 KV 캐시 풀**, **확산 4-step Denoising 중간 Latent 및 VAE 활성화 메모리**가 추가로 요구됩니다.

| 조합 번호 | 텍스트 모델 (가중치) | 확산 모델 (가중치) | 순수 가중치 합계 하한 | L40S 가용(44.70 GiB) 대비 여유분 | 판정 및 안정성 평가 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **조합 0 (기본 채택)** | **cyankiwi/Qwen 27B AWQ (19.60 GiB)** | **circulus/FLUX 9B bnb-4bit (약 10.18 GiB)** | **29.78 GiB** | **약 14.92 GiB** | **관리자 최종 채택**: 9B 4bit 전체 파이프라인 GPU 상주. 텍스트 50%(22.35 GiB 선점)와 공존 시 여유분 12.17 GiB 확보 |
| **조합 1** | Qwen3.8-27B BF16 (51.77 GiB) | FLUX.2-klein-9B (16.91 GiB) | **68.68 GiB** | **-23.98 GiB (초과)** | **불가 (단독으로도 44.70 GiB 초과, OOM 즉시 발생)** |
| **조합 2** | Qwen3.8-27B FP8 (28.77 GiB) | FLUX.2-klein-9B safetensors (16.91 GiB) | **45.68 GiB** | **-0.98 GiB (초과)** | **불가**: 가중치 합계만으로 44.70 GiB 초과. 기동 불가 |
| **조합 3** | Qwen3.8-27B FP8 (28.77 GiB) | FLUX.2-klein-9b-fp8 (8.79 GiB) | **37.56 GiB** | **약 7.14 GiB** | **FP8 대안**: 원본 FLUX NCL 라이선스 적용 체크포인트. FP8 단일 파일 기준 약 7.1 GiB 여유 확보 |
| **조합 4** | Qwen3.8-27B FP8 (28.77 GiB) | FLUX.2-klein-4B safetensors (7.22 GiB) | **35.99 GiB** | **약 8.71 GiB** | **타이트함**: 가중치 36GB 차지. 남는 8.7GB 중 CUDA context(~2GB) 제외 시 6.7GB뿐이라 Denoising 피크 시 OOM 위험 |
| **조합 5** | **Qwen3.8-27B FP8 (28.77 GiB)** | **FLUX.2-klein-4b-fp8 (3.80 GiB)** | **32.57 GiB** | **약 12.13 GiB** | **FP8 유지 시 대안**: FP8 확산 모델로 가중치를 3.8GB로 줄여 동적 여유 약 12.1GB 확보 |
| **조합 6** | **cyankiwi/Qwen 27B AWQ (19.60 GiB)** | **FLUX.2-klein-4B safetensors (7.22 GiB)** | **26.82 GiB** | **약 17.88 GiB** | **상업 오픈 대안**: Apache 2.0 4B 모델 적용 대안. VRAM 17.9GB 여유로 KV 캐시와 Denoising 동시 수용 안정적 |
| **조합 7** | **cyankiwi/Qwen 27B AWQ (19.60 GiB)** | **FLUX.2-klein-4b-fp8 (3.80 GiB)** | **23.40 GiB** | **약 21.30 GiB** | **최대 여유 확보 대안**: VRAM 21.3GB 여유로 배치 처리 및 장기 세션 처리에 최적 |

> [!NOTE]
> **nvfp4 (NVIDIA FP4) 미지원 안내**:  
> 커뮤니티의 `nvfp4` 양자화 모델은 NVIDIA Blackwell 아키텍처(sm100) 전용이므로, L40S(Ada Lovelace sm89)에서는 하드웨어 미지원으로 실행할 수 없습니다. 따라서 L40S 환경에서의 4bit 확산 서빙은 bitsandbytes 4bit(bnb nf4)를 기본 채택합니다.

### 4.3 동일 GPU 공존 시 알려진 이슈 및 운영 고려사항
1. **VRAM 경합에 따른 상호 OOM 위험**:
   - PyTorch 동적 할당자는 여유 VRAM이 부족해지는 순간 즉시 `torch.cuda.OutOfMemoryError`를 발생시키고 프로세스가 중단됩니다.
   - 따라서 텍스트 프로세스는 `--mem-fraction-static`을 엄격히 제한하고, 확산 프로세스는 동시 요청 수(`--max-running-requests 1`)를 1개로 제한하여 큐잉 처리해야 합니다.
2. **CUDA Context 드라이버 오버헤드**:
   - 프로세스 2개가 개별적으로 CUDA 런타임을 초기화하므로, 프로세스당 700MB ~ 1.2GB씩 총 약 1.5 ~ 2.4GB의 고정 메모리가 드라이버 컨텍스트로 소비됩니다.
3. **연산 코어(SM) 시분할 경합**:
   - 표준 Linux 환경에서는 단일 GPU 내 복수 프로세스가 시간 분할(Time-Slicing) 방식으로 SM을 공유합니다.
   - 텍스트 모델이 이미지 비전 토큰을 분석하는 동안 이미지 확산 모델이 Denoising 연산을 수행하면 양쪽 모두 지연 시간(Latency)이 1.3~1.8배 증가할 수 있습니다.
   - 단, 우리 서비스 파이프라인(`ANALYZING` → `RENDERING`)은 순차적으로 호출되므로 두 모델이 정확히 같은 밀리초에 풀 부하를 일으킬 확률은 제한적입니다.
4. **호스트 RAM(32GB) 제약과 CPU Offload 한계**:
   - `g6e.xlarge`는 시스템 RAM이 32 GiB에 불과합니다.
   - 만약 VRAM 부족을 해결하겠다고 확산 모델의 텍스트 인코더나 DiT를 CPU로 오프로드(`--text-encoder-cpu-offload` 등)하면, 20GB 이상의 가중치가 시스템 RAM에 적재되면서 호스트 OS의 `Out of Memory (OOM) Killer`가 발동해 Docker 데몬이나 프로세스를 강제 종료할 위험이 있습니다. **따라서 CPU 오프로드는 지양하고 가중치 자체를 FP8/INT4로 축소해 VRAM 안에 상주시켜야 합니다.**

---

## 5. FLUX.2-klein 이미지 편집 품질 이슈 분석 (Issue #19449)

### 5.1 이슈 내용 및 현황
- **대상 이슈**: `sgl-project/sglang` Issue #19449
  - 제목: *[Bug] [Diffusion] FLUX.2-klein-9B image editing produces corrupted output with multi-GPU (`--num-gpus 8`)*
  - URL: https://github.com/sgl-project/sglang/issues/19449
- **현상**:
  - `FLUX.2-klein-9B`를 8개 GPU(`--num-gpus 8`)와 시퀀스 병렬(`sp_degree=8`) 환경에서 실행할 때, **이미지 편집(`POST /v1/images/edits`) 출력이 회색 노이즈 또는 녹색 덩어리로 완전히 손상(corrupted)**되는 현상 발생.
  - HTTP 200 정상 종료 및 에러 로그 없이 조용히 깨진 이미지가 생성됨. (단, Text-to-Image 생성 `/v1/images/generations`은 8장에서도 정상 작동).
- **해결 현황**:
  - **CLOSED (종결됨)**: 2026-03-04 PR #19454에 의해 공식 해결 및 머지 완료.
  - 대상 PR: `[Diffusion] Fix corrupted image editing outputs in Multi-GPU SP mode for FLUX.2-klein models` (#19454)
  - URL: https://github.com/sgl-project/sglang/pull/19454
  - 원인: Ulysses Attention에서 노이즈 토큰과 조건 이미지 토큰의 RoPE(회전 위치 임베딩) 분할 결합 오류 및 복제 프리픽스 처리 누락.

### 5.2 단일 GPU 환경(`g6e.xlarge`)에 미치는 영향
- **영향 없음 (정상 동작)**:
  - 이슈 리포트 본문에 명시된 바와 같이, 해당 버그는 시퀀스 병렬(Sequence Parallelism) 통신 커널에서 발생한 것이며 **단일 GPU(`--num-gpus 1`)에서는 버그 발생 당시에도 100% 정상 작동**했습니다:
    > *"When serving FLUX.2-klein-9B with --num-gpus 8, image editing produces completely corrupted images... The same model, prompts, and input images work **perfectly** with `--num-gpus 1`."*
  - AWS `g6e.xlarge`는 물리 GPU 1장만을 탑재하므로 시퀀스 병렬이 활성화되지 않으며, 단일 GPU 파이프라인을 사용하므로 **편집 품질 훼손 이슈의 영향을 받지 않습니다.**
  - 또한 현재 권장 태그(`v0.5.19`) 및 최신 소스에는 PR #19454가 이미 완전히 반영되어 있습니다.

---

## 6. AWS EC2 g6e.xlarge 인스턴스 상세 사양

- **공식 출처**: AWS EC2 G6e 인스턴스 공식 제품 스펙 (https://aws.amazon.com/ec2/instance-types/g6e/)

| 사양 항목 | 세부 내용 | 배포 운영 관점의 시사점 |
| :--- | :--- | :--- |
| **인스턴스 크기** | `g6e.xlarge` | 엔트리급 GPU 인스턴스 |
| **GPU 모델 및 수량** | **1x NVIDIA L40S** (48 GB GDDR6 with ECC) | Ada Lovelace 아키텍처, Compute Capability 8.9 |
| **vCPU** | **4 vCPU** (AMD EPYC 7R13 Milan 프로세서) | CPU 연산 리소스가 타이트하므로 컨테이너 CPU 제한 조율 필요 |
| **시스템 메모리 (RAM)** | **32 GiB** | 호스트 RAM이 작아 대용량 가중치 CPU 오프로드 시 OOM Killer 위험 |
| **로컬 스토리지 (Instance Store)** | **1 x 250 GB NVMe SSD (존재함)** | **매우 중요**: 고속 임시 디스크가 제공되므로, 모델 캐시(`HF_HOME`) 및 Docker 임시 작업 볼륨으로 마운트하여 기동 속도 극대화 가능 |
| **네트워크 대역폭** | Up to 20 Gbps | Hugging Face 모델 다운로드 속도 우수 |
| **EBS 최적화 대역폭** | Up to 5 Gbps | 루트 볼륨 I/O 성능 |

---

## 7. docker-compose 작성 워커를 위한 연동 가이드

다른 워커가 `docker-compose.yml`을 작성할 때 반드시 반영해야 하는 핵심 구조와 주의사항입니다.

### 7.1 서비스 포트 및 역할 매핑
- **Text VLM Service (`sglang-text`)**:
  - 포트: `30000:30000`
  - 엔드포인트: `POST /v1/chat/completions` (OpenAI 비전 멀티모달 규격 호환)
  - 우리 서비스의 `.env`: `LOCAL_TEXT_URL=http://sglang-text:30000`
- **Diffusion Service (`sglang-image`)**:
  - 포트: `30001:30001`
  - 엔드포인트: `POST /v1/images/generations` 및 `POST /v1/images/edits`
  - 우리 서비스의 `.env`: `LOCAL_IMAGE_URL=http://sglang-image:30001`

### 7.2 클라이언트 통신 규약 주의사항 (중요 기술 부채)
기존 `src/local_detail_page_ai/clients.py`의 `MlxServeImageClient`는 MLX Serve 전용 커스텀 JSON 페이로드를 사용합니다:
```python
# MlxServeImageClient.edit()의 현재 페이로드:
POST /v1/images/generations
{
  "model": "...",
  "prompt": "...",
  "mode": "edit",
  "steps": 4,
  "strength": 0.3,
  "image": "<base64>"
}
```
그러나 SGLang 확산 서버는 표준 OpenAI Images 규약을 준수하므로:
- 이미지 생성: `POST /v1/images/generations` (JSON, `prompt`, `size`, `response_format`)
- 이미지 편집: `POST /v1/images/edits` (Multipart Form-Data, `image`, `prompt`)

**조치 방안**:
현재 태스크에서는 코드를 수정하지 않기로 하였으므로, 후속 작업에서 `clients.py`에 SGLang 전용 클라이언트(`SglangImageClient`)를 추가하거나 경량 변환 어댑터(프록시) 컨테이너를 docker-compose에 배치해야 합니다.

### 7.3 로컬 NVMe 인스턴스 스토어 활용 가이드
`g6e.xlarge`에 내장된 `1 x 250 GB NVMe SSD`는 인스턴스 재부팅/중지 시 데이터가 초기화되는 휘발성 스토리지이나, I/O 속도가 EBS 대비 월등히 빠릅니다.
- 기동 스크립트에서 NVMe 디바이스(보통 `/dev/nvme1n1`)를 포맷하여 `/mnt/nvme-cache`로 마운트합니다.
- Docker Compose에서 Hugging Face 캐시 디렉터리를 `/mnt/nvme-cache/huggingface`로 볼륨 매핑하면 40GB에 달하는 모델 로드 및 I/O 병목을 해소할 수 있습니다.

---

## 8. 출처 및 참고 문서 (References)

1. **Hugging Face Model Repositories**:
   - `Qwen/Qwen3.8-27B`: https://huggingface.co/Qwen/Qwen3.8-27B
   - `Qwen/Qwen3.8-27B-FP8`: https://huggingface.co/Qwen/Qwen3.8-27B-FP8
   - `cyankiwi/Qwen3.8-27B-AWQ-INT4`: https://huggingface.co/cyankiwi/Qwen3.8-27B-AWQ-INT4
   - `circulus/FLUX.2-klein-9B-bnb-4bit`: https://huggingface.co/circulus/FLUX.2-klein-9B-bnb-4bit
   - `black-forest-labs/FLUX.2-klein-9B`: https://huggingface.co/black-forest-labs/FLUX.2-klein-9B
   - `black-forest-labs/FLUX.2-klein-4B`: https://huggingface.co/black-forest-labs/FLUX.2-klein-4B
   - `black-forest-labs/FLUX.2-klein-4b-fp8`: https://huggingface.co/black-forest-labs/FLUX.2-klein-4b-fp8
2. **Black Forest Labs Official Blog**:
   - *FLUX.2 [klein]: Towards Interactive Visual Intelligence*: https://bfl.ai/blog/flux2-klein-towards-interactive-visual-intelligence
3. **SGLang Documentation & GitHub**:
   - SGLang Repository: https://github.com/sgl-project/sglang
   - SGLang DockerHub: https://hub.docker.com/r/lmsysorg/sglang
   - SGLang Diffusion Installation: https://raw.githubusercontent.com/sgl-project/sglang/main/docs/docs/sglang-diffusion/installation.mdx
   - SGLang Diffusion Deployment Cookbook: https://raw.githubusercontent.com/sgl-project/sglang/main/docs/docs/sglang-diffusion/deployment_cookbook.mdx
   - SGLang Diffusion OpenAI API: https://raw.githubusercontent.com/sgl-project/sglang/main/docs/docs/sglang-diffusion/api/openai_api.mdx
   - SGLang Issue #19449: https://github.com/sgl-project/sglang/issues/19449
   - SGLang PR #19454: https://github.com/sgl-project/sglang/pull/19454
   - SGLang Dockerfile: https://github.com/sgl-project/sglang/blob/main/docker/Dockerfile
4. **AWS Documentation**:
   - Amazon EC2 G6e Instances Overview: https://aws.amazon.com/ec2/instance-types/g6e/
