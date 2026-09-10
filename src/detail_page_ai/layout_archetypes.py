"""Safe, deterministic access to the detail-page layout archetype catalog."""

from __future__ import annotations

import json
import random
from collections.abc import Mapping, Sequence
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


def match_page_plan_to_archetype(
    page_plan: Sequence[Any],
    archetypes: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Find the candidate archetype that best matches the emitted page plan without altering DTO."""
    if not page_plan:
        return None
    candidates = list(archetypes) if archetypes is not None else LAYOUT_ARCHETYPES
    if not candidates:
        return None

    plan_types = [
        getattr(block, "block_type", None)
        or (block.get("block_type") if isinstance(block, dict) else str(block))
        for block in page_plan
    ]

    best_match = None
    best_score = -1.0

    for arch in candidates:
        seq = arch.get("sequence", [])
        if not seq:
            continue
        if plan_types == seq:
            return dict(arch)
        intersection = len(set(plan_types) & set(seq))
        union = len(set(plan_types) | set(seq))
        score = intersection / max(union, 1)
        if score > best_score:
            best_score = score
            best_match = dict(arch)

    return best_match

