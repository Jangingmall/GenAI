# 미담 · AI 추천 챗봇

스토리 중심 장인 공예 커머스 "미담"의 AI 추천 챗봇. 자연어 질의를 받아 의미 기반으로
장인 공예품을 추천한다. 완전 로컬(MacBook M4) 환경에서 동작한다.

## 구성

- **DB**: PostgreSQL 17 + pgvector (상품·서사·벡터)
- **LLM**: Qwen3 8B (Ollama) — 의도분류·조건추출·생성
- **임베딩**: BGE-M3 (1024차원)
- **검색**: 벡터 + BM25(Kiwi) + RRF 하이브리드
- **서버**: FastAPI (`/ai/*`)

## 폴더 구조

```
chat_bot/
├── app/
│   ├── config.py              # 설정 (.env 로드)
│   ├── main.py                # FastAPI 진입점 (/ai/health, /ai/products)
│   ├── products_service.py    # 상품 등록·수정·삭제 처리 (load_products 재활용)
│   ├── schemas.py             # API 요청·응답 스키마 (Pydantic)
│   ├── run_recommend.py       # 검색+랭킹 통합 (A 담당: search→ranking)
│   ├── pipeline/              # 추천 파이프라인 (핵심)
│   │   ├── intent.py          #  ① 의도분류·조건추출 (Qwen3)
│   │   ├── embedding.py       #  ② 쿼리 임베딩 (BGE-M3)
│   │   ├── search.py          #  ③ 하이브리드 검색 (벡터+BM25+RRF)
│   │   ├── ranking.py         #  ④ 유사도컷·등급가중·최대3개
│   │   ├── generate.py        #  ⑤ 추천이유·후속칩 생성 (Qwen3)
│   │   ├── orchestrator.py    #  ①→검색→⑤ 전체 흐름 (run)
│   │   ├── llm.py             #  Ollama 호출 공용 함수 (JSON 파싱)
│   │   ├── prompts.py         #  intent·generate 시스템 프롬프트
│   │   ├── taxonomy.py        #  단어→카테고리 사전 (자동 생성물, 직접 수정 금지)
│   │   └── build_taxonomy.py  #  taxonomy.py 생성 스크립트
│   └── ingest/
│       └── load_products.py   #  CSV → 조립·임베딩·UPSERT 적재 스크립트
├── data/                      # 목데이터·실데이터 CSV
├── eval/
│   └── eval_set.json          # 검색 평가셋 (질의+정답 속성 규칙)
├── tests/                     # 단위 테스트 (intent·generate·orchestrator 등)
├── verify_env.py              # 환경 검증
├── requirements.txt
├── README.md

```

## 파이프라인 흐름
 
```
자연어 메시지
  → ① intent (의도분류·조건추출)     app/pipeline/intent.py
  → ②③④ search·ranking (검색·랭킹)   app/pipeline/search.py, ranking.py
  → ⑤ generate (응답·이유·후속칩)     app/pipeline/generate.py
  → orchestrator가 전체 호출          app/pipeline/orchestrator.py
  → { reply, intent, products, suggestions }
```
 
## API 엔드포인트
 
| 메서드 | 경로 | 비고 |
| :--- | :--- | :--- |
| GET | /ai/health | 상태 체크 |
| POST | /ai/products | 상품 등록 및 임베딩 |
| PUT | /ai/products/{id} | 상품 정보 수정 및 재임베딩 |
| DELETE | /ai/products/{id} | 상품 삭제 |
| POST | /ai/chat | 상품 추천 |
 
## 시작하기
 
### 1. 환경 세팅
```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
 
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
| Python | 3.14 |
| DB | PostgreSQL 17 |
| LLM / 임베딩 | gemma2:9b / BAAI/bge-m3 (확정 예정) |