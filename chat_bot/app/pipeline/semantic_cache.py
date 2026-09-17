"""의도분류 결과의 의미 기반 캐시 — 비슷한 질문이면 intent LLM 호출을 건너뛴다.

실측으로 확인한 두 가지 전제 위에서 설계했다:
1. intent 분류 호출 하나가 콜드 10~15초/캐시 재사용 2~4초를 차지한다 — 반복되는
   비슷한 질문("선물로 좋은 도자기 찾아줘" vs "선물용 도자기 추천해줘")마다 이 비용을
   또 내는 건 낭비다.
2. 검색·가격 조회는 실측 결과 웜 상태에서 0.05초로 무시할 수준이다 — 그래서 캐시는
   "의도분류 결과(intent·filters·query_text)"만 저장하고, 상품 추천·가격은 항상 캐시
   조회 이후 그 자리에서 새로 계산한다. 상품·가격까지 캐싱하면 카탈로그가 바뀌어도
   옛날 가격을 계속 보여주는 위험이 있는데, 그건 "가격은 절대 지어내지 않는다"는
   원칙과 정면으로 충돌한다.

대화 맥락이 있는 턴(narrow_down 등)은 캐싱 대상에서 뺀다 — "가격대 확인해줘"처럼 문장
자체는 비슷해 보여도 의미가 직전 대화에 따라 완전히 달라지는 경우가 많아서, 맥락 없이
문장만 보고 캐시를 맞히면 엉뚱한 이전 대화의 캐시가 섞여 나갈 위험이 크다.
"""

from __future__ import annotations

import threading
import time

from app.pipeline.embedding import embed_query

_SIMILARITY_THRESHOLD = 0.82  # 실측(실제 임베딩 모델)으로 캘리브레이션한 값 — 같은 뜻
# 문장 쌍은 0.84~0.96, 다른 질문 쌍은 0.36~0.74로 갈렸다("선물로 좋은 도자기 찾아줘" vs
# "선물용 도자기 추천해줘" 0.88, vs "집들이 선물로 옹기 찾아줘"(다른 종목) 0.74). 두 구간
# 사이(0.74~0.84)에 여유를 두고 0.82로 잡았다 — 처음엔 0.93으로 잡았다가 실측해보니
# 같은 뜻 문장 쌍조차 대부분 0.93 밑이라 캐시가 전혀 안 맞아서(실측 확인) 다시 잡았다.
_TTL_SECONDS = 600  # 카탈로그 변경 반영 지연을 짧게 묶어두기 위한 상한
_MAX_ENTRIES = 200  # 무한정 커지지 않게 제한 — 다 차면 오래된 것부터 버림(FIFO)

_cache: list[dict] = []
# FastAPI는 동기 라우트를 스레드 풀에서 돌려서(app/main.py의 chat()이 plain def),
# 서로 다른 요청이 동시에 lookup·store를 호출할 수 있다 — session_store.py의 같은
# 모양 문제(app/session_store.py:27-29)를 이미 락으로 고쳐놓은 것과 동일한 이유로
# 여기도 락을 건다. 락이 없어도 list라 dict/set처럼 에러로 죽지는 않지만(직접 확인),
# store()의 append/pop(0)이 lookup()의 reversed(_cache) 순회 도중 끼어들면 있어야
# 할 캐시 히트를 조용히 놓칠 수 있다.
_lock = threading.Lock()


def _cosine(a: list[float], b: list[float]) -> float:
    """embed_query가 이미 정규화(normalize_embeddings=True)해서 주므로 내적이 곧 코사인 유사도다."""
    return sum(x * y for x, y in zip(a, b))


def lookup(message: str) -> dict | None:
    """비슷한 질문이 최근에 있었으면 그 의도분류 결과를 돌려주고, 없으면 None."""
    now = time.time()
    # embed_query는 무거운 모델 추론이라 락 밖에서 한다 — 락은 _cache 읽기·순회
    # 구간만 감싸서, 다른 요청의 embed_query 호출까지 불필요하게 직렬화하지 않는다.
    vec = embed_query(message)
    with _lock:
        for entry in reversed(_cache):
            if now - entry["ts"] > _TTL_SECONDS:
                continue
            if _cosine(vec, entry["embedding"]) >= _SIMILARITY_THRESHOLD:
                return {
                    "intent": entry["intent"],
                    "filters": entry["filters"],
                    "query_text": entry["query_text"],
                    "chat_reply": entry["chat_reply"],
                }
    return None


def store(message: str, contact1: dict) -> None:
    """의도분류 결과를 캐시에 넣는다. 대화 맥락이 있던 턴은 orchestrator가 애초에 안 부른다."""
    vec = embed_query(message)  # lookup()과 같은 이유로 락 밖에서 계산한다.
    with _lock:
        _cache.append(
            {
                "embedding": vec,
                "ts": time.time(),
                "intent": contact1["intent"],
                "filters": contact1["filters"],
                "query_text": contact1["query_text"],
                "chat_reply": contact1["chat_reply"],
            }
        )
        if len(_cache) > _MAX_ENTRIES:
            _cache.pop(0)
