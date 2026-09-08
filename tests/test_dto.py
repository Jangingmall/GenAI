import pytest
from pydantic import ValidationError

from detail_page_ai.dto import (
    AiBeProductPersistRequest,
    AiFeDraftResultDto,
    ApprovedDraftDto,
    AiFeProductSummaryDto,
    AiFeStatusResponse,
    FeDetailPageSectionDto,
    FeProductPhotoDto,
    GeneratedPhotoMetadataDto,
    GeneratedSectionMetadataDto,
    ProductProfileDto,
)
from detail_page_ai import models


def test_product_profile_serializes_observations_and_copy_separately():
    profile = ProductProfileDto(
        product_type="desk lamp",
        display_name="미니멀 데스크 램프",
        summary="깔끔한 형태의 데스크 램프",
        keywords=["미니멀", "데스크"],
        observations={"colors": ["black"], "shape": "rounded"},
        features=[
            {
                "title": "컴팩트한 형태",
                "description": "작은 공간에 어울리는 형태입니다.",
                "evidence": "image-visible",
                "confidence": 0.9,
            }
        ],
        copy_sections=[
            {
                "section_type": "hero",
                "title": "매일 함께하는 깔끔함",
                "description": "단정한 디자인의 데스크 램프",
            }
        ],
        usage_scene="책상 위 사용 장면",
        uncertain_information=["정확한 밝기 수치"],
        safety_notes=["밝기 수치를 단정하지 않음"],
    )

    payload = profile.model_dump()

    assert payload["observations"]["colors"] == ["black"]
    assert payload["copy_sections"][0]["section_type"] == "hero"
    assert payload["uncertain_information"] == ["정확한 밝기 수치"]


def test_product_profile_accepts_ai_composed_page_plan():
    profile = ProductProfileDto(
        product_type="금속 공예 세트",
        display_name="차잔을 넘어 테이블에 남는 형상",
        summary="서로 다른 금속 표면과 용기 형태가 함께 보이는 세트입니다.",
        page_plan=[
            {
                "section_id": "hero",
                "block_type": "hero",
                "eyebrow": "OBJECT TEA ART",
                "title": "차잔을 넘어",
                "body": "테이블에 남는 형상",
                "variant": "paper",
                "photo_id": "hero",
            },
            {
                "section_id": "palette",
                "block_type": "palette",
                "eyebrow": "PRODUCT GALLERY",
                "title": "4가지 금속 컬러",
                "items": [
                    {
                        "label": "Gold",
                        "value": "금빛 표면",
                        "description": "따뜻한 금속 색감",
                    }
                ],
            },
        ],
    )

    assert profile.page_plan[0].block_type == "hero"
    assert profile.page_plan[1].items[0].label == "Gold"


def test_ai_fe_processing_response_has_no_ai_be_internal_fields():
    response = AiFeStatusResponse.completed(
        job_id="job-1",
        request_id="request-1",
        generation_id="generation-1",
        profile=ProductProfileDto.minimal("desk lamp"),
        image_base64="ZmFrZQ==",
        mime_type="image/png",
    )

    payload = response.model_dump()

    assert payload["result"]["generation_id"] == "generation-1"
    assert "source_image_sha256" not in payload["result"]
    assert "prompt_version" not in payload["result"]
    assert "product_id" not in payload["result"]


def test_ai_be_payload_contains_idempotency_key_and_full_profile():
    request = AiBeProductPersistRequest.from_profile(
        generation_id="generation-1",
        job_id="job-1",
        request_id="request-1",
        source_image_mime_type="image/png",
        source_image_sha256="source-hash",
        generated_image_mime_type="image/png",
        generated_width=1024,
        generated_height=4096,
        generated_image_sha256="generated-hash",
        profile=ProductProfileDto.minimal("desk lamp"),
        generation={"prompt_version": "detail-page-v1"},
    )

    payload = request.model_dump()

    assert payload["idempotency_key"] == "generation-1"
    assert payload["source"]["sha256"] == "source-hash"
    assert payload["product"]["observations"] is not None
    assert payload["generation"]["prompt_version"] == "detail-page-v1"


def test_draft_response_exposes_structured_json_and_never_an_html_document():
    draft_data = {
        "draft_id": "job-1",
        "generation_id": "generation-1",
        "source_mime_type": "image/jpeg",
        "source_sha256": "source-hash",
        "product": AiFeProductSummaryDto.from_profile(ProductProfileDto.minimal("보관함")),
        "draft": ApprovedDraftDto(
            product_name="보관함",
            summary="이미지 기반 설명",
            hero_headline="제품의 특징",
            hero_description="이미지에서 확인되는 설명",
        ),
        "preview": {
            "source_asset_id": "source-asset-1",
            "source_sha256": "source-hash",
            "mime_type": "image/jpeg",
            "image_base64": "/9j/preview",
        },
    }
    draft = AiFeDraftResultDto(**draft_data)

    payload = draft.model_dump()

    assert "html" not in payload
    assert payload["draft"]["product_name"] == "보관함"
    assert payload["preview"]["source_asset_id"] == "source-asset-1"
    with pytest.raises(ValidationError):
        AiFeDraftResultDto(
            **draft_data,
            html="<script>alert('must not cross the boundary')</script>",
        )


def test_fe_and_be_section_contract_preserves_order_and_dimensions():
    fe_section = FeDetailPageSectionDto(
        section_id="hero",
        order=1,
        label="상품 소개",
        image_base64="aGVybw==",
        mime_type="image/png",
        width=774,
        height=526,
    )
    be_section = GeneratedSectionMetadataDto(
        section_id="hero",
        order=1,
        label="상품 소개",
        mime_type="image/png",
        width=774,
        height=526,
        sha256="hero-hash",
    )

    assert fe_section.model_dump()["order"] == 1
    assert be_section.model_dump()["width"] == 774


def test_photo_provenance_is_shared_by_domain_fe_and_be_contracts():
    transform = models.PhotoTransform(scale=0.72, x=132, y=240)
    photo = models.ProductPhoto(
        photo_id="lifestyle",
        order=4,
        label="활용 장면",
        data=b"photo",
        mime_type="image/png",
        asset_mode="source_composite",
        source_asset_id="asset-1",
        source_sha256="source-hash",
        cutout_sha256="cutout-hash",
        mask_sha256="mask-hash",
        background_generated=True,
        product_generated=False,
        transform=transform,
        fidelity_status="VERIFIED",
    )
    fe = FeProductPhotoDto(
        photo_id=photo.photo_id,
        order=photo.order,
        label=photo.label,
        mime_type=photo.mime_type,
        asset_mode=photo.asset_mode,
        source_asset_id=photo.source_asset_id,
        source_sha256=photo.source_sha256,
        cutout_sha256=photo.cutout_sha256,
        mask_sha256=photo.mask_sha256,
        background_generated=photo.background_generated,
        product_generated=photo.product_generated,
        transform=photo.transform,
        fidelity_status=photo.fidelity_status,
    )
    be = GeneratedPhotoMetadataDto(
        photo_id=photo.photo_id,
        order=photo.order,
        label=photo.label,
        mime_type=photo.mime_type,
        sha256="photo-hash",
        asset_mode=photo.asset_mode,
        source_asset_id=photo.source_asset_id,
        source_sha256=photo.source_sha256,
        cutout_sha256=photo.cutout_sha256,
        mask_sha256=photo.mask_sha256,
        background_generated=photo.background_generated,
        product_generated=photo.product_generated,
        transform=photo.transform,
        fidelity_status=photo.fidelity_status,
    )

    assert photo.product_generated is False
    assert fe.model_dump()["transform"]["scale"] == 0.72
    assert be.model_dump()["asset_mode"] == "source_composite"


def test_generated_lifestyle_scene_is_explicit_in_fe_and_be_metadata():
    common = {
        "photo_id": "lifestyle",
        "order": 4,
        "label": "AI 생성 활용 장면(참고용)",
        "mime_type": "image/png",
        "asset_mode": "generated_scene",
        "source_asset_id": "asset-1",
        "source_sha256": "source-hash",
        "background_generated": True,
        "product_generated": True,
        "fidelity_status": "GENERATED",
    }

    fe = FeProductPhotoDto(**common)
    be = GeneratedPhotoMetadataDto(sha256="photo-hash", **common)

    assert fe.model_dump()["product_generated"] is True
    assert fe.model_dump()["fidelity_status"] == "GENERATED"
    assert be.model_dump()["asset_mode"] == "generated_scene"


def test_generated_angle_detail_is_explicit_in_fe_and_be_metadata():
    common = {
        "photo_id": "detail-03",
        "order": 6,
        "label": "AI 생성 각도 디테일(참고용)",
        "mime_type": "image/png",
        "asset_mode": "generated_view",
        "source_asset_id": "asset-1",
        "source_sha256": "source-hash",
        "background_generated": True,
        "product_generated": True,
        "fidelity_status": "GENERATED",
    }

    fe = FeProductPhotoDto(**common)
    be = GeneratedPhotoMetadataDto(sha256="photo-hash", **common)

    assert fe.model_dump()["asset_mode"] == "generated_view"
    assert be.model_dump()["product_generated"] is True


def test_product_profile_carries_conservative_classification_confidence():
    profile = ProductProfileDto.minimal("나전 함").model_copy(
        update={
            "classification_confidence": 0.94,
            "craft_confidence": 0.81,
            "classification_reason": "표면에 반복되는 자개풍 문양이 보입니다.",
            "candidate_types": ["나전칠기", "장식함"],
        }
    )

    assert profile.craft_confidence == 0.81
    assert profile.candidate_types == ["나전칠기", "장식함"]
    fe_summary = AiFeProductSummaryDto.from_profile(profile)
    assert fe_summary.is_traditional_craft is False
    assert fe_summary.craft_confidence == 0.81
    assert fe_summary.classification_reason == "표면에 반복되는 자개풍 문양이 보입니다."
    assert fe_summary.candidate_types == ["나전칠기", "장식함"]
    assert fe_summary.observations == profile.observations


def test_approved_draft_converts_editor_changes_into_renderable_profile():
    draft = ApprovedDraftDto(
        product_name="수정한 나전함",
        summary="장인의 시간이 머무는 문양을 담은 보관함입니다.",
        hero_headline="수정한 핵심 문구",
        hero_description="장식과 구조를 중심으로 정리한 설명입니다.",
        usage_scene="서재 선반 위 활용 장면",
        features=[
            {
                "title": "수정한 특징",
                "description": "장인이 직접 다듬은 문구입니다.",
            }
        ],
        layout_id="catalog-grid",
    )

    profile = draft.to_profile()

    assert profile.display_name == "수정한 나전함"
    assert profile.layout_id == "catalog-grid"
    assert profile.copy_sections[0].title == "수정한 핵심 문구"
    assert profile.features[0].description == "장인이 직접 다듬은 문구입니다."
