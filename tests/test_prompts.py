from detail_page_ai.dto import ProductProfileDto, UserHintsDto
from detail_page_ai.prompts import (
    build_analysis_prompt,
    build_background_prompt,
    build_craft_research_prompt,
    build_generated_detail_cut_prompt,
    build_generated_usage_scene_prompt,
    build_usage_context_background_prompt,
)
from detail_page_ai.reference_guide import (
    REFERENCE_GUIDE_VERSION,
    build_image_mood_prompt,
    build_reference_guide_prompt,
)


def test_analysis_prompt_requires_image_visible_facts_only():
    prompt = build_analysis_prompt("ko-KR")

    assert "시각 정보의 보조 근거" in prompt
    assert "성능 수치" in prompt
    assert "JSON" in prompt
    assert "is_traditional_craft" in prompt
    assert "craft_type" in prompt
    assert "craft_confidence" in prompt
    assert "candidate_types" in prompt
    assert "layout_id" in prompt
    assert "image-first" in prompt
    assert "catalog-grid" in prompt
    assert "가능성이 있는" in prompt
    assert "page_plan" in prompt
    assert "block_type" in prompt


def test_glass_editing_does_not_inherit_plural_tea_staging_from_copy():
    profile = ProductProfileDto.minimal("유리잔").model_copy(update={
        "summary": "각각의 유리 잔은 서로 다른 표면을 지닙니다.",
        "usage_scene": "차를 나누는 테이블",
    })
    for role in ("lifestyle", "detail-02", "detail-03", "detail-04", "detail-05"):
        prompt = (build_generated_usage_scene_prompt(profile) if role == "lifestyle"
                  else build_generated_detail_cut_prompt(profile, role))
        assert "exactly ONE object" in prompt
        assert "Transparent glass must remain clear" in prompt
        assert "serving arrangement" not in prompt
        assert "각각의" not in prompt


def test_analysis_prompt_uses_agreed_be_content_contract():
    prompt = build_analysis_prompt("ko-KR").lower()

    assert "images" in prompt
    assert "imageid" in prompt
    assert "3 to 12" in prompt
    assert "productname" in prompt
    assert "howmade" in prompt
    assert "caretips" in prompt
    assert "order" in prompt
    assert "tag" in prompt
    assert "imageurl" in prompt
    assert "h2, p, img, video" in prompt
    assert "do not generate new images" in prompt
    assert "imageid" in prompt and "imageurl" in prompt


def test_analysis_prompt_requests_reference_inspired_adaptive_editorial_story():
    prompt = build_analysis_prompt("ko-KR").lower()

    assert "premium craft editorial" in prompt
    assert "9 to 12" in prompt
    assert "hero must be first" in prompt
    assert "closing must be last" in prompt
    assert "dark detail_split" in prompt
    assert "full-bleed usage_scene" in prompt
    assert "always include exactly one gallery" in prompt
    assert "palette is optional and must never replace the gallery" in prompt
    assert "recommendation" in prompt
    assert "info_table" in prompt
    assert "notice" in prompt
    assert "not a fixed template" in prompt


def test_analysis_prompt_applies_detail_page_guide_visual_direction():
    prompt = build_analysis_prompt("ko-KR")

    assert "Pretendard" in prompt
    assert "cool grey" in prompt.lower()
    assert "jade blue" in prompt.lower()
    assert "black and white" in prompt.lower()
    assert "image and text" in prompt.lower()
    assert "do not copy sample text" in prompt.lower()
    assert "no gradients" in prompt.lower()


def test_analysis_prompt_builds_an_evidence_led_premium_editorial_arc():
    prompt = build_analysis_prompt("ko-KR").lower()

    assert "editorial decision protocol" in prompt
    assert "one concrete visual truth" in prompt
    assert "hook → proof → context → use → information → close" in prompt
    assert "do not repeat the same claim" in prompt
    assert "generic luxury adjectives" in prompt
    assert "silhouette-led" in prompt
    assert "texture-led" in prompt
    assert "set-led" in prompt
    assert "일상 속 작은 예술" in prompt
    assert "조용한 변화" in prompt


def test_analysis_prompt_treats_product_introduction_as_a_section_aware_copy_brief():
    prompt = " ".join(
        build_analysis_prompt(
            "ko-KR",
            user_hints=UserHintsDto(
                product_name="숨의잔",
                making_method=(
                    "자유 취입 방식으로 제작한 유리 잔입니다. 일정한 틀 없이 호흡과 "
                    "순간의 감각에 따라 형태가 만들어집니다."
                ),
                care_guide="충격과 급격한 온도 변화를 피해주세요.",
            ),
        )
        .lower()
        .split()
    )

    assert "product introduction copy brief" in prompt
    assert "extract the product introduction into these fact slots" in prompt
    assert "identity, making/process, sensory/visual, use, care, and unknown" in prompt
    assert "do not replace a supplied product fact with generic praise" in prompt
    assert "hero: preserve the product identity" in prompt
    assert "statement: explain the supplied making/process story" in prompt
    assert "feature_grid: convert three distinct" in prompt
    assert "notice: use only supplied care guidance" in prompt
    assert "do not expose the copy brief, search process, or source urls" in prompt
    assert "숨의잔" in prompt
    assert "자유 취입 방식" in prompt
    assert "충격과 급격한 온도 변화를 피해주세요." in prompt


def test_analysis_prompt_blocks_invented_care_and_search_claims_in_customer_copy():
    prompt = " ".join(build_analysis_prompt("ko-KR").lower().split())

    assert "care data gate" in prompt
    assert 'if care_guide is absent, write "확인 필요"' in prompt
    assert "do not infer care from material, search, common knowledge, or visual appearance" in prompt
    assert "customer-facing product copy may use only creator or image evidence" in prompt
    assert "search_general" in prompt
    assert (
        'when care_guide is absent, including when the care_guide value is "(none)", '
        "the notice block must be exactly"
    ) in prompt
    assert "관리 안내는 제공되지 않아 확인 필요합니다." in prompt
    assert "do not mention temperature, impact, cleaning, detergent, or handling" in prompt


def test_detail_page_guide_is_a_single_reusable_prompt_contract():
    guide = build_reference_guide_prompt()

    assert REFERENCE_GUIDE_VERSION == "detail-page-guide-v2-premium-editorial"
    assert "Pretendard" in guide
    assert "#FAFBFC" in guide
    assert "#DAE6E8" in guide
    assert "3-up then 2-up" in guide
    assert "Do / Don't" in guide
    assert "Do not copy sample text" in guide


def test_image_2_mood_guide_contains_product_photography_do_and_dont_rules():
    guide = build_image_mood_prompt()

    assert "Image-2" in guide
    assert "white, light-grey, or deep single-color backgrounds" in guide
    assert "natural-looking soft light" in guide
    assert "material, pattern, texture" in guide
    assert "no mid-tone grey or color gradients" in guide.lower()
    assert "no modern gadgets" in guide.lower()
    assert "product remains the visual anchor" in guide.lower()
    assert "single dominant light source" in guide.lower()
    assert "material micro-contrast" in guide.lower()
    assert "prop must have a clear relationship" in guide.lower()
    assert "85mm" in guide


def test_craft_research_prompt_requires_grounded_search_and_no_authenticity_claim():
    profile = ProductProfileDto.minimal("한지 부채").model_copy(
        update={
            "is_traditional_craft": True,
            "craft_type": "한지 공예",
        }
    )

    prompt = build_craft_research_prompt(profile, "ko-KR")

    assert "Google Search" in prompt
    assert "공식" in prompt
    assert "진품" in prompt
    assert "sources" in prompt


def test_research_prompt_uses_product_data_as_primary_product_context():
    profile = ProductProfileDto.minimal("나전 보관함")
    prompt = build_craft_research_prompt(
        profile,
        "ko-KR",
        user_hints=UserHintsDto(
            product_name="나전 보관함",
            making_method="전복 껍데기 조각을 표면에 붙여 장식했습니다.",
        ),
    )

    assert "전복 껍데기 조각" in prompt
    assert "보완" in prompt
    assert "creator-provided product data" in prompt.lower()
    assert "primary source" in prompt.lower()
    assert "사용자 입력은 상품별 카피의 기준 데이터다" in prompt
    assert "사용자 입력을 증거로 취급하지 마라" not in prompt


def test_background_prompt_reserves_space_without_requesting_a_product():
    profile = ProductProfileDto.minimal("나전 함").model_copy(
        update={"usage_scene": "차분한 거실 선반 위 보관 장면"}
    )

    prompt = build_background_prompt(profile, "lifestyle", "ko-KR")

    assert "empty" in prompt.lower()
    assert "product-free" in prompt.lower()
    assert "차분한 거실 선반 위 보관 장면" in prompt
    assert "Do not draw" in prompt
    assert "empty tabletop" in prompt.lower()
    assert "lower-center" in prompt.lower()
    assert "no furniture" in prompt.lower()


def test_usage_context_prompt_requests_a_product_free_background_for_exact_composite():
    profile = ProductProfileDto.minimal("금속 공예 세트").model_copy(
        update={"usage_scene": "사람이 주전자에서 차를 따라 잔에 내는 장면"}
    )

    prompt = build_usage_context_background_prompt(profile, "ko-KR")

    assert "product-free" in prompt.lower()
    assert "usage context" in prompt.lower()
    assert "original product" in prompt.lower()
    assert "text" in prompt.lower()
    assert "dining table" in prompt.lower()
    assert "차" not in prompt


def test_usage_context_prompt_describes_a_realistic_room_not_an_empty_studio():
    profile = ProductProfileDto.minimal("나전 보관함")

    prompt = build_usage_context_background_prompt(profile, "ko-KR")

    assert "walnut" in prompt.lower()
    assert "bookcase" in prompt.lower()
    assert "open foreground" in prompt.lower()
    assert "not an isolated studio" in prompt.lower()
    assert "must visibly show" in prompt.lower()


def test_usage_context_prompt_matches_a_natural_product_photo_camera_and_light():
    profile = ProductProfileDto.minimal("나전 보관함")

    prompt = build_usage_context_background_prompt(profile, "ko-KR").lower()

    assert "tabletop height" in prompt
    assert "50mm" in prompt
    assert "no wide-angle distortion" in prompt
    assert "unstyled photograph" in prompt
    assert "wide open matte wood foreground" in prompt


def test_usage_context_prompt_includes_requested_ecommerce_visual_direction():
    profile = ProductProfileDto.minimal("나전 보관함")

    prompt = build_usage_context_background_prompt(profile, "ko-KR").lower()

    assert "e-commerce product background" in prompt
    assert "modern layout" in prompt
    assert "soft lighting" in prompt
    assert "minimal design" in prompt


def test_usage_context_background_prompt_does_not_leak_product_terms_to_flux():
    profile = ProductProfileDto.minimal("금속 주전자와 잔 세트").model_copy(
        update={
            "display_name": "오브제형 은제 차기 세트",
            "summary": "주전자와 찻잔이 함께 놓인 금속 공예품",
            "usage_scene": "차를 내는 테이블",
            "keywords": ["주전자", "찻잔", "병"],
        }
    )

    prompt = build_usage_context_background_prompt(profile, "ko-KR")

    assert "주전자" not in prompt
    assert "찻잔" not in prompt
    assert "차기 세트" not in prompt
    assert "금속 공예품" not in prompt
    assert "empty interior background plate" in prompt


def test_generated_usage_scene_prompt_matches_reference_like_real_scene():
    profile = ProductProfileDto.minimal("금속 공예 세트").model_copy(
        update={
            "display_name": "다양한 금속 소재의 병과 잔 세트",
            "summary": "서로 다른 금속 광택의 병과 잔이 함께 보이는 구성",
            "usage_scene": "차를 내는 조용한 테이블 위 활용 장면",
            "observations": {"visible_components": ["병", "주전자", "잔"]},
            "keywords": ["세트", "금속", "차 도구"],
        }
    )

    prompt = build_generated_usage_scene_prompt(profile, "ko-KR").lower()

    assert "supplied product image" in prompt
    assert "quiet tea table" in prompt
    assert "preserve the visual identity of every visible item" in prompt
    assert "soft side lighting" in prompt
    assert "natural arrangement" in prompt
    assert "e-commerce product background" in prompt
    assert "no text" in prompt
    assert "floating shelf" not in prompt
    assert "image-2" in prompt
    assert "natural-looking soft light" in prompt
    assert "no mid-tone grey or color gradients" in prompt


def test_generated_usage_scene_prompt_uses_a_precise_luxury_shoot_brief():
    profile = ProductProfileDto.minimal("나전 보관함").model_copy(
        update={
            "display_name": "다층 나전 수납함",
            "summary": "어두운 표면에 꽃과 잎 문양이 반복되는 다층 수납함",
            "usage_scene": "서재 책상 위에서 소품을 정돈하는 장면",
            "keywords": ["나전칠기", "수납함", "보석함"],
        }
    )

    prompt = build_generated_usage_scene_prompt(profile, "ko-KR").lower()

    assert "premium shoot brief" in prompt
    assert "product fidelity has priority over atmosphere" in prompt
    assert "70mm" in prompt
    assert "one dominant window-light direction" in prompt
    assert "hero-safe copy space" in prompt
    assert "surface contact" in prompt
    assert "props are optional" in prompt
    assert "editorial restraint" in prompt
    assert len(prompt) < 3600
    assert prompt.index("lifestyle setting") < 900
    assert prompt.index("placement direction") < 1500


def test_textile_usage_scene_prompt_requires_natural_functional_placement():
    profile = ProductProfileDto.minimal("수묵화 문양 손수건").model_copy(
        update={
            "display_name": "수묵화 문양 손수건",
            "summary": "흰 직물 위에 먹빛 식물 문양과 짙은 테두리가 보이는 사각 직물",
            "usage_scene": "정돈된 생활 공간에서 직물을 펼쳐 사용하는 장면",
            "keywords": ["직물", "손수건", "수묵화"],
        }
    )

    prompt = build_generated_usage_scene_prompt(profile, "ko-KR").lower()

    assert "placement direction" in prompt
    assert "draped or folded naturally" in prompt
    assert "must not stand upright" in prompt
    assert "believable use action" in prompt
    assert "not a seamless studio sweep" in prompt
    assert "no second textile" in prompt
    assert "one folded linen textile" not in prompt


def test_generated_detail_cut_prompt_assigns_one_angle_and_three_distinct_jobs():
    profile = ProductProfileDto.minimal("나전 보관함")

    angle = build_generated_detail_cut_prompt(profile, "detail-02", "ko-KR").lower()
    macro = build_generated_detail_cut_prompt(profile, "detail-03", "ko-KR").lower()
    usage = build_generated_detail_cut_prompt(profile, "detail-04", "ko-KR").lower()
    editorial = build_generated_detail_cut_prompt(profile, "detail-05", "ko-KR").lower()

    assert "front-left" in angle
    assert "18-degree" in angle
    assert "camera at table height" in angle
    assert "left edge appears closer" in angle
    assert "not a top-down view" in angle
    assert "low side-on" in angle
    assert "macro" in macro
    assert "surface texture" in macro
    assert "one continuous product surface" in macro
    assert "no product placed on another product" in macro
    assert "no small product in the foreground" in macro
    assert "real-use" in usage
    assert "functional context" in usage
    assert "top-down" in editorial
    assert "editorial arrangement" in editorial
    assert "not a low-angle shot" in editorial
    assert len({angle, macro, usage, editorial}) == 4
    for prompt in (angle, macro, usage, editorial):
        assert "exact supplied product" in prompt
        assert "same number of items" in prompt
        assert "preserve pattern" in prompt
        assert "85mm" in prompt
        assert "no duplicate" in prompt
        assert len(prompt) < 2200


def test_generated_detail_cut_prompt_rejects_the_original_detail_slot():
    profile = ProductProfileDto.minimal("나전 보관함")

    try:
        build_generated_detail_cut_prompt(profile, "detail", "ko-KR")
    except ValueError as exc:
        assert "detail-02" in str(exc)
        assert "detail-05" in str(exc)
    else:
        raise AssertionError("the original detail slot must never be generated")


def test_generated_usage_scene_prompt_uses_identity_lock_for_prompt_only_editing():
    profile = ProductProfileDto.minimal("금속 공예 세트")

    prompt = build_generated_usage_scene_prompt(profile, "ko-KR").lower()

    assert "identity lock" in prompt
    assert "pixel-exact preservation is performed by the source compositor" in prompt
    assert "retain the source-facing view" in prompt
    assert "same number" in prompt
    assert "do not change the product" in prompt
    assert "background and environment only" in prompt


def test_generated_usage_scene_prompt_adapts_storage_products_to_a_study_setting():
    profile = ProductProfileDto.minimal("나전 보관함").model_copy(
        update={
            "display_name": "다층 나전 수납함",
            "summary": "어두운 표면에 꽃과 잎 문양이 반복되는 다층 수납함",
            "usage_scene": "책상 위 소품과 중요한 물건을 정돈해 보관하는 장면",
            "keywords": ["나전칠기", "수납함", "보석함", "어두운 광택"],
            "observations": {"colors": ["검정", "갈색", "금빛"], "shape": "직사각형"},
        }
    )

    prompt = build_generated_usage_scene_prompt(profile, "ko-KR").lower()

    assert "writing desk" in prompt
    assert "bookcase" in prompt
    assert "walnut" in prompt
    assert "observed palette" in prompt
    assert "leave the near foreground clear" in prompt
    assert "quiet tea table" not in prompt


def test_generated_usage_scene_prompt_adapts_tea_products_to_a_serving_setting():
    profile = ProductProfileDto.minimal("금속 주전자와 찻잔 세트").model_copy(
        update={
            "display_name": "오브제형 티 세트",
            "summary": "서로 다른 금속 광택의 주전자와 잔이 함께 보이는 구성",
            "usage_scene": "차를 내는 조용한 테이블 위 활용 장면",
            "keywords": ["주전자", "찻잔", "차 도구", "금속"],
        }
    )

    prompt = build_generated_usage_scene_prompt(profile, "ko-KR").lower()

    assert "quiet tea table" in prompt
    assert "warm taupe" in prompt
    assert "dark matte wood or honed stone" in prompt
    assert "writing desk" not in prompt


def test_scene_direction_does_not_misclassify_a_calm_non_tea_product_as_tea():
    profile = ProductProfileDto.minimal("나전 보관함").model_copy(
        update={
            "summary": "차분한 색감과 반복 문양이 돋보이는 직사각형 수납함",
            "usage_scene": "차분한 서재 책상 위에 소품을 정돈하는 장면",
            "keywords": ["수납", "나전칠기"],
        }
    )

    prompt = build_generated_usage_scene_prompt(profile, "ko-KR").lower()

    assert "writing desk" in prompt
    assert "quiet tea table" not in prompt
