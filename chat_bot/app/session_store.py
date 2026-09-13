"""세션별 내부 상태(candidates·filters·product_ids) 보관 — narrow_down 재사용과
카드 중복 노출 억제(orchestrator.run의 previous_product_ids)에 필요하다.

백엔드가 session_id·history는 자기가 관리해서 매 요청에 실어 보내주지만(§ app/main.py 참고),
"직전 턴에 어떤 후보를 보여줬는지"·"어떤 하드필터가 이미 확정됐는지"는 orchestrator.run()
내부 개념이라 백엔드가 알지도, 들고 있지도 않는다 — 그래서 우리 AI 서버가 session_id를 키로
직접 보관한다.

TTL을 두는 이유: 백엔드가 세션을 DELETE해도 그 신호가 이 서버까지 온다는 보장이 없다 —
우리 쪽에서 자체적으로 정리하지 않으면 서버가 오래 떠 있을 때 메모리가 계속 쌓인다.
semantic_cache.py와 같은 패턴(모듈 전역 dict + TTL + 최대 개수 제한 후 오래된 것부터
제거)을 그대로 따른다.
"""

from __future__ import annotations

import threading
import time

_TTL_SECONDS = (
    1800  # 대화 하나가 30분 안에는 끝난다고 가정 — 백엔드 세션 expiresInSeconds와
)
# 별개로, 우리 쪽 메모리 방어용 상한이다.
_MAX_ENTRIES = 500

_store: dict[str, dict] = {}
# FastAPI는 동기 라우트를 스레드 풀에서 돌려서, 서로 다른 요청이 동시에 get/set을 호출할 수
# 있다 — 락 없이는 get의 만료 삭제와 set의 최대 개수 제거가 동시에 같은 딕셔너리를 건드려
# KeyError/RuntimeError로 죽을 수 있다. get·set 각각 통째로(삭제·제거 단계까지) 락을 잡는다.
_lock = threading.Lock()


def get(session_id: str) -> dict | None:
    """직전 턴의 {"candidates", "filters", "product_ids", "query_text"}를 돌려준다.
    없거나 만료됐으면 None."""
    with _lock:
        entry = _store.get(session_id)
        if entry is None:
            return None
        if time.time() - entry["ts"] > _TTL_SECONDS:
            del _store[session_id]
            return None
        return {
            "candidates": entry["candidates"],
            "filters": entry["filters"],
            "product_ids": entry["product_ids"],
            "query_text": entry["query_text"],
        }


def set(
    session_id: str,
    candidates: list[dict],
    filters: dict,
    product_ids: list[int],
    query_text: str,
) -> None:
    """이번 턴에 쓴 candidates·filters·product_ids·query_text를 저장한다.

    candidates·filters는 다음 턴 narrow_down 재사용에, product_ids는 orchestrator.run의
    previous_product_ids(카드 중복 노출 억제)에 쓰인다. product_ids엔 orchestrator가
    반환하는 shown_product_ids(화면 노출 여부와 무관한 실제 관련 상품)를 넘겨야 한다 —
    억제돼서 비어 나온 product_ids를 그대로 저장하면 다음 턴 비교 기준이 사라져 버린다.

    query_text는 orchestrator.run이 반환하는 값(이번 턴이 실제로 검색에 쓴 최종
    문장)을 그대로 저장한다 — narrow_down이 새 하드필터로 여러 턴 연속 재검색될 때
    이전 대화 주제어가 안 사라지게 다음 턴 previous_query_text로 이어 붙이는 용도다.
    """
    with _lock:
        _store[session_id] = {
            "candidates": candidates,
            "filters": filters,
            "product_ids": product_ids,
            "query_text": query_text,
            "ts": time.time(),
        }
        if len(_store) > _MAX_ENTRIES:
            oldest_id = min(_store, key=lambda k: _store[k]["ts"])
            del _store[oldest_id]
