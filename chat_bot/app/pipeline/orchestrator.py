"""오케스트레이터 — ① intent → (A: search·ranking) → ⑤ generate. docs/b-metaprompt.md §2 S6 참고.

전체 흐름:
    classify_and_extract(message)              → 접점1 {query_text, filters, intent}
    app.run_recommend.recommend(접점1)          → 접점2 [{product_id, name, score, evidence}, ...] (A 담당)
    build_reply(message, 접점2, intent, filters) → {reply, products, suggestions}

intent는 접점1 결과에서 여기서 부착한다(§0: "합체 단계에서 오케스트레이터가 부착").
"""

from __future__ import annotations

from app.pipeline.generate import build_reply
from app.pipeline.intent import classify_and_extract
from app.pipeline.llm import chat_json
from app.run_recommend import recommend as _recommend


def run(
    message: str,
    history: list[dict] | None = None,
    *,
    think: bool = True,
    chat=chat_json,
    search_and_rank=_recommend,
) -> dict:
    """자연어 한 문장 → 최종 응답 계약 {reply, intent, products, suggestions}.

    chat·search_and_rank는 테스트에서 가짜 함수로 갈아끼울 수 있게 인자로 받는다.
    search_and_rank 기본값(A의 실제 search+ranking)은 PostgreSQL·임베딩 모델이 필요하다.
    """
    contact1 = classify_and_extract(message, history, chat=chat)
    candidates = search_and_rank(contact1)
    generated = build_reply(
        message, candidates, contact1["intent"], contact1["filters"], history, think=think, chat=chat
    )
    return {
        "reply": generated["reply"],
        "intent": contact1["intent"],
        "products": generated["products"],
        "suggestions": generated["suggestions"],
    }


# 단독 실행용: python -m app.pipeline.orchestrator "차 마실 때 쓸 것"
if __name__ == "__main__":
    import sys

    message = sys.argv[1] if len(sys.argv) > 1 else "차 마실 때 쓸 것"
    result = run(message)
    print(f'질의: "{message}"\n')
    print("reply:", result["reply"])
    print("intent:", result["intent"])
    print("products:")
    for p in result["products"]:
        print(f"  - {p['product_id']}: {p['reason']}")
    print("suggestions:")
    for s in result["suggestions"]:
        print(f"  - {s}")
