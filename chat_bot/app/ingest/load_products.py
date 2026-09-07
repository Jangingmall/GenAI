"""미담 추천 카탈로그 데이터 적재 스크립트.

CSV(또는 JSON) 파일로 받은 장인·상품 데이터를 읽어
  1. 임베딩용 텍스트(embedding_text) / BM25용 형태소(search_text) / 근거(evidence) 조립
  2. BGE-M3로 임베딩 생성 (배치 1회)
  3. PostgreSQL products / artisans 테이블에 UPSERT (재실행 안전)
한다.

파이프라인(검색·생성)은 아직 없으므로 이 파일 하나에 전부 담는다.
나중에 파이프라인이 임베딩·토크나이저·조립 규칙을 공유하게 되면 그때 분리한다.

실행:
    python load_products.py --file sample_products.csv            # 스키마 생성 + 적재
    python load_products.py --file sample_products.csv --dry-run  # DB·모델 없이 조립까지만
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter
from pathlib import Path

# --- 팀 고정값  ---
# DB 접속 정보는 팀 공통값이라 기본값으로 충분하다. 다른 DB로 붙일 때만 DATABASE_URL 지정.
DEFAULT_DATABASE_URL = "postgresql://User:1234@localhost:5432/midam"
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-m3"

# Kiwi 형태소 태그 중 이 접두사로 시작하는 것만 검색 토큰으로 남긴다.
# N*(명사) V*(용언) MM(관형사) MAG(일반부사) SL(외국어) SN(숫자) — 조사·어미·기호는 버린다.
CONTENT_TAG_PREFIXES = ("N", "V", "MM", "MAG", "SL", "SN")

# 백엔드 CSV 컬럼명 → 우리 필드명. 백엔드 CSV 형식이 확정되면 이 dict를 통째로 교체한다.
# 지금 값은 sample_products.csv 용 예시 매핑이다(나머지 컬럼은 이름이 같아 매핑 불필요).
COLUMN_MAP: dict[str, str] = {
    "artisan_name": "name",
    "artisan_introduction": "introduction",
}

# certification_level 코드값 (AI파트 API 명세서 확정). 이 밖의 값은 경고만 하고 통과시킨다.
CERTIFICATION_LEVELS = ("보유자", "전승교육사", "이수자", "일반")

# CSV의 배열 컬럼(gift_theme·purpose_tags·color) 원소를 구분하는 문자. 백엔드와 최종 합의 필요.
LIST_SEPARATOR = ";"

# 원본에서 뽑아낼 필드. 나머지 컬럼은 무시한다. (명세서 §4-2 요청 예시 기준)
ARTISAN_FIELDS = ("artisan_id", "name", "certification_level", "introduction")
PRODUCT_FIELDS = (
    "product_id",
    "artisan_id",
    "title",
    "category",
    "material",
    "price",
    "gift_theme",
    "purpose_tags",
    "color",
    "making_story",
    "usage_care",
    "production_period_days",
)
INT_FIELDS = ("product_id", "artisan_id", "price", "production_period_days")
ARRAY_FIELDS = ("gift_theme", "purpose_tags", "color")

# 스키마. 스크립트 실행 시 자동 적용된다(별도 .sql 파일·psql -f 단계 없음).
# 결정 대기: (1) 재고 컬럼 부재 — 안전성 명세는 "재고 없음 상품 제외"를 요구하나 스키마에 필드 없음.
#           (2) category enum 미확정 — 적재는 원문 그대로 저장.
SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS artisans (
    artisan_id          BIGINT PRIMARY KEY,
    name                TEXT NOT NULL,
    certification_level TEXT,
    introduction        TEXT
);

CREATE TABLE IF NOT EXISTS products (
    product_id             BIGINT PRIMARY KEY,
    artisan_id             BIGINT REFERENCES artisans(artisan_id),
    title                  TEXT NOT NULL,
    category               TEXT,
    material               TEXT,
    price                  INTEGER,
    gift_theme             TEXT[],
    purpose_tags           TEXT[],
    color                  TEXT[],
    making_story           TEXT,
    usage_care             TEXT,
    production_period_days  INTEGER,
    embedding_text         TEXT,
    embedding              vector(1024),
    embedding_model        TEXT,
    search_text            TEXT,
    evidence               JSONB
);
"""


# ---------------------------------------------------------------------------
# 읽기 / 정규화 (순수 함수 — DB·모델 없음)
# ---------------------------------------------------------------------------


def read_source(path: str | Path) -> list[dict]:
    """파일 확장자를 보고 CSV 또는 JSON으로 읽어 dict 리스트로 돌려준다.

    JSON은 CSV와 같은 형태(상품마다 장인 정보가 붙은 평평한 행 목록)여야 한다.
    """
    path = Path(path)
    # utf-8-sig: Excel이 내보낸 CSV는 BOM이 붙어 첫 컬럼 키가 "﻿product_id"가 되는 일이 흔하다.
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, list):
            raise ValueError("JSON 입력은 행(dict) 목록이어야 합니다")
        return data
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _cast_int(value):
    """빈 값·None은 None, 정수로 파싱되면 int.

    파싱 실패 시 원본 문자열을 그대로 돌려준다 — 여기서 raise하면 validate 전에 죽어
    어느 행·필드가 문제인지 못 알려주기 때문. 타입 검사는 validate가 맡는다.
    """
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return value


def _cast_list(value) -> list[str]:
    """LIST_SEPARATOR로 쪼갠 문자열 배열. 빈 값은 빈 리스트."""
    if not value:
        return []
    return [part.strip() for part in str(value).split(LIST_SEPARATOR) if part.strip()]


def to_records(raw: list[dict]) -> tuple[list[dict], list[dict]]:
    """원본 행에 COLUMN_MAP을 적용하고 타입을 맞춘 뒤 (artisan_rows, product_rows)로 나눈다.

    입력은 상품마다 장인 정보가 붙은 평평한(denormalized) 행 목록이다.
    같은 artisan_id가 여러 상품에 나오면 장인은 첫 등장만 남긴다.
    """
    artisans_by_id: dict[int, dict] = {}
    products: list[dict] = []
    for source_row in raw:
        row = {COLUMN_MAP.get(key, key): value for key, value in source_row.items()}

        product = {}
        for field in PRODUCT_FIELDS:
            value = row.get(field)
            if field in INT_FIELDS:
                value = _cast_int(value)
            elif field in ARRAY_FIELDS:
                value = _cast_list(value)
            elif isinstance(value, str):
                value = (
                    value.strip() or None
                )  # 꼬리 공백이 등급 매칭·evidence를 오염시킨다
            product[field] = value
        products.append(product)

        artisan = {}
        for field in ARTISAN_FIELDS:
            value = row.get(field)
            if field == "artisan_id":
                value = _cast_int(value)
            elif isinstance(value, str):
                value = value.strip() or None
            artisan[field] = value
        aid = artisan["artisan_id"]
        if aid is not None and aid not in artisans_by_id:
            artisans_by_id[aid] = artisan

    return list(artisans_by_id.values()), products


def validate(artisans: list[dict], products: list[dict]) -> list[str]:
    """적재 전 검사. 오류 메시지 리스트를 돌려준다(빈 리스트면 정상).

    끝이 "(경고)"인 메시지는 진행 가능, 나머지는 중단 대상이다.
    """
    errors: list[str] = []

    for aid, count in Counter(a.get("artisan_id") for a in artisans).items():
        if count > 1:
            errors.append(f"artisan_id 중복: {aid} ({count}건)")
    for pid, count in Counter(p.get("product_id") for p in products).items():
        if count > 1:
            errors.append(f"product_id 중복: {pid} ({count}건)")

    known_artisans = {a.get("artisan_id") for a in artisans}
    for product in products:
        pid = product.get("product_id")
        if pid is None:
            errors.append("product_id 누락")
        # _cast_int가 파싱 실패 시 원본 문자열을 남겨 두므로 여기서 정수인지 확인한다.
        for field in ("product_id", "artisan_id", "price", "production_period_days"):
            value = product.get(field)
            if value is not None and not isinstance(value, int):
                errors.append(f"product {pid}: {field} 값이 정수가 아님 ('{value}')")
        if product.get("artisan_id") not in known_artisans:
            errors.append(
                f"product {pid}: 존재하지 않는 artisan_id {product.get('artisan_id')}"
            )
        if not (product.get("title") or "").strip():
            errors.append(f"product {pid}: title 누락")
        for field in ("price", "production_period_days"):
            value = product.get(field)
            if isinstance(value, int) and value < 0:
                errors.append(f"product {pid}: {field} 음수 ({value})")

    for artisan in artisans:
        aid = artisan.get("artisan_id")
        if not (artisan.get("name") or "").strip():
            errors.append(f"artisan {aid}: name 누락")
        if aid is not None and not isinstance(aid, int):
            errors.append(f"artisan: artisan_id 값이 정수가 아님 ('{aid}')")
        cert = artisan.get("certification_level")
        if cert and cert not in CERTIFICATION_LEVELS:
            errors.append(
                f"artisan {aid}: 알 수 없는 certification_level '{cert}' (경고)"
            )

    return errors


# ---------------------------------------------------------------------------
# 조립 (순수 함수)
# ---------------------------------------------------------------------------


def build_embedding_text(product: dict, artisan_intro: str | None) -> str:
    """임베딩할 텍스트를 명세 순서대로 이어붙인다.

    title + material + making_story + usage_care + 장인 introduction, 빈 값은 건너뛰고 " "로 join.
    """
    parts = [
        product.get("title"),
        product.get("material"),
        product.get("making_story"),
        product.get("usage_care"),
        artisan_intro,
    ]
    return " ".join(part.strip() for part in parts if part and part.strip())


_kiwi = None


def _get_kiwi():
    """Kiwi 인스턴스 싱글톤. 첫 호출에서만 로드한다(1~2초)."""
    global _kiwi
    if _kiwi is None:
        from kiwipiepy import Kiwi

        _kiwi = Kiwi()
    return _kiwi


def tokenize_ko(text: str) -> list[str]:
    """Kiwi 형태소 분석 후 CONTENT_TAG_PREFIXES로 시작하는 태그의 형태소만 남긴다.

    색인(build_search_text)과 나중의 질의 토큰화가 반드시 같은 함수를 써야 BM25가 맞물린다.
    """
    if not text:
        return []
    return [
        token.form
        for token in _get_kiwi().tokenize(text)
        if token.tag.startswith(CONTENT_TAG_PREFIXES)
    ]


def build_search_text(embedding_text: str) -> str:
    """tokenize_ko 결과를 공백으로 이어붙인 문자열. DB에는 리스트가 아니라 이 문자열을 저장하고,
    런타임에는 .split()으로 되돌려 BM25 코퍼스로 쓴다."""
    return " ".join(tokenize_ko(embedding_text))


def build_evidence(product: dict, cert: str | None) -> dict:
    """생성 단계가 근거로 삼는 값. 3키 고정 — craft_record 등 다른 키를 넣지 않는다.

    artisan_input: making_story + " " + usage_care 원문(요약·재작문 없이)
    verified:      certification_level 값
    ai_inference:  적재 시점엔 항상 None (생성 시점에 AI가 채움)
    """
    story = (product.get("making_story") or "").strip()
    care = (product.get("usage_care") or "").strip()
    artisan_input = " ".join(part for part in (story, care) if part)
    return {"artisan_input": artisan_input, "verified": cert, "ai_inference": None}


def build_rows(artisans: list[dict], products: list[dict]) -> list[dict]:
    """각 product_row에 embedding_text / search_text / evidence를 붙인다. 임베딩은 아직 안 한다."""
    intro_by_id = {a.get("artisan_id"): a.get("introduction") for a in artisans}
    cert_by_id = {a.get("artisan_id"): a.get("certification_level") for a in artisans}
    rows = []
    for product in products:
        aid = product.get("artisan_id")
        row = dict(product)
        row["embedding_text"] = build_embedding_text(product, intro_by_id.get(aid))
        row["search_text"] = build_search_text(row["embedding_text"])
        row["evidence"] = build_evidence(product, cert_by_id.get(aid))
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# 임베딩 (모델 사용)
# ---------------------------------------------------------------------------

_models: dict[str, object] = {}


def _get_model(name: str):
    if name not in _models:
        from sentence_transformers import SentenceTransformer

        _models[name] = SentenceTransformer(name)
    return _models[name]


def embed(texts: list[str], model_name: str | None = None) -> list:
    """SentenceTransformer로 정규화된 임베딩을 만든다. normalize_embeddings=True 필수
    (검색이 내적=코사인을 가정한다)."""
    name = model_name or os.environ.get("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
    return list(_get_model(name).encode(list(texts), normalize_embeddings=True))


def attach_embeddings(rows: list[dict], *, embed_fn=embed) -> None:
    """rows의 embedding_text를 한 번에 임베딩해서 각 row에 embedding / embedding_model을 채운다.
    embed_fn은 테스트에서 가짜 함수로 갈아끼울 수 있게 인자로 받는다."""
    model_name = os.environ.get("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
    vectors = embed_fn([row["embedding_text"] for row in rows], model_name=model_name)
    # strict=True: 모델이 rows와 다른 개수를 돌려주면 조용히 잘려 NULL 벡터로 적재되는 걸 막는다.
    for row, vector in zip(rows, vectors, strict=True):
        row["embedding"] = vector
        row["embedding_model"] = model_name


# ---------------------------------------------------------------------------
# UPSERT SQL (단일 출처 — 컬럼 목록에서 SQL과 파라미터를 함께 만든다)
# ---------------------------------------------------------------------------


def _artisan_columns() -> tuple[str, ...]:
    return ("artisan_id", "name", "certification_level", "introduction")


def _product_columns() -> tuple[str, ...]:
    return (
        "product_id",
        "artisan_id",
        "title",
        "category",
        "material",
        "price",
        "gift_theme",
        "purpose_tags",
        "color",
        "making_story",
        "usage_care",
        "production_period_days",
        "embedding_text",
        "embedding",
        "embedding_model",
        "search_text",
        "evidence",
    )


def _upsert_sql(table: str, columns: tuple[str, ...], pk: str) -> str:
    """INSERT ... VALUES %s ON CONFLICT (pk) DO UPDATE SET ... = EXCLUDED. ...

    execute_values가 %s 자리에 여러 튜플을 펼쳐 넣는다. 컬럼 목록에서 만들어 드리프트를 막는다.
    """
    col_list = ", ".join(columns)
    updates = ", ".join(f"{col} = EXCLUDED.{col}" for col in columns if col != pk)
    return (
        f"INSERT INTO {table} ({col_list}) VALUES %s "
        f"ON CONFLICT ({pk}) DO UPDATE SET {updates}"
    )


ARTISAN_UPSERT_SQL = _upsert_sql("artisans", _artisan_columns(), "artisan_id")
PRODUCT_UPSERT_SQL = _upsert_sql("products", _product_columns(), "product_id")


def _artisan_params(artisan: dict) -> tuple:
    return (
        artisan["artisan_id"],
        artisan.get("name"),
        artisan.get("certification_level"),
        artisan.get("introduction"),
    )


def _product_params(row: dict) -> tuple:
    from psycopg2.extras import Json

    return (
        row["product_id"],
        row.get("artisan_id"),
        row["title"],
        row.get("category"),
        row.get("material"),
        row.get("price"),
        row.get("gift_theme"),
        row.get("purpose_tags"),
        row.get("color"),
        row.get("making_story"),
        row.get("usage_care"),
        row.get("production_period_days"),
        row["embedding_text"],
        row.get("embedding"),
        row.get("embedding_model"),
        row["search_text"],
        Json(row["evidence"]),
    )


def upsert_all(conn, artisans: list[dict], product_rows: list[dict]) -> tuple[int, int]:
    """단일 트랜잭션으로 artisans(FK 때문에 먼저) → products를 UPSERT한다.

    돌려주는 값: (artisan 반영 건수, product 반영 건수).
    """
    from psycopg2.extras import execute_values

    with conn:  # noqa: SIM117 ## 성공 시 커밋, 예외 시 롤백
        with conn.cursor() as cur:
            if artisans:
                execute_values(
                    cur, ARTISAN_UPSERT_SQL, [_artisan_params(a) for a in artisans]
                )
            if product_rows:
                execute_values(
                    cur, PRODUCT_UPSERT_SQL, [_product_params(r) for r in product_rows]
                )
    return len(artisans), len(product_rows)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv):
    parser = argparse.ArgumentParser(description="미담 추천 카탈로그 데이터 적재")
    parser.add_argument("--file", required=True, help="적재할 CSV 또는 JSON 경로")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="DB·임베딩 모델 없이 읽기·검사·조립까지만 하고 결과 일부를 출력",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="앞 N건만 처리 (디버깅용)"
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)

    raw = read_source(args.file)
    if args.limit is not None:
        raw = raw[: args.limit]

    artisans, products = to_records(raw)
    errors = validate(artisans, products)
    hard_errors = [e for e in errors if not e.endswith("(경고)")]
    for error in errors:
        prefix = "경고: " if error.endswith("(경고)") else "오류: "
        print(prefix + error, file=sys.stderr)
    if hard_errors:
        print(f"{len(hard_errors)}건의 오류로 중단합니다.", file=sys.stderr)
        return 1

    rows = build_rows(artisans, products)

    if args.dry_run:
        print(
            f"[dry-run] 장인 {len(artisans)}명 / 상품 {len(rows)}건 조립 완료. 앞 3건:"
        )
        for row in rows[:3]:
            print(f"  - {row['product_id']} {row['title']}")
            print(f"    embedding_text: {row['embedding_text'][:60]}...")
            print(f"    search_text   : {row['search_text'][:60]}...")
            print(f"    evidence keys : {list(row['evidence'])}")
        return 0

    import psycopg2
    from pgvector.psycopg2 import register_vector

    conn = psycopg2.connect(os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
    try:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        conn.commit()
        register_vector(conn)  # vector 타입이 만들어진 뒤에 등록해야 한다

        print(f"임베딩 생성 중 ({len(rows)}건)...")
        attach_embeddings(rows)

        n_artisans, n_products = upsert_all(conn, artisans, rows)
        print(f"완료: 장인 {n_artisans}명 / 상품 {n_products}건 적재")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
