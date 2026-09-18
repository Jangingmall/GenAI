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

# Python 3.11 — 3.13은 일부 ML 패키지 wheel 미제공으로 빌드 실패 위험
FROM python:3.11-slim

WORKDIR /app

# 시스템 의존성 (psycopg2 빌드·실행)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

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

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
