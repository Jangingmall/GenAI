"""상품 등록·수정·삭제 서비스 — load_products의 조립·임베딩·UPSERT 로직을 재활용한다.

핵심 원칙: 적재 스크립트(app/ingest/load_products.py)와 '같은' 조립·임베딩 규칙을 써야
검색과 정합한다. 그래서 여기서 규칙을 새로 만들지 않고 load_products의 함수를 그대로 import한다.

개발 단계엔 CSV 벌크 적재를 쓰고, 이 서비스는 실서비스에서 상품이 단건으로
등록·수정·삭제될 때의 경로다. 둘 다 같은 스키마·같은 임베딩으로 수렴한다.
"""

from __future__ import annotations

import psycopg2

from app.config import settings

# load_products의 순수 함수·UPSERT를 재사용 (조립·임베딩 규칙 단일 출처).
# 적재 스크립트 위치가 다르면 이 import 경로만 조정.
from app.ingest.load_products import (
    SCHEMA_SQL,
    attach_embeddings,
    build_rows,
    upsert_all,
)

# 재임베딩이 필요한 필드 — 이 중 하나라도 바뀌면 embedding_text가 달라진다.
_EMBED_FIELDS = {
    "name",
    "category_code",
    "subcategory_code",
    "material",
    "making_story",
    "usage_care",
}


def _connect():
    conn = psycopg2.connect(settings.dsn())
    from pgvector.psycopg2 import register_vector

    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)  # 테이블 없으면 생성 (IF NOT EXISTS)
    conn.commit()
    register_vector(conn)
    return conn


def upsert_product(artisan: dict, product: dict) -> bool:
    """장인 1명 + 상품 1건을 조립·임베딩해 UPSERT한다.

    Returns:
        embedded: 임베딩까지 완료됐는지
    """
    # build_rows는 (artisans, products) 리스트를 받아 embedding_text·search_text·evidence 조립
    rows = build_rows([artisan], [product])
    attach_embeddings(rows)  # BGE-M3 임베딩 (normalize=True)

    conn = _connect()
    try:
        upsert_all(conn, [artisan], rows)
    finally:
        conn.close()
    return True


def update_product(product_id: int, changed: dict) -> bool:
    """변경된 필드만 갱신한다. 임베딩 대상 필드가 바뀌면 재임베딩.

    Returns:
        re_embedded: 재임베딩이 수행됐는지
    """
    needs_reembed = bool(_EMBED_FIELDS & set(changed.keys()))

    conn = _connect()
    try:
        with conn.cursor() as cur:
            if needs_reembed:
                # 기존 행을 읽어 변경분을 덮어쓴 뒤, 조립·임베딩을 다시 한다.
                cur.execute(
                    "SELECT product_id, artisan_id, name, category_code, subcategory_code,"
                    " material, price, color, gift_theme, purpose_tags, making_story,"
                    " usage_care, status FROM products WHERE product_id = %s",
                    (product_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise LookupError(f"product_id {product_id} 없음")
                cols = [
                    "product_id",
                    "artisan_id",
                    "name",
                    "category_code",
                    "subcategory_code",
                    "material",
                    "price",
                    "color",
                    "gift_theme",
                    "purpose_tags",
                    "making_story",
                    "usage_care",
                    "status",
                ]
                product = dict(zip(cols, row))
                product.update(changed)  # 변경분 반영

                # 장인 등급(evidence.verified)은 재조립에 필요 — artisan을 함께 조회
                cur.execute(
                    "SELECT artisan_id, business_name, certification_level, region"
                    " FROM artisans WHERE artisan_id = %s",
                    (product["artisan_id"],),
                )
                a = cur.fetchone()
                artisan = dict(
                    zip(
                        [
                            "artisan_id",
                            "business_name",
                            "certification_level",
                            "region",
                        ],
                        a,
                    )
                )

                from app.ingest.load_products import (
                    attach_embeddings as _emb,
                )
                from app.ingest.load_products import (
                    build_rows as _rows,
                )
                from app.ingest.load_products import (
                    upsert_all as _up,
                )

                rows = _rows([artisan], [product])
                _emb(rows)
                _up(conn, [artisan], rows)
            else:
                # 비임베딩 필드만: 값만 UPDATE
                sets = ", ".join(f"{k} = %s" for k in changed)
                params = list(changed.values()) + [product_id]
                cur.execute(f"UPDATE products SET {sets} WHERE product_id = %s", params)
                if cur.rowcount == 0:
                    raise LookupError(f"product_id {product_id} 없음")
        conn.commit()
    finally:
        conn.close()
    return needs_reembed


def delete_product(product_id: int) -> bool:
    """상품을 삭제한다.

    Returns:
        deleted: 실제로 삭제됐는지 (없으면 False)
    """
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM products WHERE product_id = %s", (product_id,))
            deleted = cur.rowcount > 0
        conn.commit()
    finally:
        conn.close()
    return deleted


def health() -> dict:
    """DB 연결·임베더 로드 상태를 확인한다."""
    db_status = "connected"
    try:
        conn = psycopg2.connect(settings.dsn())
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        conn.close()
    except Exception:  # noqa: BLE001
        db_status = "error"

    # 임베더는 로드 시도 없이 설정만 확인 (실로드는 무거움)
    embedder_status = "configured"
    return {"status": "ok", "db": db_status, "embedder": embedder_status}
