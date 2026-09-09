"""FastAPI 서버 — 미담 AI 챗봇의 /ai/* 엔드포인트.

현재 구현:
  GET    /ai/health              상태 확인
  POST   /ai/products            상품 등록 (저장 후 임베딩)
  PUT    /ai/products/{id}       상품 수정 (재임베딩)
  DELETE /ai/products/{id}       상품 삭제

미구현 (narrow_down 세션 입출력 구조 확정 후 추가):
  POST   /ai/chat                추천

실행:
  uvicorn app.main:app --host 0.0.0.0 --port 8000
  (로컬 호스팅 후 터널링으로 엔드포인트 노출)
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from app import products_service
from app.schemas import (
    HealthResponse,
    ProductDeleteResponse,
    ProductUpdateRequest,
    ProductUpdateResponse,
    ProductUpsertRequest,
    ProductUpsertResponse,
)

app = FastAPI(title="미담 AI 추천 챗봇", version="0.1.0")


@app.get("/ai/health", response_model=HealthResponse)
def health():
    """서비스 상태 (DB 연결·임베더)."""
    return products_service.health()


@app.post("/ai/products", response_model=ProductUpsertResponse)
def create_product(req: ProductUpsertRequest):
    """상품 등록 — 장인 upsert + 상품 저장 + 임베딩."""
    try:
        embedded = products_service.upsert_product(
            req.artisan.model_dump(), req.product.model_dump()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"등록 실패: {e}") from e
    return ProductUpsertResponse(product_id=req.product.product_id, embedded=embedded)


@app.put("/ai/products/{product_id}", response_model=ProductUpdateResponse)
def update_product(product_id: int, req: ProductUpdateRequest):
    """상품 수정 — 임베딩 대상 필드가 바뀌면 재임베딩."""
    try:
        re_embedded = products_service.update_product(product_id, req.product)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"수정 실패: {e}") from e
    return ProductUpdateResponse(product_id=product_id, re_embedded=re_embedded)


@app.delete("/ai/products/{product_id}", response_model=ProductDeleteResponse)
def delete_product(product_id: int):
    """상품 삭제."""
    try:
        deleted = products_service.delete_product(product_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"삭제 실패: {e}") from e
    if not deleted:
        raise HTTPException(status_code=404, detail=f"product_id {product_id} 없음")
    return ProductDeleteResponse(product_id=product_id, deleted=deleted)


# /ai/chat 은 narrow_down 세션 입출력 구조가 백엔드와 확정된 후 추가한다.
