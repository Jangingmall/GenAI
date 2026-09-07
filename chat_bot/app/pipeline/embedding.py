"""
② 쿼리 임베딩 — 사용자 질의를 벡터로 변환한다.

중요: 적재 스크립트(load_products.py)의 embed()와 반드시 같은 모델·같은 방식이어야
한다. 쿼리와 상품이 같은 임베딩 공간에 있어야 벡터 검색이 성립한다.
  - 모델: settings.EMBED_MODEL
  - normalize_embeddings=True (코사인 검색 전제)
"""

from app.config import settings

# 모델은 최초 1회만 로드해 재사용한다 (로드가 무겁다).
_model = None


def _get_model():
    """임베딩 모델을 지연 로드한다."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(settings.EMBED_MODEL)
    return _model


def embed_query(text: str) -> list[float]:
    """질의 문자열 하나를 정규화된 벡터로 변환한다."""
    vec = _get_model().encode(text, normalize_embeddings=True)
    return vec.tolist()
