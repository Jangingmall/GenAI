# 미담 AI 추천 챗봇 (영역 2) — FastAPI 앱 컨테이너
#
# 구조:
#   [이 컨테이너]  FastAPI 앱 + BGE-M3 임베딩 실행  (포트 8000)
#   [별도]        gemma4 LLM (SGLang)             ← 환경변수 SGLANG_HOST로 연결
#   [별도]        PostgreSQL + pgvector           ← 환경변수 DB_* 로 연결
#
# 모델(BGE-M3): 인프라가 S3 → 볼륨으로 마운트해준다.
#   컨테이너는 마운트된 로컬 경로만 읽는다 (S3 접근/다운로드 로직 없음).
#   앱은 EMBED_MODEL 환경변수가 가리키는 경로에서 모델을 로드한다.
#   BGE-M3는 CPU로 구동한다 (GPU는 별도 LLM 컨테이너 몫).

# Python 3.11 — 3.13은 일부 ML 패키지 wheel 미제공으로 빌드 실패 위험
FROM python:3.11-slim

WORKDIR /app

# 시스템 의존성 (psycopg2 빌드·실행)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# ── PyTorch: CPU 전용 빌드 설치 ────────────────────────────────────────────
# PyPI 기본 torch(리눅스)는 CUDA 런타임을 통째로 포함해 수 GB에 달한다.
# BGE-M3는 CPU로 돌리므로 CPU 전용 인덱스에서 설치해 이미지 용량을 크게 줄인다.
# requirements.txt 에 torch 가 있어도, 여기서 먼저 설치되면 아래 단계에서
# "이미 충족됨"으로 건너뛴다. torch 버전이 핀 고정돼 있으면 TORCH_VERSION 을
# 그 버전과 동일하게 맞춰 빌드하면 된다. (예: --build-arg TORCH_VERSION=2.3.1)
ARG TORCH_VERSION=2.3.1
RUN pip install --no-cache-dir --timeout 300 --retries 5 \
        torch==${TORCH_VERSION} \
        --index-url https://download.pytorch.org/whl/cpu

# 파이썬 의존성 — 코드보다 먼저 복사해 레이어 캐싱
# (코드만 바뀌면 무거운 torch 재설치 안 함)
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 300 --retries 5 -r requirements.txt

# 앱 코드
COPY app/ ./app/

# 임베딩 모델 경로 — 인프라가 볼륨 마운트해줄 위치.
# sentence-transformers는 이 값이 로컬 디렉토리면 거기서 모델을 로드한다.
# 실행 시 -v <호스트경로>:/models/bge-m3 로 마운트하고 이 경로를 맞춘다.
ENV EMBED_MODEL=/models/bge-m3

# ── non-root 실행 설정 ─────────────────────────────────────────────────────
# 전용 유저(appuser, UID 10001)를 만들고 앱/홈 디렉토리 소유권을 넘긴다.
# 모델은 로컬 마운트에서 로드하므로 네트워크 다운로드는 없지만,
# transformers/sentence-transformers 가 캐시를 쓰려 할 수 있어
# 홈 아래 쓰기 가능한 캐시 경로를 지정한다.
ARG APP_UID=10001
RUN groupadd -g ${APP_UID} appuser \
    && useradd -u ${APP_UID} -g appuser -m -s /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app

ENV HOME=/home/appuser \
    HF_HOME=/home/appuser/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/home/appuser/.cache/torch/sentence_transformers

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]