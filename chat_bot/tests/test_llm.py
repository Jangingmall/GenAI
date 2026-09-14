"""llm.py 단위 테스트. 재시도 정책 설정값만 검증 — 실제 네트워크 호출은 안 한다.

실행: python -m pytest tests/test_llm.py -q
"""

from app.pipeline import llm


def test_retry_only_retries_connection_and_server_errors_not_read_timeout():
    """읽기 타임아웃(연결은 됐지만 생성이 느려서 시간 초과)은 재시도하면 대기 시간만
    배로 늘 뿐이라 재시도 대상에서 뺀다(read=0) — 연결 실패·5xx만 자동 재시도한다."""
    assert llm._retry.connect == 2
    assert llm._retry.read == 0
    assert set(llm._retry.status_forcelist) == {500, 502, 503, 504}


def test_retry_allows_post():
    """urllib3 기본값은 POST를 비멱등으로 보고 재시도 대상에서 뺀다 — 우리 LLM 호출은
    두 번 보내도 부작용이 없어 명시적으로 허용해야 한다."""
    assert "POST" in llm._retry.allowed_methods


def test_session_mounted_with_retry_adapter():
    http_adapter = llm._session.get_adapter("http://example.com")
    https_adapter = llm._session.get_adapter("https://example.com")
    assert http_adapter.max_retries is llm._retry
    assert https_adapter.max_retries is llm._retry
