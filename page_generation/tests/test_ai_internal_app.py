import asyncio
import io
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

import detail_page_ai.app as app_module
from detail_page_ai.ai_dto import AiToBeStatusResponseDto
from detail_page_ai.dto import (
    AiFeResultDto,
    AiFeProductSummaryDto,
    FeDetailPageAssetDto,
    ProductProfileDto,
)


VALID_PNG = b"\x89PNG\r\n\x1a\nimage"


def _upload(filename: str = "product.png") -> UploadFile:
    return UploadFile(
        file=io.BytesIO(VALID_PNG),
        filename=filename,
        headers=Headers({"content-type": "image/png"}),
    )


def _result() -> AiFeResultDto:
    return AiFeResultDto(
        generation_id="generation-internal",
        product=AiFeProductSummaryDto.from_profile(ProductProfileDto.minimal("장식함")),
        detail_page=FeDetailPageAssetDto(mime_type="image/png"),
    )


class RecordingService:
    def __init__(self):
        self.submit_kwargs = None
        self.pipeline_kwargs = None

    def submit(self, source_image, source_mime_type, **kwargs):
        self.submit_kwargs = kwargs
        return {
            "job_id": "job-internal",
            "request_id": kwargs.get("request_id") or "request-generated",
            "status": "QUEUED",
            "status_url": "/internal/v1/ai/detail-page-jobs/job-internal",
            "created_at": "2026-08-31T00:00:00Z",
        }

    def get_backend(self, job_id):
        return AiToBeStatusResponseDto(
            product_id="product-42",
            job_id=job_id,
            request_id="request-42",
            status="ANALYZING",
            progress=15,
            updated_at="2026-08-31T00:00:00Z",
        )

    @property
    def pipeline(self):
        return self

    def run(self, **kwargs):
        self.pipeline_kwargs = kwargs
        return SimpleNamespace(
            fe_result=_result(),
            be_ack=None,
            backend_delivery_pending=False,
            warning=None,
        )


def test_internal_create_forwards_product_identity_and_source_asset(monkeypatch):
    service = RecordingService()
    monkeypatch.setattr(app_module, "get_service", lambda: service)
    monkeypatch.setattr(
        app_module, "get_settings", lambda: SimpleNamespace(ai_internal_auth_token="secret")
    )
    metadata = json.dumps(
        {
            "product_id": "product-42",
            "source_asset_id": "source-asset-42",
            "request_id": "request-42",
            "idempotency_key": "create-42-v1",
            "user_hints": {"product_name": "나전 보관함"},
        }
    )

    response = asyncio.run(
        app_module.create_internal_detail_page_job(
            product_image=_upload(),
            product_images=None,
            metadata=metadata,
            x_ai_internal_token="secret",
        )
    )

    assert response.product_id == "product-42"
    assert service.submit_kwargs["product_id"] == "product-42"
    assert service.submit_kwargs["source_asset_id"] == "source-asset-42"
    assert service.submit_kwargs["user_hints"].product_name == "나전 보관함"


def test_internal_status_returns_backend_shaped_product_identity(monkeypatch):
    service = RecordingService()
    monkeypatch.setattr(app_module, "get_service", lambda: service)
    monkeypatch.setattr(
        app_module, "get_settings", lambda: SimpleNamespace(ai_internal_auth_token="secret")
    )

    response = app_module.get_internal_detail_page_job(
        "job-internal", x_ai_internal_token="secret"
    )

    assert response.product_id == "product-42"
    assert response.status == "ANALYZING"


def test_internal_approval_forwards_product_identity_without_reanalysis(monkeypatch):
    service = RecordingService()
    monkeypatch.setattr(app_module, "get_service", lambda: service)
    monkeypatch.setattr(
        app_module, "get_settings", lambda: SimpleNamespace(ai_internal_auth_token="secret")
    )
    metadata = json.dumps(
        {
            "product_id": "product-42",
            "source_asset_id": "source-asset-42",
            "request_id": "approval-42",
            "idempotency_key": "approve-42-v1",
            "draft_id": "job-internal",
            "draft": {
                "product_name": "승인한 장식함",
                "summary": "승인된 설명입니다.",
                "hero_headline": "표면의 문양",
                "hero_description": "이미지에서 확인되는 특징입니다.",
            },
        }
    )

    response = asyncio.run(
        app_module.approve_internal_detail_page(
            product_image=_upload(),
            product_images=None,
            metadata=metadata,
            x_ai_internal_token="secret",
        )
    )

    assert response.product_id == "product-42"
    assert service.pipeline_kwargs["product_id"] == "product-42"
    assert service.pipeline_kwargs["source_asset_id"] == "source-asset-42"
    assert service.pipeline_kwargs["profile_override"].display_name == "승인한 장식함"


def test_internal_routes_reject_wrong_token(monkeypatch):
    monkeypatch.setattr(
        app_module, "get_settings", lambda: SimpleNamespace(ai_internal_auth_token="secret")
    )

    with pytest.raises(HTTPException) as caught:
        app_module.get_internal_detail_page_job(
            "job-internal", x_ai_internal_token="wrong"
        )

    assert caught.value.status_code == 401


def test_internal_routes_fail_closed_when_token_is_not_configured(monkeypatch):
    monkeypatch.setattr(
        app_module, "get_settings", lambda: SimpleNamespace(ai_internal_auth_token=None)
    )

    with pytest.raises(HTTPException) as caught:
        app_module.get_internal_detail_page_job(
            "job-internal", x_ai_internal_token="secret"
        )

    assert caught.value.status_code == 503


def test_every_route_is_health_internal_or_a_disabled_demo_route():
    # Security check (SAST F-1): a new route without the internal token or the
    # demo-API switch should fail here rather than ship unauthenticated.
    import inspect

    from fastapi.routing import APIRoute

    for route in app_module.app.routes:
        if not isinstance(route, APIRoute) or route.path.startswith("/health"):
            continue
        if route.path == "/metrics":
            # Prometheus scrape target: counts and latencies only, no request data.
            continue
        if route.path.startswith("/internal/"):
            assert "_require_internal_auth(" in inspect.getsource(route.endpoint), route.path
        else:
            dependencies = [dependency.call for dependency in route.dependant.dependencies]
            assert app_module._require_legacy_demo_api in dependencies, route.path


def test_metrics_are_exposed_in_prometheus_format_with_route_templates(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(
        app_module,
        "get_settings",
        lambda: SimpleNamespace(ai_internal_auth_token="secret", enable_legacy_demo_api=False),
    )
    client = TestClient(app_module.app)
    client.get("/internal/v1/ai/detail-page-jobs/job-metrics-1")

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "# HELP http_requests_total" in response.text
    # Job IDs must not become label values (one series per route, not per job).
    assert 'handler="/internal/v1/ai/detail-page-jobs/{job_id}"' in response.text
    assert "job-metrics-1" not in response.text


def test_unauthenticated_requests_are_refused(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(
        app_module,
        "get_settings",
        lambda: SimpleNamespace(ai_internal_auth_token="secret", enable_legacy_demo_api=False),
    )
    client = TestClient(app_module.app)

    assert client.get("/api/v1/ai/detail-page-jobs/job-1").status_code == 404
    assert client.get("/internal/v1/ai/detail-page-jobs/job-1").status_code == 401
    wrong = {"X-AI-Internal-Token": "wrong"}
    assert client.get("/internal/v1/ai/detail-page-jobs/job-1", headers=wrong).status_code == 401


def test_run_exits_non_zero_after_the_entrypoint_reports_a_model_failure(monkeypatch, tmp_path):
    import uvicorn

    marker = tmp_path / "model-server-failed"
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: None)
    monkeypatch.setenv("MODEL_FAILURE_MARKER", str(marker))
    app_module.run()  # no marker: normal shutdown

    marker.touch()
    with pytest.raises(SystemExit) as exit_info:
        app_module.run()
    assert exit_info.value.code == 1
