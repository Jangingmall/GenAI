"""Safe, deterministic access to the detail-page layout archetype catalog."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from .dto import UserHintsDto


LAYOUT_CATALOG_PATH = (
    Path(__file__).resolve().parents[2] / "assets" / "references" / "detail-page-layouts.json"
)


def load_layout_catalog(path: Path | None = None) -> list[dict[str, Any]]:
    """Load valid catalog entries, treating a missing or malformed asset as optional."""
    try:
        payload = json.loads((path or LAYOUT_CATALOG_PATH).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []

    if not isinstance(payload, list) or not all(
        isinstance(entry, dict)
        and isinstance(entry.get("id"), str)
        and isinstance(entry.get("name"), str)
        and isinstance(entry.get("when"), str)
        and isinstance(entry.get("sequence"), list)
        and all(isinstance(block_type, str) for block_type in entry["sequence"])
        for entry in payload
    ):
        return []
    return payload


LAYOUT_ARCHETYPES = load_layout_catalog()


def select_layout_archetypes(
    image_sha256: str,
    user_hints: UserHintsDto | None,
    count: int = 4,
) -> list[dict[str, Any]]:
    """Return a reproducible, data-compatible sample of layout examples."""
    if count <= 0:
        return []

    has_making_method = bool(user_hints and user_hints.making_method)
    candidates = [
        archetype
        for archetype in LAYOUT_ARCHETYPES
        if has_making_method or "statement" not in archetype.get("sequence", [])
    ]
    selected = random.Random(image_sha256).sample(candidates, k=min(count, len(candidates)))
    return [dict(archetype) for archetype in selected]
