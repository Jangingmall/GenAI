"""Build the curated pilot dataset used by the local image-generation workflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from detail_page_ai.training_dataset import build_training_dataset


DEFAULT_MANIFEST = PROJECT_ROOT / "data/finetune/flux2_product_scene_pilot_manifest.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "generated/datasets/flux2_product_scene_pilot_2026-09-04"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a provenance-aware image/caption dataset from a curated manifest."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    summary = build_training_dataset(
        args.manifest,
        args.output,
        project_root=PROJECT_ROOT,
    )
    print(json.dumps(summary.as_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
