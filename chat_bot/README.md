# 미담 · AI 추천 챗봇

스토리 중심 장인 공예 커머스 "미담"의 AI 추천 챗봇. 자연어 질의를 받아 의미 기반으로
장인 공예품을 추천한다. 로컬(MacBook M4)에서 개발하고, **AWS EKS(NVIDIA T4)에 배포**한다.

## 구성

- **DB**: PostgreSQL 17 + pgvector (상품·서사·벡터)
- **LLM**: gemma4 12B (Ollama, GGUF) — 의도분류·조건추출·생성
- **임베딩**: BGE-M3 (1024차원, CPU)
- **검색**: 벡터 + BM25(Kiwi) + RRF 하이브리드, 유사도 컷 τ
- **서버**: FastAPI (`/ai/*`)

> 배포 시 챗봇 API 컨테이너(FastAPI + BGE-M3, CPU)와 LLM 컨테이너(Ollama + gemma4, GPU)를
> 같은 Pod에 두고 GPU는 LLM 컨테이너에만 할당한다.

## 폴더 구조

```
chat_bot/
├── app/
│   ├── config.py              # 설정 (.env 로드)
│   ├── main.py                # FastAPI 진입점 (/ai/*)
│   ├── products_service.py    # 상품 등록·수정·삭제 처리 (load_products 재활용)
│   ├── schemas.py             # API 요청·응답 스키마 (Pydantic)
│   ├── readiness.py           # /ai/ready — DB·임베딩 파일·LLM 준비 확인
│   ├── session_store.py       # 세션별 내부 상태(candidates·filters·product_ids·query_text) 보관
│   ├── run_recommend.py       # 검색+랭킹 통합 (A 담당: search→ranking)
│   ├── pipeline/              # 추천 파이프라인 (핵심)
│   │   ├── intent.py          #  ① 의도분류·조건추출 (gemma4)
│   │   ├── embedding.py       #  ② 쿼리 임베딩 (BGE-M3)
│   │   ├── search.py          #  ③ 하이브리드 검색 (벡터+BM25+RRF, 유사도 컷)
│   │   ├── ranking.py         #  ④ 유사도컷·등급가중·최대3개
│   │   ├── generate.py        #  ⑤ 응답·후속칩 생성 (gemma4)
│   │   ├── orchestrator.py    #  ①→검색→⑤ 전체 흐름 (run)
│   │   ├── llm.py             #  LLM 호출 공용 함수 (Ollama /api/chat, JSON 강제)
│   │   ├── prompts.py         #  intent·generate 시스템 프롬프트
│   │   ├── taxonomy.py        #  단어→카테고리 사전 (자동 생성물, 직접 수정 금지)
│   │   └── build_taxonomy.py  #  taxonomy.py 생성 스크립트
│   └── ingest/
│       └── load_products.py   #  CSV → 조립·임베딩·UPSERT 적재 스크립트
├── deploy/
│   └── sglang/                # (배포용) — 현재 LLM 서빙은 Ollama 사용
│   └── ollama/                # (배포용) — Ollama용 이미지
├── data/                      # 목데이터·실데이터 CSV
├── eval/
│   ├── eval_set.json          #  검색 평가셋 (질의+정답 속성 규칙)
│   ├── run_eval.py            #  검색 평가 실행 — Recall@3·MRR (검색·랭킹 품질)
│   ├── run_generate_eval.py   #  생성 평가 실행 — 정직성·인젝션·환각 방지 (intent+응답)
│   ├── generate_grading.py    #  생성 평가 채점 3계층 (L1 규칙 / L2 근거대조 / L3 LLM판정)
│   ├── generate_cases.json    #  생성 평가 케이스 (질의+expect 라벨)
│   ├── generate_fixtures/     #  케이스별 후보 상품(접점2) 고정 입력 (contact2.json)
├── tests/                     # 단위 테스트 (intent·generate·orchestrator 등)
├── verify_env.py              # 환경 검증
├── requirements.txt
├── requirements-dev.txt.      # 개발용 추가 도구
├── .env
├── Dockerfile                 # 챗봇 API 이미지 (python:3.11-slim, torch CPU)
├── README.md
```

## 파이프라인 흐름

```
자연어 메시지
  → ① intent (의도분류·조건추출)     app/pipeline/intent.py
  → ②③④ search·ranking (검색·랭킹)   app/pipeline/search.py, ranking.py
  → ⑤ generate (응답·후속칩)          app/pipeline/generate.py
  → orchestrator가 전체 호출          app/pipeline/orchestrator.py
  → { reply, intent, product_ids, suggestions }
```

> 응답은 `product_ids`(정수 배열, 최대 3개) + 공유 `reply`다. 상품별 개별 reason은 만들지
> 않고, 백엔드가 `product_id`로 상세를 조립한다. narrow_down("그중 더 싼 거") 판단용
> 내부 캐시(candidates·filters)는 session_id로 임시 보관한다(TTL 30분).

## API 엔드포인트

| 메서드 | 경로 | 비고 |
| :--- | :--- | :--- |
| GET | /ai/health | 상태 체크 |
| GET | /ai/ready | DB·임베딩 파일·LLM 준비 확인 (미준비 시 503) |
| POST | /ai/products | 상품 등록 및 임베딩 |
| PUT | /ai/products/{id} | 상품 정보 수정 및 재임베딩 |
| DELETE | /ai/products/{id} | 상품 삭제 |
| POST | /ai/chat | 상품 추천 |

## 시작하기

### 1. 환경 세팅
```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
> BGE-M3는 `.bin`(pickle) 가중치만 제공하고 transformers가 CVE-2025-32434로 **torch ≥ 2.6**을
> 요구한다. 검증 조합: `torch==2.6.0 / transformers==5.17.0 / sentence-transformers==6.1.0`.
> 로컬 LLM은 Ollama에 `gemma4:12b`가 올라와 있어야 한다.

### 2. 환경 검증
```bash
python verify_env.py          # 전부 ✅면 준비 완료
```

### 3. 데이터 적재
```bash
python -m app.ingest.load_products \
  --file data/장인몰_샘플_product.csv \
  --artisan-file data/장인몰_샘플_artisan.csv
```

### 4. 추천 테스트 (CLI)
```bash
python -m app.pipeline.orchestrator "(사용자 쿼리)"
```

### 5. 서버 실행
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
# http://localhost:8000/docs 에서 API 문서·테스트
```

## 팀 통일 값

| 항목 | 값 |
| :--- | :--- |
| Python | 3.11 (배포 이미지 `python:3.11-slim`) |
| DB | PostgreSQL 17 |
| LLM / 임베딩 | gemma4 12B (Ollama, GGUF) / BAAI/bge-m3 |
| 서빙 / 배포 | Ollama · AWS EKS (NVIDIA T4 16GB) |

## 주요 환경변수 (`.env`)

| 변수 | 값 예시 | 설명 |
| :--- | :--- | :--- |
| `LLM_BACKEND` | `ollama` | LLM 서빙 백엔드 |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama 주소 |
| `LLM_MODEL` | `gemma4:12b` | Ollama 모델 태그와 일치 |
| `EMBED_MODEL` | `BAAI/bge-m3` (배포 시 PVC 경로) | 임베딩 모델 |
| `DB_*` / `DB_PASSWORD_FILE` | — | DB 접속(비번은 파일/시크릿 우선) |