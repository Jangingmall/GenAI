# 인프라팀 요청 회신 — 2026-09-22 (CodeBuild·모델·GPU)

- 수신: 「CodeBuild 연결, 이미지 3개 발행, 모델 파일 준비 및 GPU 검증 요청」 (기준 main `e7ce781`)
- 회신: 생성형 AI 팀 (상세페이지 생성)

## 요약

| 항목 | 상태 |
| --- | --- |
| 1. workflow 변경 (CodeBuild·ECR 이름·실패 처리) | **완료** — PR #32 머지. CodeBuild 디스크 해소 확인. **ECR push 는 IAM 리소스 목록 때문에 2/3 실패** |
| 2. 로컬 모델 검사 수정 | **완료** — 지적이 맞았습니다. 기존 코드면 파드가 못 떴습니다 |
| 3. 모델 S3 업로드 | **막힘** — `AI-Dev` 에 `s3:PutObject` 가 **명시적으로 거부**돼 있습니다 |
| 4. GPU 공동 검증 | **대기** — GPU 가 준비되면 진행 |

---

## 1. CodeBuild 연결 및 이미지 발행

### 적용한 것

`runs-on` 을 주신 값 그대로 `docker-validate`(102행)와 `publish`(170행)에 넣었습니다.
`test` job(26행)은 기존 GitHub 러너를 유지했습니다.

```yaml
runs-on: ${{ matrix.service == 'chatbot-api' && 'ubuntu-24.04' || format('codebuild-jangin-genai-runner-{0}-{1}', github.run_id, github.run_attempt) }}
```

ECR 저장소 이름을 바꿨습니다.

| 서비스 | 이전 | **변경 후** |
| --- | --- | --- |
| 상세페이지 | `jangin-ai/sglang` | **`jangin-ai/page-generation`** |
| 챗봇 API | `jangin-ai/ollama` | **`jangin-ai/chatbot-api`** |
| 챗봇 LLM | `jangin-ai/chatbot-llm` | 그대로 |

용량 부족 시 **건너뛰고 성공하던 처리를 제거**하고 실패로 바꿨습니다. `docker-validate`
의 `full_build=false` 분기와 그에 딸린 조건부 스킵을 없앴고, 두 job 모두
`::error::` + `exit 1` 로 끝납니다.

요청하신 대로 **유지한 것**: OIDC `role-to-assume`, 커밋 SHA 태그·`latest` 금지,
`linux/amd64`, digest 출력, SHA 충돌 시 기존 이미지 재사용.

YAML 파싱과 세 job 구성(`test`·`docker-validate`·`publish`)을 확인했습니다.

### 실행 결과 — CodeBuild 는 해결, IAM 정책 하나가 남았습니다

PR #32 을 머지하고 main 에서 새로 실행했습니다.

**PR 실행** (run `35709810293`) — 전부 성공

| 잡 | 결과 | 소요 |
| --- | --- | ---: |
| Docker validation **page-generation** | **성공** | 7분 10초 |
| Docker validation chatbot-llm | 성공 | 31초 |
| Docker validation chatbot-api | 성공 | — |
| Test ×2 | 성공 | — |

실제로 CodeBuild 에서 돌았습니다. 로그 경로가
`/codebuild/output/src.../actions-runner/_work/GenAI/GenAI` 이고 디스크가
`Max Used Space 93.13GiB` · `Min Free Space 59.6GiB` 입니다.
**지난번 `requires at least 35 GiB free, but the runner has 14 GiB` 로 막히던
잡이 통과했습니다.** 용량 부족 시 실패 처리도 함께 들어가 있으므로 건너뛴 것이
아닙니다.

**main 실행** (run `35710985870`) — 3개 중 1개 성공

| 이미지 | 결과 | 원인 |
| --- | --- | --- |
| `jangin-ai/chatbot-llm` | **성공** | 이름이 바뀌지 않아 정책에 이미 있음 |
| `jangin-ai/page-generation` | 실패 | IAM 정책에 새 이름 미반영 |
| `jangin-ai/chatbot-api` | 실패 | 〃 |

```
AccessDeniedException: User: arn:aws:sts::750240012008:assumed-role/
jangin-gha-genai-ci/GitHubActions is not authorized to perform:
ecr:DescribeImages on resource:
arn:aws:ecr:ap-northeast-2:750240012008:repository/jangin-ai/page-generation
because no identity-based policy allows the ecr:DescribeImages action
```

**OIDC 신뢰 정책은 해결됐습니다.** AssumeRole 이 통과해 역할을 실제로 맡았고,
`chatbot-llm` 은 push 까지 성공했습니다. 남은 것은 **그 역할의 권한 정책에 새
저장소 ARN 이 없는 것**뿐입니다. ECR 저장소 3개는 모두 생성돼 있는 것을
확인했습니다.

**요청드립니다**: `jangin-gha-genai-ci` 역할 정책의 리소스에 새 이름을 추가해
주세요. 저희 쪽에서 더 할 일은 없습니다.

```
arn:aws:ecr:ap-northeast-2:750240012008:repository/jangin-ai/page-generation
arn:aws:ecr:ap-northeast-2:750240012008:repository/jangin-ai/chatbot-api
```

(옛 이름 `jangin-ai/sglang` · `jangin-ai/ollama` 는 더 이상 쓰지 않습니다.)

반영해 주시면 main 을 재실행해 push 성공을 확인하고 Actions URL 을 전달드리겠습니다.

---

## 2. 상세페이지 로컬 모델 검사 수정 — **지적이 정확했습니다**

`deploy/sglang/entrypoint.sh` 가 텍스트·이미지 **두 모델 모두 `config.json`** 을
요구하고 있었습니다.

배포 대상 확산 모델의 실제 파일 목록을 확인했습니다.

```
circulus/FLUX.2-klein-9B-bnb-4bit  루트 파일
  .gitattributes, klein.py, klein2.py, klein3.py, ltx.py,
  model_index.json, suji.jpg

config.json : 없음
```

**즉 기존 코드였으면 정상 모델을 불완전하다고 판정해 파드가 기동하지 못했습니다.**
S3 동기화가 끝나도 `ERROR ... config.json 이 없습니다` 로 종료됐을 것입니다.

형식에 맞는 표지로 나눠 검사하도록 고쳤습니다. **빈 `config.json` 으로 우회하지
않았습니다.**

| 모델 | 규약 | 검사 파일 |
| --- | --- | --- |
| 텍스트·비전 | transformers | `config.json` |
| 이미지 확산 | diffusers | **`model_index.json`** |

`DRY_RUN=1` 로 확인했습니다.

```
정상 구조        → TEXT/IMAGE 두 명령이 정상 조립됨
model_index 누락 → ERROR: IMAGE_MODEL_PATH=... 는 디렉터리지만 model_index.json 이 없습니다.
```

회귀 테스트를 추가했습니다. 확산 모델에 `config.json` 만 있고 `model_index.json`
이 없으면 차단되는지 확인합니다 — 우려하신 우회를 막는 지점입니다.

**커밋**: `97c5f41`(수정) · `2bca808`(테스트). 전체 테스트 419개 통과.

---

## 3. 모델 파일 준비·S3 업로드 — **권한이 막혀 있습니다**

### 먼저 막힌 것

`jangin-prod-s3-models` 에 **읽기는 되지만 쓰기가 명시적으로 거부**됩니다.

```
User: arn:aws:sts::750240012008:assumed-role/AWSReservedSSO_AI-Dev_.../sigheartjm
is not authorized to perform: s3:PutObject on resource:
"arn:aws:s3:::jangin-prod-s3-models/..."
with an explicit deny in an identity-based policy
```

`s3:DeleteObject` 도 같습니다. 버킷은 현재 비어 있습니다.

**요청드립니다**: `AI-Dev` 역할에 아래 경로의 `s3:PutObject`·`s3:AbortMultipartUpload`
를 허용해 주시거나, 인프라팀이 대신 올려 주실 경우 알려 주세요.

```
s3://jangin-prod-s3-models/text/
s3://jangin-prod-s3-models/image/
s3://jangin-prod-s3-models/u2net/
```

약 33 GB 업로드라 멀티파트가 필요합니다.

### 상세페이지 모델 3종 정보

권한이 열리는 대로 업로드하고 체크섬을 전달드리겠습니다. 현재 확인된 값입니다.

#### ① 텍스트·비전

```
모델 용도: 상품 이미지 분석 · 한국어 카피 생성 (SGLang 텍스트 서버 :30000)
모델 ID / revision: cyankiwi/Qwen3.8-27B-AWQ-INT4
                    6e134bae811fb5adac50ee042ae5f029ac6779aa
S3 경로: s3://jangin-prod-s3-models/text/   (최종 경로는 네이티브와 맞춤)
전체 크기: 21.04 GB (21,041,255,875 bytes, 18개 파일)
SHA256SUMS 위치 / 해당 파일 SHA-256: 업로드 시 생성 예정
업로드 완료 여부: 미완료 — 권한 대기
추가 실행 옵션·환경변수: TEXT_MODEL_PATH, --mem-fraction-static 0.50,
                       --context-length 8192, --trust-remote-code
미완료 항목의 담당자 / 준비 예정일: 생성형 AI 팀 / 권한 부여 후 1일
```

라이선스: Apache 2.0 (모델 카드 기재).

#### ② 이미지 확산

```
모델 용도: 배경·활용 장면·디테일 연출 컷 생성 (SGLang 확산 서버 :30001)
모델 ID / revision: circulus/FLUX.2-klein-9B-bnb-4bit
                    58c2804f31af12c8888504b96250010c50b55e44
S3 경로: s3://jangin-prod-s3-models/image/
전체 크기: 10.94 GB (10,941,657,400 bytes, 24개 파일)
SHA256SUMS 위치 / 해당 파일 SHA-256: 업로드 시 생성 예정
업로드 완료 여부: 미완료 — 권한 대기
추가 실행 옵션·환경변수: IMAGE_MODEL_PATH, --num-gpus 1,
                       --dit-cpu-offload false, --text-encoder-cpu-offload false
미완료 항목의 담당자 / 준비 예정일: 생성형 AI 팀 / 권한 부여 후 1일
```

> **라이선스 확인 필요**: 원본 `black-forest-labs/FLUX.2-klein-9B` 는
> Non-Commercial License 입니다. 채택한 양자화본의 라이선스 표기를 확인하지
> 못했습니다. **상업 운영 허용 범위를 법무·제품 쪽에서 확인해 주셔야 합니다.**
> 저희가 임의로 판단할 사안이 아니라고 봅니다.

#### ③ 배경 제거(누끼)

```
모델 용도: 판매 사진 배경 제거 (rembg BiRefNet-general)
모델 ID / revision: danielgatis/rembg 릴리스 v0.0.0 의
                    BiRefNet-general-epoch_244.onnx
S3 경로: s3://jangin-prod-s3-models/u2net/birefnet-general.onnx
전체 크기: 973 MB (실측)
SHA256SUMS 위치 / 해당 파일 SHA-256: 업로드 시 생성 예정
업로드 완료 여부: 미완료 — 권한 대기
추가 실행 옵션·환경변수: U2NET_HOME (이미지 기본값
                       /var/lib/detail-page-ai/models/u2net)
미완료 항목의 담당자 / 준비 예정일: 생성형 AI 팀 / 권한 부여 후 1일
```

> **파일명 주의**: 릴리스 자산명(`BiRefNet-general-epoch_244.onnx`)이 아니라
> **`birefnet-general.onnx`** 로 두셔야 합니다. rembg 가 그 이름으로 찾습니다.
> 없으면 첫 렌더 요청에서 컨테이너가 `github.com` 으로 973 MB 를 직접 받습니다
> (사내 실측 약 17초). 라이선스는 확인하지 못했습니다.

### 챗봇 모델 2종

`bge-m3/` 와 챗봇 LLM 은 **챗봇 팀 소관**입니다. 저희가 모델 ID·revision 을
정할 수 없어 답하지 않습니다. 위 양식을 그대로 쓰시면 됩니다.

---

## 4. 배포 후 GPU 공동 검증 — **검증 대기**

말씀대로 CodeBuild 성공은 GPU 실행 검증이 아닙니다. 저희도 같은 입장입니다.

**저희가 지금까지 GPU 에서 확인한 것은 없습니다.** `deploy/sglang/Dockerfile` 은
Mac ARM64 에서 `linux/amd64` 에뮬레이션으로 **빌드만** 성공했고(16.97 GB),
컨테이너 내부 import·`DRY_RUN`·`/health` smoke test 까지입니다.

첫 배포에서 함께 확인할 항목입니다.

| 항목 | 현재 상태 |
| --- | --- |
| L40S 텍스트·이미지 동시 로딩 | **미검증**. 계산상 약 32.6 GiB / 가용 44.7 GiB |
| 상세페이지 생성 성공 | 로컬(Apple Silicon)에서는 60건 전수 성공. GPU 미검증 |
| peak VRAM | **미검증**. 계산값뿐 |
| **두 SGLang 프로세스의 호스트 RAM 합산** | **미측정**. Memory request 24Gi 산정의 최대 불확실 요소 |
| 시작 시간 | **미측정**. `startupProbe` `failureThreshold` 산정에 필요 |
| 누끼 GPU 전환 | **미검증**. `onnxruntime-gpu` 로 바꿨으나 CUDA 실행 확인 못 함 |

**로그 한 줄로 확인하실 수 있는 것**: 누끼가 실제로 GPU 를 탔는지는 컨테이너
로그에서 바로 보입니다.

```
rembg ONNX Runtime providers: available=[...] selected=[...]
```

`selected` 에 `CUDAExecutionProvider` 가 있으면 GPU 입니다. 없으면 CPU 로
떨어진 것이고, 그 경우 프로세스가 약 12.9 GiB 를 상시 점유합니다(사내 실측).

### 참고 — CPU 로 떨어지면 생기는 일

2026-09-18 사내 서버(8코어, GPU 없음) 실측입니다.

| 단계 | 시간 | 누적 피크 RSS |
| --- | ---: | ---: |
| 세션 로드 | 21.3초 | 2.18 GiB |
| 누끼 1회차 | 22.5초 | 9.22 GiB |
| 2회차 | 33.3초 | **12.90 GiB** |

`g6e.xlarge` 는 4 vCPU 이므로 CPU 경로면 누끼 1장에 50~60초가 걸릴 것으로
보입니다. GPU 전환이 실제로 되는지가 성능에 직결됩니다.

---

## 회신 부탁드릴 것

1. **`AI-Dev` 에 모델 버킷 쓰기 권한** (또는 인프라팀 대행 여부)
2. **FLUX 양자화본의 상업 이용 허용 범위** — 법무·제품 확인
3. 모델 최종 경로 규약 (`text/`·`image/`·`u2net/` 로 맞으면 그대로 진행)
4. GPU 준비 시점

workflow PR 은 준비되는 대로 올리고 Actions URL 을 별도로 전달드리겠습니다.
