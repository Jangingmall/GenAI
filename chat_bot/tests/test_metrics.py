"""GET /metrics — Prometheus 스크레이핑용 엔드포인트 계약 테스트.

인프라가 PodMonitor로 이 엔드포인트를 긁어가므로, 상태 코드·content-type만
확인한다(실제 메트릭 값은 prometheus-fastapi-instrumentator 라이브러리 책임).
"""

from fastapi.testclient import TestClient

from app import main

client = TestClient(main.app)


def test_metrics_returns_prometheus_format():
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "# HELP" in response.text
