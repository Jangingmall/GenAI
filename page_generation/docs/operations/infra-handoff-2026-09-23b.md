# 인프라팀 요청 회신 — 2026-09-23 (Stage 실기동 오류)

- 수신: 「2026-09-23 Stage EKS 실기동 로그 · 상세페이지 AI / 챗봇 AI 담당」 (재현 기준 이미지 소스 `1ba5d35`)
- 회신: 생성형 AI 팀 (상세페이지 생성)

> 완료되지 않은 추론 검증은 성공으로 표시하지 않았습니다. 이 문서 시점에 **GPU 에서 확인된 것은 없습니다.**

## 요약

| 대상 | 원인 | 조치 | 검증 |
| --- | --- | --- | --- |
| 상세페이지 · L40S | 두 SGLang 서버의 **동시 기동**. 이미지 서버가 텍스트 서버 로딩 중 VRAM 을 가져가 텍스트 캐시 예산이 음수가 됨 | 텍스트 서버 준비 후 이미지 서버를 띄우도록 수정 | **미검증** — L40S 시간이 필요합니다 |
| 챗봇 LLM · T4 | SGLang v0.5.19 의 `gemma4_unified` 설정 별칭 버그 | 챗봇 담당이 PR #37 로 백포트, main 반영 | **미검증** — 새 이미지 발행과 T4 실행 필요 |

---

## 1. 상세페이지 — 원인은 동시 기동입니다

### 로그의 숫자가 그대로 재현됩니다

SGLang 은 텍스트 서버의 캐시 예산을 이렇게 잡습니다.

```
rest = (가중치 로드 후 남은 VRAM) − (기동 시점 VRAM) × (1 − mem_fraction_static)
```

`(1 − mem_fraction_static)` 만큼은 **다른 용도로 남겨 둘 몫**입니다. 그런데 entrypoint 가 텍스트
서버와 이미지 서버를 **동시에** 띄웠습니다. 텍스트 서버가 252초 동안 가중치를 올리는 사이 이미지
서버가 VRAM 을 가져갔고, SGLang 은 그 양을 텍스트 서버가 남겨 둬야 할 몫에서 뺐습니다.

```
텍스트 가중치 (safetensors 합계)       19.57 GiB
로드 중 빠진 VRAM                     34.94 GB
→ 같은 시간에 이미지 서버가 가져간 양   약 15.4 GB  (이미지 가중치 10.18 GiB + 컨텍스트·초기화)

동시 기동:   rest = 8.52 − 43.46 × 0.5 = −13.21 GB    (로그 −13.32 GB)
             mamba 캐시 = −13.21 × 0.5 / 146.81 MB = −46  (로그 −45)
```

mamba 상태 크기도 모델 설정에서 직접 계산해 로그와 대조했습니다.

```
linear-attention 48층 × (48헤드 × 128 × 128 × fp32 + conv 상태) = 146.81 MiB/요청   (로그 146.81 MB)
full-attention  16층 × K·V × 4헤드 × 256 × bf16                  = 64 KiB/토큰
```

말씀하신 해석이 맞았습니다. **34.94 GB 는 텍스트 모델만의 사용량이 아니었고**, `−13.32 GB` 는 물리적
부족량이 아니라 설정이 반영된 내부 계산값입니다. **값을 낮추면 더 나빠진다**는 지적도 맞습니다.

### 텍스트 서버가 먼저 혼자 올라갔다면

같은 `0.50` 으로도 캐시 예산이 양수입니다.

| `TEXT_MEM_FRACTION` | 캐시 예산 | mamba 동시 요청 | KV 토큰 | 이미지 서버에 남는 몫 |
| ---: | ---: | ---: | ---: | ---: |
| 0.50 | 2.16 GB | 8 | 17.7k | 21.73 GB |
| 0.55 | 4.33 GB | 15 | 35.5k | 19.56 GB |
| 0.60 | 6.51 GB | 23 | 53.3k | 17.38 GB |

**계산값이며 실측이 아닙니다.** "이미지 서버에 남는 몫"은 이미지 서버만 쓰는 게 아닙니다.
텍스트 서버의 CUDA 그래프와 요청 처리 중 활성화 메모리도 이 몫에서 나갑니다. 이미지 서버는
가중치 10.18 GiB 에 컨텍스트와 생성 중 활성화 메모리가 더해지고, 동시 기동 때 실제로 가져간
양은 15.4 GB 였습니다. 0.55 기준으로 두 서버의 부가 사용량을 빼면 여유는 수 GB 수준이라
**실측 없이 값을 확정할 수 없습니다.**

기존 설계 문서(`aws-deployment.md` 의 "가중치 19.6 GiB + KV 캐시 약 2.75 GiB") 의 숫자 자체는
위 0.50 행과 맞습니다. **텍스트 서버가 빈 GPU 에서 먼저 초기화된다는 전제**가 entrypoint 에서
지켜지지 않은 것이 문제였습니다.

### 실행 구성 — 모델·양자화·버전

모델과 버전은 **바뀌지 않았습니다.** 값은 받은 번들의 `config.json` 에서 직접 읽었습니다.

| 역할 | 모델 ID | revision | 양자화 | 가중치 |
| --- | --- | --- | --- | ---: |
| 텍스트·비전 | `cyankiwi/Qwen3.8-27B-AWQ-INT4` | `6e134bae811fb5adac50ee042ae5f029ac6779aa` | compressed-tensors `pack-quantized`, INT4 가중치 전용(W4A16), group 32, 비대칭. 일부 linear-attention 투영·비전 타워·MTP·`lm_head` 는 비양자화 | 19.57 GiB |
| 이미지 | `circulus/FLUX.2-klein-9B-bnb-4bit` | `58c2804f31af12c8888504b96250010c50b55e44` | bitsandbytes 4bit **NF4**, compute bf16 (transformer·text_encoder 모두) | 10.18 GiB |
| 누끼 | rembg BiRefNet-general (`birefnet-general.onnx`) | — | ONNX | 930 MB |

| 항목 | 값 |
| --- | --- |
| 추론 엔진 | `lmsysorg/sglang:v0.5.19` (텍스트 `sglang.launch_server`, 이미지 `sglang serve`) |
| 모델 번들 | `s3://jangin-prod-s3-models/page-generation/20260923/` (manifest `91f2cb79…`) — 변경 없음 |

기동 명령은 컨테이너에서 `DRY_RUN=1 detail-page-ai-entrypoint` 로 그대로 출력됩니다.
기존 대비 **인자 변경은 없고**, 바뀐 것은 기동 순서와 아래 두 환경변수뿐입니다.

| 환경변수 | 기본값 | 비고 |
| --- | --- | --- |
| `TEXT_READY_TIMEOUT` | `1800` | 신규. 텍스트 서버 준비 대기 한도(초) |
| `TEXT_MAX_RUNNING_REQUESTS` | 미설정 | 신규. 설정 시에만 `--max-running-requests` 전달 |
| `TEXT_MEM_FRACTION` | `0.50` | 변경 없음 |
| `TEXT_CONTEXT_LENGTH` | `8192` | 변경 없음 |

### 수정

`deploy/sglang/entrypoint.sh` 를 고쳤습니다.

- 텍스트 서버를 먼저 띄우고, `:30000/v1/models` 가 200 을 준 **뒤에** 이미지 서버를 띄웁니다
- FastAPI 는 지금처럼 즉시 뜹니다. `/health` 200, `/health/ready` 는 두 서버가 다 뜰 때까지 503 입니다
- 텍스트가 준비 전에 죽거나 `TEXT_READY_TIMEOUT`(기본 1800초) 을 넘기면 이미지를 띄우지 않고 컨테이너를 멈춥니다
- **텍스트 준비 직후, 이미지 준비 직후 각각 VRAM 을 한 줄씩 로그에 남깁니다.** 다음 Stage 기동부터
  "텍스트만 올라간 상태"와 "둘 다 올라간 상태"의 값이 파드 로그에 자동으로 남습니다
- `TEXT_MAX_RUNNING_REQUESTS` 를 설정하면 `--max-running-requests` 로 전달합니다 (요청 3번의 동시 처리 조정)
- `TEXT_MEM_FRACTION` 기본값 0.50 은 바꾸지 않았습니다. 실측 후 정합니다

**기동 시간이 늘어납니다.** 두 서버가 병렬이 아니라 텍스트(가중치만 252초 + CUDA 그래프) →
이미지 순서로 올라옵니다. 저희 스펙대로 `startupProbe` 를 `/health/ready` 에 걸어 두셨다면,
병렬 기동 기준으로 잡은 예산이 모자라 **준비 전에 kubelet 이 파드를 재시작할 수 있습니다.**
`failureThreshold × periodSeconds` 를 최소 30분 이상으로 봐 주십시오. 정확한 시간은 새 VRAM
로그의 시각으로 확인할 수 있습니다.

새 page-generation 이미지 digest 는 이 수정이 GenAI main 에 머지되어 Actions 가 발행한 뒤 확정됩니다. 확정되면 따로 전달드리겠습니다.

### 아직 남은 것 — L40S 시간이 필요합니다

요청 1·2·4번은 **L40S 에서 직접 돌려야** 답할 수 있습니다. 저희에게는 GPU 가 없습니다.

| 요청 | 방법 | 필요한 것 |
| --- | --- | --- |
| 1. 텍스트 단독 VRAM | `scripts/runtime/measure_vram.sh text <이미지>` | 검증용 GPU 파드 |
| 2. 이미지 단독 VRAM | `scripts/runtime/measure_vram.sh image <이미지>` | 검증용 GPU 파드 |
| 3. 설정 조정 | 1·2 결과로 `TEXT_MEM_FRACTION` 확정 | — |
| 4. 함께 실행 + 상세페이지 1건 | 수정된 이미지로 Stage 기동 후 생성 요청 1건 | 새 이미지 반영 |

측정 스크립트는 프로덕션 entrypoint 의 기동 명령을 그대로 재사용합니다. 파드 env 가 그대로
반영되므로 측정값이 실제 설정과 어긋나지 않습니다.

**4번은 1건이 아니라 2건 연속으로** 보고 싶습니다. 이미지 서버는 생성 후에도 PyTorch 캐시를
쥐고 있을 수 있어서, 두 번째 건의 텍스트 분석 단계에서 문제가 드러날 수 있습니다.

### 5번 — 함께 실행이 안 될 경우의 대안

계산상으로는 함께 실행이 가능합니다. 실측에서 여유가 부족하면 모델을 바꾸기 전에 아래 순서로 봅니다.

1. `TEXT_CONTEXT_LENGTH` · `TEXT_MAX_RUNNING_REQUESTS` 축소 — 캐시 필요량을 줄임
2. 이미지 서버의 텍스트 인코더 CPU 오프로드 (`--text-encoder-cpu-offload true`) — **5.66 GiB 확보**, 대신 이미지 생성이 느려짐
3. 순차 실행 — 텍스트와 이미지를 번갈아 올림. 로컬 Mac 에서 이미 이 방식으로 돌리고 있으나 건당 시간이 크게 늘어남

모델 변경은 위 셋으로도 안 될 때 제안하겠습니다. **이번 회신에서 모델 번들 변경은 없습니다.**

---

## 2. 챗봇 LLM — 챗봇 담당이 처리했습니다

`model_patch_size` 오류는 챗봇 담당이 **PR #37** 로 수정해 main(`73b8c53`)에 반영했습니다.

> SGLang 의 `HfModelConfigParser` 가 `gemma4_unified` 체크포인트를 공식
> `transformers.Gemma4UnifiedConfig` 대신 구버전 `Gemma4Config` 로 별칭 처리해서,
> `model_patch_size = patch_size(16) × pooling_kernel_size(3) = 48` 을 계산하는 로직이 빠진다.
> 상위 수정 PR: sgl-project/sglang#34420 (미병합)

속성값을 임의로 넣는 우회가 아니라 공식 설정 클래스를 쓰도록 바꾼 백포트입니다. 모델
`config.json` 에 `model_patch_size` 가 없고 `patch_size: 16` 이 있는 것은 저희도 받은 번들에서
따로 확인했습니다.

### 회신 항목 정리

| 항목 | 내용 | 상태 |
| --- | --- | --- |
| 원인 | SGLang v0.5.19 `HfModelConfigParser` 가 `gemma4_unified` 를 구버전 `Gemma4Config` 로 별칭 처리 → `model_patch_size`(= 16 × 3 = 48) 계산 누락 | 확인 |
| 수정 코드·버전 | `chat_bot/deploy/sglang/Dockerfile` 에 sgl-project/sglang#34420 백포트. `lmsysorg/sglang:v0.5.19`, transformers 5.12.1. 원본 코드가 바뀌면 빌드가 멈추도록 문자열 일치 검사 포함 | 확인 |
| PR / commit | GenAI **#37** — `5ff7536` (merge `73b8c53`) | 확인 |
| ECR digest | `750240012008.dkr.ecr.ap-northeast-2.amazonaws.com/jangin-ai/chatbot-llm:73b8c531b15704852552a4796639bd1e4214aa5b@sha256:89fb25b177f3cec37834a4d9cb15f39f72026321ad552161428eb230f416798d` | 발행 확인 |
| Actions | https://github.com/Jangingmall/GenAI/actions/runs/35853935433 (job `Publish chatbot-llm` 성공) | 확인 |
| 실행 명령 | `python3 -m sglang.launch_server --model-path "$MODEL_PATH" --revision "$MODEL_REVISION" --served-model-name "$SERVED_MODEL_NAME" --quantization awq --grammar-backend outlines --host 0.0.0.0 --port 30000` | 이미지 ENTRYPOINT 그대로 |
| 환경변수 | `MODEL_PATH`, `MODEL_REVISION`(`c4a82eea…`), `SERVED_MODEL_NAME` | — |
| served model name | 서버 `gemma4-12b-awq` / 챗봇 API 기본값 `gemma4:12b` — **불일치** (아래 2-3) | Stage 설정 확인 필요 |
| T4 답변 생성·최대 VRAM | — | **미검증** |
| 모델 파일 변경 | **없음.** PR #37 은 SGLang 코드 백포트뿐입니다 | — |

### `20260923-v2` 번들은 저희 파일과 내용이 같습니다

요청서의 `chatbot/embedding/20260923-v2/`, `chatbot/llm/20260923-v2/` 는 저희가 올린 것이
아니어서 대조했습니다. **파일 내용은 전부 같고, 한 단계 아래 디렉터리로 옮겨진 것만 다릅니다.**

| 번들 | 경로 차이 | 파일 내용 |
| --- | --- | --- |
| `chatbot/embedding/20260923-v2/` | 모든 파일이 `bge-m3/` 아래 | 29/29 동일 |
| `chatbot/llm/20260923-v2/` | 모든 파일이 `llm/` 아래 | 10/10 동일 |

경로가 바뀌어 `SHA256SUMS` 해시는 다르지만 모델은 그대로입니다. 챗봇 컨테이너의 마운트
경로(`EMBED_MODEL=/models/bge-m3`)에 맞춘 재배치로 보입니다.

참고로 **저희가 올린 `chatbot/embedding/20260923/`, `chatbot/llm/20260923/` 은 현재 버킷에
없습니다.** `page-generation/20260923/` 은 44개 객체 그대로 있습니다. 의도하신 정리라면 무시하셔도
됩니다. 다만 저희 9월 23일 회신 문서가 가리키는 챗봇 경로는 이제 존재하지 않습니다.

남은 것은 **새 digest 로 T4 실제 답변 생성 검증**입니다.

### 요청 2-3 — 모델 이름이 맞지 않습니다

T4 에서 LLM 서버가 떠도 **`/ai/ready` 는 계속 503 일 가능성이 높습니다.**

| 위치 | 값 |
| --- | --- |
| LLM 서버가 내보내는 이름 (`SERVED_MODEL_NAME`) | `gemma4-12b-awq` |
| 챗봇 API 기본값 (`chat_bot/app/config.py` `LLM_MODEL`) | `gemma4:12b` |

`app/readiness.py` 는 `LLM_MODEL` 이 `/v1/models` 목록에 있는지로 준비 여부를 판단합니다.
Stage 매니페스트에서 `LLM_MODEL=gemma4-12b-awq` 를 명시하고 있지 않다면 이름이 어긋납니다.
저희는 Stage 매니페스트를 볼 수 없어 **설정 여부는 확인하지 못했습니다.**

### 확인이 필요한 위험 — 관측된 것은 아닙니다

T4 는 compute capability 7.5 이고 bf16 을 지원하지 않습니다. 이번 오류를 넘기면 다음으로
AWQ 커널의 T4 지원 여부와 fp16 실행 시 Gemma 계열의 수치 안정성을 확인해야 할 수 있습니다.
**로그로 확인된 문제가 아니라** T4 검증 때 함께 봐 달라는 요청입니다.

---

## 3. 회신 양식

```
대상: 상세페이지
원인 및 수정 내용: 두 SGLang 서버 동시 기동으로 이미지 서버의 VRAM 사용이 텍스트 서버
                   캐시 예산에서 차감됨. 텍스트 서버 준비 후 이미지 서버를 기동하도록 수정
검증 환경·입력 조건: 미검증 (L40S 필요)
성공한 실행 명령·환경변수: 미검증
이미지 digest / Actions URL: GenAI main 머지 후 발행 — 확정 시 전달
모델 변경 여부 / 새 S3 경로 / manifest SHA-256: 변경 없음
최대 VRAM / 실제 생성 결과: 미측정
담당자 / 완료 예정일: 생성형 AI 팀 / L40S 검증 시간 확보 후 당일

대상: 챗봇 LLM
원인 및 수정 내용: SGLang v0.5.19 가 gemma4_unified 를 구버전 Gemma4Config 로 별칭 처리해
                   model_patch_size 계산이 빠짐. sgl-project/sglang#34420 백포트 (GenAI #37, 5ff7536)
검증 환경·입력 조건: 미검증 (T4 필요)
성공한 실행 명령·환경변수: 미검증. 기동 명령은 이미지 ENTRYPOINT 그대로.
                          챗봇 API 에 LLM_MODEL=gemma4-12b-awq 필요 가능성 (2-3 참고)
이미지 digest / Actions URL: jangin-ai/chatbot-llm@sha256:89fb25b177f3cec37834a4d9cb15f39f72026321ad552161428eb230f416798d
                            https://github.com/Jangingmall/GenAI/actions/runs/35853935433
모델 변경 여부 / 새 S3 경로 / manifest SHA-256: 변경 없음 (코드 백포트뿐)
최대 VRAM / 실제 생성 결과: 미측정
담당자 / 완료 예정일: 챗봇 담당 / T4 검증 시간 확보 후
```

## 4. 요청드리는 것

1. **새 page-generation 이미지 반영** — digest 는 위 양식에 적었습니다
2. **`startupProbe` 예산 확인** — 기동이 직렬이 되어 길어집니다 (1절 "수정" 참고)
3. **L40S 검증 시간** — 기존 상세페이지 파드를 잠시 내리고 검증용 파드를 붙여 주시면 요청 1·2 를 측정하겠습니다.
   측정 스크립트는 준비돼 있어 시간은 오래 걸리지 않습니다
4. **Stage 챗봇 API 의 `LLM_MODEL` 값 확인**
