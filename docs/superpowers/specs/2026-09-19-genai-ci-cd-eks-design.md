# GenAI CI/CD·EKS 인계 설계

## 목표

`Jangingmall/GenAI` main(`535f1ac`)을 기준으로 상세페이지 통합 GPU 이미지와 챗봇 API 이미지를 서비스별로 테스트·빌드하고, main merge 때만 GitHub OIDC로 ECR에 커밋 SHA 태그를 발행한다. 챗봇 API에는 Native가 Kubernetes readiness probe로 사용할 의존성 준비 상태와 파일 기반 DB 비밀번호 주입을 추가한다.

## 기준과 범위

- 상세페이지 이미지: `page_generation/deploy/sglang/Dockerfile`, context `page_generation`, ECR `jangin-ai/sglang`.
- 챗봇 이미지: `chat_bot/Dockerfile`, context `chat_bot`, ECR `jangin-ai/ollama`.
- 모든 Docker 빌드 플랫폼: `linux/amd64`.
- AWS 리전 기본값: `ap-northeast-2`; role ARN은 `vars.AWS_ROLE_ARN`으로 받는다.
- `latest` 태그는 사용하지 않는다. 이미지 태그는 `${GITHUB_SHA}` 하나만 사용한다.
- 상세페이지의 `page_generation/deploy/Dockerfile`은 EC2 Compose용이므로 CI 발행 대상에서 제외하고 파일은 유지한다.
- 별도 LLM 이미지는 이번 범위에 추가하지 않는다. 챗봇 API 이미지는 `jangin-ai/ollama`에 저장하지만 LLM 서버는 Native 계약 수령 후 별도 이미지로 배치한다.

## CI 설계

`.github/workflows/genai-ci.yml` 하나에서 두 서비스 matrix를 관리한다.

1. `pull_request`가 `main`을 대상으로 열리거나 갱신되면 서비스별 테스트를 실행한다.
2. PR에서는 서비스별 Docker context/Dockerfile을 정확히 지정해 `linux/amd64` 전체 build를 push 없이 수행한다. 현재 확인된 상세페이지 이미지가 15.47GiB이고 BuildKit 작업층까지 필요하므로, 표준 runner는 먼저 35GiB 여유 공간을 검사하고 부족하면 요구량을 Summary와 오류로 남긴다.
3. `push`가 `main`에서 발생하면 테스트 성공 후 OIDC 인증, ECR 로그인, 서비스별 `linux/amd64` build/push를 수행한다.
4. ECR tag가 이미 존재하면 `describe-images`로 기존 digest를 읽고 push를 건너뛴다. immutable tag를 덮어쓰거나 삭제하지 않는다.
5. 새 push 또는 기존 tag 재사용 모두 Actions Summary에 서비스명, `image@digest`, source SHA, 실행 URL, 테스트 결과를 기록한다.
6. 상세페이지 image build는 최소 여유 디스크를 사전 검사하고 부족하면 실제 요구량과 runner 상태를 Summary에 남긴 뒤 명확히 실패한다. 표준 `ubuntu-24.04` runner가 부족하면 Native/Infra에 larger runner 또는 self-hosted runner가 필요하다.

## 챗봇 실행 계약

### DB 비밀번호

`DB_PASSWORD_FILE`이 있으면 해당 파일의 UTF-8 내용을 trailing newline만 제거해 비밀번호로 사용하고, 없을 때만 `DB_PASSWORD`를 사용한다. 파일 경로가 설정됐는데 읽을 수 없으면 앱을 조용히 빈 비밀번호로 시작하지 않고 설정 오류를 낸다.

### Liveness와 readiness

- 기존 `GET /ai/health` 응답 계약은 유지한다.
- `GET /ai/ready`를 readiness endpoint로 추가한다.
- readiness는 DB `SELECT 1`, 로컬 BGE-M3 모델 경로의 필수 파일, 선택된 LLM backend의 모델 목록 endpoint를 확인한다.
- 모두 준비되면 `200`과 `status=ready`, 하나라도 실패하면 `503`과 `status=not_ready` 및 check별 사유를 반환한다.
- readiness는 BGE-M3 가중치를 메모리에 로드하지 않는다. 파일 존재 검사는 빠른 probe를 위해 사용하고 실제 임베딩 로딩은 요청 경로에서 지연 로드한다.
- LLM endpoint는 backend별로 확인한다: Ollama `GET /api/tags`, SGLang `GET /v1/models`, MLX Serve `GET /v1/models`. 응답 목록에 `LLM_MODEL`이 있으면 준비 상태로 본다.

### 모델 인계

- BGE-M3: `BAAI/bge-m3`, revision `5617a9f61b028005a4858fdac845db406aefb181`, SentenceTransformers PyTorch 파일 기준 약 `2.30 GB`(약 `2.14 GiB`), 임베딩 차원 1024.
- 필수 파일: `modules.json`, `config_sentence_transformers.json`, `config.json`, `1_Pooling/config.json`, `pytorch_model.bin`, `tokenizer.json`, `tokenizer_config.json`, `special_tokens_map.json`, `sentencepiece.bpe.model`, `sparse_linear.pt`, `colbert_linear.pt`, `sentence_bert_config.json`.
- 기본 마운트 경로: `/models/bge-m3`; `EMBED_MODEL`로 override 가능하다.
- 현재 코드가 제공하는 LLM 계약은 Ollama `/api/chat` 및 SGLang/MLX Serve OpenAI 호환 `/v1/chat/completions`이다. 최종 T4 LLM image digest, model precision, command, port, health endpoint는 Native/모델 담당 인계 전까지 미확정으로 기록한다.

## 성공 기준

- PR workflow가 두 서비스 테스트와 Docker 검증을 수행하며 ECR 인증이나 push를 수행하지 않는다.
- main workflow가 두 서비스에 서로 다른 ECR digest를 기록하고 같은 SHA 재실행 시 기존 digest를 재사용한다.
- `DB_PASSWORD_FILE` 우선순위와 읽기 실패가 테스트된다.
- `/ai/ready`가 DB·모델 파일·LLM 준비 상태에 따라 200/503을 반환한다.
- 챗봇 Dockerfile은 `linux/amd64`로 빌드 가능하고 이미지에 BGE-M3 가중치를 포함하지 않는다.
- 실제 GPU 추론 성공과 T4 메모리 적합성은 CI 성공으로 주장하지 않고 별도 GPU 환경 검증 항목으로 남긴다.
