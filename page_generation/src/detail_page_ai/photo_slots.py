"""Photo slot definitions and resolution policies for detail page blocks."""

from __future__ import annotations

from collections.abc import Collection, Sequence

GALLERY_SLOTS = ("detail", "detail-02", "detail-03", "detail-04", "detail-05")
GENERATED_DETAIL_SLOTS = GALLERY_SLOTS[1:]


def resolve_gallery_photo_ids(
    requested: Sequence[str] | None,
    available: Collection[str],
) -> list[str]:
    """Resolve gallery photo IDs following the detail cut precedence policy.

    1. If any generated detail cut (detail-02 ~ detail-05) exists in ``available``,
       all slots from ``GALLERY_SLOTS`` present in ``available`` are returned in order
       (ignoring ``requested``).
    2. Otherwise, returns items from ``requested`` present in ``available``. If that
       result is empty, falls back to all slots from ``GALLERY_SLOTS`` present in
       ``available``.
    3. Duplicates are removed while preserving order, capped at ``len(GALLERY_SLOTS)``.
    """
    available_set = set(available)
    if any(slot in available_set for slot in GENERATED_DETAIL_SLOTS):
        candidates = [slot for slot in GALLERY_SLOTS if slot in available_set]
    else:
        candidates = [slot for slot in (requested or ()) if slot in available_set]
        if not candidates:
            candidates = [slot for slot in GALLERY_SLOTS if slot in available_set]

    deduplicated: list[str] = []
    for photo_id in candidates:
        if photo_id and photo_id not in deduplicated:
            deduplicated.append(photo_id)
    return deduplicated[: len(GALLERY_SLOTS)]


__all__ = [
    "GALLERY_SLOTS",
    "GENERATED_DETAIL_SLOTS",
    "resolve_gallery_photo_ids",
]
