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
#  미확인·인프라 조율 필요 (2026-09-28 기준):
#   1. 모델 배치 방식 — SGLang 컨테이너는 모델을 이미지에 안 굽고 S3 → PVC 마운트
#      방식을 썼다. Ollama도 같은 방식을 쓰려면 OLLAMA_MODELS를 그 PVC 경로로
#      맞춰야 한다(Ollama의 모델 저장 포맷은 HuggingFace 원본과 달리 자체
#      manifest+blob 구조다). 이 Dockerfile은 우선 "빌드 시 이미지에 굽는" 더 단순한
#      방식으로 작성했다 — Stage가 런타임에 외부 네트워크(ollama.com) 접근이
#      막혀 있다면 이 방식 자체가 안 될 수 있어 인프라팀 확인이 먼저 필요하다.
#   2. GPU 메모리 실측 — SGLang과 VRAM 사용 패턴이 다를 수 있어 재확인 필요.
#   3. 배포 매니페스트(K8s env var: LLM_BACKEND=ollama, OLLAMA_HOST, LLM_MODEL)는
#      이 레포 밖에 있어 인프라팀이 반영해야 한다.

# latest 대신 버전을 고정한다 — 버전이 바뀔 때마다 동작이 달라지는 위험(실제로
# 기존 OOM 조사 중 Ollama 업스트림에 RAM 캐시가 메모리 집계 밖에서 커지는 이슈가
# 보고된 걸 확인했다)을 배제하고, 언제 올릴지를 우리가 정하기 위함.
FROM ollama/ollama:0.35.0

ARG OLLAMA_MODEL=gemma4:12b
ENV OLLAMA_MODEL=${OLLAMA_MODEL}
ENV OLLAMA_HOST=0.0.0.0:11434
ENV OLLAMA_KEEP_ALIVE=-1
# 대화가 길어질수록 llama-server의 RAM 프롬프트 캐시(기본 상한 8192MiB)와 컨텍스트
# 체크포인트(슬롯당 최대 32개, 최대 10GB)가 호스트 RAM에 계속 쌓이는 게 OOM의 실제
# 원인으로 지목됐다(팀원 로그 기반 진단) — 둘 다 작은 상한으로 눌러서 호스트 RAM이
# 대화 길이에 따라 무한정 자라지 않게 한다(기존 기본값 합 최대 18GB → 이제 최대
# 약 2.7GB). 완전히 0으로 끄는 대신 작은 값을 둔 건 일부 재사용으로 속도 저하를
# 줄이기 위함이다(Stage 배포 후 /ai/chat 응답 속도로 확인 필요 — 로컬 GPU가 없어
# 사전 측정 불가 — 느리면 더 낮추는 걸 고려).
ENV LLAMA_ARG_CACHE_RAM=2048
ENV LLAMA_ARG_CTX_CHECKPOINTS=2

# entrypoint.sh가 curl로 사전 로딩 호출을 한다 — 베이스 이미지에 없을 수 있어 명시 설치.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# 빌드 시 모델을 이미지에 굽는다(런타임에 외부 네트워크 불필요).
# ollama serve를 백그라운드로 잠깐 띄워 pull한 뒤 종료 — 공식 이미지 문서 패턴.
RUN ollama serve & \
    sleep 5 && \
    ollama pull "${OLLAMA_MODEL}" && \
    pkill ollama

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 11434

# 챗봇 API의 app/readiness.py는 이 컨테이너의 /api/ps(현재 메모리에 로드된 모델
# 목록 + context 길이)로 준비 여부를 확인한다 — 설치 여부만 보는 /api/tags는
# "준비 완료"인데 실제로는 모델이 전혀 안 올라온 상태(Stage 실측, 2026-10-01: 재시작
# 20분 뒤에도 GPU 메모리 0%)를 놓친다. 이 컨테이너 자체 HEALTHCHECK도 같은 이유로
# "설치돼 있나"(ollama list) 대신 "지금 로드돼 있나"(ollama ps)로 본다.
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD ["sh", "-c", "ollama ps | grep -q \"$OLLAMA_MODEL\" || exit 1"]

ENTRYPOINT ["/entrypoint.sh"]
