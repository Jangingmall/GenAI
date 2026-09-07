"""load_products.py 순수 함수 단위 테스트. DB·임베딩 모델은 쓰지 않는다.

확정 스키마 기준:
  artisans: artisan_id, business_name, certification_level, region
  products: product_id, artisan_id, name, category_code, subcategory_code, material,
            price, gift_theme[], purpose_tags[], color, making_story, usage_care, status
상품·장인이 파일로 분리된 정규화 구조라 to_records가 두 원본을 따로 받는다.

실행: python -m pytest tests/test_load_products.py -q
"""

import re

from app.ingest import load_products as lp

# ---------------------------------------------------------------------------
# to_records — PRODUCT_COLUMN_MAP/ARTISAN_COLUMN_MAP 적용 + 타입 캐스팅
# ---------------------------------------------------------------------------


def _raw_product_row(**over):
    row = {
        "product_id": "101",
        "artisan_id": "2001",
        "name": "자개 보석함",
        "category_code": "NACRE",
        "subcategory_code": "보석함",
        "material": "자개",
        "price": "320000",
        "gift_theme": "BIRTHDAY_60TH",
        "purpose_tags": "선물|다도",
        "color": "BROWN",
        "status": "ON_SALE",
        "making_story": "오동나무를 삼 년 말렸습니다.",
        "usage_care": "마른 천으로 닦으세요.",
    }
    row.update(over)
    return row


def _raw_artisan_row(**over):
    row = {
        "artisan_id": "2001",
        "business_name": "나전칠기장 김서영",
        "certification_level": "MASTER_CRAFTSMAN",
        "region": "통영",
    }
    row.update(over)
    return row


def test_to_records_casts_price_to_int():
    _artisans, products = lp.to_records([_raw_product_row()], [_raw_artisan_row()])
    assert products[0]["price"] == 320000
    assert isinstance(products[0]["price"], int)


def test_to_records_splits_array_fields():
    _, products = lp.to_records(
        [_raw_product_row(gift_theme="BIRTHDAY_60TH", purpose_tags="선물|다도")],
        [_raw_artisan_row()],
    )
    assert products[0]["gift_theme"] == ["BIRTHDAY_60TH"]
    assert products[0]["purpose_tags"] == ["선물", "다도"]


def test_to_records_color_is_scalar_not_array():
    # 확정 스키마: color는 배열이 아니라 스칼라(실데이터 실측: 상품 1건당 항상 단일값)
    _, products = lp.to_records([_raw_product_row(color="BROWN")], [_raw_artisan_row()])
    assert products[0]["color"] == "BROWN"


def test_to_records_empty_array_field_is_empty_list():
    _, products = lp.to_records([_raw_product_row(purpose_tags="")], [_raw_artisan_row()])
    assert products[0]["purpose_tags"] == []


def test_to_records_keeps_field_names_as_is():
    # 확정 스키마는 컬럼명이 실데이터와 같아 COLUMN_MAP이 비어 있다.
    artisans, products = lp.to_records([_raw_product_row()], [_raw_artisan_row()])
    assert products[0]["name"] == "자개 보석함"
    assert products[0]["category_code"] == "NACRE"
    assert products[0]["subcategory_code"] == "보석함"
    assert artisans[0]["business_name"] == "나전칠기장 김서영"
    assert artisans[0]["region"] == "통영"


def test_to_records_dedups_artisans_by_id():
    artisans, products = lp.to_records(
        [_raw_product_row(product_id="101"), _raw_product_row(product_id="102")],
        [_raw_artisan_row(), _raw_artisan_row()],  # 같은 artisan_id 2001 두 번
    )
    assert len(artisans) == 1
    assert len(products) == 2


def test_to_records_casts_ids_to_int():
    artisans, products = lp.to_records([_raw_product_row()], [_raw_artisan_row()])
    assert products[0]["product_id"] == 101
    assert products[0]["artisan_id"] == 2001
    assert artisans[0]["artisan_id"] == 2001


def test_to_records_blank_optional_number_is_none():
    _, products = lp.to_records([_raw_product_row(price="")], [_raw_artisan_row()])
    assert products[0]["price"] is None


def test_to_records_keeps_unparseable_int_as_string():
    # validate가 잡을 수 있도록 raise하지 않고 원본을 남긴다
    _, products = lp.to_records([_raw_product_row(price="32만원")], [_raw_artisan_row()])
    assert products[0]["price"] == "32만원"


def test_to_records_strips_text_fields():
    _, products = lp.to_records([_raw_product_row(name="  자개 보석함  ")], [_raw_artisan_row()])
    assert products[0]["name"] == "자개 보석함"


def test_to_records_strips_certification_level():
    artisans, _products = lp.to_records(
        [_raw_product_row()], [_raw_artisan_row(certification_level="MASTER_CRAFTSMAN ")]
    )
    assert artisans[0]["certification_level"] == "MASTER_CRAFTSMAN"


# ---------------------------------------------------------------------------
# validate — 적재 전 검사
# ---------------------------------------------------------------------------


def _art(**over):
    a = {
        "artisan_id": 2001,
        "business_name": "김서영",
        "certification_level": "MASTER_CRAFTSMAN",
        "region": "통영",
    }
    a.update(over)
    return a


def _prod(**over):
    p = {
        "product_id": 101,
        "artisan_id": 2001,
        "name": "보석함",
        "category_code": "NACRE",
        "price": 1000,
        "gift_theme": [],
        "purpose_tags": [],
        "color": "BROWN",
        "status": "ON_SALE",
        "making_story": "",
        "usage_care": "",
    }
    p.update(over)
    return p


def test_validate_ok_returns_empty_list():
    assert lp.validate([_art()], [_prod()]) == []


def test_validate_detects_dangling_artisan_id():
    errs = lp.validate([_art(artisan_id=2001)], [_prod(artisan_id=9999)])
    assert any("9999" in e for e in errs)


def test_validate_detects_duplicate_product_id():
    errs = lp.validate([_art()], [_prod(product_id=101), _prod(product_id=101)])
    assert any("101" in e for e in errs)


def test_validate_detects_duplicate_artisan_id():
    errs = lp.validate([_art(artisan_id=2001), _art(artisan_id=2001)], [_prod()])
    assert any("2001" in e for e in errs)


def test_validate_detects_missing_name():
    errs = lp.validate([_art()], [_prod(name="")])
    assert any("name" in e.lower() for e in errs)


def test_validate_detects_negative_price():
    errs = lp.validate([_art()], [_prod(price=-5)])
    assert any("price" in e.lower() for e in errs)


def test_validate_warns_unknown_certification_level():
    errs = lp.validate([_art(certification_level="명장")], [_prod()])
    assert any("명장" in e for e in errs)


def test_validate_allows_null_price():
    assert lp.validate([_art()], [_prod(price=None)]) == []


def test_validate_detects_missing_product_id():
    errs = lp.validate([_art()], [_prod(product_id=None)])
    assert any("product_id" in e.lower() for e in errs)


def test_validate_detects_missing_artisan_business_name():
    errs = lp.validate([_art(business_name="")], [_prod()])
    assert any("business_name" in e.lower() for e in errs)


def test_validate_detects_non_integer_price():
    # _cast_int가 파싱 못 한 값이 문자열로 넘어온 상황
    errs = lp.validate([_art()], [_prod(price="비쌈")])
    assert any("정수" in e for e in errs)


def test_unknown_certification_is_soft_warning():
    # "(경고)"로 끝나야 main이 중단이 아닌 진행으로 분류한다
    errs = lp.validate([_art(certification_level="명장")], [_prod()])
    warnings = [e for e in errs if e.endswith("(경고)")]
    assert warnings and all("명장" in w for w in warnings)


def test_missing_name_is_hard_error_not_warning():
    errs = lp.validate([_art()], [_prod(name="")])
    assert any("name" in e.lower() and not e.endswith("(경고)") for e in errs)


# ---------------------------------------------------------------------------
# build_embedding_text — name+카테고리(한글)+품목+재질+... 순으로 이어붙이기
# ---------------------------------------------------------------------------


def test_embedding_text_follows_order():
    product = {
        "name": "보석함",
        "category_code": "NACRE",
        "subcategory_code": "보석함",
        "material": "오동나무",
        "making_story": "삼 년 말렸다",
        "usage_care": "마른 천",
    }
    text = lp.build_embedding_text(product, "나전장입니다")
    assert text == "보석함 나전칠기 보석함 오동나무 삼 년 말렸다 마른 천 나전장입니다"


def test_embedding_text_translates_category_code_to_korean():
    for code, ko in lp.CATEGORY_KO.items():
        product = {"name": "N", "category_code": code}
        assert ko in lp.build_embedding_text(product, None)


def test_embedding_text_unknown_category_code_kept_as_is():
    product = {"name": "N", "category_code": "UNKNOWN_CODE"}
    assert "UNKNOWN_CODE" in lp.build_embedding_text(product, None)


def test_embedding_text_skips_blank_and_none():
    product = {"name": "보석함", "material": "", "making_story": None, "usage_care": "마른 천"}
    text = lp.build_embedding_text(product, None)
    assert text == "보석함 마른 천"


def test_embedding_text_name_only():
    assert lp.build_embedding_text({"name": "보석함"}, None) == "보석함"


# ---------------------------------------------------------------------------
# tokenize_ko / build_search_text
# ---------------------------------------------------------------------------


def test_search_text_is_space_joined_string():
    out = lp.build_search_text("오동나무를 삼 년 말렸습니다")
    assert isinstance(out, str)
    assert "  " not in out.strip()


def test_search_text_round_trips_with_tokenizer():
    text = "느티나무 판재를 짜맞춤으로 결구했습니다"
    assert lp.build_search_text(text).split() == lp.tokenize_ko(text)


def test_tokenize_ko_drops_particles():
    # "를", "으로" 같은 조사는 빠져야 한다
    tokens = lp.tokenize_ko("오동나무를 옻칠로 마감했습니다")
    assert "를" not in tokens
    assert "로" not in tokens
    assert any("오동나무" in t for t in tokens)


def test_tokenize_ko_deterministic():
    text = "자개를 실톱으로 오려 붙였습니다"
    assert lp.tokenize_ko(text) == lp.tokenize_ko(text)


# ---------------------------------------------------------------------------
# build_evidence — 3키 고정
# ---------------------------------------------------------------------------


def test_evidence_has_exactly_three_keys():
    ev = lp.build_evidence({"making_story": "a", "usage_care": "b"}, "MASTER_CRAFTSMAN")
    assert set(ev.keys()) == {"artisan_input", "verified", "ai_inference"}


def test_evidence_ai_inference_always_none():
    ev = lp.build_evidence({"making_story": "a", "usage_care": "b"}, "MASTER_CRAFTSMAN")
    assert ev["ai_inference"] is None


def test_evidence_verified_is_certification_level():
    ev = lp.build_evidence({"making_story": "a", "usage_care": "b"}, "YOUNG_CRAFTSMAN")
    assert ev["verified"] == "YOUNG_CRAFTSMAN"


def test_evidence_artisan_input_is_raw_concat():
    ev = lp.build_evidence({"making_story": "삼 년 말렸다", "usage_care": "마른 천"}, None)
    assert ev["artisan_input"] == "삼 년 말렸다 마른 천"


# ---------------------------------------------------------------------------
# build_rows — 조립만, 임베딩은 아직 안 함
# ---------------------------------------------------------------------------


def test_build_rows_attaches_derived_fields():
    artisans = [_art(artisan_id=2001)]
    products = [
        _prod(
            product_id=101,
            artisan_id=2001,
            name="보석함",
            making_story="삼 년 말렸다",
            usage_care="마른 천",
        )
    ]
    rows = lp.build_rows(artisans, products)
    assert rows[0]["embedding_text"].startswith("보석함")
    assert isinstance(rows[0]["search_text"], str)
    assert set(rows[0]["evidence"].keys()) == {"artisan_input", "verified", "ai_inference"}


def test_build_rows_does_not_embed():
    rows = lp.build_rows([_art()], [_prod()])
    assert "embedding" not in rows[0]
    assert "embedding_model" not in rows[0]


def test_build_rows_count_matches_products():
    products = [_prod(product_id=101), _prod(product_id=102), _prod(product_id=103)]
    assert len(lp.build_rows([_art()], products)) == 3


# ---------------------------------------------------------------------------
# attach_embeddings — embed 함수 1회 호출, 결과를 rows에 채움
# ---------------------------------------------------------------------------


def test_attach_embeddings_calls_embed_once():
    calls = []

    def fake_embed(texts, model_name=None):
        calls.append(list(texts))
        return [[0.0] * 1024 for _ in texts]

    rows = lp.build_rows([_art()], [_prod(product_id=101), _prod(product_id=102)])
    lp.attach_embeddings(rows, embed_fn=fake_embed)
    assert len(calls) == 1
    assert len(calls[0]) == 2


def test_attach_embeddings_fills_embedding():
    def fake_embed(texts, model_name=None):
        return [[0.1] * 1024 for _ in texts]

    rows = lp.build_rows([_art()], [_prod()])
    lp.attach_embeddings(rows, embed_fn=fake_embed)
    assert len(rows[0]["embedding"]) == 1024


def test_attach_embeddings_does_not_persist_model_on_row():
    # embedding_model은 확정 스키마에 없어 row에도 컬럼에도 남기지 않는다.
    def fake_embed(texts, model_name=None):
        return [[0.1] * 1024 for _ in texts]

    rows = lp.build_rows([_art()], [_prod()])
    lp.attach_embeddings(rows, embed_fn=fake_embed)
    assert "embedding_model" not in rows[0]


# ---------------------------------------------------------------------------
# UPSERT SQL 상수 — 파라미터 개수 정합 + 멱등 계약
# ---------------------------------------------------------------------------


def test_product_upsert_sql_has_on_conflict_do_update():
    assert re.search(
        r"on conflict\s*\(\s*product_id\s*\)\s*do update", lp.PRODUCT_UPSERT_SQL, re.IGNORECASE
    )


def test_artisan_upsert_sql_has_on_conflict_do_update():
    assert re.search(
        r"on conflict\s*\(\s*artisan_id\s*\)\s*do update", lp.ARTISAN_UPSERT_SQL, re.IGNORECASE
    )


def test_product_upsert_columns_match_row_params():
    # execute_values 템플릿의 컬럼 수 == 우리가 만드는 파라미터 튜플 길이
    cols = lp._product_columns()
    params = lp._product_params(lp.build_rows([_art()], [_prod()])[0])
    assert len(cols) == len(params)


def test_artisan_upsert_columns_match_row_params():
    cols = lp._artisan_columns()
    params = lp._artisan_params(_art())
    assert len(cols) == len(params)


def test_product_params_wraps_evidence_in_json():
    from psycopg2.extras import Json

    row = lp.build_rows([_art()], [_prod()])[0]
    params = lp._product_params(row)
    assert any(isinstance(p, Json) for p in params)


def test_product_columns_and_params_align_by_name():
    # 필드마다 다른 표식 값을 넣고 컬럼명↔값 대응을 확인한다.
    # 개수만 보는 테스트는 category_code↔material 순서 뒤바뀜을 못 잡는다.
    row = {
        "product_id": 1,
        "artisan_id": 2,
        "name": "N",
        "category_code": "C",
        "subcategory_code": "SC",
        "material": "M",
        "price": 3,
        "gift_theme": ["G"],
        "purpose_tags": ["PT"],
        "color": "CL",
        "making_story": "S",
        "usage_care": "U",
        "status": "ON_SALE",
        "embedding_text": "ET",
        "embedding": [0.0],
        "search_text": "ST",
        "evidence": {"artisan_input": "", "verified": None, "ai_inference": None},
    }
    paired = dict(zip(lp._product_columns(), lp._product_params(row)))
    assert paired["product_id"] == 1
    assert paired["artisan_id"] == 2
    assert paired["name"] == "N"
    assert paired["category_code"] == "C"
    assert paired["subcategory_code"] == "SC"
    assert paired["material"] == "M"
    assert paired["price"] == 3
    assert paired["gift_theme"] == ["G"]
    assert paired["purpose_tags"] == ["PT"]
    assert paired["color"] == "CL"
    assert paired["status"] == "ON_SALE"
    assert paired["making_story"] == "S"
    assert paired["usage_care"] == "U"
    assert paired["embedding_text"] == "ET"
    assert paired["search_text"] == "ST"


def test_artisan_columns_and_params_align_by_name():
    a = {
        "artisan_id": 9,
        "business_name": "N",
        "certification_level": "MASTER_CRAFTSMAN",
        "region": "이천",
    }
    paired = dict(zip(lp._artisan_columns(), lp._artisan_params(a)))
    assert paired["artisan_id"] == 9
    assert paired["business_name"] == "N"
    assert paired["certification_level"] == "MASTER_CRAFTSMAN"
    assert paired["region"] == "이천"


def test_product_upsert_set_clause_updates_non_pk_columns():
    # 재적재 시 어떤 컬럼이 갱신되는지를 잠근다. pk는 갱신 대상이 아니어야 한다.
    set_part = lp.PRODUCT_UPSERT_SQL.lower().split("do update set", 1)[1]
    assert "price = excluded.price" in set_part
    assert "embedding = excluded.embedding" in set_part
    assert "search_text = excluded.search_text" in set_part
    assert "product_id = excluded.product_id" not in set_part


def test_artisan_upsert_set_clause_excludes_pk():
    set_part = lp.ARTISAN_UPSERT_SQL.lower().split("do update set", 1)[1]
    assert "business_name = excluded.business_name" in set_part
    assert "artisan_id = excluded.artisan_id" not in set_part


# ---------------------------------------------------------------------------
# read_source — CSV 읽기, BOM 처리
# ---------------------------------------------------------------------------


def test_read_source_reads_csv(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8")
    assert lp.read_source(path) == [{"a": "1", "b": "2"}]


def test_read_source_strips_utf8_bom(tmp_path):
    path = tmp_path / "x.csv"
    path.write_bytes("product_id,name\n1,보석함\n".encode("utf-8-sig"))
    assert "product_id" in lp.read_source(path)[0]  # BOM이 키에 안 붙어야 한다
