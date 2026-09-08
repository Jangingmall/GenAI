"""Create a 50-image product-scene augmentation pack for Flux2 experiments.

The generated images are deterministic source-preserving composites, not new
ground-truth product photographs.  Each image keeps a link to its source and
stores the intended scene instruction as a caption for later fine-tuning.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from pathlib import Path
from typing import Any, Mapping

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from detail_page_ai.training_augmentation import build_editorial_variant
from detail_page_ai.training_dataset import build_training_dataset


DEFAULT_RECIPES = PROJECT_ROOT / "data/finetune/flux2_product_scene_50_recipes.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "generated/datasets/flux2_product_scene_50_2026-09-04"
STAGING_ROOT = PROJECT_ROOT / "generated/runs/flux2_product_scene_50_augmentation_v1/images"
MODEL_NAME = "PIL-product-preserving-augmentation-v1"
PROMPT_VERSION = "flux2-product-scene-v1"

COMMON_PROMPT = "e-commerce product photography, modern layout, soft lighting, minimal design"
COMMON_NEGATIVE = (
    "invented product detail, changed silhouette, changed color, changed pattern, "
    "missing component, extra component, duplicate product, floating product, unstable base, "
    "unrelated props, invented logo, invented text, watermark, typography"
)

_PIL_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the 50-image Flux2 product-scene pack.")
    parser.add_argument("--recipes", type=Path, default=DEFAULT_RECIPES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--staging", type=Path, default=STAGING_ROOT)
    args = parser.parse_args()

    recipes = json.loads(args.recipes.read_text(encoding="utf-8"))
    manifest, prompt_lines, expected_count = _materialize_manifest(recipes, args.staging)
    if expected_count != 50:
        raise ValueError(f"recipe count must be exactly 50, got {expected_count}")

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "manifest_resolved.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output / "prompt_lines.txt").write_text(
        "\n".join(prompt_lines) + "\n", encoding="utf-8"
    )
    summary = build_training_dataset(manifest, args.output, project_root=PROJECT_ROOT)
    print(json.dumps(summary.as_dict(), ensure_ascii=False, indent=2))


def _materialize_manifest(
    recipes: Mapping[str, Any], staging_root: Path
) -> tuple[dict[str, Any], list[str], int]:
    products: list[dict[str, Any]] = []
    prompt_lines: list[str] = []
    total_count = 0

    for product in recipes.get("products", []):
        product_id = _required_text(product, "product_id")
        product_type = _required_text(product, "product_type")
        split = _required_text(product, "split")
        description = _required_text(product, "description")
        negative_product = _required_text(product, "negative_product")
        source_assets = product.get("source_assets", [])
        if not isinstance(source_assets, list) or not source_assets:
            raise ValueError(f"source_assets must be a non-empty list for {product_id}")
        source_by_id: dict[str, Mapping[str, Any]] = {}
        assets: list[dict[str, Any]] = []

        for index, source_asset in enumerate(source_assets):
            source_id = _required_text(source_asset, "asset_id")
            source_path = _required_text(source_asset, "path")
            source_by_id[source_id] = source_asset
            source_caption = (
                f"{COMMON_PROMPT} of the exact supplied {product_type}; {description}; "
                f"original source photograph, preserve the original camera angle, framing, "
                f"product shape, colors, surface details, and all visible components"
            )
            assets.append(
                {
                    "asset_id": source_id,
                    "path": source_path,
                    "source_path": source_path,
                    "role": _required_text(source_asset, "role"),
                    "asset_mode": "source",
                    "fidelity_status": "VERIFIED" if index == 0 and product_id == "metal-tea-set-01" else "SOURCE",
                    "human_approved": True,
                    "approved_for_training": True,
                    "caption": source_caption,
                    "negative_prompt": f"{negative_product}, {COMMON_NEGATIVE}",
                    "model": None,
                    "prompt_version": "source-anchor-v1",
                    "notes": "source anchor; do not alter the original pixels",
                }
            )
            total_count += 1

        variants = product.get("variants", [])
        if not isinstance(variants, list):
            raise ValueError(f"variants must be a list for {product_id}")
        for variant_index, variant in enumerate(variants):
            asset_id = _required_text(variant, "asset_id")
            source_id = _required_text(variant, "source_asset")
            source_asset = source_by_id.get(source_id)
            if source_asset is None:
                raise ValueError(f"unknown source_asset {source_id} for {product_id}/{asset_id}")
            source_path = _required_text(source_asset, "path")
            source_file = PROJECT_ROOT / source_path
            if not source_file.is_file():
                raise FileNotFoundError(source_path)
            image_path = staging_root / product_id / f"{asset_id}.png"
            image_path.parent.mkdir(parents=True, exist_ok=True)
            result = build_editorial_variant(
                source_file.read_bytes(),
                _mime_type(source_file),
                variant,
                seed=1000 + variant_index + _stable_product_seed(product_id),
                size=tuple(recipes.get("image_size", [1024, 1024])),
            )
            result.image.save(image_path, format="PNG", optimize=False)
            relative_image_path = image_path.relative_to(PROJECT_ROOT).as_posix()
            caption = _build_prompt(product, variant)
            prompt_lines.append(f"{product_id}/{asset_id}\t{caption}")
            assets.append(
                {
                    "asset_id": asset_id,
                    "path": relative_image_path,
                    "source_path": source_path,
                    "role": _required_text(variant, "role"),
                    "asset_mode": "synthetic_composite",
                    "fidelity_status": "SYNTHETIC",
                    "human_approved": False,
                    "approved_for_training": True,
                    "automated_invariant_check": result.invariant_check_passed,
                    "caption": caption,
                    "negative_prompt": f"{negative_product}, {COMMON_NEGATIVE}",
                    "model": MODEL_NAME,
                    "prompt_version": PROMPT_VERSION,
                    "notes": (
                        f"deterministic source-preserving composite; preservation_mode="
                        f"{result.preservation_mode}; source_region={result.source_region}"
                    ),
                }
            )
            total_count += 1

        products.append(
            {
                "product_id": product_id,
                "product_type": product_type,
                "split": split,
                "assets": assets,
            }
        )

    _append_existing_candidates(products)
    manifest = {
        "dataset_id": _required_text(recipes, "dataset_id"),
        "dataset_version": _required_text(recipes, "dataset_version"),
        "products": products,
    }
    return manifest, prompt_lines, total_count


def _append_existing_candidates(products: list[dict[str, Any]]) -> None:
    metal = next((product for product in products if product["product_id"] == "metal-tea-set-01"), None)
    if metal is None:
        return
    candidate_specs = (
        ("generated-scene-01", "generated/runs/images2_metal_tea_set_detail_page_v1/photos/04-lifestyle.png", "generated_scene"),
        ("generated-angle-02", "generated/runs/images2_metal_tea_set_detail_page_v1/photos/05-detail-02.png", "generated_angle"),
        ("generated-detail-03", "generated/runs/images2_metal_tea_set_detail_page_v1/photos/06-detail-03.png", "generated_macro"),
        ("generated-usage-04", "generated/runs/images2_metal_tea_set_detail_page_v1/photos/07-detail-04.png", "generated_usage"),
        ("generated-topdown-05", "generated/runs/images2_metal_tea_set_detail_page_v1/photos/08-detail-05.png", "generated_topdown"),
    )
    for asset_id, path, role in candidate_specs:
        if not (PROJECT_ROOT / path).is_file():
            continue
        metal["assets"].append(
            {
                "asset_id": asset_id,
                "path": path,
                "source_path": "assets/samples/images-2.jpeg",
                "role": role,
                "asset_mode": "generated_view" if role != "generated_scene" else "generated_scene",
                "fidelity_status": "GENERATED",
                "human_approved": False,
                "approved_for_training": False,
                "caption": "previous Flux2 candidate retained for human review only",
                "negative_prompt": COMMON_NEGATIVE,
                "model": "mlx-community/flux2-klein-9b-4bit",
                "prompt_version": "previous-run-candidate",
                "notes": "candidate only; never promote without human product-fidelity review",
            }
        )


def _build_prompt(product: Mapping[str, Any], variant: Mapping[str, Any]) -> str:
    product_type = _required_text(product, "product_type")
    description = _required_text(product, "description")
    scene = _required_text(variant, "scene")
    background = _required_text(variant, "background")
    return (
        f"{COMMON_PROMPT}; exact supplied {product_type}, {description}; {scene}; "
        f"product-preserving editorial composition, {background} studio background, "
        f"natural contact shadow, believable scale, no added props, retain every visible "
        f"product detail and source color"
    )


def _stable_product_seed(product_id: str) -> int:
    return sum((index + 1) * ord(char) for index, char in enumerate(product_id)) % 10000


def _mime_type(path: Path) -> str:
    return _PIL_MIME.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "image/jpeg"


def _required_text(value: Mapping[str, Any], key: str) -> str:
    candidate = value.get(key)
    if not isinstance(candidate, str) or not candidate.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return candidate.strip()


if __name__ == "__main__":
    main()
