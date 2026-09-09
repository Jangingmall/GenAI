"""FastAPI 서버 — 미담 AI 챗봇의 /ai/* 엔드포인트.

구현:
  GET    /ai/health              상태 확인
  POST   /ai/products            상품 등록 (저장 후 임베딩)
  PUT    /ai/products/{id}       상품 수정 (재임베딩)
  DELETE /ai/products/{id}       상품 삭제
  POST   /ai/chat                추천 대화

/ai/chat의 백엔드 쪽 계약(Notion "서비스 전체 api" 문서, 챗봇 메시지 전송 API 설명 참고):
"소비자 원문 메시지를 가공 없이 그대로 내부 AI파트 /ai/chat 으로 전달(최근 5~6턴 history
동봉)한다. AI가 반환한 product_id+reason을 백엔드가 상품 상세와 결합해 카드로 조립한다."

그래서 /ai/chat은:
- session_id·history를 우리가 만들지 않는다 — 백엔드가 매 요청에 실어 보내는 값을 그대로 쓴다.
- 상품명·가격·이미지·장인 정보를 채우지 않는다 — product_id·reason만 준다(백엔드가 조립).
- 다만 narrow_down("그중 더 싼 거") 판단에 필요한 candidates·filters는 백엔드가 안 들고 있는
  우리만의 내부 개념이라, session_id를 키로 이 서버가 직접 보관한다(app/session_store.py).

orchestrator.run()이 이미 chat·search_and_rank·fetch_prices·fetch_artisans·cache_lookup·
cache_store를 전부 주입 가능한 인자로 받게 설계돼 있다 — 그 패턴을 FastAPI Depends로 HTTP
계층까지 그대로 이어서, 테스트에서 실제 LLM·DB·임베딩 모델 없이 계약만 검증할 수 있게 한다.

실행:
  uvicorn app.main:app --host 0.0.0.0 --port 8000
  (로컬 호스팅 후 터널링으로 엔드포인트 노출)
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from app import products_service, session_store
from app.pipeline import orchestrator, semantic_cache
from app.pipeline.generate import _fetch_artisans, _fetch_prices
from app.pipeline.llm import chat_json
from app.run_recommend import recommend as _recommend
from app.schemas import (
    HealthResponse,
    ProductDeleteResponse,
    ProductUpdateRequest,
    ProductUpdateResponse,
    ProductUpsertRequest,
    ProductUpsertResponse,
)


def _default_chat():
    return chat_json


def _default_search_and_rank():
    return _recommend


def _default_fetch_prices():
    return _fetch_prices


def _default_fetch_artisans():
    return _fetch_artisans


def _default_cache_lookup():
    return semantic_cache.lookup


def _default_cache_store():
    return semantic_cache.store


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 실제 사용자의 첫 요청이 콜드 스타트 비용(프롬프트 캐시 미형성 + 임베딩 모델 미로딩,
    # 실측 10~30초)을 그대로 떠안지 않도록 서버가 요청을 받기 전에 미리 다 태운다
    # (app/pipeline/orchestrator.py:warmup 참고).
    orchestrator.warmup()
    yield


app = FastAPI(title="미담 AI 추천 챗봇", version="0.1.0", lifespan=lifespan)


# ── /ai/health, /ai/products — 상품 등록·수정·삭제 ──────────────────────


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


# ── /ai/chat — 추천 대화 ─────────────────────────────────────────────


class ChatRequest(BaseModel):
    session_id: str
    message: str
    # 백엔드 "챗봇 대화 히스토리 조회" API가 쓰는 실제 형식({"sender": "USER"|"ARTISAN"|
    # "ADMIN", "content": str, ...}) 그대로 받는다 — orchestrator.run()이 기대하는
    # {"role": "user"/"assistant", "content": str} 변환은 _to_pipeline_history가 한다.
    history: list[dict] = Field(default_factory=list)


def _to_pipeline_history(items: list[dict]) -> list[dict]:
    """백엔드의 {sender, content} 히스토리를 orchestrator.run()이 쓰는 {role, content}로 바꾼다.

    sender=="USER"만 소비자 발화고, 나머지(ARTISAN·ADMIN 등)는 챗봇 쪽 발화로 취급한다 —
    이 챗봇은 소비자 1명과 나누는 1:1 대화라 실질적으로 USER/그 외 둘로만 나뉜다.
    """
    return [
        {
            "role": "user" if item.get("sender") == "USER" else "assistant",
            "content": item.get("content", ""),
        }
        for item in items
    ]


class ProductOut(BaseModel):
    product_id: int
    reason: str


class ChatResponse(BaseModel):
    reply: str
    intent: str
    products: list[ProductOut]
    suggestions: list[str]


@app.post("/ai/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    chat_fn=Depends(_default_chat),
    search_and_rank=Depends(_default_search_and_rank),
    fetch_prices=Depends(_default_fetch_prices),
    fetch_artisans=Depends(_default_fetch_artisans),
    cache_lookup=Depends(_default_cache_lookup),
    cache_store=Depends(_default_cache_store),
) -> ChatResponse:
    state = session_store.get(request.session_id)
    previous_candidates = state["candidates"] if state else None
    previous_filters = state["filters"] if state else None

    result = orchestrator.run(
        request.message,
        _to_pipeline_history(request.history),
        chat=chat_fn,
        search_and_rank=search_and_rank,
        previous_candidates=previous_candidates,
        previous_filters=previous_filters,
        fetch_prices=fetch_prices,
        fetch_artisans=fetch_artisans,
        cache_lookup=cache_lookup,
        cache_store=cache_store,
    )

    # candidates·filters는 확정된 외부 응답 계약에 없는 내부 전용 필드다(orchestrator.run
    # docstring 참고) — 응답으로 내보내지 않고 다음 턴 narrow_down 재사용을 위해 세션
    # 저장소에만 남긴다.
    session_store.set(request.session_id, result["candidates"], result["filters"])

    return ChatResponse(
        reply=result["reply"],
        intent=result["intent"],
        products=result["products"],
        suggestions=result["suggestions"],
    )
