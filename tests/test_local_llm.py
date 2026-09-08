import base64
import json

from detail_page_ai.dto import (
    ApprovedDraftDto,
    AiFeProductSummaryDto,
    AiFeResultDto,
    FeDetailPageAssetDto,
    FeDetailPageSectionDto,
    FeProductPhotoDto,
    ProductProfileDto,
    UserHintsDto,
)
from detail_page_ai.react_document_builder import build_react_document_from_draft
from detail_page_ai.pipeline import PipelineResult
from detail_page_ai.source_photos import SourcePreservingProductPhotoGenerator
from local_detail_page_ai.adapters import (
    LocalProductAnalyzer,
)
from local_detail_page_ai.clients import (
    MlxServeChatClient,
    MlxServeImageClient,
    OllamaChatClient,
)
from local_detail_page_ai.runner import LocalPreviewBackend, save_pipeline_result
from local_detail_page_ai.runner import (
    MlxServeBackgroundGenerator,
    MlxServeDetailViewGenerator,
    MlxServeUsageSceneGenerator,
    build_local_pipeline,
)


class FakeJsonTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, payload, timeout):
        self.calls.append((url, payload, timeout))
        return self.response


class FakeMultipartTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post_multipart(self, url, fields, files, timeout):
        self.calls.append((url, fields, files, timeout))
        return self.response


def test_ollama_chat_client_sends_image_and_returns_structured_json():
    transport = FakeJsonTransport(
        {"message": {"content": '{"product_type":"desk lamp"}'}}
    )
    schema = {
        "type": "object",
        "properties": {"product_type": {"type": "string"}},
        "required": ["product_type"],
    }
    client = OllamaChatClient(
        base_url="http://ollama.local",
        model="gemma3:12b",
        transport=transport,
    )

    result = client.generate_json(
        "analyze",
        image=b"image-bytes",
        mime_type="image/jpeg",
        json_schema=schema,
    )

    assert result == {"product_type": "desk lamp"}
    url, payload, _ = transport.calls[0]
    assert url == "http://ollama.local/api/chat"
    assert payload["model"] == "gemma3:12b"
    assert payload["messages"][0]["images"] == [base64.b64encode(b"image-bytes").decode()]
    assert payload["format"] == "json"
    assert payload["options"]["temperature"] == 0


def test_mlx_chat_client_sends_openai_multimodal_json_request():
    transport = FakeJsonTransport(
        {
            "choices": [
                {
                    "message": {
                        "content": '```json\n{"product_type":"tea service"}\n```'
                    }
                }
            ]
        }
    )
    client = MlxServeChatClient(
        base_url="http://mlx.local",
        model="mlx-community/gemma-4-12b-it-4bit",
        transport=transport,
    )

    result = client.generate_json(
        "analyze",
        image=b"image-bytes",
        mime_type="image/jpeg",
        json_schema={"type": "object"},
    )

    assert result == {"product_type": "tea service"}
    url, payload, _ = transport.calls[0]
    assert url == "http://mlx.local/v1/chat/completions"
    assert payload["model"] == "mlx-community/gemma-4-12b-it-4bit"
    content = payload["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "analyze"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["temperature"] == 0


def test_local_text_inference_defaults_to_gemma_12b():
    expected_model = "mlx-community/gemma-4-12b-it-4bit"

    client = MlxServeChatClient()
    pipeline = build_local_pipeline(
        text_provider="mlx",
        image_provider="none",
        generate_product_photos=False,
    )

    assert client.model == expected_model
    assert pipeline.analyzer.chat_client.model == expected_model


def test_mlx_image_client_decodes_generated_background():
    transport = FakeJsonTransport(
        {"created": 0, "data": [{"b64_json": base64.b64encode(b"png-bytes").decode()}]}
    )
    client = MlxServeImageClient(
        base_url="http://mlx.local",
        model="mlx-community/flux2-klein-9b-4bit",
        transport=transport,
    )

    result = client.generate(
        "empty product-free background",
        negative_prompt="product, object, text",
        width=1200,
        height=1200,
    )

    assert result == b"png-bytes"
    url, payload, _ = transport.calls[0]
    assert url == "http://mlx.local/v1/images/generations"
    assert payload["model"] == "mlx-community/flux2-klein-9b-4bit"
    assert payload["size"] == "1024x1024"
    assert payload["response_format"] == "b64_json"
    assert payload["negative_prompt"] == "product, object, text"
    assert payload["steps"] == 12


def test_mlx_image_client_edits_using_the_original_image_reference():
    transport = FakeMultipartTransport(
        {"created": 0, "data": [{"b64_json": base64.b64encode(b"edited-png").decode()}]}
    )
    client = MlxServeImageClient(
        base_url="http://mlx.local",
        model="mlx-community/flux2-klein-9b-4bit",
        transport=FakeJsonTransport({}),
        multipart_transport=transport,
    )

    result = client.edit(
        "e-commerce product background, modern layout, soft lighting, minimal design",
        source_image=b"source-jpeg",
        source_mime_type="image/jpeg",
    )

    assert result == b"edited-png"
    url, fields, files, _ = transport.calls[0]
    assert url == "http://mlx.local/v1/images/edits"
    assert fields["model"] == "mlx-community/flux2-klein-9b-4bit"
    assert fields["output_format"] == "png"
    assert fields["response_format"] == "b64_json"
    assert fields["n"] == "1"
    assert files["image"]["data"] == b"source-jpeg"
    assert files["image"]["content_type"] == "image/jpeg"


def test_mlx_usage_scene_generator_uses_balanced_strength_for_real_usage_context():
    transport = FakeMultipartTransport(
        {"created": 0, "data": [{"b64_json": base64.b64encode(b"edited-png").decode()}]}
    )
    client = MlxServeImageClient(
        base_url="http://mlx.local",
        model="mlx-community/flux2-klein-9b-4bit",
        multipart_transport=transport,
    )
    generator = MlxServeUsageSceneGenerator(client)
    profile = ProductProfileDto.minimal("금속 공예 세트")

    result = generator.generate(
        profile=profile,
        role="lifestyle",
        source_image=b"source-jpeg",
        source_mime_type="image/jpeg",
        width=1200,
        height=1200,
    )

    assert result == b"edited-png"
    assert transport.calls[0][0] == "http://mlx.local/v1/images/edits"
    assert transport.calls[0][1]["strength"] == "0.22"


def test_mlx_detail_view_generator_edits_each_generated_detail_job():
    transport = FakeMultipartTransport(
        {"created": 0, "data": [{"b64_json": base64.b64encode(b"angle-png").decode()}]}
    )
    client = MlxServeImageClient(
        base_url="http://mlx.local",
        model="mlx-community/flux2-klein-9b-4bit",
        multipart_transport=transport,
    )
    generator = MlxServeDetailViewGenerator(client)

    profile = ProductProfileDto.minimal("나전 보관함")
    for role in ("detail-02", "detail-03", "detail-04", "detail-05"):
        result = generator.generate(
            profile=profile,
            role=role,
            source_image=b"source-jpeg",
            source_mime_type="image/jpeg",
            width=1200,
            height=1200,
        )
        assert result == b"angle-png"

    assert [call[0] for call in transport.calls] == [
        "http://mlx.local/v1/images/edits"
    ] * 4
    prompts = [call[1]["prompt"].lower() for call in transport.calls]
    assert "front-left" in prompts[0]
    assert "macro" in prompts[1]
    assert "real-use" in prompts[2]
    assert "top-down" in prompts[3]


def test_mlx_detail_view_generator_rejects_the_original_detail_role():
    generator = MlxServeDetailViewGenerator(
        MlxServeImageClient(base_url="http://mlx.local", model="flux")
    )

    try:
        generator.generate(
            profile=ProductProfileDto.minimal("나전 보관함"),
            role="detail",
            source_image=b"source-jpeg",
            source_mime_type="image/jpeg",
            width=1200,
            height=1200,
        )
    except ValueError as exc:
        assert "detail-02" in str(exc)
        assert "detail-05" in str(exc)
    else:
        raise AssertionError("unsupported detail role must be rejected")


def test_local_analyzer_validates_ollama_profile_response():
    class FakeChat:
        def generate_json(self, prompt, *, image, mime_type, json_schema):
            assert image == b"source"
            assert mime_type == "image/jpeg"
            assert json_schema == ProductProfileDto.model_json_schema()
            assert "JSON Schema" in prompt
            assert "입력 데이터가 이미지보다 우선" in prompt
            assert "입력된 제품명" in prompt
            assert "충돌 표시" not in prompt
            return ProductProfileDto.minimal("desk lamp").model_dump(mode="json")

    profile = LocalProductAnalyzer(chat_client=FakeChat()).analyze(
        b"source", "image/jpeg"
    )

    assert profile.product_type == "desk lamp"


def test_local_analyzer_uses_only_image_and_creator_hints():
    class FakeChat:
        def __init__(self):
            self.prompts = []

        def generate_json(self, prompt, *, image, mime_type, json_schema):
            self.prompts.append(prompt)
            return ProductProfileDto.minimal("유리잔").model_dump(mode="json")

    chat = FakeChat()
    profile = LocalProductAnalyzer(chat_client=chat).analyze(
        b"source",
        "image/jpeg",
        user_hints=UserHintsDto(product_name="숨의잔"),
    )

    assert len(chat.prompts) == 1
    assert "LIVE WEB SEARCH CONTEXT" not in chat.prompts[0]
    assert "web_search" not in profile.observations


def test_local_analyzer_repairs_page_plan_labels_leaking_into_copy_sections():
    class FakeChat:
        def generate_json(self, prompt, *, image, mime_type, json_schema):
            payload = ProductProfileDto.minimal("desk lamp").model_dump(mode="json")
            payload["copy_sections"] = [{
                "section_type": "recommendation",
                "title": "책상 위 포인트",
                "description": "이미지 기반 연출 제안",
            }]
            return payload

    profile = LocalProductAnalyzer(chat_client=FakeChat()).analyze(
        b"source", "image/jpeg"
    )

    assert profile.copy_sections[0].section_type == "benefit"


def test_save_pipeline_result_writes_page_sections_and_product_photos(tmp_path):
    profile = ProductProfileDto.minimal("나전 함")
    result = PipelineResult(
        generation_id="generation-1",
        fe_result=AiFeResultDto(
            generation_id="generation-1",
            product=AiFeProductSummaryDto.from_profile(profile),
            detail_page=FeDetailPageAssetDto(
                image_base64=base64.b64encode(b"page").decode(),
                mime_type="image/png",
                sections=[
                    FeDetailPageSectionDto(
                        section_id="detail-cuts",
                        order=1,
                        label="상세 컷",
                        image_base64=base64.b64encode(b"section").decode(),
                        mime_type="image/png",
                    )
                ],
                photos=[
                    FeProductPhotoDto(
                        photo_id="detail",
                        order=1,
                        label="매크로 디테일",
                        image_base64=base64.b64encode(b"photo").decode(),
                        mime_type="image/png",
                    )
                ],
                react_document=build_react_document_from_draft(
                    ApprovedDraftDto.from_profile(profile)
                ),
            ),
        ),
        be_ack=None,
        backend_delivery_pending=False,
    )

    output = save_pipeline_result(result, tmp_path)

    assert output == tmp_path
    assert (tmp_path / "detail_page.png").read_bytes() == b"page"
    assert (tmp_path / "sections/01-detail-cuts.png").read_bytes() == b"section"
    assert (tmp_path / "photos/01-detail.png").read_bytes() == b"photo"
    assert (tmp_path / "react_document.json").exists()
    assert (
        json.loads((tmp_path / "react_document.json").read_text(encoding="utf-8"))[
            "schemaVersion"
        ]
        == "2.0"
    )
    assert (tmp_path / "result_summary.json").exists()


def test_local_preview_backend_returns_a_complete_persist_ack():
    class Request:
        generation_id = "generation-1"

    ack = LocalPreviewBackend().persist(Request(), b"page")

    assert ack.generation_id == "generation-1"
    assert ack.status == "SAVED"
    assert ack.saved_at is not None


def test_local_pipeline_uses_source_preserving_photo_generator():
    pipeline = build_local_pipeline()

    assert isinstance(
        pipeline.photo_generator, SourcePreservingProductPhotoGenerator
    )


def test_local_pipeline_can_use_mlx_gemma_and_flux_clients():
    pipeline = build_local_pipeline(
        text_provider="mlx",
        text_url="http://mlx.local",
        text_model="mlx-community/gemma-4-12b-it-4bit",
        image_provider="mlx",
        image_url="http://mlx.local",
        image_model="mlx-community/flux2-klein-9b-4bit",
    )

    assert isinstance(pipeline.analyzer.chat_client, MlxServeChatClient)
    assert isinstance(
        pipeline.photo_generator.background_generator,
        MlxServeBackgroundGenerator,
    )


def test_local_pipeline_never_wires_gemini_from_environment(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "must-not-be-read")
    monkeypatch.setenv("GEMINI_RESEARCH_MODEL", "must-not-be-read")
    pipeline = build_local_pipeline(
        text_provider="mlx",
        image_provider="none",
        generate_product_photos=False,
    )

    assert not hasattr(pipeline.analyzer, "web_search_client")
