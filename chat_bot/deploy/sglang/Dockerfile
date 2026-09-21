# 미담 챗봇 LLM 서버 (SGLang) — T4 GPU 컨테이너
#
# 구조:
#   [이 컨테이너]  SGLang이 Gemma 4 12B(AWQ 양자화)를 로드해 OpenAI 호환 API로 서빙 (포트 30000)
#   [별도]        챗봇 API 컨테이너(FastAPI, chat_bot/Dockerfile) ← 이 컨테이너를
#                  SGLANG_HOST=http://<이-컨테이너>:30000 로 호출
#
# 같은 Pod 안에 두 컨테이너를 둘 때, GPU(nvidia.com/gpu: 1)는 이 컨테이너에만 할당한다.
# API 컨테이너(BGE-M3 임베딩)는 CPU만 쓴다.
#
# 실측으로 확인된 SGLang 제약(로컬 Mac/MPS 기준 — CUDA·T4에서 재확인 필요):
#   1. 기본 grammar backend(xgrammar)는 JSON 스키마 강제 시 매 토큰을 거부해 응답을 못
#      만든다(Accepted tokens: []) — 그래서 아래 --grammar-backend outlines 필수.
#   2. outlines도 완벽하진 않아 응답을 마크다운 코드펜스로 감싸는 경우가 있다
#      (```json\n{...}\n```) — 챗봇 API 쪽 llm.py가 파싱 전에 벗겨내도록 이미 처리돼 있다.
#   3. 가장 심각한 문제: 프롬프트가 이전 요청과 비슷하면(prefix cache 히트로 추정) 응답
#      앞부분이 통째로 잘려서 온다 — 에러 없이 200 OK로 조용히 틀린 데이터를 준다. 코드로
#      방어 불가능하므로, 실제 T4 배포 전 반드시 재현 여부를 확인해야 한다.

FROM lmsysorg/sglang:v0.5.19
# Gemma 4 아키텍처는 SGLang v0.5.12(2026-05-16)부터 지원된다 — v0.5.19는 그 이후 버전이라
# 문제없다(상세페이지 컨테이너와 동일 버전으로 맞춤). 공식 릴리스 노트로 확인함.

# Gemma 4 12B의 AWQ 양자화본. 구글 공식 양자화는 GGUF(llama.cpp/Ollama 전용)뿐이라
# SGLang이 읽을 수 없다 — 아래는 커뮤니티 변환본이며, 실제 배포 전 품질 검증이 필요하다.
# 다른 후보로 바꾸려면 빌드 시 `--build-arg MODEL_PATH=...`로 교체한다.
ARG MODEL_PATH=mattbucci/gemma-4-12B-AWQ
ARG MODEL_REVISION=main
ARG SERVED_MODEL_NAME=gemma4-12b-awq
ENV MODEL_PATH=${MODEL_PATH} \
    MODEL_REVISION=${MODEL_REVISION} \
    SERVED_MODEL_NAME=${SERVED_MODEL_NAME}

EXPOSE 30000

# 챗봇 API의 app/readiness.py가 SGLang 백엔드 준비 여부를 이 엔드포인트로 확인한다
# (readiness.py의 _check_llm(): backend가 "sglang"이면 GET /v1/models 호출).
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD ["python3", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:30000/v1/models', timeout=3).status == 200 else 1)"]

# 컨테이너 시작 시 모델을 로드하며 SGLang 서버를 띄운다.
#   --quantization awq        : 위 모델이 AWQ로 양자화돼 있음을 명시
#   --grammar-backend outlines: intent.py·generate.py가 요구하는 JSON 스키마 강제 대응
# 메모리 사용 비율(--mem-fraction-static) 등 T4 튜닝 값은 실제 GPU 실측 후 추가한다.
ENTRYPOINT ["sh", "-c", "python3 -m sglang.launch_server \
    --model-path \"$MODEL_PATH\" \
    --revision \"$MODEL_REVISION\" \
    --served-model-name \"$SERVED_MODEL_NAME\" \
    --quantization awq \
    --grammar-backend outlines \
    --host 0.0.0.0 \
    --port 30000"]
