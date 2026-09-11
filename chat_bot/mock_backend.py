"""임시 mock 백엔드 — Notion "서비스 전체 api" 챗봇 API 4개를 최소 구현.

목적: 백엔드 관점에서 우리 실제 /ai/chat(app/main.py)을 호출했을 때 계약대로 동작하는지
실제 HTTP로 확인하는 것. 실제 백엔드가 아직 없어 임시로 만든 수동 확인용 스크립트다 —
실제 서비스 코드(app/ 아래)는 아니다.

전제: 실제 백엔드는 자기 상품 DB를 쓰겠지만, 지금은 이 리포의 Postgres(products·artisans
테이블)를 그대로 재사용해 카드를 조립한다.

실행 (터미널 3개, 전부 저장소 루트에서):
    .venv/bin/uvicorn app.main:app --port 8001       # 우리 AI 서버
    .venv/bin/uvicorn mock_backend:app --port 8000   # 이 파일
    curl로 /api/chatbot/sessions 부터 순서대로 호출(README 또는 대화 이력 참고)
"""

from __future__ import annotations

import uuid

import httpx
import psycopg2
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.pipeline import taxonomy

AI_CHAT_URL = "http://localhost:8001/ai/chat"

app = FastAPI()

_sessions: dict[str, dict] = {}  # session_id -> {"history": [...]}


class SessionCreateResponse(BaseModel):
    sessionId: str
    expiresInSeconds: int


class MessageRequest(BaseModel):
    message: str


def _fetch_product_cards(product_ids: list[int]) -> dict[int, dict]:
    """product_id -> 카드 조립에 필요한 필드. 실제 백엔드가 자기 상품 DB에서 할 일의 대역."""
    if not product_ids:
        return {}
    conn = psycopg2.connect(settings.dsn())
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.product_id, p.name, p.price, p.category_code,
                       a.business_name, a.region
                FROM products p JOIN artisans a ON p.artisan_id = a.artisan_id
                WHERE p.product_id = ANY(%s)
                """,
                (product_ids,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    cards = {}
    for product_id, name, price, category_code, artisan_name, region in rows:
        cards[product_id] = {
            "productId": product_id,
            "name": name,
            "price": price,
            "technique": taxonomy.CATEGORY_LABELS.get(category_code, category_code),
            "artisanName": artisan_name,
            "region": region,
            # 실제 CDN URL 패턴(data/장인몰_샘플_products_popular_top50.json에서 확인) — 이
            # product_id가 실제로 그 경로에 이미지가 있다는 보장은 없다, 구조 검증용 mock이다.
            "thumbnail": [
                {
                    "url": f"https://cdn.jangingmall.com/products/{product_id}/images/0_{w}w.webp",
                    "width": w,
                }
                for w in (320, 640, 1280)
            ],
        }
    return cards


@app.post("/api/chatbot/sessions", status_code=201)
def create_session() -> SessionCreateResponse:
    session_id = str(uuid.uuid4())
    _sessions[session_id] = {"history": []}
    return SessionCreateResponse(sessionId=session_id, expiresInSeconds=1800)


@app.post("/api/chatbot/sessions/{session_id}/messages")
def send_message(session_id: str, body: MessageRequest):
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    history = _sessions[session_id]["history"]
    # 백엔드 명세: "가공 없이 그대로 /ai/chat 으로 전달(최근 5~6턴 history 동봉)".
    resp = httpx.post(
        AI_CHAT_URL,
        json={
            "session_id": session_id,
            "message": body.message,
            "history": history[-6:],
        },
        timeout=180,
    )
    resp.raise_for_status()
    ai_result = resp.json()

    # AI가 상품마다 다른 reason을 안 주고 product_ids + 공유 reply로 준다. reply를 각
    # 상품의 reason에 그대로 복사하는 방식도 해봤지만, reply가 특정 상품 이름을 콕 집어
    # 말하는 문장을 포함하게 되면서(예: "청자 찻잔은 ~, 백자 머그는 ~") 다른 상품의
    # reason에 엉뚱한 상품 얘기가 들어가는 오류가 생겨 그만뒀다 — products[].reason은
    # 아예 채우지 않고, reply는 data.reply로만 내려서 프론트가 카드 목록 위에 한 줄로
    # 보여주게 한다.
    product_ids = ai_result["product_ids"]
    cards = _fetch_product_cards(product_ids)
    products = [cards[pid] for pid in product_ids if pid in cards]

    # 백엔드 "히스토리 조회" API 명세의 실제 필드명(sender: USER|ARTISAN|ADMIN)을 그대로
    # 쓴다 — 챗봇 자신의 답변을 나타낼 sender 값이 명세엔 없어 ADMIN으로 임시 표시한다
    # (확인 필요: 실제 백엔드가 챗봇 응답에 어떤 sender 값을 쓸지).
    history.append({"sender": "USER", "content": body.message})
    history.append({"sender": "ADMIN", "content": ai_result["reply"]})

    return {
        "success": True,
        "status": 200,
        "data": {
            "sessionId": session_id,
            "reply": ai_result["reply"],
            "intent": ai_result["intent"],
            "products": products,
            "suggestions": ai_result[
                "suggestions"
            ],  # 명세엔 없지만 실제 화면엔 필요(확인 필요 항목)
        },
    }


@app.get("/api/chatbot/sessions/{session_id}/messages")
def get_history(session_id: str):
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return {
        "success": True,
        "status": 200,
        "data": {"items": _sessions[session_id]["history"]},
    }


@app.delete("/api/chatbot/sessions/{session_id}", status_code=200)
def delete_session(session_id: str):
    _sessions.pop(session_id, None)
    return {"success": True, "status": 200, "data": None}
