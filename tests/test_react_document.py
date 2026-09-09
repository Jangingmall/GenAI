import pytest
from pydantic import ValidationError

from detail_page_ai.dto import ApprovedDraftDto, PageBlockDto, PageBlockItemDto
from detail_page_ai.react_document import ReactDetailPageDocumentDto
from detail_page_ai.react_document_builder import build_react_document_from_draft


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
