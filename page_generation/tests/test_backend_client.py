import pytest

from detail_page_ai.backend_client import BackendDeliveryError, BackendProductClient
from detail_page_ai.ai_dto import AiToBePersistRequestDto
from detail_page_ai.dto import (
    ApprovedDraftDto,
    ProductProfileDto,
)
from detail_page_ai.models import GeneratedImage, GeneratedSection, ProductPhoto
from detail_page_ai.react_document_builder import build_react_document_from_draft
from local_detail_page_ai.factory import _UnconfiguredBackend


class FakeHttpTransport:
    def __init__(self):
        self.request = None

    def post_multipart(self, url, fields, files, headers, timeout):
        self.request = {
            "url": url,
            "fields": fields,
            "files": files,
            "headers": headers,
            "timeout": timeout,
        }
        return {
            "generation_id": "generation-1",
            "product_id": "product-1",
            "status": "SAVED",
            "saved_at": "2026-08-26T08:01:12Z",
        }


def make_request() -> AiToBePersistRequestDto:
    return AiToBePersistRequestDto.from_profile(
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
        product_id="product-1",
    )


@pytest.mark.parametrize(
    "base_url",
    ["https://backend.example", "https://backend.example/"],
)
def test_persist_assembles_default_generation_callback_url(base_url):
    transport = FakeHttpTransport()
    client = BackendProductClient(url=base_url, transport=transport)

    client.persist(
        make_request(),
        GeneratedImage(data=b"png", mime_type="image/png", width=1024, height=4096),
    )

    assert (
        transport.request["url"]
        == "https://backend.example/internal/generations/generation-1/completion"
    )


def test_persist_assembles_overridden_generation_callback_url():
    transport = FakeHttpTransport()
    client = BackendProductClient(
        url="https://backend.example/",
        callback_path="/internal/v2/generations/{generation_id}/complete",
        transport=transport,
    )

    client.persist(
        make_request(),
        GeneratedImage(data=b"png", mime_type="image/png", width=1024, height=4096),
    )

    assert (
        transport.request["url"]
        == "https://backend.example/internal/v2/generations/generation-1/complete"
    )


def test_persist_sends_generation_id_as_the_idempotency_key():
    transport = FakeHttpTransport()
    client = BackendProductClient(url="https://backend.example", transport=transport)
    request = make_request()

    assert request.idempotency_key == request.generation_id

    client.persist(
        request,
        GeneratedImage(data=b"png", mime_type="image/png", width=1024, height=4096),
    )

    assert transport.request["headers"]["Idempotency-Key"] == request.generation_id


def test_unconfigured_backend_preserves_deferred_delivery():
    with pytest.raises(BackendDeliveryError, match="BACKEND_URL is not configured"):
        _UnconfiguredBackend().persist(
            make_request(),
            GeneratedImage(data=b"png", mime_type="image/png", width=1024, height=4096),
        )


def test_persist_sends_metadata_and_image_as_separate_parts():
    transport = FakeHttpTransport()
    client = BackendProductClient(
        url="https://backend.example",
        token="secret",
        transport=transport,
    )

    ack = client.persist(
        make_request(),
        GeneratedImage(data=b"png", mime_type="image/png", width=1024, height=4096),
    )

    assert ack.status == "SAVED"
    metadata = transport.request["fields"]["metadata"]
    assert metadata["generationId"] == "generation-1"
    assert metadata["productId"] == "product-1"
    assert "generation_id" not in metadata
    assert "detail_page" not in metadata
    assert transport.request["files"]["detail_page_image"]["data"] == b"png"
    assert transport.request["files"]["detail_page_image"]["filename"] == "generation-1.png"
    assert transport.request["headers"]["Authorization"] == "Bearer secret"


def test_persist_serializes_react_document_with_contract_aliases():
    transport = FakeHttpTransport()
    client = BackendProductClient(
        url="https://backend.example",
        transport=transport,
    )
    request = make_request()
    request.detail_page.react_document = build_react_document_from_draft(
        ApprovedDraftDto.from_profile(request.product)
    )

    client.persist(
        request,
        GeneratedImage(data=b"png", mime_type="image/png", width=1024, height=4096),
    )

    document = transport.request["fields"]["metadata"]["detailPage"]["reactDocument"]
    assert document["schemaVersion"] == "2.0"
    assert "schema_version" not in document
    assert document["root"][0]["children"][0]["type"] == "element"


def test_persist_sends_ordered_section_images_when_available():
    transport = FakeHttpTransport()
    client = BackendProductClient(
        url="https://backend.example",
        transport=transport,
    )
    image = GeneratedImage(
        data=b"png",
        mime_type="image/png",
        sections=(
            GeneratedSection(
                section_id="hero",
                order=1,
                label="상품 소개",
                data=b"hero-png",
                mime_type="image/png",
                width=774,
                height=526,
            ),
        ),
    )

    client.persist(make_request(), image)

    section_file = transport.request["files"]["detail_page_section_01"]
    assert section_file["filename"] == "generation-1-01-hero.png"
    assert section_file["data"] == b"hero-png"


def test_persist_sends_generated_product_photos_when_available():
    transport = FakeHttpTransport()
    client = BackendProductClient(
        url="https://backend.example",
        transport=transport,
    )
    image = GeneratedImage(
        data=b"png",
        mime_type="image/png",
        photos=(
            ProductPhoto(
                photo_id="hero",
                order=1,
                label="히어로 3/4 구도",
                data=b"hero-photo",
                mime_type="image/jpeg",
                source_sha256="source-hash",
                product_generated=False,
                fidelity_status="VERIFIED",
            ),
        ),
    )

    client.persist(make_request(), image)

    photo_file = transport.request["files"]["product_photo_01"]
    assert photo_file["filename"] == "generation-1-photo-01-hero.jpg"
    assert photo_file["data"] == b"hero-photo"


def test_persist_sends_generated_lifestyle_scene_with_explicit_marker():
    transport = FakeHttpTransport()
    client = BackendProductClient(
        url="https://backend.example",
        transport=transport,
    )
    image = GeneratedImage(
        data=b"png",
        mime_type="image/png",
        photos=(
            ProductPhoto(
                photo_id="lifestyle",
                order=4,
                label="AI 생성 활용 장면",
                data=b"generated-scene",
                mime_type="image/png",
                asset_mode="generated_scene",
                source_sha256="source-hash",
                background_generated=True,
                product_generated=True,
                fidelity_status="GENERATED",
            ),
        ),
    )

    client.persist(make_request(), image)

    photo_file = transport.request["files"]["product_photo_04"]
    assert photo_file["data"] == b"generated-scene"
    assert photo_file["filename"] == "generation-1-photo-04-lifestyle.png"


def test_persist_sends_generated_angle_detail_with_explicit_marker():
    transport = FakeHttpTransport()
    client = BackendProductClient(
        url="https://backend.example",
        transport=transport,
    )
    image = GeneratedImage(
        data=b"png",
        mime_type="image/png",
        photos=(
            ProductPhoto(
                photo_id="detail-03",
                order=6,
                label="AI 생성 디테일",
                data=b"generated-angle",
                mime_type="image/png",
                asset_mode="generated_view",
                source_sha256="source-hash",
                background_generated=True,
                product_generated=True,
                fidelity_status="GENERATED",
            ),
        ),
    )

    client.persist(make_request(), image)

    photo_file = transport.request["files"]["product_photo_06"]
    assert photo_file["data"] == b"generated-angle"
    assert photo_file["filename"] == "generation-1-photo-06-detail-03.png"


def test_persist_omits_rejected_product_photos():
    transport = FakeHttpTransport()
    client = BackendProductClient(
        url="https://backend.example",
        transport=transport,
    )
    image = GeneratedImage(
        data=b"png",
        mime_type="image/png",
        photos=(
            ProductPhoto(
                photo_id="unsafe",
                order=1,
                label="거부된 이미지",
                data=b"unsafe-photo",
                mime_type="image/png",
                fidelity_status="REJECTED",
            ),
        ),
    )

    client.persist(make_request(), image)

    assert not any(
        field_name.startswith("product_photo_")
        for field_name in transport.request["files"]
    )


def test_persist_omits_product_photo_without_explicit_provenance():
    transport = FakeHttpTransport()
    client = BackendProductClient(
        url="https://backend.example",
        transport=transport,
    )
    image = GeneratedImage(
        data=b"png",
        mime_type="image/png",
        photos=(
            ProductPhoto(
                photo_id="unknown",
                order=1,
                label="provenance missing",
                data=b"unknown-photo",
                mime_type="image/png",
            ),
        ),
    )

    client.persist(make_request(), image)

    assert not any(
        field_name.startswith("product_photo_")
        for field_name in transport.request["files"]
    )
