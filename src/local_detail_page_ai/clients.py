from __future__ import annotations

import base64
import binascii
import json
from typing import Any, Protocol
from urllib import error, request


class LocalModelError(RuntimeError):
    """Raised when a local model server returns an unusable response."""


class JsonTransport(Protocol):
    def post(self, url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        ...


class StructuredJsonChatClient(Protocol):
    def generate_json(
        self,
        prompt: str,
        *,
        image: bytes | None = None,
        mime_type: str | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...


class UrllibJsonTransport:
    """Small dependency-free JSON POST transport for local model servers."""

    def post(self, url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        http_request = request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=timeout) as response:
                raw = response.read()
        except (error.HTTPError, error.URLError, TimeoutError) as exc:
            raise LocalModelError(f"Local model request failed: {exc}") from exc
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LocalModelError("Local model returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise LocalModelError("Local model response must be a JSON object")
        return payload


class OllamaChatClient:
    """Ollama vision/text client using its native non-streaming JSON API."""

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "gemma3:12b",
        timeout: float = 180.0,
        transport: JsonTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.transport = transport or UrllibJsonTransport()

    def generate_json(
        self,
        prompt: str,
        *,
        image: bytes | None = None,
        mime_type: str | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del mime_type  # Ollama's native API accepts the image bytes directly.
        message: dict[str, Any] = {"role": "user", "content": prompt}
        if image:
            message["images"] = [base64.b64encode(image).decode("ascii")]
        response = self.transport.post(
            f"{self.base_url}/api/chat",
            {
                "model": self.model,
                "messages": [message],
                "stream": False,
                # Ollama's grammar parser can reject deeply nested Pydantic schemas.
                # The analyzer still validates the response against its Pydantic DTO;
                # use JSON mode here for reliable local multimodal inference.
                "format": "json",
                "options": {"temperature": 0},
            },
            self.timeout,
        )
        message_payload = response.get("message")
        content = message_payload.get("content") if isinstance(message_payload, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise LocalModelError("Ollama response has no message content")
        return _parse_json_object(content, provider="Ollama")


class MlxServeChatClient:
    """MLX Serve OpenAI-compatible multimodal client for local vision models."""

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:11234",
        model: str = "ddalcu/Qwen3.8-27B-MLX-Serve-4bit",
        timeout: float = 300.0,
        max_tokens: int = 4096,
        transport: JsonTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.transport = transport or UrllibJsonTransport()

    def generate_json(
        self,
        prompt: str,
        *,
        image: bytes | None = None,
        mime_type: str | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del json_schema  # The prompt carries the schema; Pydantic validates the result.
        if image and not mime_type:
            raise ValueError("mime_type is required when image is provided")
        if image:
            content: str | list[dict[str, Any]] = [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,"
                        f"{base64.b64encode(image).decode('ascii')}"
                    },
                },
            ]
        else:
            content = prompt
        response = self.transport.post(
            f"{self.base_url}/v1/chat/completions",
            {
                "model": self.model,
                "messages": [{"role": "user", "content": content}],
                "stream": False,
                "temperature": 0,
                "max_tokens": self.max_tokens,
                "response_format": {"type": "json_object"},
            },
            self.timeout,
        )
        choices = response.get("choices")
        choice = choices[0] if isinstance(choices, list) and choices else None
        message = choice.get("message") if isinstance(choice, dict) else None
        raw_content = message.get("content") if isinstance(message, dict) else None
        content_text = _message_content_text(raw_content)
        if not content_text:
            raise LocalModelError("MLX Serve response has no message content")
        return _parse_json_object(content_text, provider="MLX Serve")


class MlxServeImageClient:
    """MLX Serve image-generation client for Flux image models."""

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:11234",
        model: str = "mlx-community/flux2-klein-9b-4bit",
        timeout: float = 300.0,
        # FLUX.2 Klein is a 4-step distilled model, and all measurements so
        # far used 4 steps. Increase this only after a valid quality A/B test
        # provides evidence that a higher value helps.
        steps: int = 4,
        transport: JsonTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.steps = steps
        self.transport = transport or UrllibJsonTransport()

    def generate(
        self,
        prompt: str,
        *,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
    ) -> bytes:
        del width, height  # Flux2 MLX Serve currently renders the supported square size.
        response = self.transport.post(
            f"{self.base_url}/v1/images/generations",
            {
                "model": self.model,
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "n": 1,
                "size": "1024x1024",
                "response_format": "b64_json",
                "steps": self.steps,
            },
            self.timeout,
        )
        return self._decode_image_response(response)

    def edit(
        self,
        prompt: str,
        *,
        source_image: bytes,
        source_mime_type: str,
        width: int = 1024,
        height: int = 1024,
        strength: float = 0.30,
    ) -> bytes:
        """Edit one source image while keeping its visible arrangement as a reference."""
        del width, height
        if not source_image:
            raise ValueError("source_image must not be empty")
        if not source_mime_type.startswith("image/"):
            raise ValueError("source_mime_type must be an image MIME type")
        # MLX Serve's multipart adapter translates edits into its JSON image
        # generation schema and does not carry steps/strength through. Use that
        # schema directly so both values arrive as JSON numbers. The current
        # FLUX.2 in-context edit mode accepts strength but intentionally ignores it.
        response = self.transport.post(
            f"{self.base_url}/v1/images/generations",
            {
                "model": self.model,
                "prompt": prompt,
                "size": "1024x1024",
                "mode": "edit",
                "steps": self.steps,
                "strength": strength,
                "image": base64.b64encode(source_image).decode("ascii"),
            },
            self.timeout,
        )
        return self._decode_image_response(response)

    @staticmethod
    def _decode_image_response(response: dict[str, Any]) -> bytes:
        data = response.get("data")
        item = data[0] if isinstance(data, list) and data else None
        encoded = item.get("b64_json") if isinstance(item, dict) else None
        if not isinstance(encoded, str) or not encoded:
            raise LocalModelError("MLX Serve image response has no b64_json image")
        try:
            return base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise LocalModelError("MLX Serve image output is not valid base64") from exc


def _message_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        ]
        return "".join(parts).strip()
    return ""


def _parse_json_object(content: str, *, provider: str) -> dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        cleaned = "\n".join(lines[1:-1]).strip()
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LocalModelError(f"{provider} response content is not valid JSON") from exc
    if not isinstance(result, dict):
        raise LocalModelError(f"{provider} JSON response must be an object")
    return result
