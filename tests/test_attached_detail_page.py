from scripts.runtime.generate_attached_detail_page import build_profile


def test_attached_profile_is_image_grounded_and_has_complete_editorial_plan():
    profile = build_profile()

    assert profile.product_type == "손잡이 부채"
    assert profile.display_name == "분홍 곡선 손잡이 부채"
    assert "정확한 소재" in profile.uncertain_information
    assert "가격" in " ".join(profile.uncertain_information)
    assert len(profile.page_plan) == 11
    assert profile.page_plan[0].block_type == "hero"
    assert profile.page_plan[-1].block_type == "closing"
    assert all(feature.evidence == "image-visible" for feature in profile.features)
