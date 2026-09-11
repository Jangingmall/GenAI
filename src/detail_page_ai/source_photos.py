import hashlib
import io
import math
from collections import deque
from dataclasses import dataclass, replace
from typing import Protocol

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps, UnidentifiedImageError

from .assets import MemoryAssetStore
from .dto import GenerationOptions, ProductProfileDto
from .models import FidelityStatus, PhotoTransform, ProductPhoto, ProductPhotoSet
from .ports import SourceAssetStore


class BackgroundGenerator(Protocol):
    def generate(
        self,
        *,
        profile: ProductProfileDto,
        role: str,
        width: int,
        height: int,
    ) -> bytes:
        ...


class UsageSceneGenerator(Protocol):
    """Generate a finished lifestyle scene for the explicitly allowed lifestyle slot."""

    def generate(
        self,
        *,
        profile: ProductProfileDto,
        role: str,
        source_image: bytes,
        source_mime_type: str,
        width: int,
        height: int,
    ) -> bytes:
        ...


class DetailViewGenerator(Protocol):
    """Generate only the explicitly allowed alternative-angle detail slots."""

    def generate(
        self,
        *,
        profile: ProductProfileDto,
        role: str,
        source_image: bytes,
        source_mime_type: str,
        width: int,
        height: int,
    ) -> bytes:
        ...


@dataclass(frozen=True, slots=True)
class ProductCutout:
    rgba_png: bytes
    mask_png: bytes
    bbox: tuple[int, int, int, int]
    width: int
    height: int
    source_sha256: str
    cutout_sha256: str
    mask_sha256: str


def _encode_png(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=False, compress_level=9)
    return output.getvalue()


def _decode_rgb(data: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("source image could not be decoded") from exc
    return image.convert("RGB")


class SolidBackgroundCutoutExtractor:
    """Build only an alpha mask; RGB bytes always come from the decoded source."""

    def __init__(
        self,
        *,
        background_tolerance: float = 36.0,
        corner_uniformity_tolerance: float = 24.0,
        min_foreground_ratio: float = 0.01,
        max_foreground_ratio: float = 0.90,
        min_largest_component_ratio: float = 0.50,
        max_shadow_foreground_loss: float = 0.15,
    ):
        # The edge field is sampled on a 16-pixel grid, so matching needs an
        # 8-point interpolation allowance beyond the former 28-point
        # single-colour threshold.  This value applies only after the spatial
        # model is built; it is not a replacement for that model.
        self.background_tolerance = background_tolerance
        # Kept for baseline-diagnostic compatibility.  Extraction no longer
        # rejects a photograph by comparing its four corners to this value.
        self.corner_uniformity_tolerance = corner_uniformity_tolerance
        self.min_foreground_ratio = min_foreground_ratio
        self.max_foreground_ratio = max_foreground_ratio
        # A genuine product silhouette should have a connected core.  Requiring
        # half of the foreground to share one component rejects scattered
        # pattern/noise fragments while still allowing small detached details.
        self.min_largest_component_ratio = min_largest_component_ratio
        # The wider tolerance is a shadow-only cleanup, never a second
        # segmentation pass.  It may remove at most 15% of the primary mask,
        # so it can clear a narrow contact shadow but cannot erase a light
        # product surface that the primary, local-background mask retained.
        self.max_shadow_foreground_loss = max_shadow_foreground_loss

    def extract(self, source_image: bytes, source_mime_type: str) -> ProductCutout | None:
        del source_mime_type
        source = _decode_rgb(source_image)
        width, height = source.size
        if min(width, height) < 6 * 16 and self._has_nonuniform_frame(source):
            # The 16-pixel field has fewer than six cells on this axis, too few
            # boundary samples to distinguish a product boundary from a scene
            # gradient.  Preserve a small nonuniform source rather than guess.
            return None
        confidence_tolerance = max(24.0, self.background_tolerance * 0.75)
        if not self._edge_field_is_reliable(
            source, tolerance=confidence_tolerance
        ):
            # The frame changes too much for the harmonic field to make a
            # trustworthy interior/background decision.  Returning the source
            # is safer than turning an unsupported scene interpolation into a
            # product mask.
            return None
        background_model = self._edge_background_model(source)

        alpha_values = None
        for multiplier in (1, 2, 4):
            tolerance = self.background_tolerance * multiplier
            candidate_mask = self._connected_foreground_mask(
                source, background_model, tolerance
            )
            alpha_values = list(candidate_mask.getdata())
            foreground_ratio = sum(value > 0 for value in alpha_values) / (width * height)
            # A higher tolerance is useful only when the initial foreground is
            # implausibly large.  Frame contact alone must never trigger it:
            # connected foreground can be a valid product boundary.
            if foreground_ratio <= self.max_foreground_ratio:
                break
        if alpha_values is None:
            return None
        mask = Image.new("L", source.size)
        mask.putdata(alpha_values)
        mask = self._refine_mask(mask)
        mask = self._suppress_unreliable_edge_shadow(
            mask, source, background_model
        )
        confidence_mask = self._refine_mask(
            self._connected_foreground_mask(
                source, background_model, confidence_tolerance
            )
        )
        primary_ratio = sum(value > 0 for value in mask.getdata()) / (width * height)
        confidence_ratio = (
            sum(value > 0 for value in confidence_mask.getdata()) / (width * height)
        )
        if (
            self.min_foreground_ratio <= confidence_ratio <= self.max_foreground_ratio
            and min(primary_ratio, confidence_ratio) > self.max_shadow_foreground_loss
            and not self._foreground_masks_are_stable(mask, confidence_mask)
        ):
            # A product-sized foreground that moves by more than the already
            # permitted shadow-loss budget when the tolerance narrows is not a
            # stable segmentation.  Small isolated products are exempt: a
            # small alpha footprint can legitimately grow around a thin edge.
            return None
        if self._has_foreground_on_frame(mask):
            # A cutout destined for a new background must expose a transparent
            # frame.  Frame contact is indistinguishable from a surviving
            # source backdrop, so keep the original instead of compositing it.
            return None
        bbox = mask.getbbox()
        if bbox is None:
            return None
        foreground_count = sum(value > 0 for value in mask.getdata())
        foreground_ratio = foreground_count / (width * height)
        if not self.min_foreground_ratio <= foreground_ratio <= self.max_foreground_ratio:
            return None
        if (
            self._largest_foreground_component_ratio(mask, foreground_count)
            < self.min_largest_component_ratio
        ):
            return None

        red, green, blue = source.split()
        rgba = Image.merge("RGBA", (red, green, blue, mask))
        rgba_png = _encode_png(rgba)
        mask_png = _encode_png(mask)
        return ProductCutout(
            rgba_png=rgba_png,
            mask_png=mask_png,
            bbox=bbox,
            width=width,
            height=height,
            source_sha256=hashlib.sha256(source_image).hexdigest(),
            cutout_sha256=hashlib.sha256(rgba_png).hexdigest(),
            mask_sha256=hashlib.sha256(mask_png).hexdigest(),
        )

    @staticmethod
    def _refine_mask(mask: Image.Image) -> Image.Image:
        """Remove a one-pixel light halo while keeping source RGB untouched."""
        eroded = mask.filter(ImageFilter.MinFilter(3))
        softened = eroded.filter(ImageFilter.GaussianBlur(0.6))
        # Do not let the blur create alpha outside the original foreground mask.
        return ImageChops.multiply(softened, mask)

    @staticmethod
    def _connected_foreground_mask(
        source: Image.Image,
        background_model: Image.Image | tuple[int, int, int],
        tolerance: float,
    ) -> Image.Image:
        """Return foreground after flooding only edge-connected background candidates."""
        width, height = source.size
        source_pixels = source.load()
        background_pixels = (
            background_model.load()
            if isinstance(background_model, Image.Image)
            else None
        )
        background_candidates = bytearray(width * height)
        tolerance_squared = tolerance * tolerance
        for y in range(height):
            row_start = y * width
            for x in range(width):
                source_pixel = source_pixels[x, y]
                background_pixel = (
                    background_pixels[x, y]
                    if background_pixels is not None
                    else background_model
                )
                background_candidates[row_start + x] = int(
                    sum(
                        (source_channel - background_channel) ** 2
                        for source_channel, background_channel in zip(
                            source_pixel, background_pixel, strict=True
                        )
                    )
                    <= tolerance_squared
                )

        reachable_background = bytearray(width * height)
        pending: deque[tuple[int, int]] = deque()

        def enqueue_if_background(x: int, y: int) -> None:
            index = y * width + x
            if background_candidates[index] and not reachable_background[index]:
                reachable_background[index] = 1
                pending.append((x, y))

        for x in range(width):
            enqueue_if_background(x, 0)
            enqueue_if_background(x, height - 1)
        for y in range(height):
            enqueue_if_background(0, y)
            enqueue_if_background(width - 1, y)

        while pending:
            x, y = pending.popleft()
            for neighbor_x, neighbor_y in (
                (x - 1, y),
                (x + 1, y),
                (x, y - 1),
                (x, y + 1),
            ):
                if 0 <= neighbor_x < width and 0 <= neighbor_y < height:
                    enqueue_if_background(neighbor_x, neighbor_y)

        mask = Image.new("L", source.size)
        mask.putdata(
            [
                0 if reachable_background[index] else 255
                for index in range(width * height)
            ]
        )
        return mask

    def _has_nonuniform_frame(self, source: Image.Image) -> bool:
        """Return whether a small image's boundary exceeds one match tolerance."""
        width, height = source.size
        pixels = source.load()
        frame = [pixels[x, 0] for x in range(width)]
        frame += [pixels[x, height - 1] for x in range(width)]
        frame += [pixels[0, y] for y in range(height)]
        frame += [pixels[width - 1, y] for y in range(height)]
        reference = tuple(
            round(sum(pixel[channel] for pixel in frame) / len(frame))
            for channel in range(3)
        )
        nonuniform_pixels = sum(
            self._distance(pixel, reference) > self.corner_uniformity_tolerance
            for pixel in frame
        )
        # A broad gradient affects at least a quarter of frame samples; a
        # narrow contact shadow or JPEG outlier does not trigger this fallback.
        return nonuniform_pixels * 4 >= len(frame)

    def _edge_field_is_reliable(
        self, source: Image.Image, *, tolerance: float | None = None
    ) -> bool:
        """Check whether a broad boundary change can be interpolated safely.

        The spatial model is intentionally allowed to handle a dark-to-light
        studio gradient.  A wide range alone therefore cannot reject a photo.
        It becomes unsafe only when the full frame spans two match bands *and*
        its edge samples deviate by more than one match band from their own
        end-point trend.  In that situation a harmonic fill would be guessing
        at interior scene structure, which is exactly the case where a source
        fallback is safer than a plausible-looking partial cutout.
        """
        match_tolerance = tolerance or self.background_tolerance
        width, height = source.size
        pixels = source.load()
        edge_radius = max(1, min(16, min(width, height) // 40))
        edges = (
            self._median_smoothed_edge(
                [pixels[x, 0] for x in range(width)], edge_radius
            ),
            self._median_smoothed_edge(
                [pixels[x, height - 1] for x in range(width)], edge_radius
            ),
            self._median_smoothed_edge(
                [pixels[0, y] for y in range(height)], edge_radius
            ),
            self._median_smoothed_edge(
                [pixels[width - 1, y] for y in range(height)], edge_radius
            ),
        )
        samples = [pixel for edge in edges for pixel in edge]
        mean = tuple(
            sum(pixel[channel] for pixel in samples) / len(samples)
            for channel in range(3)
        )
        spread = sorted(self._distance(pixel, mean) for pixel in samples)
        spread_p90 = spread[round((len(spread) - 1) * 0.90)]
        # Two tolerance bands are the minimum range where a field has to
        # extrapolate rather than merely denoise a single background colour.
        if spread_p90 <= match_tolerance * 2:
            return True

        trend_residuals: list[float] = []
        for edge in edges:
            first, last = edge[0], edge[-1]
            denominator = max(1, len(edge) - 1)
            for index, pixel in enumerate(edge):
                weight = index / denominator
                expected = tuple(
                    first[channel] * (1 - weight) + last[channel] * weight
                    for channel in range(3)
                )
                trend_residuals.append(self._distance(pixel, expected))
        trend_residuals.sort()
        trend_p90 = trend_residuals[
            round((len(trend_residuals) - 1) * 0.90)
        ]
        return trend_p90 <= match_tolerance

    @staticmethod
    def _median_smoothed_edge(
        pixels: list[tuple[int, int, int]], radius: int
    ) -> list[tuple[int, int, int]]:
        """Smooth one frame edge without borrowing product pixels from its interior."""
        smoothed = []
        for index in range(len(pixels)):
            window = pixels[
                max(0, index - radius) : min(len(pixels), index + radius + 1)
            ]
            smoothed.append(
                tuple(
                    sorted(pixel[channel] for pixel in window)[len(window) // 2]
                    for channel in range(3)
                )
            )
        return smoothed

    def _edge_background_model(self, source: Image.Image) -> Image.Image:
        """Estimate a smooth background field from the full image boundary.

        A single corner average rejects ordinary studio gradients and vignettes.
        Here every frame pixel participates; a local median removes isolated
        JPEG noise and a thin edge contact before a harmonic interpolation fills
        the image interior.  The smoothing radius is at most 16 source pixels
        and otherwise 1/40 of the shorter side, keeping the model limited to
        broad lighting changes rather than product texture.
        """
        width, height = source.size
        pixels = source.load()
        edge_radius = max(1, min(16, min(width, height) // 40))
        top = self._median_smoothed_edge(
            [pixels[x, 0] for x in range(width)], edge_radius
        )
        bottom = self._median_smoothed_edge(
            [pixels[x, height - 1] for x in range(width)], edge_radius
        )
        left = self._median_smoothed_edge(
            [pixels[0, y] for y in range(height)], edge_radius
        )
        right = self._median_smoothed_edge(
            [pixels[width - 1, y] for y in range(height)], edge_radius
        )

        # One grid cell represents at least 16 source pixels.  This keeps the
        # field a lighting model, while the 64-cell cap bounds extraction work
        # for high-resolution inputs without changing its spatial intent.
        grid_width = max(3, min(64, math.ceil(width / 16)))
        grid_height = max(3, min(64, math.ceil(height / 16)))
        all_edges = top + bottom + left + right
        initial = tuple(
            round(sum(pixel[channel] for pixel in all_edges) / len(all_edges))
            for channel in range(3)
        )
        grid = [initial] * (grid_width * grid_height)

        def source_x(grid_x: int) -> int:
            return round(grid_x * (width - 1) / (grid_width - 1))

        def source_y(grid_y: int) -> int:
            return round(grid_y * (height - 1) / (grid_height - 1))

        for grid_x in range(grid_width):
            grid[grid_x] = top[source_x(grid_x)]
            grid[(grid_height - 1) * grid_width + grid_x] = bottom[
                source_x(grid_x)
            ]
        for grid_y in range(grid_height):
            grid[grid_y * grid_width] = left[source_y(grid_y)]
            grid[grid_y * grid_width + grid_width - 1] = right[
                source_y(grid_y)
            ]

        # One relaxation step moves boundary information one grid cell.  Four
        # times both dimensions is more than two traversals across this grid,
        # enough for a smooth field to settle while remaining input-size bound.
        for _ in range(4 * (grid_width + grid_height)):
            next_grid = grid[:]
            for grid_y in range(1, grid_height - 1):
                for grid_x in range(1, grid_width - 1):
                    above = grid[(grid_y - 1) * grid_width + grid_x]
                    below = grid[(grid_y + 1) * grid_width + grid_x]
                    left_pixel = grid[grid_y * grid_width + grid_x - 1]
                    right_pixel = grid[grid_y * grid_width + grid_x + 1]
                    next_grid[grid_y * grid_width + grid_x] = tuple(
                        (
                            above[channel]
                            + below[channel]
                            + left_pixel[channel]
                            + right_pixel[channel]
                        )
                        // 4
                        for channel in range(3)
                    )
            grid = next_grid

        # A harmonic field can understate a broad, neutral spotlight because
        # its dark top and bottom pull the center down.  For neutral-only
        # boundary samples, retain the brightest of the vertical, horizontal,
        # and harmonic estimates.  Colored backgrounds keep the harmonic value
        # so this cannot turn a similarly colored product into background.
        neutral_limit = self.background_tolerance / 2
        for grid_y in range(grid_height):
            vertical_weight = grid_y / (grid_height - 1)
            for grid_x in range(grid_width):
                horizontal_weight = grid_x / (grid_width - 1)
                vertical = tuple(
                    round(
                        top[source_x(grid_x)][channel] * (1 - vertical_weight)
                        + bottom[source_x(grid_x)][channel] * vertical_weight
                    )
                    for channel in range(3)
                )
                horizontal = tuple(
                    round(
                        left[source_y(grid_y)][channel]
                        * (1 - horizontal_weight)
                        + right[source_y(grid_y)][channel] * horizontal_weight
                    )
                    for channel in range(3)
                )
                index = grid_y * grid_width + grid_x
                estimates = (grid[index], vertical, horizontal)
                if all(
                    max(estimate) - min(estimate) <= neutral_limit
                    for estimate in estimates
                ):
                    grid[index] = max(estimates, key=sum)

        coarse_model = Image.new("RGB", (grid_width, grid_height))
        coarse_model.putdata(grid)
        return coarse_model.resize(source.size, Image.Resampling.BILINEAR)

    def _suppress_unreliable_edge_shadow(
        self,
        mask: Image.Image,
        source: Image.Image,
        background_model: Image.Image | tuple[int, int, int],
    ) -> Image.Image:
        """Suppress a tolerant edge shadow only when its own mask is trustworthy."""
        # Keep the low-contrast edge-shadow behavior without treating a broad
        # local-background match as permission to re-segment the product.
        tolerant_mask = self._connected_foreground_mask(
            source, background_model, self.background_tolerance * 4
        )
        tolerant_mask = self._refine_mask(tolerant_mask)
        tolerant_foreground_count = sum(value > 0 for value in tolerant_mask.getdata())
        primary_foreground_count = sum(value > 0 for value in mask.getdata())
        if tolerant_foreground_count == 0:
            return mask
        tolerant_ratio = tolerant_foreground_count / (source.width * source.height)
        if not self.min_foreground_ratio <= tolerant_ratio <= self.max_foreground_ratio:
            return mask
        if (
            self._largest_foreground_component_ratio(
                tolerant_mask, tolerant_foreground_count
            )
            < self.min_largest_component_ratio
        ):
            return mask
        if isinstance(background_model, Image.Image) and tolerant_foreground_count < primary_foreground_count * (
            1 - self.max_shadow_foreground_loss
        ):
            return mask
        return ImageChops.multiply(mask, tolerant_mask)

    def _suppress_connected_background_gradient(
        self,
        mask: Image.Image,
        source: Image.Image,
        background: tuple[int, int, int],
    ) -> Image.Image:
        """Compatibility hook for baseline-only regression diagnostics.

        The live extractor uses the edge field in its primary flood instead of
        applying a second global-colour gradient pass.  The comparison utility
        still invokes this former private hook while reconstructing a baseline;
        returning the supplied mask keeps that diagnostic path callable without
        letting it alter the new extraction flow.
        """
        del source, background
        return mask

    def _foreground_masks_are_stable(
        self, primary: Image.Image, confidence: Image.Image
    ) -> bool:
        """Return whether a narrower confidence mask keeps the same silhouette."""
        primary_values = primary.getdata()
        confidence_values = confidence.getdata()
        intersection = 0
        union = 0
        for primary_value, confidence_value in zip(
            primary_values, confidence_values, strict=True
        ):
            primary_visible = primary_value > 0
            confidence_visible = confidence_value > 0
            intersection += primary_visible and confidence_visible
            union += primary_visible or confidence_visible
        if union == 0:
            return False
        # Keep this budget tied to the shadow cleanup invariant rather than a
        # new image-set-specific threshold: a wider pass may move at most the
        # silhouette share that was already considered a possible shadow.
        return intersection / union >= 1 - self.max_shadow_foreground_loss

    @staticmethod
    def _has_foreground_on_frame(mask: Image.Image) -> bool:
        """Return whether any visible alpha remains at the source boundary."""
        width, height = mask.size
        pixels = mask.load()
        for x in range(width):
            if pixels[x, 0] > 0 or pixels[x, height - 1] > 0:
                return True
        for y in range(height):
            if pixels[0, y] > 0 or pixels[width - 1, y] > 0:
                return True
        return False

    @staticmethod
    def _largest_foreground_component_ratio(
        mask: Image.Image, foreground_count: int
    ) -> float:
        if foreground_count == 0:
            return 0.0
        width, height = mask.size
        pixels = mask.load()
        visited = bytearray(width * height)
        largest_component = 0
        for y in range(height):
            for x in range(width):
                index = y * width + x
                if visited[index] or pixels[x, y] == 0:
                    continue
                visited[index] = 1
                pending: deque[int] = deque((index,))
                component_size = 0
                while pending:
                    current = pending.popleft()
                    component_size += 1
                    current_x = current % width
                    current_y = current // width
                    for neighbor_x, neighbor_y in (
                        (current_x - 1, current_y),
                        (current_x + 1, current_y),
                        (current_x, current_y - 1),
                        (current_x, current_y + 1),
                    ):
                        if 0 <= neighbor_x < width and 0 <= neighbor_y < height:
                            neighbor = neighbor_y * width + neighbor_x
                            if (
                                not visited[neighbor]
                                and pixels[neighbor_x, neighbor_y] > 0
                            ):
                                visited[neighbor] = 1
                                pending.append(neighbor)
                largest_component = max(largest_component, component_size)
        return largest_component / foreground_count

    @staticmethod
    def _distance(left: tuple[int, int, int], right: tuple[int, int, int]) -> float:
        """Retain the diagnostic helper used by cutout regression reporting."""
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))


class ProductFidelityValidator:
    def __init__(
        self, extractor: SolidBackgroundCutoutExtractor | None = None
    ) -> None:
        self.extractor = extractor or SolidBackgroundCutoutExtractor()

    def validate(
        self,
        photo: ProductPhoto,
        *,
        source_images: tuple[tuple[bytes, str], ...] = (),
    ) -> FidelityStatus:
        if photo.asset_mode in {"generated_scene", "generated_view"}:
            role_is_allowed = (
                photo.asset_mode == "generated_scene" and photo.photo_id == "lifestyle"
            ) or (
                photo.asset_mode == "generated_view"
                and photo.photo_id in {"detail-02", "detail-03", "detail-04", "detail-05"}
            )
            if (
                not role_is_allowed
                or not photo.product_generated
                or not photo.background_generated
                or photo.fidelity_status != "GENERATED"
                or not photo.source_sha256
                or not source_images
            ):
                return "REJECTED"
            source_hashes = {
                hashlib.sha256(data).hexdigest() for data, _ in source_images
            }
            return "GENERATED" if photo.source_sha256 in source_hashes else "REJECTED"
        if photo.product_generated:
            return "REJECTED"
        if photo.asset_mode not in {"source", "source_crop", "source_composite"}:
            return "REJECTED"
        if not photo.source_sha256:
            return "REJECTED"
        if photo.asset_mode == "source_crop" and photo.transform.crop is None:
            return "REJECTED"
        if photo.asset_mode == "source_composite" and (
            not photo.cutout_sha256 or not photo.mask_sha256
        ):
            return "REJECTED"
        if photo.fidelity_status == "REJECTED" or not source_images:
            return "REJECTED"

        source_by_hash = {
            hashlib.sha256(data).hexdigest(): (data, mime_type)
            for data, mime_type in source_images
        }
        source_record = source_by_hash.get(photo.source_sha256)
        if source_record is None:
            return "REJECTED"
        source_data, source_mime_type = source_record

        if photo.asset_mode == "source":
            if hashlib.sha256(photo.data).hexdigest() != photo.source_sha256:
                return "REJECTED"
            return photo.fidelity_status

        try:
            source = _decode_rgb(source_data)
            rendered = _decode_rgb(photo.data)
        except ValueError:
            return "REJECTED"

        if photo.asset_mode == "source_crop":
            crop = photo.transform.crop
            if crop is None or not self._crop_in_bounds(crop, source.size):
                return "REJECTED"
            expected = source.crop(crop)
            if rendered.size != expected.size or rendered.tobytes() != expected.tobytes():
                return "REJECTED"
            return photo.fidelity_status

        cutout = self.extractor.extract(source_data, source_mime_type)
        if cutout is None:
            return "REJECTED"
        if (
            photo.source_sha256 != cutout.source_sha256
            or photo.cutout_sha256 != cutout.cutout_sha256
            or photo.mask_sha256 != cutout.mask_sha256
            or photo.transform.crop != cutout.bbox
            or photo.transform.scale <= 0
        ):
            return "REJECTED"

        rgba = Image.open(io.BytesIO(cutout.rgba_png)).convert("RGBA")
        visible = rgba.crop(cutout.bbox)
        resized_size = (
            max(1, round(visible.width * photo.transform.scale)),
            max(1, round(visible.height * photo.transform.scale)),
        )
        resized = visible.resize(resized_size, Image.Resampling.LANCZOS)
        expected_x = (rendered.width - resized.width) // 2
        expected_y = (
            rendered.height
            - resized.height
            - round(rendered.height * 0.14)
            if photo.photo_id in {"lifestyle", "scale"}
            else (rendered.height - resized.height) // 2
        )
        if (photo.transform.x, photo.transform.y) != (expected_x, expected_y):
            return "REJECTED"
        if (
            expected_x < 0
            or expected_y < 0
            or expected_x + resized.width > rendered.width
            or expected_y + resized.height > rendered.height
        ):
            return "REJECTED"

        alpha = resized.getchannel("A")
        opaque_points = 0
        for y in range(resized.height):
            for x in range(resized.width):
                if alpha.getpixel((x, y)) == 255:
                    opaque_points += 1
                    if rendered.getpixel((expected_x + x, expected_y + y)) != resized.getpixel(
                        (x, y)
                    )[:3]:
                        return "REJECTED"
        if opaque_points == 0:
            return "REJECTED"
        return photo.fidelity_status

    @staticmethod
    def _crop_in_bounds(
        crop: tuple[int, int, int, int], size: tuple[int, int]
    ) -> bool:
        left, top, right, bottom = crop
        width, height = size
        return 0 <= left < right <= width and 0 <= top < bottom <= height


class SourcePreservingProductPhotoGenerator:
    _layout_roles = ("hero", "packshot", "detail", "lifestyle")
    _labels = {
        "hero": "원본 보존 대표 이미지",
        "packshot": "원본 보존 팩샷",
        "detail": "원본 디테일 크롭",
        "lifestyle": "원본 제품 활용 장면",
        "scale": "원본 제품 크기 비교",
        "alternate": "추가 원본 구도",
    }

    def __init__(
        self,
        *,
        asset_store: SourceAssetStore | None = None,
        extractor: SolidBackgroundCutoutExtractor | None = None,
        background_generator: BackgroundGenerator | None = None,
        usage_scene_generator: UsageSceneGenerator | None = None,
        detail_view_generator: DetailViewGenerator | None = None,
        validator: ProductFidelityValidator | None = None,
        canvas_size: tuple[int, int] = (1200, 1200),
        include_scale: bool = False,
        source_photo_variation_threshold: int = 4,
        photo_roles: tuple[str, ...] | None = None,
    ):
        if source_photo_variation_threshold < 1:
            raise ValueError("source_photo_variation_threshold must be at least 1")
        self.asset_store = asset_store or MemoryAssetStore()
        self.extractor = extractor or SolidBackgroundCutoutExtractor()
        self.background_generator = background_generator
        self.usage_scene_generator = usage_scene_generator
        self.detail_view_generator = detail_view_generator
        self.validator = validator or ProductFidelityValidator()
        self.canvas_size = canvas_size
        self.include_scale = include_scale
        self.source_photo_variation_threshold = source_photo_variation_threshold
        requested_roles = tuple(photo_roles or self._layout_roles)
        allowed_roles = set(self._layout_roles) | {"scale"}
        if not requested_roles or any(role not in allowed_roles for role in requested_roles):
            raise ValueError("photo_roles contains an unsupported role")
        self.photo_roles = requested_roles

    def generate(
        self,
        *,
        source_image: bytes,
        source_mime_type: str,
        profile: ProductProfileDto,
        options: GenerationOptions,
        additional_source_images: tuple[tuple[bytes, str], ...] = (),
    ) -> ProductPhotoSet:
        del options
        source_images = ((source_image, source_mime_type),) + additional_source_images
        roles = list(self.photo_roles)
        if self.include_scale and "scale" not in roles:
            roles.append("scale")
        preserve_arrangement = self._preserve_arrangement(profile)

        # Four source photos cover the current layout roles. In that case, do not
        # extract a mask, request a background, or derive any additional view.
        if len(source_images) >= max(self.source_photo_variation_threshold, len(roles)):
            return self._validated_source_set(source_images, roles)

        source_record = self.asset_store.put(source_image, source_mime_type, "source")
        source_rgb = _decode_rgb(source_image)
        cutout = self.extractor.extract(source_image, source_mime_type)

        if cutout is None:
            photos = [
                self._source_fallback(
                    role=role,
                    order=index,
                    source_image=source_image,
                    source_mime_type=source_mime_type,
                    source_asset_id=source_record.asset_id,
                    source_sha256=source_record.sha256,
                    size=source_rgb.size,
                )
                for index, role in enumerate(roles, start=1)
            ]
            # Reference-image editing does not require a foreground mask.
            reference_args = dict(
                profile=profile,
                source_asset_id=source_record.asset_id,
                source_sha256=source_record.sha256,
                source_image=source_image,
                source_mime_type=source_mime_type,
            )
            if "lifestyle" in roles:
                index = roles.index("lifestyle")
                scene = self._generated_usage_scene(order=index + 1, **reference_args)
                if scene is not None:
                    photos[index] = scene
            if "detail" in roles:
                for role in ("detail-02", "detail-03", "detail-04", "detail-05"):
                    view = self._generated_detail_view(
                        role=role, order=len(photos) + 1, **reference_args
                    )
                    if view is not None:
                        photos.append(view)
        else:
            photos = []
            if "hero" in roles:
                if preserve_arrangement:
                    photos.append(
                        self._source_fallback(
                            role="hero",
                            order=len(photos) + 1,
                            source_image=source_image,
                            source_mime_type=source_mime_type,
                            source_asset_id=source_record.asset_id,
                            source_sha256=source_record.sha256,
                            size=source_rgb.size,
                        )
                    )
                else:
                    photos.append(
                        self._composite(
                            role="hero",
                            order=len(photos) + 1,
                            cutout=cutout,
                            source_asset_id=source_record.asset_id,
                            background=self._solid_background("#F7F7F5"),
                            background_generated=False,
                        )
                    )
            if "packshot" in roles:
                if preserve_arrangement:
                    photos.append(
                        self._source_fallback(
                            role="packshot",
                            order=len(photos) + 1,
                            source_image=source_image,
                            source_mime_type=source_mime_type,
                            source_asset_id=source_record.asset_id,
                            source_sha256=source_record.sha256,
                            size=source_rgb.size,
                        )
                    )
                else:
                    photos.append(
                        self._composite(
                            role="packshot",
                            order=len(photos) + 1,
                            cutout=cutout,
                            source_asset_id=source_record.asset_id,
                            background=self._solid_background("#FFFFFF"),
                            background_generated=False,
                        )
                    )
            detail_crops = self._detail_crops(
                order=len(photos) + 1,
                source=source_rgb,
                cutout=cutout,
                source_asset_id=source_record.asset_id,
            )
            if "detail" in roles:
                photos.append(detail_crops[0])
            if "lifestyle" in roles:
                generated_scene = self._generated_usage_scene(
                    profile=profile,
                    order=len(photos) + 1,
                    source_asset_id=source_record.asset_id,
                    source_sha256=source_record.sha256,
                    source_image=source_image,
                    source_mime_type=source_mime_type,
                )
                if generated_scene is not None:
                    photos.append(generated_scene)
                else:
                    lifestyle_background, generated = self._background_for(
                        profile=profile, role="lifestyle"
                    )
                    photos.append(
                        self._composite(
                            role="lifestyle",
                            order=len(photos) + 1,
                            cutout=cutout,
                            source_asset_id=source_record.asset_id,
                            background=lifestyle_background,
                            background_generated=generated,
                        )
                    )
            if "scale" in roles:
                if preserve_arrangement:
                    photos.append(
                        self._source_fallback(
                            role="scale",
                            order=len(photos) + 1,
                            source_image=source_image,
                            source_mime_type=source_mime_type,
                            source_asset_id=source_record.asset_id,
                            source_sha256=source_record.sha256,
                            size=source_rgb.size,
                        )
                    )
                else:
                    scale_background, scale_generated = self._background_for(
                        profile=profile, role="scale"
                    )
                    photos.append(
                        self._composite(
                            role="scale",
                            order=len(photos) + 1,
                            cutout=cutout,
                            source_asset_id=source_record.asset_id,
                            background=scale_background,
                            background_generated=scale_generated,
                        )
                    )
            if "detail" in roles:
                for detail_photo in detail_crops[1:]:
                    order = len(photos) + 1
                    generated_view = None
                    if detail_photo.photo_id in {
                        "detail-02",
                        "detail-03",
                        "detail-04",
                        "detail-05",
                    }:
                        generated_view = self._generated_detail_view(
                            profile=profile,
                            role=detail_photo.photo_id,
                            order=order,
                            source_asset_id=source_record.asset_id,
                            source_sha256=source_record.sha256,
                            source_image=source_image,
                            source_mime_type=source_mime_type,
                        )
                    photos.append(generated_view or replace(detail_photo, order=order))

        for index, (alternate_data, alternate_mime) in enumerate(
            additional_source_images, start=1
        ):
            photos.append(
                self._source_original(
                    photo_id="alternate" if index == 1 else f"alternate-{index:02d}",
                    order=len(photos) + 1,
                    data=alternate_data,
                    mime_type=alternate_mime,
                    label=self._labels["alternate"],
                )
            )

        safe_photos = []
        for photo in photos:
            status = self.validator.validate(photo, source_images=source_images)
            if status != "REJECTED":
                safe_photos.append(photo)
        return ProductPhotoSet(photos=tuple(safe_photos))

    def _generated_usage_scene(
        self,
        *,
        profile: ProductProfileDto,
        order: int,
        source_asset_id: str,
        source_sha256: str,
        source_image: bytes,
        source_mime_type: str,
    ) -> ProductPhoto | None:
        if self.usage_scene_generator is None:
            return None
        try:
            data = self.usage_scene_generator.generate(
                profile=profile,
                role="lifestyle",
                source_image=source_image,
                source_mime_type=source_mime_type,
                width=self.canvas_size[0],
                height=self.canvas_size[1],
            )
            image = _decode_rgb(data)
        except (RuntimeError, ValueError, OSError):
            return None
        return ProductPhoto(
            photo_id="lifestyle",
            order=order,
            label="AI 생성 활용 장면(참고용)",
            data=data,
            mime_type="image/png",
            width=image.width,
            height=image.height,
            asset_mode="generated_scene",
            source_asset_id=source_asset_id,
            source_sha256=source_sha256,
            background_generated=True,
            product_generated=True,
            fidelity_status="GENERATED",
        )

    def _generated_detail_view(
        self,
        *,
        profile: ProductProfileDto,
        role: str,
        order: int,
        source_asset_id: str,
        source_sha256: str,
        source_image: bytes,
        source_mime_type: str,
    ) -> ProductPhoto | None:
        if self.detail_view_generator is None:
            return None
        try:
            data = self.detail_view_generator.generate(
                profile=profile,
                role=role,
                source_image=source_image,
                source_mime_type=source_mime_type,
                width=self.canvas_size[0],
                height=self.canvas_size[1],
            )
            image = _decode_rgb(data)
        except (RuntimeError, ValueError, OSError):
            return None
        return ProductPhoto(
            photo_id=role,
            order=order,
            label="AI 생성 디테일(참고용)",
            data=data,
            mime_type="image/png",
            width=image.width,
            height=image.height,
            asset_mode="generated_view",
            source_asset_id=source_asset_id,
            source_sha256=source_sha256,
            background_generated=True,
            product_generated=True,
            fidelity_status="GENERATED",
        )

    def _validated_source_set(
        self,
        source_images: tuple[tuple[bytes, str], ...],
        roles: list[str],
    ) -> ProductPhotoSet:
        photos = []
        for index, (data, mime_type) in enumerate(source_images):
            if index < len(roles):
                photo_id = roles[index]
                label = self._labels[photo_id]
            else:
                alternate_index = index - len(roles) + 1
                photo_id = (
                    "alternate"
                    if alternate_index == 1
                    else f"alternate-{alternate_index:02d}"
                )
                label = self._labels["alternate"]
            photos.append(
                self._source_original(
                    photo_id=photo_id,
                    order=index + 1,
                    data=data,
                    mime_type=mime_type,
                    label=label,
                )
            )
        return ProductPhotoSet(
            photos=tuple(
                photo
                for photo in photos
                if self.validator.validate(photo, source_images=source_images)
                != "REJECTED"
            )
        )

    def _source_original(
        self,
        *,
        photo_id: str,
        order: int,
        data: bytes,
        mime_type: str,
        label: str,
    ) -> ProductPhoto:
        record = self.asset_store.put(data, mime_type, "source")
        image = _decode_rgb(data)
        return ProductPhoto(
            photo_id=photo_id,
            order=order,
            label=label,
            data=data,
            mime_type=mime_type,
            width=image.width,
            height=image.height,
            asset_mode="source",
            source_asset_id=record.asset_id,
            source_sha256=record.sha256,
            product_generated=False,
            fidelity_status="VERIFIED",
        )

    def _source_fallback(
        self,
        *,
        role: str,
        order: int,
        source_image: bytes,
        source_mime_type: str,
        source_asset_id: str,
        source_sha256: str,
        size: tuple[int, int],
    ) -> ProductPhoto:
        return ProductPhoto(
            photo_id=role,
            order=order,
            label=self._labels[role],
            data=source_image,
            mime_type=source_mime_type,
            width=size[0],
            height=size[1],
            asset_mode="source",
            source_asset_id=source_asset_id,
            source_sha256=source_sha256,
            product_generated=False,
            fidelity_status="FALLBACK",
        )

    def _detail_crops(
        self,
        *,
        order: int,
        source: Image.Image,
        cutout: ProductCutout,
        source_asset_id: str,
    ) -> list[ProductPhoto]:
        left, top, right, bottom = cutout.bbox
        box_width = right - left
        box_height = bottom - top
        crop_width = max(1, round(box_width * 0.62))
        crop_height = max(1, round(box_height * 0.62))
        center_positions = (
            (0.50, 0.50),
            (0.35, 0.35),
            (0.65, 0.65),
            (0.65, 0.35),
            (0.35, 0.65),
        )
        crops = []
        seen: set[tuple[int, int, int, int]] = set()
        for index, (horizontal, vertical) in enumerate(center_positions):
            center_x = round(left + box_width * horizontal)
            center_y = round(top + box_height * vertical)
            crop_left = max(0, min(source.width - crop_width, center_x - crop_width // 2))
            crop_top = max(0, min(source.height - crop_height, center_y - crop_height // 2))
            crop = (
                crop_left,
                crop_top,
                min(source.width, crop_left + crop_width),
                min(source.height, crop_top + crop_height),
            )
            if crop in seen:
                continue
            seen.add(crop)
            crops.append(
                ProductPhoto(
                    photo_id="detail" if index == 0 else f"detail-{index + 1:02d}",
                    order=order + len(crops),
                    label=self._labels["detail"],
                    data=_encode_png(source.crop(crop)),
                    mime_type="image/png",
                    width=crop[2] - crop[0],
                    height=crop[3] - crop[1],
                    asset_mode="source_crop",
                    source_asset_id=source_asset_id,
                    source_sha256=cutout.source_sha256,
                    transform=PhotoTransform(crop=crop),
                    product_generated=False,
                    fidelity_status="VERIFIED",
                )
            )
        return crops

    def _composite(
        self,
        *,
        role: str,
        order: int,
        cutout: ProductCutout,
        source_asset_id: str,
        background: Image.Image,
        background_generated: bool,
    ) -> ProductPhoto:
        canvas_width, canvas_height = self.canvas_size
        canvas = ImageOps.fit(
            background.convert("RGB"),
            self.canvas_size,
            method=Image.Resampling.LANCZOS,
        )
        rgba = Image.open(io.BytesIO(cutout.rgba_png)).convert("RGBA")
        visible = rgba.crop(cutout.bbox)
        max_width = round(canvas_width * (0.72 if role != "lifestyle" else 0.50))
        max_height = round(canvas_height * (0.72 if role != "lifestyle" else 0.50))
        scale = min(max_width / visible.width, max_height / visible.height)
        resized_size = (
            max(1, round(visible.width * scale)),
            max(1, round(visible.height * scale)),
        )
        resized = visible.resize(resized_size, Image.Resampling.LANCZOS)
        x = (canvas_width - resized.width) // 2
        if role in {"lifestyle", "scale"}:
            # Lifestyle/scale shots need a believable ground plane. Anchor the
            # source-preserved product near the lower surface instead of floating
            # it at the canvas center.
            y = canvas_height - resized.height - round(canvas_height * 0.14)
            canvas = self._add_contact_shadow(
                canvas,
                x=x,
                y=y,
                width=resized.width,
                height=resized.height,
            )
        else:
            y = (canvas_height - resized.height) // 2
        canvas.paste(resized, (x, y), resized.getchannel("A"))
        data = _encode_png(canvas)
        return ProductPhoto(
            photo_id=role,
            order=order,
            label=self._labels[role],
            data=data,
            mime_type="image/png",
            width=canvas_width,
            height=canvas_height,
            asset_mode="source_composite",
            source_asset_id=source_asset_id,
            source_sha256=cutout.source_sha256,
            cutout_sha256=cutout.cutout_sha256,
            mask_sha256=cutout.mask_sha256,
            background_generated=background_generated,
            product_generated=False,
            transform=PhotoTransform(scale=scale, x=x, y=y, crop=cutout.bbox),
            fidelity_status="VERIFIED",
        )

    @staticmethod
    def _add_contact_shadow(
        canvas: Image.Image,
        *,
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> Image.Image:
        """Add only a soft grounding shadow behind the immutable source pixels."""
        shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(shadow)
        shadow_left = x + round(width * 0.10)
        shadow_right = x + round(width * 0.90)
        shadow_y = y + height - max(2, round(height * 0.012))
        draw.ellipse(
            (shadow_left, shadow_y, shadow_right, shadow_y + max(6, round(height * 0.055))),
            fill=(35, 30, 25, 105),
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(max(2, round(width * 0.014))))
        return Image.alpha_composite(canvas.convert("RGBA"), shadow).convert("RGB")

    def _background_for(
        self, *, profile: ProductProfileDto, role: str
    ) -> tuple[Image.Image, bool]:
        if self.background_generator is None:
            return self._solid_background("#E9E4DC"), False
        try:
            data = self.background_generator.generate(
                profile=profile,
                role=role,
                width=self.canvas_size[0],
                height=self.canvas_size[1],
            )
            return _decode_rgb(data), True
        except (RuntimeError, ValueError, OSError):
            return self._solid_background("#E9E4DC"), False

    @staticmethod
    def _preserve_arrangement(profile: ProductProfileDto) -> bool:
        """Avoid AI recomposition when the input is a photographed multi-item set."""
        visible_components = profile.observations.get("visible_components")
        if isinstance(visible_components, list) and len(visible_components) >= 3:
            return True
        searchable = " ".join(
            value
            for value in (
                profile.product_type,
                profile.display_name or "",
                profile.summary,
                *profile.keywords,
            )
            if value
        ).lower()
        return any(
            marker in searchable
            for marker in (
                "세트",
                "set",
                "컬렉션",
                "collection",
                "병과",
                "잔과",
                "주전자 및",
            )
        )

    def _solid_background(self, color: str) -> Image.Image:
        return Image.new("RGB", self.canvas_size, color)
