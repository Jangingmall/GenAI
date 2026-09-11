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


def _keep_known(values: list[str] | None, allowed: set[str]) -> list[str]:
    """LLM이 뱉은 값 중 allowed 목록에 있는 것만 남긴다(환각 방어)."""
    if not values:
        return []
    return [v for v in values if v in allowed]


# "제사용으로 쓸 만한 그릇" 같은 "-(으)로 [형용사 수식어] 명사" 문형에서, 로컬 9B 모델이
# 수식어(쓸 만한·좋은 등)를 요청 동사("찾아줘" 등)와 같은 부류의 "지워도 되는 말"로
# 착각해 같이 잘라내는 경우가 있다(실측 확인: 같은 프롬프트 규칙·예시를 줘도 문장
# 표면이 조금만 달라지면 50% 확률로 재발 — few-shot 예시를 늘려도 다음 변형에서 또
# 터지는 악순환이라, 프롬프트만으론 안정적으로 못 잡는다). 패턴 자체는 명확하므로
# extract_ordinal·is_all_request와 같은 이유로 여기서 코드로 확정 복원한다.
_ADJ_SUFFIX_WORDS = ("쓸 만한", "쓸만한", "좋은", "괜찮은", "무난한", "적당한")
_ADJ_SUFFIX_PATTERN = re.compile(
    r"(?P<head>\S+?)(?P<conn>으로|로)\s*(?P<adj>"
    + "|".join(re.escape(w) for w in _ADJ_SUFFIX_WORDS)
    + r")\s*(?P<tail>\S+)"
)


def _restore_adjective_suffix(message: str, query_text: str) -> str:
    """query_text가 원문의 "-(으)로 [형용사] 명사" 수식어를 놓쳤으면 원문에서 복원한다.

    수식어 낱말이 이미 query_text에 남아 있으면(정상 동작) 손대지 않는다. 복원은
    "head+adj+tail 조각을 새로 조립"하지 않고, 원문에서 tail이 끝나는 지점까지
    그대로 잘라 쓴다 — 조각을 새로 이어붙이면 head 앞에 있던 다른 단어(예: "손님
    접대용으로 좋은 다과상"의 "손님")가 유실된다.
    """
    m = _ADJ_SUFFIX_PATTERN.search(message)
    if not m:
        return query_text
    adj_normalized = m.group("adj").replace(" ", "")
    if adj_normalized in query_text.replace(" ", ""):
        return query_text
    return message[: m.end("tail")].strip()


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
        # narrow_down은 이전 대화 주제어를 query_text에 이어 붙이는 별도 로직을
        # LLM이 맡고 있어서(prompts.py 참고) 여기서 건드리면 그 맥락이 깨진다 —
        # 이 복원은 "이번 문장 자체가 새 주제인" 두 intent에만 적용한다.
        query_text = _restore_adjective_suffix(message, query_text)
    return {
        "query_text": query_text,
        "filters": {
            "max_price": _price_to_won(raw.get("max_price")),
            "min_price": _price_to_won(raw.get("min_price")),
            "gift_theme": gift_theme or None,
            "color": color or None,
        },
        "intent": intent,
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
