"""① 자연어 → 접점 1(query_text·filters·intent). docs/b-metaprompt.md §2 S2 참고.

프로토타입(parser.py)과의 차이: 프로토타입은 max_price/min_price/purpose/recipient/vibe만
뽑지만, 여기서는 gift_theme·color 하드필터 추출을 추가한다. vibe·맥락은 query_text로 합친다.
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel, Field

from app.pipeline import prompts
from app.pipeline.llm import chat_json


class _RawIntent(BaseModel):
    """LLM이 직접 뱉는 원시 출력. 접점 1로 조립하기 전 단계.

    필드에 default를 주면 JSON 스키마가 "생략 가능"으로 표시돼, 모델이 일부 필드만 쓰고
    조기 종료해도 스키마상 유효해진다(Constraint Tax — query_text 하나만 채우고 나머지
    필드를 통째로 생략한 채 잡음 텍스트를 채우는 실패 양상이 있다). default를 빼서 모든
    필드를 항상 채우도록 강제하고, query_text는 자유 텍스트라 상한을 둬 폭주 생성을 막는다.
    """

    intent: str
    # "왜 추천했어?"류 이유 질문인지 — 어떤 상품을 설명할지(순번·"모두")는 코드로 확정
    # 판단하지만(extract_ordinal·is_all_request), "설명이 필요한 질문인가" 자체는 진짜
    # 자연어 뉘앙스 판단이라 LLM에 맡긴다. 새 LLM 호출을 추가하는 대신 이미 매 턴 도는
    # intent 분류 호출의 출력 필드 하나로 얹어서 속도 비용을 없앴다.
    wants_reason: bool
    # "선물", "뭔가 좋은거" 처럼 검색에 쓸 구체적인 단서(용도·받는사람·예산·재질·색상
    # 등)가 하나도 없는 product_search·gift_recommendation 요청인지 — 실측 확인:
    # 이런 문장도 임베딩 검색이 뭔가는 찾아와서(유사도 낮은 억지 매칭) 시스템이
    # 근거 없이 자신 있게 답해버리는 문제가 있었다. wants_reason과 같은 이유로 새
    # LLM 호출 없이 이 필드로 판단해 검색 전에 되묻는다.
    needs_clarification: bool
    # "다른 거 추천해줘"·"그거말고 또 없어?"처럼 새 종목·조건을 안 밝히고 그냥 다른
    # 상품을 원하는 narrow_down인지 — 실측 확인: 이런 문장은 새 하드필터가 없어서
    # 그냥 속성 질문("가격대 확인해줘")과 똑같이 취급돼 재검색을 안 했다. 그 결과
    # 카피라이터가 "다른 걸 찾았다"면서 직전과 완전히 같은 상품을 또 보여주는
    # 거짓 응답이 나갔다. wants_reason과 같은 이유로 새 LLM 호출 없이 이 필드로 잡는다.
    wants_alternatives: bool
    max_price: int | None
    min_price: int | None
    gift_theme: list[str]
    color: list[str]
    query_text: str = Field(max_length=200)
    # intent가 general_chat일 때만 채워지는, 소비자에게 바로 보여줄 답변. 이 필드 덕분에
    # 잡담 턴은 generate.py의 무거운 두 번째 LLM 호출(가격 환각 방지·종목 대조 등 상품
    # 관련 규칙 전체)을 아예 안 거친다 — 애초에 상품이 없는 턴에 그 규칙들은 불필요하다.
    chat_reply: str = Field(max_length=200)


_RAW_INTENT_SCHEMA = _RawIntent.model_json_schema()  # 매 요청마다 재계산할 필요 없다


def _price_to_won(text_or_num) -> int | None:
    """가격 표현을 원 단위 정수로 정규화한다.

    LLM 스키마가 정수를 요구하지만, "5만원"·"3만원대"처럼 원문이 그대로 새어나오는
    경우까지 방어적으로 처리한다("만" 단위 표기 → ×10000). 숫자를 못 찾으면 None.
    """
    if text_or_num is None:
        return None
    if isinstance(text_or_num, int):
        return text_or_num
    text = str(text_or_num).strip()
    if not text:
        return None
    man_match = re.search(r"(\d+(?:\.\d+)?)\s*만", text)
    if man_match:
        return int(float(man_match.group(1)) * 10000)
    num_match = re.search(r"\d+", text)
    return int(num_match.group()) if num_match else None


_MIN_PRICE_WORDS = ("이상", "부터", "넘는", "넘게", "초과")
_MAX_PRICE_WORDS = ("이하", "까지", "미만", "아래", "이내", "안으로")


def _price_direction(message: str) -> str | None:
    """메시지에 하한(min)·상한(max) 표현 중 한쪽만 있으면 그 방향을 돌려준다.

    실측 확인: "100만원 이상"처럼 명확한 하한 표현도 LLM이 습관적으로 max_price에
    넣는 경우가 있었다(프롬프트 규칙·전용 예시를 추가해도 재현 — 19개 기존 예시가
    전부 "이하"만 다뤄서 생긴 강한 편향으로 추정). 방향이 반대로 뽑히면 정반대
    가격대 상품을 보여주는 심각한 오류가 되므로, query_text와 같은 이유로 프롬프트
    신뢰 대신 코드로 확정한다. 두 방향이 같이 있으면(예: "3만원 이상 5만원 이하"
    범위 질문) 어느 숫자가 어느 쪽인지 코드로 안전하게 갈라낼 근거가 없어 None을
    반환하고 LLM 추출을 그대로 둔다.
    """
    has_min = any(w in message for w in _MIN_PRICE_WORDS)
    has_max = any(w in message for w in _MAX_PRICE_WORDS)
    if has_min and not has_max:
        return "min"
    if has_max and not has_min:
        return "max"
    return None


def _resolve_price_filters(
    max_price: int | None, min_price: int | None, message: str
) -> tuple[int | None, int | None]:
    """LLM이 뽑은 max_price/min_price를 메시지의 실제 방향과 맞춰 확정한다."""
    direction = _price_direction(message)
    if direction is None:
        return max_price, min_price
    value = max_price if max_price is not None else min_price
    if value is None:
        return max_price, min_price
    if direction == "min":
        return None, value
    return value, None


def _keep_known(values: list[str] | None, allowed: set[str]) -> list[str]:
    """LLM이 뱉은 값 중 allowed 목록에 있는 것만 남긴다(환각 방어)."""
    if not values:
        return []
    return [v for v in values if v in allowed]


def _to_contact1(
    raw: dict, *, gift_themes: set[str], colors: set[str], message: str
) -> dict:
    """raw LLM 출력 → 접점 1(§0) 조립 + enum 검증."""
    intent = raw.get("intent")
    if intent not in prompts.INTENT_VALUES:
        intent = "general_chat"
    gift_theme = _keep_known(raw.get("gift_theme"), gift_themes)
    color = _keep_known(raw.get("color"), colors)
    query_text = raw.get("query_text") or ""
    if intent in ("product_search", "gift_recommendation"):
        # 검색팀 실측: 축약·수식어 제거 없이 원문 그대로 넘길 때 임베딩 검색이 가장
        # 잘 된다. LLM이 뭘 뽑아내든(축약·수식어 누락 등) 여기서 원문으로 덮어써
        # 프롬프트 판단에 기대지 않고 코드로 확정한다. narrow_down은 이전 대화
        # 주제어를 이어 붙이는 별도 합성이 필요해(prompts.py 참고) 예외로 둔다.
        query_text = message

    max_price, min_price = _resolve_price_filters(
        _price_to_won(raw.get("max_price")),
        _price_to_won(raw.get("min_price")),
        message,
    )

    return {
        "query_text": query_text,
        "filters": {
            "max_price": max_price,
            "min_price": min_price,
            "gift_theme": gift_theme or None,
            "color": color or None,
        },
        "intent": intent,
        "wants_reason": bool(raw.get("wants_reason")),
        "needs_clarification": bool(raw.get("needs_clarification")),
        "wants_alternatives": bool(raw.get("wants_alternatives")),
        "chat_reply": raw.get("chat_reply") or "",
    }


# 최근 N턴(2N개 메시지)만 남긴다 — LangChain ConversationBufferWindowMemory와 같은
# 절단 방식. 요약 방식(ConversationSummaryMemory) 대신 이걸 고른 이유: 요약은 LLM 호출을
# 하나 더 추가해 응답 지연을 늘린다. 시스템 프롬프트+대화 맥락+후보 목록이 num_ctx(8192,
# llm.py 참고) 안에 여유 있게 들어가도록 K=3으로 보수적으로 잡았다.
_MAX_HISTORY_TURNS = 3


def _format_history(history: list[dict] | None) -> str:
    if not history:
        # "이전 대화:" 블록이 그냥 없는 것과 "첫 턴임을 명시"하는 건 다르다 — 전자는
        # 모델이 "이력 유무"를 스스로 추론해야 해서, 가격 조건이 있는 문장("5만원
        # 이하로 추천해줘")을 narrow_down 예시와 표면이 비슷하다는 이유로 잘못
        # 분류하는 사례가 실측됐다(첫 턴인데도). 구조적으로 명시해 추론 부담을 없앤다.
        return "[대화 시작 — 이전 턴 없음]\n\n"
    recent = history[-_MAX_HISTORY_TURNS * 2 :]
    lines = [
        f"{'소비자' if m['role'] == 'user' else '챗봇'}: {m['content']}" for m in recent
    ]
    return "이전 대화:\n" + "\n".join(lines) + "\n\n"


def _spacing_hint(message: str) -> str:
    """단어 중간에 우연히 들어간 공백으로 오분류되는 문제 방어용 참고 문자열.

    실측 확인된 버그: "도자기 추 천해줘"(공백 오타)를 LLM이 "추"+"천"(옷감이라는 별개
    단어)으로 잘못 쪼개 해석해 "도자기 천을 찾으시는군요"로 응답이 오염됨. PyKoSpacing
    같은 맞춤법 모델을 새로 얹는 방법도 검토했지만, 이 버그는 "특정 단어가 우연히 다른
    실존 단어로 쪼개져야만" 터지는 드문 케이스라 모델 로딩 비용(콜드스타트가 이미 문제인
    파이프라인에 하나 더 추가됨)을 감수할 만큼 흔하지 않다. 대신 공백을 다 제거한 원문을
    참고용으로 같이 보여줘 LLM이 스스로 원래 단어를 재구성해 판단하게 한다 — 별도
    의존성·모델 없이 문자열 처리 한 줄로 끝난다.
    """
    collapsed = message.replace(" ", "")
    if collapsed == message:
        return ""
    return f"\n(공백 제거 참고: {collapsed})"


def classify_and_extract(
    message: str, history: list[dict] | None = None, *, chat=chat_json
) -> dict:
    """자연어 한 문장 → 접점 1. chat은 테스트에서 가짜 함수로 주입한다.

    intent·generate 시스템 프롬프트를 하나로 합치거나 일부만 공유하는 방식도 실측해봤지만,
    완전 병합은 모델이 두 작업 규칙을 섞어 써서 intent 정확도가 떨어지는 회귀가 났고
    (예: "나전으로 만든 곡물독"이 unsupported가 아니라 product_search로 잘못 분류됨),
    일부(<role>)만 공유하는 절충안은 회귀는 없었지만 속도 이득이 측정 오차 수준이라 실효가
    없었다. 그래서 각자 독립된 INTENT_SYSTEM을 그대로 쓴다 — 응답 속도는 대신 Ollama 자체
    업데이트(캐시 알고리즘 개선)와 llm.py의 num_ctx 고정으로 개선했다.
    """
    user_content = (
        _format_history(history)
        + f"소비자의 마지막 문장: {message}"
        + _spacing_hint(message)
    )
    raw_json = chat(
        [
            {"role": "system", "content": prompts.INTENT_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        _RAW_INTENT_SCHEMA,
        think=False,
    )
    raw = json.loads(raw_json)
    return _to_contact1(
        raw, gift_themes=prompts.GIFT_THEMES, colors=prompts.COLORS, message=message
    )
