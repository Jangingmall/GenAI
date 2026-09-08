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
