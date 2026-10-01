# 미담 챗봇 LLM 서버 (Ollama) — T4 GPU 컨테이너
#
# SGLang(chat_bot/deploy/sglang/Dockerfile)이 T4에서 공유 메모리 한도(64KiB)를
# 넘는 커널 요구(decode CUDA graph 96KiB, extend_attention 128KiB)로 실제 추론이
# 불가능하다고 확인되어(2026-09-28), Ollama로 전환했다.
#
# 구조:
#   [이 컨테이너]  Ollama가 모델을 로드해 자체 API로 서빙 (포트 11434)
#   [별도]        챗봇 API 컨테이너(FastAPI, chat_bot/Dockerfile) ← 이 컨테이너를
#                  OLLAMA_HOST=http://<이-컨테이너>:11434 로 호출
#
# app/config.py의 LLM_BACKEND·LLM_MODEL 기본값이 이미 "ollama"·동일 모델이라서
# 챗봇 API 쪽은 모델이 바뀌어도 코드 수정이 필요 없다(app/pipeline/llm.py의
# _chat_ollama()가 Ollama의 /api/show로 모델 capabilities를 동적으로 판단함 —
# 특정 모델명을 하드코딩하지 않는다).
#
# gemma4:12b → gemma2:9b로 임시 하향(2026-10-01): gemma4:12b가 T4(16GB VRAM,
# 노드 자체 RAM도 16GiB)에서 기본 사용량만으로 chatbot-llm 메모리 한도(10Gi)의
# 78%(7.8GB)를 차지해, 동시 요청이 겹치면 OOMKilled가 재현됐다(Stage 실측,
# 09:56:29 등). gemma2:9b는 5.4GB로 더 가벼워 여유를 확보한다 — 품질은
# gemma4:12b가 더 우수함이 이미 측정돼 있다(docs/model-selection-comparison.md).
# 메모리 할당·동시 처리 설정(OLLAMA_NUM_PARALLEL 등)이 정리되면 gemma4:12b로
# 되돌리는 걸 고려한다.
#
# ⚠️ 미확인·인프라 조율 필요 (2026-09-28 기준, 아직 유효):
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

ARG OLLAMA_MODEL=gemma2:9b
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
