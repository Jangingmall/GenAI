"""오케스트레이터 — ① intent → (A: search·ranking) → ⑤ generate. docs/b-metaprompt.md §2 S6 참고.

전체 흐름:
    classify_and_extract(message)              → 접점1 {query_text, filters, intent}
    app.run_recommend.recommend(접점1)          → 접점2 [{product_id, name, score, evidence}, ...] (A 담당)
    build_reply(message, 접점2, intent, filters) → {reply, product_ids, suggestions}

intent는 접점1 결과에서 여기서 부착한다(§0: "합체 단계에서 오케스트레이터가 부착").

대화 맥락이 없는 첫 턴은 의도분류 결과를 의미 기반 캐시(semantic_cache.py)에서 먼저
찾아본다 — 비슷한 질문("선물로 좋은 도자기 찾아줘" vs "선물용 도자기 추천해줘")이면
intent LLM 호출을 건너뛴다. 상품·가격은 캐싱하지 않고 항상 새로 계산한다(카탈로그
최신 상태 보장).

intent가 general_chat이면 검색·⑤ 호출을 둘 다 건너뛰고 접점1의 chat_reply를 그대로
반환한다 — 잡담엔 상품 근거 기반 규칙(⑤)이 애초에 불필요하고, 검색도 엉뚱한 결과를
끼워 넣을 위험만 있다(아래 run() 본문 참고).

narrow_down("그중 더 싼 거" 등)은 두 가지로 갈린다 — ① 직전에 보여준 후보에 대한 순수
속성 질문("가격대 확인해줘", "포장되나요?")은 새로 검색하지 않고 그 후보 그대로 답해야
한다(안 그러면 query_text가 "가장 저렴한 제품"처럼 원래 주제를 잃어 엉뚱한 종목이 나옴 —
실측 확인됨). ② 반대로 새 하드필터가 실제로 뽑힌 요청("3만 원 아래로")은 진짜 재검색해서
그 조건을 반영해야 한다 — 이걸 ①처럼 재사용해버리면 가격을 낮춰달라는 요청에 아무 변화
없는 답이 나간다. 그래서 "새 하드필터가 있는가"로 재사용/재검색을 가른다.
"""

from __future__ import annotations

from app.pipeline import semantic_cache
from app.pipeline.generate import (
    _fetch_artisans,
    _fetch_prices,
    build_reply,
    explain_product,
    explain_products,
    extract_ordinal,
    is_all_request,
    is_explain_request,
)
from app.pipeline.intent import classify_and_extract
from app.pipeline.llm import chat_json
from app.pipeline.taxonomy import CATEGORY_LABELS
from app.run_recommend import recommend as _recommend

# needs_clarification 되물음에 함께 낼 빠른 답변 칩 — 대화형 검색 연구(clarifying
# question 관련 문헌)에 따르면 열린 질문만 던지는 것보다 후보 답까지 같이 제시하는
# 편이 사용자 응답 부담을 줄인다. 카탈로그에 실제로 없는 옵션을 지어내면 안 되므로
# (같은 연구가 지적하는 흔한 실패), 실제 스키마 값(GIFT_THEMES 일부·taxonomy 카테고리)에
# 기반한 문구만 쓴다.
_CLARIFICATION_CHIPS_GIFT = ["부모님 선물", "생일 선물", "집들이 선물"]
_CLARIFICATION_CHIPS_PRODUCT = [
    f"{label}로 검색" for label in sorted(CATEGORY_LABELS.values())
][:3]

# "이 상품 설명해줘"류 요청에 순번을 못 찾았을 때 되묻는 고정 문구. 상수로 빼서
# _is_disambiguation_followup이 "직전 봇 턴이 이 되물음이었는가"를 문자열로 재확인할 수
# 있게 한다 — 문구를 바꿀 땐 이 상수만 바꾸면 양쪽(생성·판정)이 같이 맞는다.
_DISAMBIGUATION_PROMPT = "몇 번째 상품을 말씀하시는 건가요?"


def _last_user_message(history: list[dict] | None) -> str | None:
    """history에서 가장 최근 사용자 발화를 찾는다(narrow_down 재검색 주제어 보강용).

    intent.py가 "이전 대화 주제어 + 현재 문장"을 프롬프트만으로 합치도록 시켜봤지만
    실측 확인 결과 새 문장이 조금만 바뀌어도 주제어가 빠졌다(예: "도자기"·"찻잔"·
    "옹기" 전부 재현) — 프롬프트로 안정적으로 못 잡는 합성 작업이라 여기서 코드로
    확정 보강한다.
    """
    if not history:
        return None
    for turn in reversed(history):
        if turn.get("role") == "user":
            return turn.get("content") or None
    return None


def _is_disambiguation_followup(history: list[dict] | None) -> bool:
    """직전 봇 턴이 _DISAMBIGUATION_PROMPT 되물음이었는지 본다.

    "설명해줘"류 키워드 없이 "모두"·"1번"만 답해도(clarification subdialogue 원칙 —
    명확화 질문 다음 턴은 새 메시지로 재분류하지 않고 그 질문의 답으로 먼저 해석한다)
    이 함수가 True를 반환해 is_explain_request 없이도 설명 경로로 이어지게 한다.
    """
    if not history:
        return False
    last = history[-1]
    return last.get("role") == "assistant" and last.get("content", "").startswith(
        _DISAMBIGUATION_PROMPT
    )


def run(
    message: str,
    history: list[dict] | None = None,
    *,
    think: bool = True,
    chat=chat_json,
    search_and_rank=_recommend,
    previous_candidates: list[dict] | None = None,
    previous_filters: dict | None = None,
    previous_product_ids: list[int] | None = None,
    previous_query_text: str | None = None,
    fetch_prices=_fetch_prices,
    fetch_artisans=_fetch_artisans,
    cache_lookup=semantic_cache.lookup,
    cache_store=semantic_cache.store,
) -> dict:
    """자연어 한 문장 → 최종 응답 계약 {reply, intent, product_ids, suggestions} + candidates.

    chat·search_and_rank는 테스트에서 가짜 함수로 갈아끼울 수 있게 인자로 받는다.
    search_and_rank 기본값(A의 실제 search+ranking)은 PostgreSQL·임베딩 모델이 필요하다.

    candidates는 이번 턴에 실제로 쓴 후보 목록이다 — 확정된 외부 응답 계약(§0의 4개
    필드)엔 없는 내부용 필드다. app/main.py의 /ai/chat이 session_store.py를 통해
    session_id를 키로 이 값을 보관했다가 다음 턴 previous_candidates로 넘겨 대화
    연속성을 유지한다.

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

    previous_product_ids는 직전 턴에 실제로 화면에 보여준 상품 ID 목록이다(내부 전용,
    §0 계약엔 없음). "포장되나요?"·"가격대 확인해줘"처럼 순수 속성 질문이 이어지면
    narrow_down이 매번 같은 후보를 재사용해 매 턴 똑같은 카드가 또 뜨는 문제가 있었다
    (실측 확인) — 이번 턴 product_ids가 previous_product_ids와 완전히 같은 세트면 카드를
    비워서 반환한다(reply 텍스트만 답). 다르면(예: "포장되는 것만"으로 3개→1개로 좁혀짐)
    새 정보이므로 그대로 보여준다. explain_product·explain_products 경로는 사용자가
    명시적으로 상품을 다시 보여달라 요청한 것이라 이 억제를 적용하지 않는다.

    previous_query_text는 직전 턴이 실제로 검색에 쓴 최종 query_text다(내부 전용, §0
    계약엔 없음). narrow_down이 새 하드필터로 재검색할 때 이전 대화 주제어를 이어
    붙이는 근거로 쓴다 — "직전 사용자 발화 1개"만 기억하면 narrow_down이 연달아 여러
    번 이어질 때 두 번째 재검색부터 주제어가 다시 사라진다(실측 확인: "도자기 선물
    찾아줘"→"3만원 이하로"→"그럼 5만원으로 다시"에서 세 번째 턴에 "도자기"가 없어짐 —
    "직전 발화"가 "3만원 이하로"로 바뀌어버려서). previous_query_text는 매 턴 누적된
    최종 문장이라(예: 2턴엔 "도자기 선물 찾아줘 3만원 이하로") 여기서 계속 이어 붙이면
    몇 턴이 지나도 원래 주제어가 안 사라진다 — 대화형 검색에서 "직전 발화 하나만 보고
    다시 쓰기"보다 "누적된 문맥을 그대로 이어 붙이기"가 더 안정적이라는 건 TREC CAsT
    conversational search의 "Concat" 베이스라인과 같은 발상이다(주제 전환이 실제로
    있으면 위험하다고도 알려져 있지만, 여기선 intent가 이미 narrow_down으로 "같은
    주제의 연속"이라고 확정 판단한 경우에만 적용해 그 위험을 피한다).

    "왜 추천했어?"류는 is_explain_request(키워드 하드코딩)로 못 잡는다 — "어떤 상품을"
    설명할지(순번·"모두")는 코드로 확정 판단해야 안정적이지만, "설명이 필요한
    질문인가" 자체는 진짜 자연어 뉘앙스 판단이 필요해 intent.py의 wants_reason
    필드(LLM 판단)로 잡는다. 새 LLM 호출을 추가하는 대신 이미 매 턴 도는 intent
    분류 호출에 필드 하나를 얹었다 — classify_and_extract 이후에만 확인 가능하므로
    이 분기는 general_chat 처리 다음, 검색·narrow_down 분기 이전에 둔다.

    needs_clarification도 같은 방식이다 — "선물"처럼 product_search·gift_recommendation
    인데 검색에 쓸 단서(용도·받는사람·예산·재질·색상·종목)가 하나도 없으면, 검색을
    시도하지 않고 intent.py가 미리 만들어둔 chat_reply(되묻는 질문)를 그대로 반환한다
    (사용자 시나리오 E23: 의도 불명확 → 추가 질문으로 구체화). 실측 확인: 이런 문장도
    임베딩 검색은 유사도 낮은 상품을 억지로 찾아와서, 그대로 두면 근거 없이 자신 있게
    추천해버리는 문제가 있었다.
    """

    def _short_circuit(
        reply: str,
        intent: str,
        *,
        product_ids: list[int] | None = None,
        suggestions: list[str] | None = None,
        candidates: list[dict] | None = None,
        filters: dict | None = None,
        shown_product_ids: list[int] | None = None,
    ) -> dict:
        """검색을 새로 하지 않고 즉시 반환하는 조기 응답 8개 지점이 전부 같은 8개
        키 구조를 반복해서 여기로 모았다. 이번 턴에 검색을 안 했으니 candidates·
        filters·shown_product_ids·query_text는 대부분 "이전 값 그대로"가 맞다 —
        인자로 안 주면 그 기본값을 쓰고, 준 값이 있으면(예: 설명 대상 상품으로
        candidates를 좁힘) 그 값으로 덮어쓴다.
        """
        return {
            "reply": reply,
            "intent": intent,
            "product_ids": product_ids or [],
            "suggestions": suggestions or [],
            "candidates": (
                candidates if candidates is not None else (previous_candidates or [])
            ),
            "filters": filters if filters is not None else (previous_filters or {}),
            "shown_product_ids": (
                shown_product_ids
                if shown_product_ids is not None
                else (previous_product_ids or [])
            ),
            "query_text": previous_query_text or "",
        }

    # "이 상품 설명해줘"류 요청은 의도분류·검색을 거치지 않고 여기서 바로 처리한다 —
    # "몇 번째"를 LLM 자연어 판단에 맡기면 여러 후보가 남아있을 때 불안정하다(실측
    # 확인: 후보 전체를 설명하거나 엉뚱한 걸 고름). 순서 지정은 코드로 확정 판단하고,
    # 없으면 되묻는다(추가 LLM 호출 없이 즉시 응답).
    #
    # _is_disambiguation_followup도 같이 본다 — 직전 봇 턴이 "몇 번째예요?" 되물음이면,
    # 이번 메시지("모두"·"1번" 등)엔 "설명해"라는 단어가 없어도 그 질문에 대한 답으로
    # 먼저 해석한다(clarification subdialogue 원칙 — 명확화 질문 다음 턴을 새 메시지로
    # 재분류하면 안 된다는 실측 확인된 버그: "모두"가 일반 narrow_down으로 새 분류되면서
    # evidence 없는 뭉뚱그린 답이 나갔었다).
    if is_explain_request(message) or _is_disambiguation_followup(history):
        if not previous_candidates:
            return _short_circuit(
                "설명해 드릴 상품이 아직 없어요. 먼저 어떤 걸 찾으실지 말씀해 주세요!",
                "narrow_down",
                candidates=[],
                shown_product_ids=[],
            )
        if is_all_request(message):
            explained = explain_products(message, previous_candidates, chat=chat)
            return _short_circuit(
                explained["reply"],
                "narrow_down",
                product_ids=explained["product_ids"],
                suggestions=explained["suggestions"],
                candidates=previous_candidates,
                shown_product_ids=explained["product_ids"],
            )
        ordinal = extract_ordinal(message, len(previous_candidates))
        if ordinal is None or not (1 <= ordinal <= len(previous_candidates)):
            chips = [f"{i + 1}번" for i in range(len(previous_candidates))] + [
                "전체 설명"
            ]
            return _short_circuit(
                f"{_DISAMBIGUATION_PROMPT} ({'/'.join(chips)} 중에서 골라주세요)",
                "narrow_down",
                suggestions=chips,
                candidates=previous_candidates,
            )
        target = previous_candidates[ordinal - 1]
        explained = explain_product(message, target, chat=chat)
        return _short_circuit(
            explained["reply"],
            "narrow_down",
            product_ids=explained["product_ids"],
            suggestions=explained["suggestions"],
            candidates=previous_candidates,
            shown_product_ids=explained["product_ids"],
        )

    # 대화 맥락이 없는 첫 턴만 캐시 대상이다 — "가격대 확인해줘" 같은 narrow_down 문장은
    # 직전 대화에 따라 의미가 완전히 달라지는데, 문장만 보고 캐시를 맞히면 엉뚱한 이전
    # 대화의 결과가 섞여 나갈 위험이 크다(semantic_cache.py 모듈 docstring 참고).
    if not history:
        contact1 = cache_lookup(message)
        if contact1 is None:
            contact1 = classify_and_extract(message, history, chat=chat)
            cache_store(message, contact1)
    else:
        contact1 = classify_and_extract(message, history, chat=chat)

    if contact1["intent"] == "general_chat":
        # 잡담은 상품이 전혀 관련 없으므로 generate.py의 두 번째 LLM 호출(가격 환각 방지·
        # 종목 대조 등 상품 근거 기반 규칙 전체)을 아예 안 거친다 — classify_and_extract가
        # 이미 만들어둔 chat_reply를 그대로 쓴다. 검색도 안 한다: query_text가 빈 문자열
        # 이어도 검색 엔진(임베딩 유사도)은 뭔가는 반환해서(실측: "안녕하십니까?" → 옹기
        # 아닌 나전칠기 상품 3건) 잡담에 엉뚱한 상품이 낄 위험이 있다.
        return _short_circuit(
            contact1["chat_reply"], "general_chat", filters=contact1["filters"]
        )

    if contact1["intent"] in ("product_search", "gift_recommendation") and contact1.get(
        "needs_clarification"
    ):
        # "선물", "뭔가 좋은거 없나요"처럼 검색에 쓸 단서가 하나도 없으면 검색을
        # 건너뛰고 먼저 되묻는다 — 실측 확인: 이런 문장도 임베딩 검색이 유사도 낮은
        # 상품을 억지로 찾아와서, 근거 없이 자신 있게 추천해버리는 문제가 있었다
        # (사용자 시나리오 E23: 의도 불명확 → 추가 질문으로 구체화). 열린 질문만 던지지
        # 않고 후보 답까지 칩으로 같이 준다 — 대화형 검색 clarifying question 연구에
        # 따르면 이쪽이 사용자 응답 부담을 줄인다(직접 타이핑보다 탭 한 번).
        clarification_chips = (
            _CLARIFICATION_CHIPS_GIFT
            if contact1["intent"] == "gift_recommendation"
            else _CLARIFICATION_CHIPS_PRODUCT
        )
        return _short_circuit(
            contact1["chat_reply"],
            contact1["intent"],
            suggestions=clarification_chips,
            filters=contact1["filters"],
        )

    if contact1.get("wants_reason"):
        # "왜 추천했어?"류 — 어떤 상품을(순번·"모두") 설명할지는 코드로 확정 판단하지만
        # (파일 상단 is_explain_request 분기), "이유를 궁금해하는 질문인가" 자체는
        # intent 분류 LLM이 이미 판단해 넘겨준 신호를 그대로 쓴다. 순번을 안 짚었으므로
        # explain_products(전체 설명)로 답한다 — is_all_request 분기와 같은 처리.
        if not previous_candidates:
            return _short_circuit(
                "아직 추천해 드린 상품이 없어요. 먼저 어떤 걸 찾으실지 말씀해 주세요!",
                contact1["intent"],
                candidates=[],
                filters=contact1["filters"],
                shown_product_ids=[],
            )
        explained = explain_products(message, previous_candidates, chat=chat)
        return _short_circuit(
            explained["reply"],
            contact1["intent"],
            product_ids=explained["product_ids"],
            suggestions=explained["suggestions"],
            candidates=previous_candidates,
            filters=contact1["filters"],
            shown_product_ids=explained["product_ids"],
        )

    prev_filters = previous_filters or {}
    new_filters = contact1["filters"]
    # max_price·min_price는 0도 유효한 값이라(예: "0원짜리 무료 나눔") None인지로 판단해야
    # 한다 — 진리값 검사(truthy)를 쓰면 0이 falsy라 "새 조건 없음"으로 잘못 판정돼 재검색을
    # 건너뛴다. color는 빈 리스트/None이 "조건 없음"의 정상 표현이라 진리값 검사를 유지한다.
    price_changed = any(
        new_filters.get(k) is not None and new_filters.get(k) != prev_filters.get(k)
        for k in ("max_price", "min_price")
    )
    color_changed = bool(new_filters.get("color")) and new_filters.get(
        "color"
    ) != prev_filters.get("color")
    has_new_filter = price_changed or color_changed
    did_search = False
    if (
        contact1["intent"] == "narrow_down"
        and previous_candidates
        and not has_new_filter
    ):
        candidates = previous_candidates
    else:
        if contact1["intent"] == "narrow_down" and has_new_filter:
            # 새 하드필터가 있는 narrow_down 재검색 — query_text에 이전 대화
            # 주제어가 빠지면 엉뚱한 종목으로 재검색된다(§ run() 문서 참고).
            # previous_query_text(직전 턴이 실제로 쓴 누적 문장)를 우선 쓰고, 아직
            # 그 값이 없는 호출자를 위해 history의 직전 사용자 발화로 대체한다. LLM이
            # 이미 주제어를 살렸어도 무조건 이어 붙인다 — 단어가 겹쳐 살짝 중복돼도
            # 임베딩 검색엔 해가 없고(실측 확인), "이미 포함됐는지"를 문자열로 정확히
            # 판별할 방법이 없어 조건부로 하면 오히려 놓치는 경우가 생긴다.
            topic_context = previous_query_text or _last_user_message(history)
            if topic_context:
                contact1["query_text"] = (
                    f"{topic_context} {contact1['query_text']}".strip()
                )
        candidates = search_and_rank(contact1)
        did_search = True
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
    # 직전 턴에 보여준 것과 완전히 똑같은 세트면 카드를 다시 안 띄운다 — "가격대
    # 확인해줘"처럼 순수 속성 질문이 이어지면 매번 같은 카드가 또 뜨는 문제가 실측
    # 확인됐다. 부분적으로만 겹치거나(예: 3개→1개로 좁혀짐) 완전히 새 후보면 새
    # 정보이므로 그대로 보여준다 — set 비교라 순서 차이는 무시한다.
    raw_product_ids = generated["product_ids"]
    is_repeat = bool(previous_product_ids) and set(raw_product_ids) == set(
        previous_product_ids
    )
    return {
        "reply": generated["reply"],
        "intent": contact1["intent"],
        "product_ids": [] if is_repeat else raw_product_ids,
        "suggestions": generated["suggestions"],
        # build_reply가 종목 대조까지 마친 뒤 돌려준 candidates를 쓴다 — search_and_rank의
        # 원본(미필터링) 출력을 그대로 넘기면, 이번 턴에 걸러낸 다른 종목 후보가 다음 턴
        # narrow_down 재사용에서 그대로 다시 나타난다(실측 확인).
        "candidates": generated["candidates"],
        "filters": contact1["filters"],
        # 카드 억제 여부와 무관하게 "실제로 관련된 상품이 뭔지"는 그대로 넘긴다 — 다음
        # 턴 previous_product_ids 비교 기준이 화면 표시 여부에 따라 계속 바뀌면(억제된
        # 빈 배열을 기준으로 삼으면) 아무것도 안 바뀌었는데도 다음 턴에 카드가 다시
        # 뜨는 역효과가 난다.
        "shown_product_ids": raw_product_ids,
        # 실제로 검색에 쓰인 최종 query_text만 다음 턴 previous_query_text로 넘긴다 —
        # 후보를 재사용해 검색을 안 한 턴(did_search=False)의 query_text는 검색에
        # 안 쓰였으니 그대로 넘기면 주제어가 아닌 값으로 덮어써버릴 수 있다.
        "query_text": (
            contact1["query_text"] if did_search else (previous_query_text or "")
        ),
    }


def warmup(
    *,
    chat=chat_json,
    fetch_prices=_fetch_prices,
    fetch_artisans=_fetch_artisans,
    search_and_rank=_recommend,
) -> None:
    """서버 시작 시 한 번 호출해 콜드 스타트 비용 두 가지를 미리 다 내둔다.

    ① INTENT_SYSTEM·GENERATE_SYSTEM 프롬프트 캐시 — 실제 사용자가 오기 전까지 한 번도
    처리된 적이 없어서, 첫 턴은 두 프롬프트를 처음부터 다 읽는 콜드 비용을 그대로 낸다
    (실측: 10~25초 → 캐시 재사용 시 2~4초).
    ② 검색용 임베딩 모델(sentence-transformers) 최초 로딩 — 이것도 프로세스에서 한 번만
    일어나는데, 처음 겪으면 그 자체로 ~10초가 걸린다(실측 확인). ①만 예열하고 ②를
    빼먹으면, generate 계열 intent(예: product_search)에서 검색을 처음 호출하는 순간
    이 비용이 고스란히 남아 예열 효과가 반쪽만 난다(실측: LLM은 빨라졌는데 전체는 여전히
    28초 — 검색 임베딩 모델 로딩이 그대로 남아있었기 때문).

    search_and_rank가 기본으로 실제 DB·임베딩 모델을 쓰므로, 이 함수를 처음 부르면 그
    비용이 여기서 한 번에 다 발생한다 — 그 뒤로는 intent·generate·검색 셋 다 웜 상태다.
    candidates를 빈 배열로 둬서 build_reply가 fetch_prices/fetch_artisans로 인한 추가
    DB 연결 없이 끝난다(product_ids가 비어 있으면 바로 빈 딕셔너리를 반환한다).

    chat·fetch_prices·fetch_artisans·search_and_rank는 다른 함수들과 같은 이유로
    테스트에서 가짜로 갈아끼울 수 있게 인자로 받는다. app/main.py의 lifespan이 서버
    시작 시 한 번 호출한다.
    """
    classify_and_extract("워밍업", chat=chat)
    search_and_rank({"query_text": "워밍업", "filters": {}, "intent": "product_search"})
    build_reply(
        "워밍업",
        [],
        "general_chat",
        chat=chat,
        fetch_prices=fetch_prices,
        fetch_artisans=fetch_artisans,
    )


# 단독 실행용: python -m app.pipeline.orchestrator "차 마실 때 쓸 것"
if __name__ == "__main__":
    import sys

    message = sys.argv[1] if len(sys.argv) > 1 else "차 마실 때 쓸 것"
    result = run(message)
    print(f'질의: "{message}"\n')
    print("reply:", result["reply"])
    print("intent:", result["intent"])
    print("product_ids:", result["product_ids"])
    print("suggestions:")
    for s in result["suggestions"]:
        print(f"  - {s}")
