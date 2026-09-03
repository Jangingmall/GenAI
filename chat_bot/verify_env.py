#!/usr/bin/env python3
"""
미담 AI파트 · 로컬 환경 검증 스크립트
------------------------------------------------
세팅이 끝난 뒤 이 스크립트를 실행해 모든 구성요소가 정상인지 한 번에 확인한다.
전부 [OK]가 뜨면 개발 시작 준비 완료.

접속 정보·모델명은 코드에 하드코딩하지 않고 app.config(=.env)에서 읽는다.

실행 (프로젝트 루트 chat_bot/ 에서):
    python verify_env.py
"""

import sys

try:
    from app.config import settings
except Exception as e:  # noqa: BLE001
    print(f"❌ app.config 를 불러오지 못했습니다: {e}")
    print("   → chat_bot/ 폴더에서 실행했는지, app/config.py 가 있는지 확인하세요.")
    sys.exit(1)

RESULTS = []


def check(name):
    """데코레이터: 각 점검 항목을 실행하고 결과를 수집."""
    def deco(fn):
        def wrapper():
            try:
                msg = fn()
                RESULTS.append(("OK", name, msg or ""))
            except Exception as e:  # noqa: BLE001
                RESULTS.append(("FAIL", name, str(e)))
        return wrapper
    return deco


@check("Python 버전 (3.10+)")
def check_python():
    v = sys.version_info
    if v < (3, 10):
        raise RuntimeError(f"현재 {v.major}.{v.minor} — 3.10 이상 필요")
    return f"{v.major}.{v.minor}.{v.micro}"


@check(".env 설정 로드")
def check_env():
    """민감 값(비밀번호)이 .env에서 실제로 읽혔는지 확인."""
    if not settings.DB_PASSWORD:
        raise RuntimeError(".env에 DB_PASSWORD가 없습니다. .env.example을 복사해 채우세요.")
    return f"DB={settings.DB_NAME} / USER={settings.DB_USER} / 모델={settings.LLM_MODEL}"


@check("PostgreSQL + pgvector 연결")
def check_pgvector():
    import psycopg2
    # 접속 정보는 config(.env)에서 읽는다 — 하드코딩하지 않는다.
    conn = psycopg2.connect(settings.dsn())
    cur = conn.cursor()
    # pgvector 확장 존재 확인
    cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector';")
    row = cur.fetchone()
    if not row:
        raise RuntimeError("vector 확장 미설치 — CREATE EXTENSION vector; 실행 필요")
    # 벡터 연산 실제 동작 확인
    cur.execute("SELECT '[1,2,3]'::vector <-> '[4,5,6]'::vector;")
    dist = cur.fetchone()[0]
    cur.close()
    conn.close()
    return f"pgvector 동작 확인 (거리 계산 = {dist:.3f})"


@check("Ollama + Qwen3 응답")
def check_qwen():
    import requests
    # 호스트·모델명은 config(.env)에서 읽는다.
    r = requests.post(
        f"{settings.OLLAMA_HOST}/api/generate",
        json={"model": settings.LLM_MODEL,
              "prompt": "한국어로 '준비 완료'라고만 답해줘.",
              "stream": False},
        timeout=120,
    )
    r.raise_for_status()
    text = r.json().get("response", "").strip()
    if not text:
        raise RuntimeError("빈 응답 — 모델 로드 확인 필요")
    return f"{settings.LLM_MODEL} 응답 수신 ({text[:20]}...)"


@check("임베딩 모델 (EMBED_DIM 차원)")
def check_embed():
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(settings.EMBED_MODEL)
    vec = model.encode("청자 상감 다완")
    dim = len(vec)
    if dim != settings.EMBED_DIM:
        raise RuntimeError(f"차원 {dim} — {settings.EMBED_DIM} 예상 (.env EMBED_DIM 확인)")
    return f"{settings.EMBED_MODEL} 임베딩 성공 (차원 {dim})"


@check("FastAPI import")
def check_fastapi():
    import fastapi
    import uvicorn  # noqa: F401
    return f"FastAPI {fastapi.__version__}"


def main():
    print("\n미담 AI파트 · 로컬 환경 검증\n" + "=" * 40)
    for fn_name in ["check_python", "check_env", "check_pgvector",
                    "check_qwen", "check_embed", "check_fastapi"]:
        globals()[fn_name]()

    print()
    all_ok = True
    for status, name, msg in RESULTS:
        mark = "✅" if status == "OK" else "❌"
        print(f"{mark} [{status:4}] {name}")
        if msg:
            print(f"          └ {msg}")
        if status == "FAIL":
            all_ok = False

    print("=" * 40)
    if all_ok:
        print("🎉 전부 정상 — 개발 시작 준비 완료\n")
        sys.exit(0)
    else:
        print("⚠️  실패 항목이 있습니다. 위 메시지를 확인하세요.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()