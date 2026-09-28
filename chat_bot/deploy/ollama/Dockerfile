# 미담 챗봇 LLM 서버 (Ollama) — T4 GPU 컨테이너
#
# SGLang(chat_bot/deploy/sglang/Dockerfile)이 T4에서 공유 메모리 한도(64KiB)를
# 넘는 커널 요구(decode CUDA graph 96KiB, extend_attention 128KiB)로 실제 추론이
# 불가능하다고 확인되어(2026-09-28), Ollama gemma4:12b(GGUF)로 전환한다.
#
# 구조:
#   [이 컨테이너]  Ollama가 gemma4:12b를 로드해 자체 API로 서빙 (포트 11434)
#   [별도]        챗봇 API 컨테이너(FastAPI, chat_bot/Dockerfile) ← 이 컨테이너를
#                  OLLAMA_HOST=http://<이-컨테이너>:11434 로 호출
#
# app/config.py의 LLM_BACKEND·LLM_MODEL 기본값이 이미 "ollama"·"gemma4:12b"라서
# 챗봇 API 쪽은 코드 수정이 필요 없다(app/pipeline/llm.py의 _chat_ollama(),
# app/readiness.py의 _check_llm()이 이미 이 백엔드를 지원).
#
# ⚠️ 미확인·인프라 조율 필요 (2026-09-28 기준):
#   1. 모델 배치 방식 — SGLang 컨테이너는 모델을 이미지에 안 굽고 S3 → PVC 마운트
#      방식을 썼다. Ollama도 같은 방식을 쓰려면 OLLAMA_MODELS를 그 PVC 경로로
#      맞춰야 한다(Ollama의 모델 저장 포맷은 HuggingFace 원본과 달리 자체
#      manifest+blob 구조다). 이 Dockerfile은 우선 "빌드 시 이미지에 굽는" 더 단순한
#      방식으로 작성했다 — Stage가 런타임에 외부 네트워크(ollama.com) 접근이
#      막혀 있다면 이 방식 자체가 안 될 수 있어 인프라팀 확인이 먼저 필요하다.
#   2. GPU 메모리 실측 — SGLang과 VRAM 사용 패턴이 다를 수 있어 재확인 필요.
#   3. 배포 매니페스트(K8s env var: LLM_BACKEND=ollama, OLLAMA_HOST, LLM_MODEL)는
#      이 레포 밖에 있어 인프라팀이 반영해야 한다.

FROM ollama/ollama:latest

ARG OLLAMA_MODEL=gemma4:12b
ENV OLLAMA_MODEL=${OLLAMA_MODEL}
ENV OLLAMA_HOST=0.0.0.0:11434
ENV OLLAMA_KEEP_ALIVE=-1

# 빌드 시 모델을 이미지에 굽는다(런타임에 외부 네트워크 불필요).
# ollama serve를 백그라운드로 잠깐 띄워 pull한 뒤 종료 — 공식 이미지 문서 패턴.
RUN ollama serve & \
    sleep 5 && \
    ollama pull "${OLLAMA_MODEL}" && \
    pkill ollama

EXPOSE 11434

# 챗봇 API의 app/readiness.py가 이 엔드포인트로 준비 여부를 확인한다
# (readiness.py의 _check_llm(): backend가 "ollama"면 GET /api/tags 호출,
# 응답의 models[].name 목록에 LLM_MODEL이 있는지 확인).
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD ["sh", "-c", "ollama list | grep -q \"$OLLAMA_MODEL\" || exit 1"]

ENTRYPOINT ["ollama", "serve"]
