from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from detail_page_ai.dto import (
    AiFeAcceptedResponse,
    AiFeApprovedResponse,
    AiFeResultDto,
    AiFeStatusResponse,
    ApprovedDraftDto,
    GenerationOptions,
    UserHintsDto,
)
from detail_page_ai import (
    AiFeCreateJobRequestDto as PublicAiFeCreateJobRequestDto,
    AiFeDraftResponseDto as PublicAiFeDraftResponseDto,
)
from detail_page_ai.fe_dto import (
    AiFeApprovalRequestDto,
    AiFeCreateJobRequestDto,
    AiFeApprovedResponseDto,
    AiFeDraftDto,
    AiFeDraftResponseDto,
    AiFeJobAcceptedResponseDto,
    AiFeJobStatusResponseDto,
    AiFeResultResponseDto,
)


def test_fe_create_job_request_parses_multipart_metadata_defaults():
    request = AiFeCreateJobRequestDto(
        product_name=" 나전 보관함 ",
        making_method="표면 장식으로 완성했습니다.",
        care_guide="마른 천으로 닦아 주세요.",
    )

    assert request.user_hints == UserHintsDto(
        product_name="나전 보관함",
        making_method="표면 장식으로 완성했습니다.",
        care_guide="마른 천으로 닦아 주세요.",
    )
    assert request.request_id is None
    assert request.template_id == "default-long-detail-page"
    assert request.locale == "ko-KR"
    assert request.options == GenerationOptions()


def test_fe_create_job_request_rejects_unsupported_locale():
    with pytest.raises(ValidationError):
        AiFeCreateJobRequestDto(locale="en-US")


def test_fe_approval_request_contains_current_draft_and_options():
    draft = AiFeDraftDto(
        product_name="수정한 나전함",
        summary="승인된 설명입니다.",
        hero_headline="장인의 시간이 머무는 문양",
        hero_description="검은 바탕 위 문양의 깊이를 담았습니다.",
    )
    request = AiFeApprovalRequestDto(
        draft=draft,
        request_id="request-1",
        options=GenerationOptions(image_size="1K"),
    )

    assert request.draft.product_name == "수정한 나전함"
    assert request.options.image_size == "1K"


def test_fe_response_names_are_compatible_with_current_api_models():
    assert issubclass(AiFeJobAcceptedResponseDto, AiFeAcceptedResponse)
    assert issubclass(AiFeJobStatusResponseDto, AiFeStatusResponse)
    assert issubclass(AiFeResultResponseDto, AiFeResultDto)
    assert issubclass(AiFeApprovedResponseDto, AiFeApprovedResponse)
    assert issubclass(AiFeDraftDto, ApprovedDraftDto)


def test_ai_fe_result_contract_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        AiFeResultResponseDto.model_validate(
            {
                "generation_id": "generation-1",
                "product": {
                    "product_type": "보관함",
                    "display_name": "나전 보관함",
                    "summary": "이미지 기반 설명",
                    "keywords": ["나전"],
                    "features": [],
                    "warnings": [],
                    "unexpected": "must be rejected",
                },
                "detail_page": {"mime_type": "image/png"},
            }
        )


def test_fe_response_aliases_validate_the_completed_contract():
    response = AiFeJobStatusResponseDto(
        job_id="job-1",
        request_id="request-1",
        status="COMPLETED",
        progress=100,
        result=AiFeResultResponseDto.model_validate(
            {
                "generation_id": "generation-1",
                "product": {
                    "product_type": "보관함",
                    "display_name": "나전 보관함",
                    "summary": "이미지 기반 설명",
                    "keywords": ["나전"],
                    "features": [],
                    "warnings": [],
                },
                "detail_page": {
                    "mime_type": "image/png",
                    "image_base64": "iVBORw0KGgo=",
                },
            }
        ),
        updated_at=datetime.now(timezone.utc),
    )

    assert response.result.detail_page.mime_type == "image/png"
    assert response.result.detail_page.photo_generation_failures == []
    assert response.result.detail_page.unused_generated_photo_ids == []


def test_fe_request_dto_is_available_from_package_public_api():
    assert PublicAiFeCreateJobRequestDto is AiFeCreateJobRequestDto


def test_fe_draft_response_dto_is_available_from_package_public_api():
    assert PublicAiFeDraftResponseDto is AiFeDraftResponseDto
