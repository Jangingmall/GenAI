"""
설정 관리 — .env 파일에서 값을 읽어 한곳에서 제공한다.
코드 곳곳에 비밀번호·모델명을 하드코딩하지 않고 여기서만 관리한다.

사용:
    from app.config import settings
    settings.DB_NAME, settings.LLM_MODEL ...
"""

import os
from pathlib import Path

# .env 파일을 직접 파싱 (외부 라이브러리 없이 간단하게)
# python-dotenv를 쓰고 싶으면 requirements에 추가 후 load_dotenv()로 대체 가능.
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _load_env():
    """.env 파일을 읽어 os.environ에 없는 키만 채운다."""
    if not _ENV_PATH.exists():
        return
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        os.environ.setdefault(key, value)


_load_env()


class Settings:
    # --- PostgreSQL ---
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = int(os.environ.get("DB_PORT", "5432"))
    DB_NAME = os.environ.get("DB_NAME", "midam")
    DB_USER = os.environ.get("DB_USER", "User")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")

    # --- Ollama ---
    OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    # 30건 평가셋에서 qwen3:8b보다 사실왜곡률(13.3%→0%)·인젝션방어율(50%→100%)이 크게 앞서고
    # 더 빠르다(p50 24.2s→18.6s) — eval/reports/gemma2-9b-think.json 실측 근거. 종목 모순
    # 케이스(b27) 1건은 아직 못 잡아 tests/test_generate.py에 xfail로 남겨뒀다(알려진 한계).
    LLM_MODEL = os.environ.get("LLM_MODEL", "gemma2:9b")

    # --- LLM 백엔드 선택 ---
    # "ollama"(기본) 또는 "mlx-serve". gemma4:12b-mlx를 Ollama의 MLX 프리뷰로 띄워보니
    # 캐시가 예측 불가하게 축출되고(콜드콜 2번 필요, 이후에도 가끔 900초대까지 튐) 메모리도
    # 계속 불어났다(10GB→16GB, 최대 32개 컨텍스트 체크포인트를 다 못 비움). 같은 모델을
    # mlx-serve(OpenAI 호환 API, Apple Silicon 전용 네이티브 서버)로 띄우면 콜드콜 1번
    # 이후 캐시 히트율 95~99%로 안정적이고 메모리도 6.3GB로 고정됐다(실측 확인) — 그래서
    # 백엔드를 선택 가능하게 둔다. 기본값은 검증된 "ollama"를 유지한다.
    LLM_BACKEND = os.environ.get("LLM_BACKEND", "ollama")
    MLX_SERVE_HOST = os.environ.get("MLX_SERVE_HOST", "http://localhost:11234")

    # "sglang" — 팀이 실제 배포할 CUDA 서버용 백엔드(RadixAttention으로 intent·generate
    # 두 시스템 프롬프트를 동시에 캐싱할 수 있어 mutual eviction 문제를 구조적으로
    # 없앨 후보). 이 Mac(M4, MPS)에선 정식 지원이 아니라 실험적인 경로라 실측으로 확인된
    # 제약이 있다: 기본 그래마 백엔드(xgrammar)는 JSON 스키마 강제 시 매 토큰을
    # 거부해(Accepted tokens: []) 아예 응답을 못 만든다 — 서버를 `--grammar-backend
    # outlines`로 띄워야 한다. outlines도 완벽하진 않아 응답을 마크다운 코드 펜스로
    # 감싸는 경우가 있다(````json\n{...}\n````) — llm.py가 파싱 전에 벗겨낸다. CUDA
    # 서버는 xgrammar가 원래 성숙한 플랫폼이라 이 두 제약이 안 나올 가능성이 높지만,
    # 확인 전까진 마크다운 벗기기 방어는 유지한다.
    SGLANG_HOST = os.environ.get("SGLANG_HOST", "http://localhost:30000")

    # --- 임베딩 ---
    EMBED_MODEL = os.environ.get("EMBED_MODEL", "BAAI/bge-m3")
    EMBED_DIM = int(os.environ.get("EMBED_DIM", "1024"))

    def dsn(self) -> str:
        """psycopg2 접속 문자열."""
        return (
            f"host={self.DB_HOST} port={self.DB_PORT} "
            f"dbname={self.DB_NAME} user={self.DB_USER} "
            f"password={self.DB_PASSWORD}"
        )


settings = Settings()
