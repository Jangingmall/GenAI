# 인프라팀 요청 회신 — 2026-09-21

- 수신: 「GitHub Actions 변수 등록」 · 「챗봇 LLM 실행 확인 요청」
- 회신: 생성형 AI 팀 (상세페이지 생성)

<details>
<summary>받은 요청 원문</summary>

### GitHub Actions 변수 등록

저장소 Settings → Secrets and variables → Actions → Variables에 등록 부탁드립니다.

- AWS_REGION: ap-northeast-2
- AWS_ROLE_ARN: arn:aws:iam::750240012008:role/jangin-gha-genai-ci

ECR URI:

상세페이지:
`750240012008.dkr.ecr.ap-northeast-2.amazonaws.com/jangin-ai/sglang`

챗봇 API:
`750240012008.dkr.ecr.ap-northeast-2.amazonaws.com/jangin-ai/ollama`

챗봇 LLM:
`750240012008.dkr.ecr.ap-northeast-2.amazonaws.com/jangin-ai/chatbot-llm`

ECR 저장소 3개 생성 및 최신 main의 chatbot-llm Dockerfile·CI 항목 추가를 확인했습니다.

변수 등록 후 main 기준 이미지 3개의 ECR push 성공 여부 확인 부탁드립니다.

### 챗봇 LLM 실행 확인 요청

추가된 구성을 다음과 같이 확인했습니다.

- 서버: SGLang v0.5.19
- 모델: mattbucci/gemma-4-12B-AWQ
- 포트: 30000
- served model name: gemma4-12b-awq

네이티브에서는 T4의 같은 Pod 안에 API와 LLM을 별도 컨테이너로 연결합니다.
GPU 1개는 LLM 컨테이너에만 할당합니다.

API 연결 설정:
- LLM_BACKEND=sglang
- SGLANG_HOST=http://127.0.0.1:30000
- LLM_MODEL=gemma4-12b-awq

다음 사항 확인 부탁드립니다.

1. 모델 카드에 명시된 SGLang 추가 패치가 v0.5.19에 포함되어 있는지
   - 미포함이라면 필요한 이미지 수정 또는 호환 모델 선정
2. 사용할 모델의 고정 revision(commit SHA)
   - 현재 Dockerfile 기본값은 main입니다.
3. 모델 다운로드에 별도 인증이 필요한지

현재 Dockerfile은 모델을 이미지에 포함하지 않습니다.
기존 S3 → 모델 볼륨 방식에 맞춰 네이티브에서 MODEL_PATH를 연결할 예정입니다.
모델 revision 확정 후 해당 버전의 모델 파일을 준비해야 합니다.

</details>

## 요약

| 요청 | 상태 |
| --- | --- |
| Actions 변수 2개 등록 | **완료** |
| main 기준 이미지 3개 ECR push 확인 | **확인했고, 3개 모두 실패합니다.** 원인이 둘 다 인프라팀 쪽입니다 |
| 챗봇 LLM 관련 3개 질문 | **챗봇 팀 소관**입니다. 저희가 답할 수 없는 부분을 아래에 구분해 두었습니다 |

---

## 1. Actions 변수 — 등록 완료

`Jangingmall/GenAI` → Settings → Secrets and variables → Actions → Variables 에
등록했습니다.

```
AWS_REGION    = ap-northeast-2
AWS_ROLE_ARN  = arn:aws:iam::750240012008:role/jangin-gha-genai-ci
```

등록 후 main 최신 커밋(`Merge pull request #28`)의 워크플로를 재실행해
확인했습니다. 변수 미설정 오류(`Actions variable AWS_ROLE_ARN is not set by Infra`)는
사라졌습니다.

---

## 2. ECR push 결과 — **3개 모두 실패했습니다**

재실행한 run: `35551187612` (main, GenAI CI/CD)

| 이미지 | ECR 저장소 | 결과 | 막힌 지점 |
| --- | --- | --- | --- |
| 상세페이지 | `jangin-ai/sglang` | **실패** | 러너 디스크 |
| 챗봇 API | `jangin-ai/ollama` | **실패** | OIDC 역할 신뢰 정책 |
| 챗봇 LLM | `jangin-ai/chatbot-llm` | **실패** | 러너 디스크 |

테스트 잡(`Test page-generation`, `Test chatbot-api`)은 **성공**했습니다. 막힌 것은
빌드·푸시 단계뿐입니다.

### 2-1. 러너 디스크가 모자랍니다 — 상세페이지·챗봇 LLM

```
##[error]page-generation requires at least 35 GiB free, but the runner has 14 GiB.
##[error]chatbot-llm requires at least 35 GiB free, but the runner has 14 GiB.
```

**GitHub-hosted 표준 러너(`ubuntu-24.04`)의 여유 디스크는 14 GiB 입니다.** 저희
상세페이지 이미지는 2026-09-18 빌드 실측 기준 **16.97 GB(15.81 GiB)** 이고, 빌드
중간 레이어와 캐시까지 합치면 35 GiB 가 필요합니다.

워크플로는 ECR 인증 **전에** 이 조건을 검사하고 멈추도록 되어 있어, 자격 증명을
쓰지 않고 명확한 메시지를 남깁니다. 즉 **설정 실수가 아니라 러너 용량 문제**입니다.

> 2026-09-17 ECR 구성 검토 회신에서 "이미지가 커서 표준 러너에서 빌드가 실패할 수
> 있습니다" 라고 말씀드린 항목이 실제로 확인된 것입니다. 당시에는 18~22 GB 추정이었고,
> 지금은 16.97 GB 실측입니다.

**정해 주셔야 할 것**: 아래 중 무엇으로 갈지 알려 주시면 저희가 워크플로의
`runs-on` 을 맞추겠습니다.

| 방안 | 비고 |
| --- | --- |
| GitHub 큰 러너(Larger runner) | 가장 간단합니다. 디스크 여유가 큰 사양을 골라 주세요 |
| 자체 호스팅 러너 | 사내 서버를 쓰면 디스크·네트워크가 자유롭습니다 |
| AWS CodeBuild | ECR 과 같은 계정 안에서 빌드해 push 시간이 짧습니다 |

챗봇 LLM 이미지도 같은 35 GiB 기준에 걸립니다. 그쪽은 챗봇 팀 이미지이지만
러너 선택은 저장소 공통이라 함께 정해야 합니다.

### 2-2. OIDC 역할이 이 저장소를 신뢰하지 않습니다 — 챗봇 API

```
##[error]Could not assume role with OIDC:
Not authorized to perform sts:AssumeRoleWithWebIdentity
```

워크플로가 보낸 값은 다음과 같습니다.

```
role-to-assume : arn:aws:iam::750240012008:role/jangin-gha-genai-ci
aws-region     : ap-northeast-2
audience       : sts.amazonaws.com
```

챗봇 API 는 디스크 조건(10 GiB)을 통과해 **실제로 AssumeRole 까지 갔고, 거기서
거부됐습니다.** 변수는 정상이므로 **역할의 신뢰 정책(Trust policy) 쪽을 봐 주셔야
합니다.**

확인 부탁드릴 항목입니다.

- 신뢰 정책의 `Principal` 에 이 계정의 GitHub OIDC 공급자
  (`token.actions.githubusercontent.com`)가 있는지
- `Condition` 의 `token.actions.githubusercontent.com:sub` 가
  `repo:Jangingmall/GenAI:*` 를 허용하는지 — 브랜치를 `ref:refs/heads/main` 으로
  좁혀 두셨다면 main push 는 통과해야 하는데 거부된 것이라, 저장소 이름이나
  조직 이름이 어긋났을 가능성이 있습니다
- `token.actions.githubusercontent.com:aud` 가 `sts.amazonaws.com` 인지

**이것이 풀리면 챗봇 API 이미지는 바로 push 될 것으로 보입니다.** 나머지 둘은
2-1 의 러너 문제가 함께 풀려야 합니다.

---

## 3. ECR 저장소 이름에 대해 (재확인만, 진행에는 지장 없음)

`jangin-ai/sglang` 으로 생성하신 것 확인했습니다. 2026-09-17 회신에서 **엔진 이름
대신 용도로** 지어 주시길 권했던 항목입니다.

```
jangin-ai/sglang      →  jangin-ai/page-generation  (권했던 이름)
jangin-ai/ollama      →  jangin-ai/chatbot          (권했던 이름)
```

이미 `jangin-ai/chatbot-llm` 이 생기면서 **`ollama` 저장소에는 Ollama 가 아니라
챗봇 API 가 들어가고, 실제 LLM 은 `chatbot-llm` 에 들어가는** 상태가 됐습니다.
이름과 내용이 어긋난 것이 하나 늘었습니다.

**지금 바꾸실 필요는 없습니다.** 다만 IMMUTABLE 태그 정책상 나중에 옮기기 어려우니,
초기인 지금이 바꾸기 가장 쉬운 시점이라는 점만 말씀드립니다.

---

## 4. 챗봇 LLM 질문 — 챗봇 팀 소관입니다

「챗봇 LLM 실행 확인 요청」의 세 질문은 **저희 팀 범위가 아닙니다.** 저희는
상세페이지 생성만 맡고 있고, `mattbucci/gemma-4-12B-AWQ` 모델과 `chat_bot/` 의
구성은 챗봇 팀이 결정합니다. 저희가 추측으로 답하면 틀린 정보가 갑니다.

| 질문 | 답할 수 있는 팀 |
| --- | --- |
| 1. 모델 카드의 SGLang 추가 패치가 v0.5.19 에 포함되는지 | 챗봇 팀 |
| 2. 모델 고정 revision(commit SHA) | 챗봇 팀 |
| 3. 모델 다운로드에 인증이 필요한지 | 챗봇 팀 |

**저희가 말씀드릴 수 있는 것 하나**는 SGLang 버전이 같다는 점입니다. 저희
상세페이지도 `lmsysorg/sglang:v0.5.19` 를 베이스로 씁니다. 다만 저희는 텍스트에
`Qwen3.8-27B-AWQ-INT4`, 이미지에 `FLUX.2-klein-9B` 를 쓰므로, **`gemma-4` 계열이
v0.5.19 에서 동작하는지는 저희가 확인한 바가 없습니다.**

참고로 저희 쪽 모델 고정 방식은 이렇습니다. 챗봇 팀이 같은 형식으로 답하시면
인프라팀이 S3 에 올리실 때 그대로 쓰실 수 있습니다.

| 용도 | 저장소 | 고정 커밋 |
| --- | --- | --- |
| 텍스트·비전 | `cyankiwi/Qwen3.8-27B-AWQ-INT4` | `6e134bae811fb5adac50ee042ae5f029ac6779aa` |
| 이미지 확산 | `circulus/FLUX.2-klein-9B-bnb-4bit` | `58c2804f31af12c8888504b96250010c50b55e44` |

---

## 5. 저희 쪽 모델 동기화 목록이 하나 늘었습니다

지난 회신 이후 **누끼(rembg) 모델**을 S3 동기화 대상에 추가해 주시길 요청드렸습니다.
[`eks-workload-spec.md`](eks-workload-spec.md) 의 「인프라팀 동기화 대상」 표에
반영해 두었습니다.

| 용도 | 파일 | 크기 | PVC 배치 경로 |
| --- | --- | ---: | --- |
| 누끼 | `BiRefNet-general-epoch_244.onnx` | 973 MB | `models/u2net/birefnet-general.onnx` |

**파일명을 `birefnet-general.onnx` 로 바꿔서** 두셔야 합니다. rembg 가 그 이름으로
찾습니다. 넣지 않으시면 첫 렌더 요청에서 컨테이너가 `github.com` 으로 973 MB 를
직접 내려받습니다(사내 서버 실측 약 17초). 2026-09-18 컨테이너 연동 테스트에서
실제로 관측한 동작입니다.

---

## 6. 자원 요청값을 실측 기반으로 고쳤습니다

[`eks-workload-spec.md`](eks-workload-spec.md) 1-4 절을 갱신했습니다.

| 항목 | 이전 | **변경** | 사유 |
| --- | --- | --- | --- |
| Memory request | 16Gi | **24Gi** | 누끼 프로세스가 12.90 GiB 를 상시 점유(실측) |
| CPU limit | 6 | **4** | `g6e.xlarge` 가 4 vCPU 라 6 은 도달 불가 |

누끼 모델을 GPU 에서 돌리도록 `deploy/sglang/Dockerfile` 에서 `onnxruntime` 을
`onnxruntime-gpu` 로 바꿨습니다. **다만 저희에게 GPU 가 없어 실제 CUDA 실행은
확인하지 못했습니다.** 첫 AWS 배포에서 컨테이너 로그의
`rembg ONNX Runtime providers: available=... selected=...` 한 줄로 CUDA 를 탔는지
확인하실 수 있습니다.
