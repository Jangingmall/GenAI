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


def _to_contact1(raw: dict, *, gift_themes: set[str], colors: set[str]) -> dict:
    """raw LLM 출력 → 접점 1(§0) 조립 + enum 검증."""
    intent = raw.get("intent")
    if intent not in prompts.INTENT_VALUES:
        intent = "general_chat"
    gift_theme = _keep_known(raw.get("gift_theme"), gift_themes)
    color = _keep_known(raw.get("color"), colors)
    return {
        "query_text": raw.get("query_text") or "",
        "filters": {
            "max_price": _price_to_won(raw.get("max_price")),
            "min_price": _price_to_won(raw.get("min_price")),
            "gift_theme": gift_theme or None,
            "color": color or None,
        },
        "intent": intent,
    }


# 최근 N턴(2N개 메시지)만 남긴다 — LangChain ConversationBufferWindowMemory와 같은
# 절단 방식. 요약 방식(ConversationSummaryMemory) 대신 이걸 고른 이유: 요약은 LLM 호출을
# 하나 더 추가하는데, 지금 이미 응답 지연(24~30초)이 문제라 지연을 더 늘리는 방향은 곤란하다.
# Ollama 실측 context_length=4096이고 GENERATE_SYSTEM만 이미 ~2920 토큰이라 여유가 크지
# 않아 K=3으로 보수적으로 잡았다.
_MAX_HISTORY_TURNS = 3


def _format_history(history: list[dict] | None) -> str:
    if not history:
        return ""
    recent = history[-_MAX_HISTORY_TURNS * 2 :]
    lines = [
        f"{'소비자' if m['role'] == 'user' else '챗봇'}: {m['content']}" for m in recent
    ]
    return "이전 대화:\n" + "\n".join(lines) + "\n\n"


def classify_and_extract(
    message: str, history: list[dict] | None = None, *, chat=chat_json
) -> dict:
    """자연어 한 문장 → 접점 1. chat은 테스트에서 가짜 함수로 주입한다."""
    user_content = _format_history(history) + f"소비자의 마지막 문장: {message}"
    raw_json = chat(
        [
            {"role": "system", "content": prompts.INTENT_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        _RAW_INTENT_SCHEMA,
        think=False,
    )
    raw = json.loads(raw_json)
    return _to_contact1(raw, gift_themes=prompts.GIFT_THEMES, colors=prompts.COLORS)
