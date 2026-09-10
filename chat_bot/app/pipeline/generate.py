"""⑤ 접점 2(랭킹 후보) → allowed_ids(필터링 판단) + 공유 reply. docs/b-metaprompt.md §2 S3 참고.

LLM은 상품별 reason을 따로 안 쓰고, "이 후보 중 뭘 보여줄지"(allowed_ids)와 전체를
아우르는 문장 하나(reply)만 만든다 — HTTP 계약(products: [{product_id, reason}])은
그대로 두되, reason 자리엔 build_reply가 reply 텍스트를 복제해 채운다(reason은 카드에
안 보이는 로그용이라 상품마다 달라야 할 이유가 없고, 상품별로 새로 짓게 하면 출력
토큰이 늘어 응답이 느려진다 — _GenerateOutput 참고).

프로토타입(generator.py)과의 차이:
  - items → products 로 이름 변경(계약 필드명)

가격(price): 접점2(A가 만드는 검색 결과)엔 없지만, price는 products 테이블의 공유 컬럼이라
A의 검색·랭킹 로직과 무관하게 B가 product_id로 직접 조회할 수 있다(_fetch_prices). A의 코드는
건드리지 않는다 — 그냥 같은 DB의 다른 컬럼을 읽어오는 것뿐이다.

종목 대조 방어(_mentioned_category)는 이 파일 안에서만 쓴다 — docs/b-metaprompt.md §0이
category·재료·취향은 하드필터가 아니라 query_text로 처리하도록 이미 정해 놔서, 접점 1(intent.py)
계약에 category 필드를 추가하면 안 된다.

카테고리 사전(taxonomy.py)은 백엔드 실데이터에서 자동 생성한다(app/pipeline/build_taxonomy.py
참고) — 카테고리 체계는 POTTERY·ONGGI·NACRE·DYEING·WOOD·METAL 6종이다.

접점2(app/pipeline/search.py·ranking.py가 만듦)의 실제 출력 형식은
{product_id, name, score, evidence}이고 category는 포함되지 않는다(§3-1). 그래서
candidate의 상품명을 뜻하는 키는 name이고, category는 candidate에 없다는 전제로
name에서 역추정하는 폴백(_category_from_name)이 카테고리 대조의 주 방어선이다.
"""

from __future__ import annotations

import logging

import psycopg2
from pydantic import BaseModel, Field

from app.config import settings
from app.pipeline import prompts, taxonomy
from app.pipeline.llm import chat_json

logger = logging.getLogger(__name__)


class _GenerateOutput(BaseModel):
    # allowed_ids·suggestions에 default([])를 주면 JSON 스키마가 이 필드를 "생략 가능"으로
    # 표시해, 모델이 reply만 쓰고 조기 종료해도 스키마상 유효해진다(Constraint Tax) —
    # 기본값을 빼서 항상 세 필드를 다 채우도록 강제한다. reply는 output_format상 1~3문장이라
    # 500자면 충분히 여유 있게 상한을 둬 자유 텍스트 필드의 무한 생성(반복 루프) 위험을 줄인다.
    #
    # 상품별 reason을 따로 안 쓰고 allowed_ids(필터링 판단)+reply(공유 요약 문장) 둘로만
    # 답하게 한 이유: reason은 카드에 안 보이는 로그용인데도(§output_format 참고) 상품마다
    # 문장을 새로 짓게 하면 출력 토큰이 늘어 응답이 느려진다(실측: 상품 3개 기준 응답
    # 시간이 절반 가까이 줄어듦). products 필드(HTTP 계약)는 build_reply에서 이 reply
    # 텍스트를 그대로 복제해 채운다.
    reply: str = Field(max_length=500)
    allowed_ids: list[int]
    suggestions: list[str]


_GENERATE_OUTPUT_SCHEMA = (
    _GenerateOutput.model_json_schema()
)  # 매 요청마다 재계산할 필요 없다


def _mentioned_categories(message: str) -> set[str]:
    """소비자 발화에서 taxonomy.CATEGORY_SIGNALS로 매칭되는 카테고리 코드 전체 집합."""
    return {code for term, code in taxonomy.CATEGORY_SIGNALS.items() if term in message}


def _mentioned_category(message: str) -> str | None:
    """단일 카테고리만 명확히 언급됐을 때만 값을 준다.

    두 카테고리 신호가 동시에 언급되면(예: "옹기 소반") 어느 게 진짜 요청인지 코드로
    판단할 근거가 없어 None을 반환한다 — 후보를 함부로 지우지 않고, 대신
    _ambiguity_warning으로 LLM에게 직접 확인하라고 넘긴다.
    """
    matched = _mentioned_categories(message)
    return matched.pop() if len(matched) == 1 else None


def _category_from_name(name: str) -> str | None:
    """candidate에 category 필드가 없을 때(§3-1) 상품명에서 역추정하는 폴백.

    실데이터 상품명은 "재질+세부품목" 조합이라 name과 taxonomy 신호를 대조하면 카테고리를
    복원할 수 있다. 완벽한 보장은 아니지만, candidate에 category가 오지 않는 한 이게
    유일한 방어선이다. candidate에 category가 실제로 오면 이 함수는 호출되지 않는다
    (_effective_category).
    """
    matched = {code for term, code in taxonomy.CATEGORY_SIGNALS.items() if term in name}
    return matched.pop() if len(matched) == 1 else None


def _effective_category(candidate: dict) -> str | None:
    """candidate['category']가 있으면 그대로, 없으면 name 역추정값을 쓴다."""
    return candidate.get("category") or _category_from_name(candidate.get("name") or "")


def _filter_by_category(candidates: list[dict], message: str) -> list[dict]:
    """사용자가 카테고리를 명시했으면, 유효 카테고리가 다른 후보를 뺀다.

    유효 카테고리를 candidate['category']에서도 name 역추정에서도 못 정하면
    (_effective_category가 None) 그 후보는 건드리지 않는다.
    """
    mentioned = _mentioned_category(message)
    if mentioned is None:
        return candidates
    return [c for c in candidates if _effective_category(c) in (None, mentioned)]


def _ambiguity_warning(message: str) -> str:
    """카테고리 신호가 2개 이상 동시에 감지되면, 그 요청에만 붙는 동적 경고 한 줄을 만든다.

    실제로 존재하지 않는 카테고리 조합을 묻는 문장(서로 다른 종목의 재질·품목 단어가
    같은 문장에 있는 경우)일 가능성이 높다. 모든 요청의 시스템 프롬프트를 늘리는 대신,
    이 신호가 있을 때만 사용자 메시지 바로 옆에 경고를 붙여 LLM이 놓치기 어렵게 만든다.
    """
    matched = _mentioned_categories(message)
    if len(matched) < 2:
        return ""
    names = "·".join(sorted(taxonomy.CATEGORY_LABELS.get(c, c) for c in matched))
    return (
        f"\n\n[시스템 경고] 이 문장에서 서로 다른 카테고리({names})를 가리키는 단어가 "
        "동시에 감지됐다. 이런 조합은 카탈로그에 실제로 존재하지 않을 가능성이 높다 — "
        '후보의 evidence "종목:" 값을 문자 그대로 다시 확인하고, 조금이라도 다르면 '
        "products에서 제외하라."
    )


def _fetch_prices(product_ids: list[int]) -> dict[int, int]:
    """product_id → price. 접점2엔 가격이 없지만, products 테이블 자체엔 있는 공유 컬럼이라
    A의 검색·랭킹을 거치지 않고 B가 직접 조회한다(search.py·ranking.py는 안 건드린다).

    DB 연결·쿼리 실패는 빈 딕셔너리로 흡수한다 — 여기서 예외가 build_reply까지 전파되면
    채팅 호출 자체가 실패해서, _format_candidates가 원래 대비해 둔 "정보 없음" 대체
    경로(가격만 못 가져와도 상품 추천 자체는 계속하는 동작)에 도달하지 못한다.
    """
    if not product_ids:
        return {}
    try:
        conn = psycopg2.connect(settings.dsn())
    except psycopg2.Error:
        logger.exception("가격 조회용 DB 연결 실패")
        return {}
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT product_id, price FROM products WHERE product_id = ANY(%s)",
                (list(product_ids),),
            )
            return dict(cur.fetchall())
    except psycopg2.Error:
        logger.exception("가격 조회 쿼리 실패")
        return {}
    finally:
        conn.close()


def _fetch_artisans(product_ids: list[int]) -> dict[int, dict]:
    """product_id → {"business_name", "region"}. price와 같은 이유로 B가 직접 조회하고,
    DB 실패도 같은 이유로 빈 딕셔너리로 흡수한다(_fetch_prices 참고).
    """
    if not product_ids:
        return {}
    try:
        conn = psycopg2.connect(settings.dsn())
    except psycopg2.Error:
        logger.exception("장인 조회용 DB 연결 실패")
        return {}
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.product_id, a.business_name, a.region
                FROM products p JOIN artisans a ON p.artisan_id = a.artisan_id
                WHERE p.product_id = ANY(%s)
                """,
                (list(product_ids),),
            )
            return {
                product_id: {"business_name": name, "region": region}
                for product_id, name, region in cur.fetchall()
            }
    except psycopg2.Error:
        logger.exception("장인 조회 쿼리 실패")
        return {}
    finally:
        conn.close()


def _format_candidates(
    candidates: list[dict],
    prices: dict[int, int] | None = None,
    artisans: dict[int, dict] | None = None,
) -> str:
    """프롬프트에 넣을 후보 목록 텍스트 블록. prices·artisans가 없으면(예: DB 접속 실패) 정보 없음으로 표시."""
    if not candidates:
        return "(검색 결과 없음)"
    prices = prices or {}
    artisans = artisans or {}
    blocks = []
    for c in candidates:
        ev = c.get("evidence") or {}
        category = _effective_category(c)
        label = (
            taxonomy.CATEGORY_LABELS.get(category, category)
            if category
            else "정보 없음"
        )
        price = prices.get(c["product_id"])
        artisan = artisans.get(c["product_id"])
        lines = [
            f"- product_id: {c['product_id']}",
            f"  이름: {c['name']}",
            f"  종목: {label}",
            f"  가격: {price}원" if price is not None else "  가격: 정보 없음",
            (
                f"  장인: {artisan['business_name']} ({artisan['region']})"
                if artisan
                else "  장인: 정보 없음"
            ),
            f"  장인 등급(verified): {ev.get('verified') or '정보 없음'}",
            f"  장인 서술(artisan_input): {ev.get('artisan_input') or '없음'}",
        ]
        blocks.append("\n".join(lines))
    return "\n".join(blocks)


def _drop_unknown_ids(ids: list[int], candidate_ids: set[int]) -> list[int]:
    """후보에 없는 product_id를 모델이 만들어냈으면 제거한다(환각 최종 방어선)."""
    return [pid for pid in ids if pid in candidate_ids]


def _format_filters(filters: dict | None) -> str:
    """접점1에서 뽑힌 하드필터 요약. 후속 질문이 이미 아는 조건을 다시 묻지 않게 한다.

    하나도 없으면 그 사실 자체가 "특징을 거의 못 뽑았다"는 신호라 그대로 노출한다.
    """
    if not filters:
        return "(추출된 조건 없음)"
    parts = []
    min_price, max_price = filters.get("min_price"), filters.get("max_price")
    if min_price is not None and max_price is not None:
        parts.append(f"가격: {min_price}~{max_price}원")
    elif max_price is not None:
        parts.append(f"가격: {max_price}원 이하")
    elif min_price is not None:
        parts.append(f"가격: {min_price}원 이상")
    if filters.get("gift_theme"):
        parts.append(f"선물테마: {', '.join(filters['gift_theme'])}")
    if filters.get("color"):
        parts.append(f"색상: {', '.join(filters['color'])}")
    return "\n".join(parts) if parts else "(추출된 조건 없음)"


def _cap_suggestions(suggestions: list[str]) -> list[str]:
    """후속 질문 칩은 2~4어절짜리만 남기고 최대 3개까지 노출한다.

    output_format이 "2~4어절짜리 짧은 문구"라고 지시하지만, LLM이 가끔 완전한 문장을
    그대로 반환할 수 있다 — 개수만 제한하면 그런 문장이 칩 형식을 어긴 채 그대로
    나간다. 어절 수 검증을 코드에서 한 번 더 강제한다.
    """
    return [s for s in suggestions if 2 <= len(s.split()) <= 4][:3]


# intent.py와 같은 이유로 같은 값을 쓴다(app/pipeline/intent.py:_MAX_HISTORY_TURNS 참고).
_MAX_HISTORY_TURNS = 3


def _format_history(history: list[dict] | None) -> str:
    if not history:
        return ""
    recent = history[-_MAX_HISTORY_TURNS * 2 :]
    lines = [
        f"{'소비자' if m['role'] == 'user' else '챗봇'}: {m['content']}" for m in recent
    ]
    return "이전 대화:\n" + "\n".join(lines) + "\n\n"


def build_reply(
    message: str,
    candidates: list[dict],
    intent: str,
    filters: dict | None = None,
    history: list[dict] | None = None,
    *,
    query_text: str | None = None,
    think: bool = True,
    chat=chat_json,
    fetch_prices=_fetch_prices,
    fetch_artisans=_fetch_artisans,
) -> dict:
    """접점 2 후보 → {"reply", "products": [{"product_id", "reason"}], "suggestions": [str]}.

    filters는 접점1(intent.py)이 뽑은 하드필터 — 후속 질문(suggestions)이 이미 아는
    조건을 다시 묻지 않고, 조건을 하나도 못 뽑았을 땐 조건을 캐묻는 질문을 하도록 넘긴다.
    intent는 최종 응답에서 오케스트레이터(S6)가 부착한다 — 여기서는 안 담는다.

    query_text는 종목 대조(_filter_by_category)에 message와 함께 쓴다 — narrow_down
    후속 질문("가격대 확인해줘", "3만원 아래로 보여줘")은 종목 단어가 이번 message엔
    없고 intent.py가 이전 대화에서 이어 붙인 query_text에만 있을 수 있다(실측 확인:
    query_text 없이 message만 보면 종목 대조가 아예 안 걸려 다른 종목이 새어나감).

    fetch_prices·fetch_artisans는 테스트에서 가짜로 갈아끼울 수 있게 인자로 받는다(chat과
    같은 이유 — 유닛 테스트가 실제 DB 연결 없이 돌아가야 한다). 기본값은 PostgreSQL이
    필요하다.

    think 기본값 True: qwen3 계열로 되돌아갈 경우를 대비한 스위치다. 지금 쓰는
    gemma2:9b는 think 파라미터 자체를 지원하지 않아(llm.py:_THINK_SUPPORTED_PREFIX가
    "qwen3"만 허용) 이 값은 현재 아무 효과가 없다 — API 요청에 think 키 자체가 실리지
    않는다.
    """
    category_text = f"{message} {query_text}" if query_text else message
    candidates = _filter_by_category(candidates, category_text)
    candidate_ids = [c["product_id"] for c in candidates]
    prices = fetch_prices(candidate_ids)
    artisans = fetch_artisans(candidate_ids)
    # intent.py와 같은 이유(app/pipeline/intent.py:classify_and_extract 참고)로 독립된
    # GENERATE_SYSTEM을 그대로 쓴다 — 프롬프트 병합·부분 공유 둘 다 실측했지만 병합은
    # intent 정확도 회귀, 부분 공유는 속도 이득이 없어 둘 다 되돌렸다.
    user_content = (
        f"{_format_history(history)}소비자의 마지막 문장: {message}\n"
        f"분류된 intent: {intent}\n"
        f"[추출된 조건]\n{_format_filters(filters)}\n\n"
        f"[후보 상품]\n{_format_candidates(candidates, prices, artisans)}"
        f"{_ambiguity_warning(category_text)}"
    )

    raw = chat(
        [
            {"role": "system", "content": prompts.GENERATE_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        _GENERATE_OUTPUT_SCHEMA,
        think=think,
    )
    output = _GenerateOutput.model_validate_json(raw)

    # products(HTTP 계약 필드)는 상품별 reason이 따로 없으므로 reply를 그대로 복제해
    # 채운다 — 카드에 안 보이는 로그용이라 공유 문장이어도 정보 손실이 없다(§_GenerateOutput).
    allowed = _drop_unknown_ids(
        output.allowed_ids, {c["product_id"] for c in candidates}
    )
    products = [{"product_id": pid, "reason": output.reply} for pid in allowed]
    return {
        "reply": output.reply,
        "products": products,
        "suggestions": _cap_suggestions(output.suggestions),
        # 종목 대조를 통과한 후보 목록 — narrow_down 재사용(orchestrator.previous_candidates)의
        # 다음 턴 재료가 된다. 여기서 안 걸러진 채로 넘기면(원래 A의 미필터링 출력을 그대로
        # 재사용하면) 이번 턴에 걸러진 다른 종목 후보가 다음 턴에 그대로 재등장한다(실측 확인).
        "candidates": candidates,
    }
