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


def _read_db_password() -> str:
    """Read the database password from a mounted secret when configured.

    Kubernetes Secret Store CSI mounts are exposed as files.  Prefer that file
    over the legacy environment variable, remove only the newline written by
    the secret mount, and fail closed when a configured file cannot be read.
    """

    password_file = os.environ.get("DB_PASSWORD_FILE", "").strip()
    if not password_file:
        return os.environ.get("DB_PASSWORD", "")

    try:
        return Path(password_file).read_text(encoding="utf-8").rstrip("\r\n")
    except OSError as exc:
        raise RuntimeError(
            f"DB_PASSWORD_FILE is configured but cannot be read: {password_file}"
        ) from exc


class Settings:
    # --- PostgreSQL ---
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = int(os.environ.get("DB_PORT", "5432"))
    DB_NAME = os.environ.get("DB_NAME", "midam")
    DB_USER = os.environ.get("DB_USER", "User")
    DB_PASSWORD = _read_db_password()

    # --- Ollama ---
    OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    # 과거 30건 평가셋에서 qwen3:8b보다 사실왜곡률(13.3%→0%)·인젝션방어율(50%→100%)이
    # 크게 앞서고 더 빨라(p50 24.2s→18.6s) gemma2:9b를 채택했었다(근거:
    # docs/model-selection-comparison.md). 이후 gemma4:12b로 올라갔는데, 최신 28건
    # 평가셋으로 재측정해보면 gemma4:12b가 모든 지표(사실왜곡·인젝션방어·의도분류·속도)
    # 에서 gemma2:9b보다 우수하다 — 즉 품질만 보면 gemma4:12b가 맞다.
    # 지금 gemma2:9b로 다시 내린 건 품질 때문이 아니라, gemma4:12b가 T4 GPU 노드의
    # 메모리 한도(10Gi)를 기본 사용량만으로 거의 다 채워(7.8GB) 동시 요청 시 OOM이
    # 재현됐기 때문이다(임시 조치) — gemma2:9b는 그보다 가벼워(5.4GB) 여유를 번다.
    # 종목 모순 케이스(b27) 1건은 gemma2:9b가 아직 못 잡아 tests/test_generate.py에
    # xfail로 남아있다(알려진 한계).
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
    # 없앨 후보). 이 Mac(M4, MPS)에선 정식 지원이 아니라 실험적인 경로라 실측으로 세
    # 가지 문제를 확인했다(CUDA에선 안 나올 가능성이 높지만 프로덕션 전환 전 재확인
    # 필수): (1) 기본 그래마 백엔드(xgrammar)는 JSON 스키마 강제 시 매 토큰을
    # 거부해(Accepted tokens: []) 아예 응답을 못 만든다 — `--grammar-backend outlines`로
    # 띄워야 한다. (2) outlines도 완벽하진 않아 응답을 마크다운 코드 펜스로 감싸는
    # 경우가 있다(````json\n{...}\n````) — llm.py가 파싱 전에 벗겨낸다. (3) 가장
    # 심각한 문제: 프롬프트가 이전 요청과 비슷하면(prefix cache 히트로 추정) 이번
    # 응답의 앞부분이 통째로 잘려서 온다(실측 재현: 정상 JSON 대신 쉼표로 시작하는
    # 조각만 반환됨) — 이건 에러 없이 200 OK로 조용히 틀린 데이터를 주므로 코드로
    # 방어할 수 없다. 그래서 로컬 Mac에서의 sglang 검증은 "연동 배관이 맞는가"까지만
    # 하고, 실제 신뢰도 검증은 CUDA 서버에서 다시 해야 한다.
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
