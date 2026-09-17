import json
from dataclasses import dataclass
from typing import Any, Protocol

from .ai_dto import AiToBePersistRequestDto, BeToAiPersistAckDto
from .models import GeneratedImage


class BackendDeliveryError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool, status_code: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class TransportResponse:
    status_code: int
    body: dict[str, Any]


class MultipartTransport(Protocol):
    def post_multipart(
        self,
        url: str,
        fields: dict[str, Any],
        files: dict[str, dict[str, Any]],
        headers: dict[str, str],
        timeout: float,
    ) -> TransportResponse | dict[str, Any]:
        ...


class HttpxMultipartTransport:
    def post_multipart(
        self,
        url: str,
        fields: dict[str, Any],
        files: dict[str, dict[str, Any]],
        headers: dict[str, str],
        timeout: float,
    ) -> TransportResponse:
        import httpx

        encoded_files = {
            field_name: (
                file_info["filename"],
                file_info["data"],
                file_info["content_type"],
            )
            for field_name, file_info in files.items()
        }
        response = httpx.post(
            url,
            data={
                field_name: json.dumps(value, ensure_ascii=False)
                for field_name, value in fields.items()
            },
            files=encoded_files,
            headers=headers,
            timeout=timeout,
        )
        try:
            body = response.json()
        except ValueError:
            body = {"message": response.text}
        if not isinstance(body, dict):
            body = {"message": "Backend returned a non-object response"}
        return TransportResponse(status_code=response.status_code, body=body)


class BackendProductClient:
    def __init__(
        self,
        *,
        url: str,
        token: str | None = None,
        timeout: float = 60.0,
        transport: MultipartTransport | None = None,
    ):
        self.url = url
        self.token = token
        self.timeout = timeout
        self.transport = transport or HttpxMultipartTransport()

    def persist(
        self,
        request: AiToBePersistRequestDto,
        image: GeneratedImage,
    ) -> BeToAiPersistAckDto:
        headers = {
            "Accept": "application/json",
            "Idempotency-Key": request.idempotency_key,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        # The persisted React document is a public JSON contract and uses the
        # documented camelCase keys (schemaVersion, imageId, ...).
        fields = {"metadata": request.model_dump(mode="json", by_alias=True)}
        extension = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
        }.get(image.mime_type, "bin")
        files = {
            "detail_page_image": {
                "filename": f"{request.generation_id}.{extension}",
                "content_type": image.mime_type,
                "data": image.data,
            }
        }
        for section in image.sections:
            section_extension = {
                "image/jpeg": "jpg",
                "image/png": "png",
                "image/webp": "webp",
            }.get(section.mime_type, "bin")
            files[f"detail_page_section_{section.order:02d}"] = {
                "filename": (
                    f"{request.generation_id}-{section.order:02d}-"
                    f"{section.section_id}.{section_extension}"
                ),
                "content_type": section.mime_type,
                "data": section.data,
        }
        for photo in image.photos:
            allowed_generated_reference = (
                (
                    photo.photo_id == "lifestyle"
                    and photo.asset_mode == "generated_scene"
                )
                or (
                    photo.photo_id in {"detail-02", "detail-03", "detail-04", "detail-05"}
                    and photo.asset_mode == "generated_view"
                )
            ) and photo.product_generated and photo.fidelity_status == "GENERATED"
            if (
                photo.fidelity_status not in {"VERIFIED", "FALLBACK", "GENERATED"}
                or (photo.product_generated and not allowed_generated_reference)
                or not photo.source_sha256
            ):
                continue
            photo_extension = {
                "image/jpeg": "jpg",
                "image/png": "png",
                "image/webp": "webp",
            }.get(photo.mime_type, "bin")
            files[f"product_photo_{photo.order:02d}"] = {
                "filename": (
                    f"{request.generation_id}-photo-{photo.order:02d}-"
                    f"{photo.photo_id}.{photo_extension}"
                ),
                "content_type": photo.mime_type,
                "data": photo.data,
            }
        try:
            response = self.transport.post_multipart(
                self.url,
                fields,
                files,
                headers,
                self.timeout,
            )
        except Exception as exc:
            if isinstance(exc, BackendDeliveryError):
                raise
            raise BackendDeliveryError(
                "Backend request failed", retryable=True
            ) from exc

        status_code, body = self._response_parts(response)
        if 200 <= status_code < 300:
            try:
                return BeToAiPersistAckDto.model_validate(body)
            except Exception as exc:
                raise BackendDeliveryError(
                    "Backend returned an invalid persistence response",
                    retryable=True,
                    status_code=status_code,
                ) from exc
        if status_code == 409:
            body = {**body, "status": "ALREADY_SAVED"}
            try:
                return BeToAiPersistAckDto.model_validate(body)
            except Exception as exc:
                raise BackendDeliveryError(
                    "Backend duplicate response is invalid",
                    retryable=False,
                    status_code=status_code,
                ) from exc
        raise BackendDeliveryError(
            f"Backend returned HTTP {status_code}",
            retryable=status_code >= 500 or status_code == 429,
            status_code=status_code,
        )

    @staticmethod
    def _response_parts(
        response: TransportResponse | dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        if isinstance(response, TransportResponse):
            return response.status_code, response.body
        return 200, response
