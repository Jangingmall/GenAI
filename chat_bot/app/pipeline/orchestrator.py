"""오케스트레이터 — ① intent → (A: search·ranking) → ⑤ generate. docs/b-metaprompt.md §2 S6 참고.

전체 흐름:
    classify_and_extract(message)              → 접점1 {query_text, filters, intent}
    app.run_recommend.recommend(접점1)          → 접점2 [{product_id, name, score, evidence}, ...] (A 담당)
    build_reply(message, 접점2, intent, filters) → {reply, products, suggestions}

intent는 접점1 결과에서 여기서 부착한다(§0: "합체 단계에서 오케스트레이터가 부착").

narrow_down("그중 더 싼 거" 등)은 두 가지로 갈린다 — ① 직전에 보여준 후보에 대한 순수
속성 질문("가격대 확인해줘", "포장되나요?")은 새로 검색하지 않고 그 후보 그대로 답해야
한다(안 그러면 query_text가 "가장 저렴한 제품"처럼 원래 주제를 잃어 엉뚱한 종목이 나옴 —
실측 확인됨). ② 반대로 새 하드필터가 실제로 뽑힌 요청("3만 원 아래로")은 진짜 재검색해서
그 조건을 반영해야 한다 — 이걸 ①처럼 재사용해버리면 가격을 낮춰달라는 요청에 아무 변화
없는 답이 나간다. 그래서 "새 하드필터가 있는가"로 재사용/재검색을 가른다.
"""

from __future__ import annotations

from app.pipeline.generate import _fetch_artisans, _fetch_prices, build_reply
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
    previous_candidates: list[dict] | None = None,
    previous_filters: dict | None = None,
    fetch_prices=_fetch_prices,
    fetch_artisans=_fetch_artisans,
) -> dict:
    """자연어 한 문장 → 최종 응답 계약 {reply, intent, products, suggestions} + candidates.

    chat·search_and_rank는 테스트에서 가짜 함수로 갈아끼울 수 있게 인자로 받는다.
    search_and_rank 기본값(A의 실제 search+ranking)은 PostgreSQL·임베딩 모델이 필요하다.

    candidates는 이번 턴에 실제로 쓴 후보 목록이다 — 확정된 외부 응답 계약(§0의 4개
    필드)엔 없는 내부용 필드다. FastAPI 서버가 아직 없어 세션을 어디에 보관할지
    확정 전이라, 지금은 호출부(예: chat_repl.py)가 이 값을 다음 턴 previous_candidates로
    직접 넘겨 대화 연속성을 유지하는 임시 방편이다. 실제 서버가 생기면 세션 저장소가
    이 역할을 대신할 수 있다.

    previous_filters도 같은 이유로 내부 전용이다 — intent.py는 이전 턴에 이미 확정된
    조건(예: "집들이"→gift_theme=HOUSEWARMING)을 매 턴 계속 다시 채워 넣는다(맥락을
    기억하는 정상 동작). 그래서 "필터가 있는가"만으로는 "이번 턴에 새로 생긴 조건인가"를
    구분 못 한다 — 실측 확인: "가격대 확인해줘"에 이전 턴부터 있던 gift_theme이 그대로
    다시 채워지면서 새 조건으로 오인돼 불필요하게 재검색되고 후보가 바뀌었다. 이전 턴
    필터와 비교해 "값이 달라진 것"만 새 조건으로 센다.

    gift_theme은 이 비교에서 아예 뺀다 — search.py 자체 문서(§ 접점1 입력 형식)에 이미
    "부스팅(하드필터 아님)"이라고 명시돼 있다. 순위에 살짝 가점만 주는 값이라 새로
    검색해도 후보 자체가 크게 안 바뀌는데, gift_theme 추출은 턴마다 미묘하게 흔들릴 수
    있어(실측: 완전히 같은 문장인데 한 번은 뽑히고 한 번은 안 뽑힘) 이걸 "새 조건"
    판단에 넣으면 노이즈로 불필요한 재검색이 계속 발생한다. max_price·min_price·color만
    진짜 하드필터(SQL WHERE)라 이 셋만 본다.
    """
    contact1 = classify_and_extract(message, history, chat=chat)
    prev_filters = previous_filters or {}
    has_new_filter = any(
        contact1["filters"].get(k) and contact1["filters"].get(k) != prev_filters.get(k)
        for k in ("max_price", "min_price", "color")
    )
    if contact1["intent"] == "narrow_down" and previous_candidates and not has_new_filter:
        candidates = previous_candidates
    else:
        candidates = search_and_rank(contact1)
    generated = build_reply(
        message,
        candidates,
        contact1["intent"],
        contact1["filters"],
        history,
        query_text=contact1["query_text"],
        think=think,
        chat=chat,
        fetch_prices=fetch_prices,
        fetch_artisans=fetch_artisans,
    )
    return {
        "reply": generated["reply"],
        "intent": contact1["intent"],
        "products": generated["products"],
        "suggestions": generated["suggestions"],
        # build_reply가 종목 대조까지 마친 뒤 돌려준 candidates를 쓴다 — search_and_rank의
        # 원본(미필터링) 출력을 그대로 넘기면, 이번 턴에 걸러낸 다른 종목 후보가 다음 턴
        # narrow_down 재사용에서 그대로 다시 나타난다(실측 확인).
        "candidates": generated["candidates"],
        "filters": contact1["filters"],
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
