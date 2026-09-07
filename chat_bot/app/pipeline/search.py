"""
③ 하이브리드 검색 — 벡터 + BM25 + RRF + 하드필터 + gift_theme 부스팅.

로드맵 진행:
  [1단계] 순수 벡터 검색                     
  [2단계] 하드 필터(price/color) + gift_theme 부스팅  
  [3단계] BM25 + RRF 하이브리드              

접점 1(intent → search) 입력 형식:
  {
    "query_text": str,                       # 벡터·BM25 검색용 자연어
    "filters": {
        "max_price": int | None,
        "min_price": int | None,
        "color": [str] | None,               # enum 하드 필터
        "gift_theme": [str] | None,          # 부스팅 (하드필터 아님)
    },
    "intent": str
  }
접점 2(search → ranking) 출력 형식:
  [ { "product_id", "name", "score", "evidence" }, ... ]

주의: BM25 토크나이저는 적재(load_products.py)의 tokenize_ko와 동일해야 맞물린다.
      여기서는 그 함수를 import해서 재사용한다(색인=질의 토큰화 일치).
"""

import json

import psycopg2

from app.config import settings
from app.pipeline.embedding import embed_query

# 적재 때 쓴 것과 '같은' 토크나이저를 재사용해야 BM25 색인/질의가 맞물린다.
# load_products가 app/ingest에 있다고 가정. 위치가 다르면 import 경로만 조정.
try:
    from app.ingest.load_products import tokenize_ko
except Exception:  # noqa: BLE001
    # 적재 스크립트를 아직 못 받은 경우를 대비한 폴백 (BM25 비활성).
    tokenize_ko = None

# gift_theme 부스팅 크기. 유사도(0~1)에 더해지는 소폭 가점.
GIFT_THEME_BONUS = 0.05
# RRF 상수. 관례적으로 60을 쓴다(순위 차이를 완만하게 반영).
RRF_K = 60


def _vector_search(cur, qvec_literal, where_sql, where_params, limit):
    """벡터 검색: 코사인 거리 순. (product_id, name, similarity, evidence) 반환."""
    sql = f"""
        SELECT p.product_id, p.name,
               1 - (p.embedding <=> %s::vector) AS similarity,
               p.evidence, p.gift_theme
        FROM products p
        WHERE p.status = 'ON_SALE' {where_sql}
        ORDER BY p.embedding <=> %s::vector
        LIMIT %s;
    """
    cur.execute(sql, (qvec_literal, *where_params, qvec_literal, limit))
    return cur.fetchall()


def _bm25_candidates(cur, query_tokens, where_sql, where_params, limit):
    """BM25 후보: search_text에 질의 토큰이 겹치는 상품을 PostgreSQL 전문검색으로 근사.

    간단화를 위해 여기서는 search_text에 대한 텍스트 매칭 점수를 쓴다.
    (본격 BM25는 rank_bm25로 앱단 구현 가능하나, 1차는 DB 텍스트랭크로 근사.)
    """
    if not query_tokens:
        return []
    q = " ".join(query_tokens)
    sql = f"""
        SELECT p.product_id, p.name,
               ts_rank(to_tsvector('simple', p.search_text),
                       plainto_tsquery('simple', %s)) AS bm25,
               p.evidence, p.gift_theme
        FROM products p
        WHERE p.status = 'ON_SALE'
          AND to_tsvector('simple', p.search_text) @@ plainto_tsquery('simple', %s)
          {where_sql}
        ORDER BY bm25 DESC
        LIMIT %s;
    """
    cur.execute(sql, (q, q, *where_params, limit))
    return cur.fetchall()


def _rrf_fuse(vector_rows, bm25_rows):
    """RRF(Reciprocal Rank Fusion)로 두 순위를 합친다.

    각 결과에서의 순위(rank) 역수를 더해 최종 점수를 만든다. 양쪽 상위일수록 높다.
    반환: {product_id: {name, evidence, gift_theme, rrf}}
    """
    fused: dict = {}

    def add(rows):
        for rank_idx, row in enumerate(rows, start=1):
            pid, name, _score, evidence, gift_theme = row
            entry = fused.setdefault(
                pid,
                {"name": name, "evidence": evidence, "gift_theme": gift_theme, "rrf": 0.0},
            )
            entry["rrf"] += 1.0 / (RRF_K + rank_idx)

    add(vector_rows)
    add(bm25_rows)
    return fused


def _build_where(filters):
    """filters에서 하드 필터 SQL과 파라미터를 만든다. gift_theme은 부스팅이라 제외."""
    filters = filters or {}
    clauses, params = [], []

    if filters.get("max_price") is not None:
        clauses.append("p.price <= %s")
        params.append(filters["max_price"])
    if filters.get("min_price") is not None:
        clauses.append("p.price >= %s")
        params.append(filters["min_price"])
    if filters.get("color"):
        # color는 단일값 컬럼. 여러 후보 중 하나면 매칭(IN).
        clauses.append("p.color = ANY(%s)")
        params.append(list(filters["color"]))

    where_sql = (" AND " + " AND ".join(clauses)) if clauses else ""
    return where_sql, params


def search(query: dict, top_k: int = 10) -> list[dict]:
    """접점 1을 받아 하이브리드 검색 후보를 접점 2 형식으로 돌려준다.

    Args:
        query: { query_text, filters, intent }
        top_k: 랭킹에 넘길 후보 수 (랭킹이 최종 3개로 자름)

    Returns:
        [ { product_id, name, score, evidence }, ... ]  (score=RRF+부스팅)
    """
    query_text = query.get("query_text", "")
    filters = query.get("filters") or {}

    qvec = embed_query(query_text)
    qvec_literal = "[" + ",".join(str(x) for x in qvec) + "]"
    where_sql, where_params = _build_where(filters)

    conn = psycopg2.connect(settings.dsn())
    try:
        with conn.cursor() as cur:
            vector_rows = _vector_search(
                cur, qvec_literal, where_sql, where_params, top_k
            )
            bm25_rows = []
            if tokenize_ko is not None:
                tokens = tokenize_ko(query_text)
                bm25_rows = _bm25_candidates(
                    cur, tokens, where_sql, where_params, top_k
                )
    finally:
        conn.close()

    # RRF 융합
    fused = _rrf_fuse(vector_rows, bm25_rows)

    # gift_theme 부스팅 + 접점 2 형식 조립
    want_themes = set(filters.get("gift_theme") or [])
    results = []
    for pid, entry in fused.items():
        evidence = entry["evidence"]
        if isinstance(evidence, str):
            evidence = json.loads(evidence)
        score = entry["rrf"]
        # 요청 선물테마가 상품 gift_theme에 있으면 소폭 가점 (부스팅, 하드필터 아님)
        product_themes = set(entry.get("gift_theme") or [])
        if want_themes and (want_themes & product_themes):
            score += GIFT_THEME_BONUS
        results.append(
            {
                "product_id": pid,
                "name": entry["name"],
                "score": float(score),
                "evidence": evidence,
            }
        )

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


# 하위호환: 순수 벡터 검색만 쓰고 싶을 때
def vector_search(query_text: str, top_k: int = 5) -> list[dict]:
    """query_text만으로 하는 단순 벡터 검색 (필터·BM25 없음). 디버깅용."""
    return search({"query_text": query_text, "filters": {}}, top_k=top_k)


# 단독 실행용: python -m app.pipeline.search "차 마실 때 쓸 것"
if __name__ == "__main__":
    import sys

    q = sys.argv[1] if len(sys.argv) > 1 else "차 마실 때 쓸 것"
    print(f'질의: "{q}"\n')
    for i, r in enumerate(search({"query_text": q, "filters": {}}), 1):
        print(f"{i}. {r['name']}  (score {r['score']:.4f})")
