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
