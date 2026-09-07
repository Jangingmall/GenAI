"""⑤ 접점 2(랭킹 후보) → reply + 상품별 reason. docs/b-metaprompt.md §2 S3 참고.

프로토타입(generator.py)과의 차이:
  - suggestions 필드 제거(08.28 확정 응답 계약에 없음 — §3-3)
  - items → products 로 이름 변경(계약 필드명)
  - 접점 2 에는 price 가 없어 _format_candidates 에서 뺀다(프로토타입은 price 포함)

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

from pydantic import BaseModel, Field

from app.pipeline import prompts, taxonomy
from app.pipeline.llm import chat_json


class _ProductReason(BaseModel):
    product_id: int
    reason: str


class _GenerateOutput(BaseModel):
    # products에 default([])를 주면 JSON 스키마가 이 필드를 "생략 가능"으로 표시해, 모델이
    # reply만 쓰고 조기 종료해도 스키마상 유효해진다(Constraint Tax) — 기본값을 빼서 항상
    # 두 필드를 다 채우도록 강제한다. reply는 output_format상 1~3문장이라 500자면 충분히
    # 여유 있게 상한을 둬 자유 텍스트 필드의 무한 생성(반복 루프) 위험을 줄인다.
    reply: str = Field(max_length=500)
    products: list[_ProductReason]


_GENERATE_OUTPUT_SCHEMA = _GenerateOutput.model_json_schema()  # 매 요청마다 재계산할 필요 없다


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
        "후보의 evidence \"종목:\" 값을 문자 그대로 다시 확인하고, 조금이라도 다르면 "
        "products에서 제외하라."
    )


def _format_candidates(candidates: list[dict]) -> str:
    """프롬프트에 넣을 후보 목록 텍스트 블록. 접점 2(§0)엔 price 가 없어 종목·evidence만 담는다."""
    if not candidates:
        return "(검색 결과 없음)"
    blocks = []
    for c in candidates:
        ev = c.get("evidence") or {}
        category = _effective_category(c)
        label = taxonomy.CATEGORY_LABELS.get(category, category) if category else "정보 없음"
        lines = [
            f"- product_id: {c['product_id']}",
            f"  이름: {c['name']}",
            f"  종목: {label}",
            f"  장인 등급(verified): {ev.get('verified') or '정보 없음'}",
            f"  장인 서술(artisan_input): {ev.get('artisan_input') or '없음'}",
        ]
        blocks.append("\n".join(lines))
    return "\n".join(blocks)


def _drop_unknown_ids(items: list[dict], allowed_ids: set[int]) -> list[dict]:
    """후보에 없는 product_id를 모델이 만들어냈으면 제거한다(환각 최종 방어선)."""
    return [item for item in items if item["product_id"] in allowed_ids]


def _format_history(history: list[dict] | None) -> str:
    if not history:
        return ""
    lines = [
        f"{'소비자' if m['role'] == 'user' else '챗봇'}: {m['content']}" for m in history
    ]
    return "이전 대화:\n" + "\n".join(lines) + "\n\n"


def build_reply(
    message: str,
    candidates: list[dict],
    intent: str,
    history: list[dict] | None = None,
    *,
    think: bool = True,
    chat=chat_json,
) -> dict:
    """접점 2 후보 → {"reply": str, "products": [{"product_id", "reason"}]}.

    intent는 최종 응답에서 오케스트레이터(S6)가 부착한다 — 여기서는 안 담는다.
    think 기본값 True: 종목 환각(예: 다른 카테고리 상품을 엉뚱한 종목으로 답함) 위험이 있어
    근거기반 생성은 사실 일치가 표현 다양성보다 중요하다. 모델 비교(S5)에서 thinking
    효과를 재보려는 게 아니면 기본값 그대로 둔다.
    """
    candidates = _filter_by_category(candidates, message)
    user_content = (
        f"{_format_history(history)}소비자의 마지막 문장: {message}\n"
        f"분류된 intent: {intent}\n\n"
        f"[후보 상품]\n{_format_candidates(candidates)}"
        f"{_ambiguity_warning(message)}"
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

    allowed_ids = {c["product_id"] for c in candidates}
    products = _drop_unknown_ids(
        [p.model_dump() for p in output.products], allowed_ids
    )
    return {"reply": output.reply, "products": products}
