import pytest
from pydantic import ValidationError

from detail_page_ai.ai_dto import (
    AiToBeAcceptedResponseDto,
    AiToBeApprovedResponseDto,
    AiToBePersistRequestDto,
    AiToBeStatusResponseDto,
    BeToAiApproveDraftRequestDto,
    BeToAiCreateJobRequestDto,
    BeToAiPersistAckDto,
)
from detail_page_ai.dto import (
    AiBePersistAck,
    AiBeProductPersistRequest,
    AiFeProductSummaryDto,
    AiFeResultDto,
    ProductProfileDto,
)


def _create_payload() -> dict:
    return {
        "product_id": "product-42",
        "source_asset_id": "source-asset-42",
        "request_id": "request-42",
        "idempotency_key": "create-42-v1",
        "user_hints": {"product_name": "나전 보관함"},
        "options": {"aspect_ratio": "1:8", "image_size": "2K"},
    }


def test_be_to_ai_create_request_requires_product_identity():
    request = BeToAiCreateJobRequestDto.model_validate(_create_payload())

    assert request.product_id == "product-42"
    assert request.source_asset_id == "source-asset-42"
    assert request.user_hints.product_name == "나전 보관함"
    assert request.options.aspect_ratio == "1:8"

    with pytest.raises(ValidationError):
        BeToAiCreateJobRequestDto.model_validate(
            {**_create_payload(), "unexpected": "rejected"}
        )


def test_be_to_ai_approval_request_contains_creator_approved_draft():
    request = BeToAiApproveDraftRequestDto.model_validate(
        {
            "product_id": "product-42",
            "request_id": "approval-42",
            "idempotency_key": "approve-42-v1",
            "draft_id": "job-42",
            "draft": {
                "product_name": "수정한 나전 보관함",
                "summary": "승인된 설명입니다.",
                "hero_headline": "장인의 시간이 머무는 문양",
                "hero_description": "표면의 문양과 구조를 담았습니다.",
            },
        }
    )

    assert request.product_id == "product-42"
    assert request.draft.product_name == "수정한 나전 보관함"
    assert request.options.output_mime_type == "image/png"


def test_ai_to_be_status_keeps_product_identity_separate_from_fe_result():
    result = AiFeResultDto(
        generation_id="generation-42",
        product=AiFeProductSummaryDto.from_profile(ProductProfileDto.minimal("장식함")),
        detail_page={"mime_type": "image/png"},
    )
    response = AiToBeStatusResponseDto(
        product_id="product-42",
        job_id="job-42",
        request_id="request-42",
        status="COMPLETED",
        progress=100,
        result=result,
        updated_at="2026-08-31T00:00:00Z",
    )

    payload = response.model_dump()

    assert payload["product_id"] == "product-42"
    assert payload["result"]["generation_id"] == "generation-42"
    assert payload["result"]["product"].get("product_id") is None


def test_ai_to_be_accepted_and_approved_contracts_are_explicit():
    accepted = AiToBeAcceptedResponseDto(
        product_id="product-42",
        job_id="job-42",
        request_id="request-42",
        status="QUEUED",
        status_url="/internal/v1/ai/detail-page-jobs/job-42",
        created_at="2026-08-31T00:00:00Z",
    )
    approved = AiToBeApprovedResponseDto(
        product_id="product-42",
        status="COMPLETED",
        result=AiFeResultDto(
            generation_id="generation-42",
            product=AiFeProductSummaryDto.from_profile(ProductProfileDto.minimal("장식함")),
            detail_page={"mime_type": "image/png"},
        ),
    )

    assert accepted.product_id == approved.product_id == "product-42"
    assert approved.backend_delivery_pending is False


def test_ai_to_be_envelopes_reject_unknown_fields():
    with pytest.raises(ValidationError):
        AiToBeAcceptedResponseDto.model_validate(
            {
                "product_id": "product-42",
                "job_id": "job-42",
                "request_id": "request-42",
                "status": "QUEUED",
                "status_url": "/internal/v1/ai/detail-page-jobs/job-42",
                "created_at": "2026-08-31T00:00:00Z",
                "unexpected": "must be rejected",
            }
        )


def test_canonical_persist_names_point_to_validated_shared_models():
    request = AiToBePersistRequestDto.from_profile(
        generation_id="generation-42",
        job_id="job-42",
        request_id="request-42",
        source_image_mime_type="image/png",
        source_image_sha256="source-hash",
        generated_image_mime_type="image/png",
        generated_width=774,
        generated_height=3000,
        generated_image_sha256="page-hash",
        profile=ProductProfileDto.minimal("장식함"),
        generation={"prompt_version": "source-safe-v2"},
        product_id="product-42",
    )
    ack = BeToAiPersistAckDto(
        generation_id="generation-42",
        product_id="product-42",
        status="SAVED",
        saved_at="2026-08-31T00:00:00Z",
    )

    assert request.product_id == "product-42"
    assert isinstance(ack, AiBePersistAck)


def test_canonical_persist_request_rejects_missing_product_identity():
    legacy_request = AiBeProductPersistRequest.from_profile(
        generation_id="generation-legacy",
        job_id="job-legacy",
        request_id="request-legacy",
        source_image_mime_type="image/png",
        source_image_sha256="source-hash",
        generated_image_mime_type="image/png",
        generated_width=774,
        generated_height=3000,
        generated_image_sha256="page-hash",
        profile=ProductProfileDto.minimal("장식함"),
        generation={"prompt_version": "source-safe-v2"},
    )

    with pytest.raises(ValidationError):
        AiToBePersistRequestDto.model_validate(legacy_request.model_dump())
