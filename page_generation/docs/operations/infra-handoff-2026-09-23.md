# 인프라팀 요청 회신 — 2026-09-23 (모델 3종 S3 업로드)

- 수신: 「상세페이지 모델·챗봇 임베딩 모델·챗봇 LLM 모델을 `jangin-prod-s3-models` 새 버전 폴더에 업로드, SHA256SUMS 포함 및 업로드 후 검증, 경로와 해시 전달」
- 회신: 생성형 AI 팀 (상세페이지 생성)

## 요약

| 항목 | 상태 |
| --- | --- |
| 모델 3종 업로드 | **완료** — 버전 폴더 `20260923/` |
| SHA256SUMS 포함 | **완료** — 각 폴더 루트 |
| 업로드 후 검증 | **완료** — 전량 되받아 `shasum -c` 전수 대조 |
| 기존 버전 폴더 보존 | **해당 없음** — 작업 시작 시 버킷이 비어 있었습니다 |
| `s3:PutObject` 거부 | **해제 확인** — 9월 22일 보고했던 차단이 풀려 있었습니다 |

---

## 1. 경로와 SHA256SUMS 해시

```
s3://jangin-prod-s3-models/page-generation/20260923/
  SHA256SUMS : 91f2cb7959cfa0e76d80b9e60ec239fa397eb3bd023c04b27196a87fd8095661

s3://jangin-prod-s3-models/chatbot/embedding/20260923/
  SHA256SUMS : 214ad76e6d4afb5d55e38c9845094738c20e1f4932c6a691355f1f35b6afd59a

s3://jangin-prod-s3-models/chatbot/llm/20260923/
  SHA256SUMS : 42bd9300a8a4536ce15527976278c2bcd1365521807f4d5bb6dc177a91f10357
```

## 2. 각 폴더에 무엇이 들어 있는지

| 경로 | 모델 | 리비전 | 파일 | 크기 |
| --- | --- | --- | ---: | ---: |
| `page-generation/20260923/` | | | 41 | 31 GB |
| `  ├ text/` | `cyankiwi/Qwen3.8-27B-AWQ-INT4` | `6e134bae811fb5adac50ee042ae5f029ac6779aa` | 17 | 20 GB |
| `  ├ image/` | `circulus/FLUX.2-klein-9B-bnb-4bit` | `58c2804f31af12c8888504b96250010c50b55e44` | 23 | 10 GB |
| `  └ u2net/birefnet-general.onnx` | rembg BiRefNet-general | — | 1 | 930 MB |
| `chatbot/embedding/20260923/` | `BAAI/bge-m3` | — | 29 | 4.3 GB |
| `chatbot/llm/20260923/` | `mattbucci/gemma-4-12B-AWQ` | `c4a82eea03b40ecaeb4ef265b3fd27461c8a87ed` | 10 | 7.3 GB |

### 마운트하실 때 주의할 점 두 가지

**상세페이지 모델은 한 버전 폴더 아래 3개가 들어 있습니다.** 컨테이너가
`TEXT_MODEL_PATH`·`IMAGE_MODEL_PATH`·rembg 경로를 **각각 따로** 보기 때문입니다.
`page-generation/20260923/` 를 통째로 받으신 뒤 아래처럼 연결해 주십시오.

| 컨테이너가 보는 경로 | S3 하위 경로 |
| --- | --- |
| `TEXT_MODEL_PATH` | `text/` |
| `IMAGE_MODEL_PATH` | `image/` |
| `models/u2net/birefnet-general.onnx` | `u2net/birefnet-general.onnx` |

**rembg 파일명은 바꿔서 올렸습니다.** 원본 릴리스 자산명은
`BiRefNet-general-epoch_244.onnx` 이지만 rembg 가 `birefnet-general.onnx` 라는
이름으로 찾습니다. S3 에는 **이미 바뀐 이름**으로 올렸으니 그대로 두시면 됩니다.

## 3. 검증을 어떻게 했는지

업로드한 것을 **전부 S3 에서 다시 내려받아** 로컬 체크섬과 대조했습니다.

```
page-generation    41개 전부 일치
chatbot/embedding  29개 전부 일치
chatbot/llm        10개 전부 일치
```

매니페스트와 S3 객체 목록도 따로 대조했습니다. **매니페스트에 있는데 S3 에 없는
파일 0건.** S3 에만 있는 것은 `SHA256SUMS` 자신과 `.gitattributes`(Hugging Face
저장소 메타파일)뿐이며 의도한 대로입니다.

`SHA256SUMS` 는 각 폴더 루트에 있고 경로는 그 폴더 기준 상대 경로입니다.
받으신 뒤 해당 폴더에서 `shasum -a 256 -c SHA256SUMS` 로 그대로 확인하실 수 있습니다.

## 4. 덮어쓰기·삭제 여부

**아무것도 덮어쓰거나 지우지 않았습니다.**

- 작업 시작 시점에 `jangin-prod-s3-models` 는 **비어 있었습니다**. 기존 버전 폴더가
  없었으므로 충돌 대상 자체가 없었습니다
- `aws s3 sync` 를 `--delete` 없이 사용했고, 쓰기 대상은 `20260923/` 접두사 아래로
  한정했습니다
- 작업 후 확인 결과 버킷에 `20260923/` 외의 객체는 없습니다

## 5. `s3:PutObject` 는 풀려 있었습니다

9월 22일 회신에서 `AI-Dev` 역할에 `s3:PutObject` 가 **명시적으로 거부**돼 있다고
보고드렸습니다. 이번에 작은 파일로 먼저 확인해 보니 **해제돼 있었습니다.** 그래서
별도 요청 없이 그대로 진행했습니다.

확인에 쓴 프로브 파일(`page-generation/.permcheck-20260923.txt`)은 확인 직후
삭제했습니다.

## 6. FLUX 라이선스

`circulus/FLUX.2-klein-9B-bnb-4bit` 의 라이선스는 9월 22일 회신에서 미확인으로
올렸던 항목입니다. 원본 `black-forest-labs/FLUX.2-klein-9B` 가 Non-Commercial
License 이기 때문입니다.

**저희 쪽 관리자가 확인했다는 판단을 받아 업로드했습니다.** 저희가 직접 라이선스
원문을 대조해 확인한 것은 아니므로, 상용 배포 전 법무 확인이 필요하다고 보시면
그쪽 절차를 따라 주십시오.

## 7. 아직 저희 쪽에서 확인 못 한 것

- **GPU 실행 검증**: 여전히 **한 번도 못 했습니다.** GPU 가 준비되면 함께
  진행하겠습니다. 이번 업로드는 파일 준비까지이며 GPU 에서 모델이 뜨는지는
  확인되지 않았습니다
- **누끼 GPU 전환**: `onnxruntime-gpu` 로 바꿨으나 CUDA 실행 확인 못 했습니다

Stage Kubernetes 연결 중 파일이 맞지 않거나 로드가 실패하면 알려 주십시오.
해시를 다시 대조해 드리겠습니다.
