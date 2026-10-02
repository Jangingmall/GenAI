"""
② 쿼리 임베딩 — 사용자 질의를 벡터로 변환한다.

중요: 적재 스크립트(load_products.py)의 embed()와 반드시 같은 모델·같은 방식이어야
한다. 쿼리와 상품이 같은 임베딩 공간에 있어야 벡터 검색이 성립한다.
  - 모델: settings.EMBED_MODEL
  - normalize_embeddings=True (코사인 검색 전제)
"""

import threading

from app.config import settings

# 모델은 최초 1회만 로드해 재사용한다 (로드가 무겁다).
_model = None
# 첫 요청이 동시에 여러 건 들어오면 각자 모델을 적재해 메모리가 겹쳐 올라간다
# (Stage 2026-10-02 09:47:08, Loading weights 2회). 락으로 적재를 한 번만 하게 한다.
_model_lock = threading.Lock()


def _get_model():
    """임베딩 모델을 지연 로드한다. 동시 호출에도 한 번만 적재한다."""
    global _model
    if _model is None:  # 적재 후에는 락 없이 바로 반환
        with _model_lock:
            if _model is None:  # 락을 기다리는 동안 다른 요청이 적재했을 수 있다
                from sentence_transformers import SentenceTransformer

                _model = SentenceTransformer(settings.EMBED_MODEL)
    return _model


def embed_query(text: str) -> list[float]:
    """질의 문자열 하나를 정규화된 벡터로 변환한다."""
    vec = _get_model().encode(text, normalize_embeddings=True)
    return vec.tolist()
