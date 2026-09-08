from detail_page_ai import dto
from detail_page_ai.dto import AiBeProductPersistRequest, GenerationMetadataDto
from detail_page_ai.models import GenerationOptions
from detail_page_ai.prompts import build_analysis_prompt


def test_creator_product_data_is_primary_source_for_analysis():
    hints = dto.UserHintsDto(
        product_name="나전 보관함",
        making_method="표면에 장식 문양을 더해 제작했습니다.",
        care_guide="마른 천으로 닦아 주세요.",
    )

    prompt = build_analysis_prompt(user_hints=hints)

    assert "나전 보관함" in prompt
    assert "표면에 장식 문양을 더해 제작했습니다." in prompt
    assert "마른 천으로 닦아 주세요." in prompt
    assert "creator-provided product data is the primary source" in prompt.lower()
    assert "제품명·제작과정·관리법" in prompt
    assert "이미지에 보이지 않는다는 이유만으로 입력 데이터를" in prompt
    assert "삭제하거나 추정으로 대체하지 마라" in prompt
    assert "입력 데이터가 이미지보다 우선" in prompt
    assert "이미지와 다르게" in prompt
    assert "입력 데이터를 기준으로 작성하라" in prompt
    assert "충돌 표시" not in prompt
    assert "충돌을 uncertain_information에 기록" not in prompt
    assert "User-provided hints are unverified context" not in prompt


def test_be_persist_request_keeps_creator_product_data_separate_from_profile():
    hints = dto.UserHintsDto(product_name="나전 보관함")
    profile = dto.ProductProfileDto.minimal("보관함")

    request = AiBeProductPersistRequest.from_profile(
        generation_id="generation-1",
        job_id="job-1",
        request_id="request-1",
        source_image_mime_type="image/png",
        source_image_sha256="source-hash",
        generated_image_mime_type="image/png",
        generated_width=774,
        generated_height=4096,
        generated_image_sha256="generated-hash",
        profile=profile,
        generation=GenerationMetadataDto(
            provider="test",
            analysis_model="test-model",
            image_model="html-css-browser",
        ),
        user_hints=hints,
    )

    assert request.user_hints == hints
    assert request.product == profile


def test_generation_options_remain_independent_from_user_hints():
    assert GenerationOptions().aspect_ratio == "1:4"
