import logging

import pytest
from pydantic import ValidationError

from detail_page_ai.dto import (
    ApprovedDraftDto,
    PageBlockDto,
    PageBlockItemDto,
)
from detail_page_ai.react_document import ReactDetailPageDocumentDto
from detail_page_ai.react_document_builder import (
    build_react_document_from_draft,
    resolve_page_block_photos,
    resolve_page_plan_photos,
)


def _walk(node):
    yield node
    if node.get("type") == "element":
        for child in node.get("children", []):
            yield from _walk(child)


def _style(node):
    return node["props"]["style"]


def _zero_edges():
    return {"top": 0.0, "right": 0.0, "bottom": 0.0, "left": 0.0}


def _edge_values(value):
    return {"top": float(value), "right": float(value), "bottom": float(value), "left": float(value)}


def test_builder_emits_react_json_ast_with_image_ids_and_aliases():
    draft = ApprovedDraftDto(
        product_name="숨의잔",
        summary="자유 취입으로 완성한 유리 잔입니다.",
        hero_headline="호흡이 만든 하나의 잔",
        hero_description="빛과 액체에 따라 다른 표정을 보여 줍니다.",
        page_plan=[
            PageBlockDto(
                section_id="hero",
                block_type="hero",
                eyebrow="PRODUCT STORY",
                title="숨의잔",
                body="자유 취입으로 완성한 유리 잔입니다.",
                photo_id="hero",
            ),
            PageBlockDto(
                section_id="gallery",
                block_type="gallery",
                title="가까이 보는 표면",
                body="빛에 따라 달라지는 표면을 살펴보세요.",
                photo_ids=["detail", "detail-02"],
                items=[PageBlockItemDto(label="표면", value="미세하게 다른 균형")],
            ),
        ],
    )

    document = build_react_document_from_draft(draft)
    payload = document.model_dump(by_alias=True, exclude_none=True)

    assert payload["schemaVersion"] == "2.0"
    assert payload["canvasWidth"] == 774
    assert payload["root"][0]["type"] == "element"
    assert payload["root"][0]["tag"] == "section"
    image_nodes = [
        node
        for root in payload["root"]
        for node in _walk(root)
        if node.get("type") == "element" and node.get("tag") == "img"
    ]
    assert {node["props"]["imageId"] for node in image_nodes} == {
        "hero",
        "detail",
        "detail-02",
    }
    assert all(
        key not in payload
        for key in ("html", "css", "script", "dangerouslySetInnerHTML")
    )


def test_builder_falls_back_to_existing_block_default_for_missing_photo_id(caplog):
    draft = ApprovedDraftDto(
        product_name="숨의잔",
        summary="자유 취입으로 완성한 유리 잔입니다.",
        hero_headline="호흡이 만든 하나의 잔",
        hero_description="빛과 액체에 따라 다른 표정을 보여 줍니다.",
        page_plan=[
            PageBlockDto(
                section_id="wide",
                block_type="wide_image",
                title="넓게 보는 표면",
                photo_id="wide",
            )
        ],
    )

    with caplog.at_level(
        logging.WARNING, logger="detail_page_ai.react_document_builder"
    ):
        document = build_react_document_from_draft(
            draft, available_photo_ids={"hero", "detail"}
        )

    image_ids = [
        node["props"]["image_id"]
        for root in document.root
        for node in _walk(root.model_dump())
        if node.get("type") == "element" and node.get("tag") == "img"
    ]
    assert image_ids == ["hero"]
    assert "wide" in caplog.text
    assert "hero" in caplog.text


def test_builder_omits_image_when_requested_photo_and_default_are_missing(caplog):
    draft = ApprovedDraftDto(
        product_name="숨의잔",
        summary="자유 취입으로 완성한 유리 잔입니다.",
        hero_headline="호흡이 만든 하나의 잔",
        hero_description="빛과 액체에 따라 다른 표정을 보여 줍니다.",
        page_plan=[
            PageBlockDto(
                section_id="wide",
                block_type="wide_image",
                title="넓게 보는 표면",
                photo_id="wide",
            )
        ],
    )

    with caplog.at_level(
        logging.WARNING, logger="detail_page_ai.react_document_builder"
    ):
        document = build_react_document_from_draft(
            draft, available_photo_ids={"detail"}
        )

    assert not any(
        node.get("type") == "element" and node.get("tag") == "img"
        for root in document.root
        for node in _walk(root.model_dump())
    )
    assert "wide" in caplog.text
    assert "hero" in caplog.text


def test_builder_does_not_emit_reference_labels():
    draft = ApprovedDraftDto(
        product_name="숨의잔",
        summary="자유 취입으로 완성한 유리 잔입니다.",
        hero_headline="호흡이 만든 하나의 잔",
        hero_description="빛과 액체에 따라 다른 표정을 보여 줍니다.",
        page_plan=[
            PageBlockDto(section_id="hero", block_type="hero", photo_id="hero"),
            PageBlockDto(
                section_id="usage",
                block_type="usage_scene",
                photo_id="lifestyle",
            ),
        ],
    )

    payload = build_react_document_from_draft(draft).model_dump(
        by_alias=True, exclude_none=True
    )
    figures = {
        figure["children"][0]["props"]["imageId"]: figure
        for root in payload["root"]
        for figure in _walk(root)
        if figure.get("type") == "element" and figure.get("tag") == "figure"
    }

    assert figures["hero"]["children"] == [figures["hero"]["children"][0]]
    assert figures["lifestyle"]["children"] == [figures["lifestyle"]["children"][0]]
    figcaptions = [
        node
        for root in payload["root"]
        for node in _walk(root)
        if node.get("type") == "element" and node.get("tag") == "figcaption"
    ]
    assert not figcaptions


def test_builder_emits_guide_driven_typography_groups_and_feature_cards():
    draft = ApprovedDraftDto(
        product_name="나전 보관함",
        summary="어두운 바탕에 자개 문양이 장식된 보관함입니다.",
        hero_headline="빛을 담아내는 나전 보관함",
        hero_description="검은 바탕 위 자개 문양이 빛의 방향에 따라 다른 표정을 보여 줍니다.",
        page_plan=[
            PageBlockDto(
                section_id="hero",
                block_type="hero",
                eyebrow="PRODUCT STORY",
                photo_id="hero",
            ),
            PageBlockDto(
                section_id="features",
                block_type="feature_grid",
                eyebrow="VISIBLE DETAILS",
                title="가까이 볼수록 선명해지는 디테일",
                body="원본 이미지에서 확인되는 특징을 정리했습니다.",
                items=[
                    PageBlockItemDto(label="반복 문양", value="꽃과 구름 문양이 이어집니다."),
                    PageBlockItemDto(label="빛의 변화", value="표면의 색감이 각도에 따라 달라집니다."),
                    PageBlockItemDto(label="직사각형 실루엣", value="평평한 면과 안정적인 비례가 보입니다."),
                ],
            ),
            PageBlockDto(
                section_id="detail",
                block_type="detail_split",
                eyebrow="SURFACE DETAIL",
                title="표면의 대비",
                body="어두운 바탕과 장식 문양의 대비가 표면의 인상을 만듭니다.",
                variant="dark",
                photo_id="detail",
            ),
        ],
    )

    payload = build_react_document_from_draft(draft).model_dump(
        by_alias=True, exclude_none=True
    )

    hero = payload["root"][0]
    assert _style(hero)["padding"] == _edge_values(40)
    assert hero["props"]["layout"]["gap"] == 24.0
    hero_copy = hero["children"][0]
    hero_media = hero["children"][1]
    assert hero_copy["tag"] == "div"
    assert hero_copy["props"]["layout"]["display"] == "stack"
    assert [child["tag"] for child in hero_copy["children"]] == ["span", "h2", "p"]
    assert hero_media["tag"] == "div"

    eyebrow_style = _style(hero_copy["children"][0])
    assert eyebrow_style["fontFamily"] == "sans"
    assert eyebrow_style["fontSize"] == 13.0
    assert eyebrow_style["fontWeight"] == 500
    assert eyebrow_style["lineHeight"] == 1.5
    assert eyebrow_style["margin"] == _zero_edges()

    title_style = _style(hero_copy["children"][1])
    assert title_style["fontSize"] == 40.0
    assert title_style["fontWeight"] == 700
    assert title_style["lineHeight"] == 1.25
    assert title_style["margin"] == _zero_edges()

    body_style = _style(hero_copy["children"][2])
    assert body_style["fontSize"] == 16.0
    assert body_style["fontWeight"] == 400
    assert body_style["lineHeight"] == 1.7
    assert body_style["margin"] == _zero_edges()
    assert _style(hero_media["children"][0])["margin"] == _zero_edges()

    features = payload["root"][1]
    cards = features["children"][1]
    assert cards["tag"] == "div"
    assert cards["props"]["layout"] == {
        "display": "grid",
        "columns": 3,
        "gap": 16.0,
        "wrap": False,
        "align": "stretch",
    }
    assert len(cards["children"]) == 3
    for card in cards["children"]:
        assert card["tag"] == "article"
        assert card["props"]["layout"]["display"] == "stack"
        assert card["props"]["layout"]["gap"] == 12.0
        card_style = _style(card)
        assert card_style["padding"] == _edge_values(20)
        assert card_style["borderRadius"] == 12.0
        assert card_style["margin"] == _zero_edges()
        assert [child["tag"] for child in card["children"]] == ["h3", "p"]
        assert _style(card["children"][0])["fontSize"] == 19.0
        assert _style(card["children"][0])["fontWeight"] == 600
        assert _style(card["children"][0])["lineHeight"] == 1.4
        assert _style(card["children"][1])["fontSize"] == 16.0
        assert _style(card["children"][1])["fontWeight"] == 400

    detail = payload["root"][2]
    assert detail["props"]["layout"]["display"] == "flex"
    assert [child["tag"] for child in detail["children"]] == ["div", "div"]
    assert [child["tag"] for child in detail["children"][0]["children"]] == [
        "span",
        "h2",
        "p",
    ]
    assert detail["children"][1]["children"][0]["tag"] == "figure"


def test_react_document_rejects_executable_tags_and_javascript_links():
    with pytest.raises(ValidationError):
        ReactDetailPageDocumentDto.model_validate(
            {
                "schemaVersion": "2.0",
                "canvasWidth": 774,
                "root": [
                    {"id": "bad-script", "type": "element", "tag": "script"}
                ],
            }
        )

    with pytest.raises(ValidationError):
        ReactDetailPageDocumentDto.model_validate(
            {
                "schemaVersion": "2.0",
                "canvasWidth": 774,
                "root": [
                    {
                        "id": "bad-link",
                        "type": "element",
                        "tag": "a",
                        "props": {"href": "javascript:alert(1)"},
                    }
                ],
            }
        )


def test_react_document_rejects_invalid_parent_child_relationships():
    with pytest.raises(ValidationError):
        ReactDetailPageDocumentDto.model_validate(
            {
                "schemaVersion": "2.0",
                "canvasWidth": 774,
                "root": [
                    {
                        "id": "invalid-list",
                        "type": "element",
                        "tag": "ul",
                        "children": [
                            {"id": "not-li", "type": "text", "value": "잘못된 항목"}
                        ],
                    }
                ],
            }
        )


def test_react_document_limits_depth_and_duplicate_node_ids():
    duplicate = {
        "schemaVersion": "2.0",
        "canvasWidth": 774,
        "root": [
            {
                "id": "same-id",
                "type": "element",
                "tag": "section",
                "children": [{"id": "same-id", "type": "text", "value": "중복"}],
            }
        ],
    }

    with pytest.raises(ValidationError):
        ReactDetailPageDocumentDto.model_validate(duplicate)


def test_resolve_page_plan_photos_replaces_unavailable_photo_with_default(caplog):
    plan = [
        PageBlockDto(
            section_id="hero",
            block_type="hero",
            photo_id="hero",
        ),
        PageBlockDto(
            section_id="scale_ref",
            block_type="scale_reference",
            photo_id="scale",
        ),
    ]

    with caplog.at_level(logging.WARNING, logger="detail_page_ai.react_document_builder"):
        resolved = resolve_page_plan_photos(
            plan,
            available_photo_ids={"hero", "detail", "lifestyle"},
            log_warnings=True,
        )

    assert resolved[0].photo_id == "hero"
    assert resolved[1].photo_id == "hero"
    assert "photo_id 'scale' requested by scale_reference block is unavailable; using default photo_id 'hero'" in caplog.text


def test_resolve_page_plan_photos_filters_gallery_unavailable_photos(caplog):
    plan = [
        PageBlockDto(
            section_id="gallery",
            block_type="gallery",
            photo_ids=["detail", "scale", "detail-02"],
        ),
    ]

    with caplog.at_level(logging.WARNING, logger="detail_page_ai.react_document_builder"):
        resolved = resolve_page_plan_photos(
            plan,
            available_photo_ids={"hero", "detail", "detail-02"},
            log_warnings=True,
        )

    assert resolved[0].photo_ids == ["detail", "detail-02"]
    assert "photo_id 'scale' requested by gallery block is unavailable" in caplog.text


def test_resolve_page_plan_photos_clears_photo_when_default_also_unavailable(caplog):
    plan = [
        PageBlockDto(
            section_id="scale_ref",
            block_type="scale_reference",
            photo_id="scale",
        ),
    ]

    with caplog.at_level(logging.WARNING, logger="detail_page_ai.react_document_builder"):
        resolved = resolve_page_plan_photos(
            plan,
            available_photo_ids={"detail"},
            log_warnings=True,
        )

    assert resolved[0].photo_id is None
    assert "photo_id 'scale' requested by scale_reference block is unavailable and default photo_id 'hero' is unavailable" in caplog.text


def test_build_react_document_does_not_mutate_draft_page_plan(caplog):
    draft = ApprovedDraftDto(
        product_name="초충도 부채 세트",
        summary="전통 공예 부채입니다.",
        hero_headline="부채의 멋",
        hero_description="한지와 대나무 살이 어우러진 부채입니다.",
        page_plan=[
            PageBlockDto(
                section_id="scale_reference",
                block_type="scale_reference",
                title="부채와 파우치의 비율",
                photo_id="scale",
            ),
        ],
    )

    with caplog.at_level(logging.WARNING, logger="detail_page_ai.react_document_builder"):
        doc = build_react_document_from_draft(
            draft, available_photo_ids={"hero", "detail"}
        )

    # The caller's draft.page_plan must NOT be mutated in-place
    assert draft.page_plan[0].photo_id == "scale"
    # The react document should reference resolved 'hero'
    img_nodes = [
        node
        for root in doc.root
        for node in _walk(root.model_dump())
        if node.get("type") == "element" and node.get("tag") == "img"
    ]
    assert len(img_nodes) == 1
    assert img_nodes[0]["props"]["image_id"] == "hero"
    # Warning was logged
    assert "photo_id 'scale' requested by scale_reference block is unavailable; using default photo_id 'hero'" in caplog.text


def test_gallery_uses_generated_detail_cuts_when_available_ignoring_model_request():
    draft = ApprovedDraftDto(
        product_name="백자 다기 세트",
        summary="전통 기법으로 빚어낸 백자 다기입니다.",
        hero_headline="단아한 선의 백자",
        hero_description="백색의 은은한 광택과 단아한 선이 돋보입니다.",
        page_plan=[
            PageBlockDto(
                section_id="gallery",
                block_type="gallery",
                title="상세 컷",
                body="각도별 디테일을 확인하세요.",
                photo_ids=["hero"],  # Model gave non-standard photo_ids
            ),
        ],
    )
    available = {"hero", "detail", "detail-02", "detail-03", "detail-04", "detail-05"}
    doc = build_react_document_from_draft(draft, available_photo_ids=available)

    image_ids = [
        node["props"]["image_id"]
        for root in doc.root
        for node in _walk(root.model_dump())
        if node.get("type") == "element" and node.get("tag") == "img"
    ]
    assert image_ids == ["detail", "detail-02", "detail-03", "detail-04", "detail-05"]


def test_gallery_preserves_model_photo_ids_when_no_generated_cuts_available():
    draft = ApprovedDraftDto(
        product_name="백자 다기 세트",
        summary="전통 기법으로 빚어낸 백자 다기입니다.",
        hero_headline="단아한 선의 백자",
        hero_description="백색의 은은한 광택과 단아한 선이 돋보입니다.",
        page_plan=[
            PageBlockDto(
                section_id="gallery",
                block_type="gallery",
                title="상세 컷",
                body="각도별 디테일을 확인하세요.",
                photo_ids=["hero"],  # Model gave hero, and no generated detail cuts exist
            ),
        ],
    )
    available = {"hero", "detail"}
    doc = build_react_document_from_draft(draft, available_photo_ids=available)

    image_ids = [
        node["props"]["image_id"]
        for root in doc.root
        for node in _walk(root.model_dump())
        if node.get("type") == "element" and node.get("tag") == "img"
    ]
    assert image_ids == ["hero"]


def test_png_and_react_document_use_same_gallery_photos():
    import base64
    import re
    from detail_page_ai.html_renderer import build_detail_page_html
    from detail_page_ai.models import ProductPhoto, ProductPhotoSet

    photo_ids = ["hero", "detail", "detail-02", "detail-03", "detail-04", "detail-05"]
    photos = tuple(
        ProductPhoto(
            photo_id=pid,
            order=i,
            label=f"Photo {pid}",
            data=f"raw-photo-data-{pid}".encode(),
            mime_type="image/png",
            source_sha256="dummy-sha",
            product_generated=(pid.startswith("detail-0")),
            asset_mode="generated_view" if pid.startswith("detail-0") else "source_crop",
            fidelity_status="GENERATED" if pid.startswith("detail-0") else "VERIFIED",
        )
        for i, pid in enumerate(photo_ids, start=1)
    )
    photo_set = ProductPhotoSet(photos=photos)
    available_ids = {p.photo_id for p in photos}

    gallery_block = PageBlockDto(
        section_id="gallery",
        block_type="gallery",
        title="상세 컷",
        body="각도별 디테일",
        photo_ids=["hero"],  # Model incorrectly requested only hero
    )

    draft = ApprovedDraftDto(
        product_name="백자 다기 세트",
        summary="전통 기법으로 빚어낸 백자 다기입니다.",
        hero_headline="단아한 선의 백자",
        hero_description="백색의 은은한 광택과 단아한 선이 돋보입니다.",
        page_plan=[gallery_block],
    )
    profile = draft.to_profile()

    # 1. HTML rendered for PNG output
    html = build_detail_page_html(
        profile,
        b"dummy-source-bytes",
        mime_type="image/png",
        photo_set=photo_set,
    )
    gallery_section = html.split('data-section="gallery"', 1)[1].split("</section>", 1)[0]
    html_img_srcs = re.findall(r'<img[^>]+src="([^"]+)"', gallery_section)
    html_photo_ids = []
    for pid in ("detail", "detail-02", "detail-03", "detail-04", "detail-05"):
        b64_content = base64.b64encode(f"raw-photo-data-{pid}".encode()).decode("ascii")
        if any(b64_content in src for src in html_img_srcs):
            html_photo_ids.append(pid)

    # 2. React document output
    doc = build_react_document_from_draft(draft, available_photo_ids=available_ids)
    react_photo_ids = [
        node["props"]["image_id"]
        for root in doc.root
        for node in _walk(root.model_dump())
        if node.get("type") == "element" and node.get("tag") == "img"
    ]

    # Both render pipelines must reference the exact same 5 photos
    expected = ["detail", "detail-02", "detail-03", "detail-04", "detail-05"]
    assert html_photo_ids == expected
    assert react_photo_ids == expected
    assert html_photo_ids == react_photo_ids


def test_gallery_warning_log_matches_resolved_photos(caplog):
    # Case 1: Model requested unavailable 'bogus' while generated cuts exist
    draft = ApprovedDraftDto(
        product_name="백자 다기 세트",
        summary="전통 기법으로 빚어낸 백자 다기입니다.",
        hero_headline="단아한 선의 백자",
        hero_description="백색의 은은한 광택과 단아한 선이 돋보입니다.",
        page_plan=[
            PageBlockDto(
                section_id="gallery",
                block_type="gallery",
                photo_ids=["bogus"],
            ),
        ],
    )
    available = {"hero", "detail", "detail-02", "detail-03", "detail-04", "detail-05"}
    with caplog.at_level(logging.WARNING, logger="detail_page_ai.react_document_builder"):
        doc = build_react_document_from_draft(draft, available_photo_ids=available)

    # Log must accurately reflect that 5 images are used, never falsely claiming 'omitting image'
    assert "omitting image" not in caplog.text
    assert "default photo_id None is unavailable" not in caplog.text
    assert (
        "gallery block requested ['bogus'] but generated detail cuts are present; "
        "using ['detail', 'detail-02', 'detail-03', 'detail-04', 'detail-05'] instead"
    ) in caplog.text
    assert (
        "photo_id 'bogus' requested by gallery block is unavailable; "
        "using ['detail', 'detail-02', 'detail-03', 'detail-04', 'detail-05'] instead"
    ) in caplog.text

    caplog.clear()

    # Case 2: Model requested available 'hero' while generated cuts exist
    draft_hero = draft.model_copy(
        update={
            "page_plan": [
                PageBlockDto(
                    section_id="gallery",
                    block_type="gallery",
                    photo_ids=["hero"],
                )
            ]
        }
    )
    with caplog.at_level(logging.WARNING, logger="detail_page_ai.react_document_builder"):
        doc_hero = build_react_document_from_draft(
            draft_hero, available_photo_ids=available
        )

    # 'hero' is available so it is not logged as unavailable, but intentional override is logged
    assert "is unavailable" not in caplog.text
    assert "omitting image" not in caplog.text
    assert (
        "gallery block requested ['hero'] but generated detail cuts are present; "
        "using ['detail', 'detail-02', 'detail-03', 'detail-04', 'detail-05'] instead"
    ) in caplog.text





def test_section_colors_match_the_png_design_tokens():
    # Stage 2026-10-01: sections drawn from the React document were beige
    # rgb(246, 242, 236) (#F6F2EC) while the PNG used web/detail_page.css's
    # cool tokens. Expected values are the computed colors of the HTML page.
    variants = {
        "paper": ("#FFFFFF", "#121B29"),
        "light": ("#FAFBFC", "#121B29"),
        "sand": ("#EFF1F1", "#121B29"),
        "dark": ("#121B29", "#FFFFFF"),
    }
    blocks = [
        PageBlockDto(section_id=f"split-{variant}", block_type="detail_split", variant=variant, title="제목")
        for variant in variants
    ] + [PageBlockDto(section_id="features", block_type="feature_grid", variant="paper", title="특징",
                      items=[PageBlockItemDto(label="결", value="손으로 깎은 대나무")])]
    draft = ApprovedDraftDto(product_name="합죽선", summary="부채", hero_headline="합죽선",
                             hero_description="부채", page_plan=blocks)

    payload = build_react_document_from_draft(draft).model_dump(by_alias=True, exclude_none=True)
    sections = {node["id"].split("-", 2)[2].removesuffix("-root"): _style(node) for node in payload["root"]}

    for variant, (background, color) in variants.items():
        assert sections[f"split-{variant}"]["backgroundColor"] == background
        assert sections[f"split-{variant}"]["color"] == color
    assert sections["features"]["backgroundColor"] == "#C6D9DC"
    assert "#F6F2EC" not in str(payload)
