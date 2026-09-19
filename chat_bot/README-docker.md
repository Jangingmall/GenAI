# 챗봇(영역2) 도커 컨테이너 가이드

## 파일 구성
- `Dockerfile` — FastAPI 앱 + BGE-M3 실행 컨테이너
- `requirements.txt` — 프로덕션 의존성 (버전 고정)
- `requirements-dev.txt` — 개발용 (pytest·black·ruff 추가)
- `.dockerignore` — 빌드 컨텍스트 축소

ECR 저장소 이름은 Native 인계 계약에 따라 `jangin-ai/ollama`로 고정되어 있지만,
이 Dockerfile은 **Ollama/LLM 서버를 포함하지 않는 챗봇 API 이미지**다. LLM은 같은
Pod의 별도 컨테이너 또는 Native가 지정한 별도 서비스로 연결한다.

## 배치
프로젝트 루트(app/ 있는 위치)에 놓는다.
```
chat_bot/
  app/
  Dockerfile
  requirements.txt
  .dockerignore
```

## 컨테이너 구조
```
[이 컨테이너]  FastAPI 앱 + BGE-M3 임베딩 실행  (포트 8000)
[별도]        gemma4 LLM (SGLang)   ← SGLANG_HOST로 연결
[별도]        PostgreSQL + pgvector ← DB_* 로 연결
[볼륨]        BGE-M3 모델            ← 인프라가 S3에서 볼륨 마운트
```
LLM·DB는 이 컨테이너에 없다. BGE-M3 모델도 이미지에 없다 —
인프라가 S3에 올려둔 모델을 볼륨으로 마운트해주고, 컨테이너는 그 경로만 읽는다.

### BGE-M3 모델 인계

- Hugging Face model: `BAAI/bge-m3`
- Revision: `5617a9f61b028005a4858fdac845db406aefb181`
- Embedding dimension: `1024`
- SentenceTransformers runtime subset: 약 `2.30 GB` (약 `2.14 GiB`)
- Full Hub repository는 ONNX 변형까지 포함하면 약 `4.59 GB`이므로, CPU
  SentenceTransformers 경로에 필요하지 않은 `onnx/` 파일은 동기화하지 않아도 된다.
- 필수 파일: `modules.json`, `config.json`, `config_sentence_transformers.json`,
  `1_Pooling/config.json`, `pytorch_model.bin`, `tokenizer.json`,
  `tokenizer_config.json`, `special_tokens_map.json`, `sentencepiece.bpe.model`,
  `sparse_linear.pt`, `colbert_linear.pt`, `sentence_bert_config.json`

## 빌드
```bash
docker build -t midam-chatbot .
```
이미지에 모델이 없어 가볍다(torch 등 런타임만 포함).

## 실행 (볼륨 마운트 + 환경변수)
```bash
docker run -p 8000:8000 \
  -v /host/path/to/bge-m3:/models/bge-m3:ro \
  -e EMBED_MODEL=/models/bge-m3 \
  -e DB_HOST=<postgres-host> \
  -e DB_PORT=5432 \
  -e DB_NAME=midam \
  -e DB_USER=<user> \
  -v /host/path/to/secrets:/mnt/secrets-store:ro \
  -e DB_PASSWORD_FILE=/mnt/secrets-store/password \
  -e LLM_BACKEND=sglang \
  -e LLM_MODEL=<served-model-name> \
  -e SGLANG_HOST=http://<sglang-host>:30000 \
  midam-chatbot
```
- `-v <호스트경로>:/models/bge-m3` : 인프라가 S3에서 받아둔 모델을 이 경로로 마운트
- `EMBED_MODEL=/models/bge-m3` : 앱이 이 로컬 경로에서 모델 로드
  (sentence-transformers는 경로가 로컬 디렉토리면 거기서 읽음 — 코드 수정 불필요)
- `DB_PASSWORD_FILE`이 설정되면 `DB_PASSWORD`보다 우선하며, 파일을 읽지 못하면
  앱은 빈 비밀번호로 시작하지 않고 설정 오류를 낸다.

## 헬스 체크
```bash
curl http://localhost:8000/ai/health
# {"status":"ok","db":"connected","embedder":"configured"}

curl -i http://localhost:8000/ai/ready
# 200 + {"status":"ready", "checks": {...}} when DB, BGE-M3 files, and LLM are ready
# 503 + {"status":"not_ready", "checks": {...}} otherwise
```

## 역할 분담
| 항목 | 담당 |
| :--- | :--- |
| 앱 컨테이너(이 Dockerfile) | 챗봇 파트 |
| BGE-M3를 S3에 올리고 볼륨 마운트 | 인프라 |
| 최종 LLM 컨테이너·모델 | 인프라/모델 담당 |
| PostgreSQL(RDS 등) | 인프라 |

## 확인 필요
1. **EMBED_MODEL 환경변수명** — 앱 config가 읽는 실제 설정명 확인 (embedding.py).
   다르면 Dockerfile ENV 이름을 맞춘다.
2. **마운트 경로** — 인프라가 어느 경로로 마운트하는지 합의 (기본 /models/bge-m3).
3. **SGLANG_HOST / DB 연결** — 배포 환경 주소.
4. **LLM 실행 계약** — 최종 image digest, model/precision, command, port, `/v1/models`
   또는 `/api/tags` health 응답은 별도 LLM 이미지 확정 후 인계한다. 이 API 이미지에
   LLM 서버를 넣지 않는다.

## 주의
- 로컬 빌드·기동은 되지만, 실제 추천은 SGLang·DB 연결돼야 동작.
  로컬에선 /ai/health 정도, 전체 검증은 배포 환경에서.
- 로컬 개발은 LLM_BACKEND=ollama, 배포는 sglang (llm.py가 분기).
- 로컬 테스트 시 BGE-M3 마운트가 없으면, EMBED_MODEL을 "BAAI/bge-m3"로 두면
  HuggingFace에서 받아 동작(개발용). 배포는 볼륨 마운트 경로 사용.
- Python 3.11 고정 (3.13은 ML 패키지 wheel 미제공 위험).
