"""API 요청·응답 스키마 (Pydantic).

인터페이스 명세의 /ai/products, /ai/health 계약을 코드로 표현한다.
/ai/chat 스키마는 narrow_down 세션 구조 확정 후 추가한다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── /ai/products 요청 ──────────────────────────────────────────────


class ArtisanIn(BaseModel):
    """상품 등록 시 장인 정보. 명세 B-2 기준."""

    artisan_id: int
    business_name: str
    certification_level: str | None = None
    region: str | None = None


class ProductIn(BaseModel):
    """상품 등록 시 상품 정보. making_story·usage_care가 서사 핵심."""

    product_id: int
    name: str
    category_code: str | None = None
    subcategory_code: str | None = None
    material: str | None = None
    price: int | None = None
    color: str | None = None
    gift_theme: list[str] = Field(default_factory=list)
    purpose_tags: list[str] = Field(default_factory=list)
    making_story: str | None = None
    usage_care: str | None = None
    status: str | None = None


class ProductUpsertRequest(BaseModel):
    """POST /ai/products 본문 — 장인 + 상품 한 쌍."""

    artisan: ArtisanIn
    product: ProductIn


class ProductUpdateRequest(BaseModel):
    """PUT /ai/products/{id} 본문 — 변경된 상품 필드만 (부분 갱신)."""

    product: dict


# ── 응답 ───────────────────────────────────────────────────────────


class ProductUpsertResponse(BaseModel):
    success: bool = True
    product_id: int
    embedded: bool


class ProductUpdateResponse(BaseModel):
    success: bool = True
    product_id: int
    re_embedded: bool


class ProductDeleteResponse(BaseModel):
    success: bool = True
    product_id: int
    deleted: bool


class HealthResponse(BaseModel):
    status: str
    db: str
    embedder: str
