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
midam_chat_bot/
├── app/
│   ├── config.py          # 설정 (.env 로드)
│   ├── main.py            # FastAPI 진입점 (나중에 채움)
│   ├── models/            # 요청·응답 스키마
│   ├── pipeline/          # 추천 파이프라인 (핵심)
│   │   ├── intent.py      #  ① 의도분류·조건추출
│   │   ├── embedding.py   #  ② 임베딩
│   │   ├── search.py      #  ③ 하이브리드 검색
│   │   ├── ranking.py     #  ④ 유사도컷·등급가중·최대3개
│   │   └── generate.py    #  ⑤ 추천이유·후속칩 생성
│   └── ingest/            # 데이터 적재
│       ├── loader.py      #  JSON → 변환 → 임베딩 → DB
│       └── mappings.py    #  코드→한글 (POTTERY→도자기)
├── sql/schema.sql         # 테이블 정의
├── data/                  # 목데이터
├── eval/                  # 평가셋 + 지표 측정
├── verify_env.py          # 환경 검증
└── requirements.txt
```
