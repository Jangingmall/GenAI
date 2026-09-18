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

import re
import threading
import time

from app.pipeline.embedding import embed_query
from app.pipeline.generate import _COLOR_LABELS, _mentioned_categories

_SIMILARITY_THRESHOLD = 0.82  # 실측(실제 임베딩 모델)으로 캘리브레이션한 값 — 같은 뜻
# 문장 쌍은 0.84~0.96, 다른 질문 쌍은 0.36~0.74로 갈렸다("선물로 좋은 도자기 찾아줘" vs
# "선물용 도자기 추천해줘" 0.88, vs "집들이 선물로 옹기 찾아줘"(다른 종목) 0.74). 두 구간
# 사이(0.74~0.84)에 여유를 두고 0.82로 잡았다 — 처음엔 0.93으로 잡았다가 실측해보니
# 같은 뜻 문장 쌍조차 대부분 0.93 밑이라 캐시가 전혀 안 맞아서(실측 확인) 다시 잡았다.
#
# 실측 확인된 버그(2026-09-18): 이 임계값만으로는 못 거르는 사각지대가 있다 — "부모님
# 퇴직선물 도자기 50만원 이하로 추천해줘"와 "...목공예품 50만원 이하로 추천해줘"처럼
# 문장 틀이 거의 같고 종목명만 바뀐 경우, 실제로 종목이 완전히 다른데도 유사도가
# 0.93까지 나와(위 "다른 질문 쌍" 상한 0.74를 훨씬 넘음) 캐시가 오판했다 — 도자기로
# 캐싱된 query_text·filters가 목공예품 질문에 그대로 새어나갔다. 처음엔 종목만 막았지만
# ("이런 유사한 상황을 더 테스트해봤냐"는 지적으로 재점검) 가격 숫자만 다른 쌍("도자기
# 5만원" vs "10만원", 유사도 0.871)·색상만 다른 쌍("빨간색" vs "파란색", 유사도 0.876)도
# 같은 사각지대에 있는 걸 실측으로 추가 확인했다 — "문장 틀은 같고 한 단어(슬롯)만
# 바뀌면 임베딩이 그 차이를 충분히 크게 반영 못 한다"는 같은 근본 원인이다. 임베딩
# 하나로는 못 막아서, 종목·가격 숫자·색상 셋 다 코드로 뽑아 대조하는 추가 방어선을
# 건다 — 아래 _cache_signal·lookup() 참고.
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


_DIGITS_RE = re.compile(r"\d+")
_COLOR_WORDS = frozenset(_COLOR_LABELS.values())  # {"흰색", "검정색", ...} — DB enum
# 한국어 라벨을 그대로 재사용한다(단일 출처, generate.py와 어긋날 일이 없음).


def _cache_signal(message: str) -> dict[str, frozenset[str]]:
    """임베딩 유사도의 사각지대를 코드로 보강하는 신호 3가지.

    "문장 틀은 같고 한 단어(종목·가격 숫자·색상)만 바뀐" 문장 쌍은 임베딩 유사도가
    임계값을 넘어버릴 수 있다(_SIMILARITY_THRESHOLD 주석의 실측 사례 참고) — 그
    바뀐 단어 자체를 코드로 뽑아 두 문장이 정말 같은 요청인지 한 번 더 확인한다.
    """
    return {
        "categories": frozenset(_mentioned_categories(message)),
        "colors": frozenset(w for w in _COLOR_WORDS if w in message),
        "digits": frozenset(_DIGITS_RE.findall(message)),
    }


def _signal_conflicts(
    a: dict[str, frozenset[str]], b: dict[str, frozenset[str]]
) -> bool:
    """두 신호가 "같은 요청"이라고 보기엔 서로 다른지 판단한다.

    한쪽에 신호가 아예 없으면(예: 종목을 안 언급한 자유 서술) 그 축은 비교하지
    않는다 — 무조건 다르다고 막으면 캐시가 과도하게 안 맞는다. 양쪽 다 신호가
    있는데 집합이 다르면(부분적으로만 겹쳐도) 다른 요청으로 본다 — 첫 턴에만
    쓰는 캐시라(narrow_down 등 맥락 있는 턴은 대상이 아님) 엄격하게 판단해도
    손해가 적다.
    """
    for key, a_signal in a.items():
        if a_signal and b[key] and a_signal != b[key]:
            return True
    return False


def lookup(message: str) -> dict | None:
    """비슷한 질문이 최근에 있었으면 그 의도분류 결과를 돌려주고, 없으면 None."""
    now = time.time()
    # embed_query는 무거운 모델 추론이라 락 밖에서 한다 — 락은 _cache 읽기·순회
    # 구간만 감싸서, 다른 요청의 embed_query 호출까지 불필요하게 직렬화하지 않는다.
    vec = embed_query(message)
    signal = _cache_signal(message)
    with _lock:
        for entry in reversed(_cache):
            if now - entry["ts"] > _TTL_SECONDS:
                continue
            if _cosine(vec, entry["embedding"]) < _SIMILARITY_THRESHOLD:
                continue
            if _signal_conflicts(signal, entry["signal"]):
                continue
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
    signal = _cache_signal(message)  # lookup()과 같은 추가 방어선.
    with _lock:
        _cache.append(
            {
                "embedding": vec,
                "signal": signal,
                "ts": time.time(),
                "intent": contact1["intent"],
                "filters": contact1["filters"],
                "query_text": contact1["query_text"],
                "chat_reply": contact1["chat_reply"],
            }
        )
        if len(_cache) > _MAX_ENTRIES:
            _cache.pop(0)
