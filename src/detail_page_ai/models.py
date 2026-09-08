from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field


class GenerationOptions(BaseModel):
    aspect_ratio: Literal["1:4", "1:8"] = "1:4"
    image_size: Literal["1K", "2K", "4K"] = "2K"
    # The HTML/CSS detail-page renderer always emits PNG.
    output_mime_type: Literal["image/png"] = "image/png"


class ProductPhotoGenerationOptions(BaseModel):
    """Aspect ratio and size for individual product-photo variations."""

    aspect_ratio: Literal["1:1", "4:3", "3:2", "2:3"] = "1:1"
    image_size: Literal["1K", "2K", "4K"] = "1K"
    output_mime_type: Literal["image/jpeg"] = "image/jpeg"


AssetMode = Literal[
    "source",
    "source_crop",
    "source_composite",
    "generated_scene",
    "generated_view",
]
FidelityStatus = Literal["VERIFIED", "FALLBACK", "GENERATED", "REJECTED"]


@dataclass(frozen=True, slots=True)
class PhotoTransform:
    scale: float = 1.0
    x: int = 0
    y: int = 0
    crop: tuple[int, int, int, int] | None = None


@dataclass(frozen=True, slots=True)
class ProductPhoto:
    photo_id: str
    order: int
    label: str
    data: bytes
    mime_type: str
    width: int | None = None
    height: int | None = None
    asset_mode: AssetMode = "source"
    source_asset_id: str | None = None
    source_sha256: str | None = None
    cutout_sha256: str | None = None
    mask_sha256: str | None = None
    background_generated: bool = False
    product_generated: bool = True
    transform: PhotoTransform = field(default_factory=PhotoTransform)
    fidelity_status: FidelityStatus = "REJECTED"


@dataclass(frozen=True, slots=True)
class ProductPhotoSet:
    photos: tuple[ProductPhoto, ...] = ()


@dataclass(frozen=True, slots=True)
class GeneratedSection:
    section_id: str
    order: int
    label: str
    data: bytes
    mime_type: str
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True, slots=True)
class GeneratedImage:
    data: bytes
    mime_type: str
    width: int | None = None
    height: int | None = None
    sections: tuple[GeneratedSection, ...] = ()
    photos: tuple[ProductPhoto, ...] = ()
