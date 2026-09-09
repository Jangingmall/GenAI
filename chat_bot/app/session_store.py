"""세션별 내부 상태(candidates·filters) 보관 — narrow_down 재사용에 필요하다.

백엔드가 session_id·history는 자기가 관리해서 매 요청에 실어 보내주지만(§ app/main.py 참고),
"직전 턴에 어떤 후보를 보여줬는지"·"어떤 하드필터가 이미 확정됐는지"는 orchestrator.run()
내부 개념이라 백엔드가 알지도, 들고 있지도 않는다 — 그래서 우리 AI 서버가 session_id를 키로
직접 보관한다.

TTL을 두는 이유: 백엔드가 세션을 DELETE해도 그 신호가 이 서버까지 온다는 보장이 아직 없다
(app/main.py 확인 필요 목록 참고) — 우리 쪽에서 자체적으로 정리하지 않으면 서버가 오래 떠
있을 때 메모리가 계속 쌓인다. semantic_cache.py와 같은 패턴(모듈 전역 dict + TTL + 최대
개수 제한 후 오래된 것부터 제거)을 그대로 따른다.
"""

from __future__ import annotations

import time

_TTL_SECONDS = 1800  # 대화 하나가 30분 안에는 끝난다고 가정 — 백엔드 세션 expiresInSeconds와
# 별개로, 우리 쪽 메모리 방어용 상한이다.
_MAX_ENTRIES = 500

_store: dict[str, dict] = {}


def get(session_id: str) -> dict | None:
    """직전 턴의 {"candidates", "filters"}를 돌려준다. 없거나 만료됐으면 None."""
    entry = _store.get(session_id)
    if entry is None:
        return None
    if time.time() - entry["ts"] > _TTL_SECONDS:
        del _store[session_id]
        return None
    return {"candidates": entry["candidates"], "filters": entry["filters"]}


def set(session_id: str, candidates: list[dict], filters: dict) -> None:
    """이번 턴에 쓴 candidates·filters를 저장해 다음 턴 narrow_down이 재사용할 수 있게 한다."""
    _store[session_id] = {"candidates": candidates, "filters": filters, "ts": time.time()}
    if len(_store) > _MAX_ENTRIES:
        oldest_id = min(_store, key=lambda k: _store[k]["ts"])
        del _store[oldest_id]
