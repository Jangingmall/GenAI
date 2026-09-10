import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "assets" / "references" / "detail-page-layouts.json"
ALLOWED_BLOCK_TYPES = {
    "hero",
    "statement",
    "feature_grid",
    "detail_split",
    "wide_image",
    "gallery",
    "usage_scene",
    "scale_reference",
    "palette",
    "recommendation",
    "info_table",
    "notice",
    "closing",
}
ALLOWED_VARIANTS = {
    "paper",
    "light",
    "sand",
    "dark",
    "image-left",
    "image-right",
    "full-bleed",
    "compact",
}
REQUIRED_KEYS = {
    "id",
    "name",
    "when",
    "avoid_when",
    "sequence",
    "middle_count",
    "rationale",
    "source",
    "variants",
}


def load_catalog() -> list[dict]:
    assert CATALOG_PATH.is_file(), f"catalog is missing: {CATALOG_PATH}"
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    assert isinstance(catalog, list), "catalog must be a top-level JSON array"
    return catalog


def test_catalog_uses_only_supported_block_types():
    for layout in load_catalog():
        assert isinstance(layout["sequence"], list)
        assert set(layout["sequence"]) <= ALLOWED_BLOCK_TYPES


def test_catalog_uses_only_supported_variants():
    for layout in load_catalog():
        assert isinstance(layout["variants"], list)
        assert set(layout["variants"]) <= ALLOWED_VARIANTS


def test_catalog_variant_count_matches_sequence():
    for layout in load_catalog():
        assert len(layout["variants"]) == len(layout["sequence"])


def test_catalog_contains_at_least_ten_distinct_variant_combinations():
    layouts = load_catalog()
    variant_combinations = {tuple(layout["variants"]) for layout in layouts}
    assert len(variant_combinations) >= 10


def test_catalog_layouts_have_required_edges_and_maximum_size():
    for layout in load_catalog():
        sequence = layout["sequence"]
        assert sequence[0] == "hero"
        assert sequence[-1] == "closing"
        assert len(sequence) <= 14


def test_catalog_middle_count_matches_sequence():
    for layout in load_catalog():
        assert layout["middle_count"] == len(layout["sequence"]) - 2


def test_catalog_layout_ids_are_unique():
    layouts = load_catalog()
    ids = [layout["id"] for layout in layouts]
    assert len(ids) == len(set(ids))


def test_catalog_contains_at_least_twenty_five_distinct_sequences():
    layouts = load_catalog()
    sequences = {tuple(layout["sequence"]) for layout in layouts}
    assert len(sequences) >= 25


def test_catalog_spans_at_least_four_block_lengths():
    lengths = {len(layout["sequence"]) for layout in load_catalog()}
    assert len(lengths) >= 4


def test_no_single_block_length_dominates_catalog():
    lengths = Counter(len(layout["sequence"]) for layout in load_catalog())
    assert max(lengths.values()) * 5 <= sum(lengths.values()) * 3


def test_catalog_entries_have_all_documented_fields():
    for layout in load_catalog():
        assert REQUIRED_KEYS <= layout.keys()

