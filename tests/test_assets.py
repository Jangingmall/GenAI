import hashlib

import pytest

from detail_page_ai.assets import LocalFileAssetStore, MemoryAssetStore


def test_memory_store_deduplicates_content_and_preserves_metadata():
    store = MemoryAssetStore()

    first = store.put(b"same", "image/png", "source")
    second = store.put(b"same", "image/png", "result")

    assert first.asset_id == hashlib.sha256(b"same").hexdigest()
    assert second.asset_id == first.asset_id
    assert store.get(first.asset_id) == b"same"
    assert first.size == 4
    assert first.mime_type == "image/png"


def test_local_store_deduplicates_same_bytes_after_reopen(tmp_path):
    first_store = LocalFileAssetStore(tmp_path)
    first = first_store.put(b"same", "image/png", "source")

    second_store = LocalFileAssetStore(tmp_path)
    second = second_store.put(b"same", "image/png", "source")

    assert first.asset_id == second.asset_id
    assert second_store.exists(first.asset_id)
    assert second_store.get(first.asset_id) == b"same"
    assert second_store.get_record(first.asset_id).location == second.location


def test_asset_id_cannot_escape_store(tmp_path):
    store = LocalFileAssetStore(tmp_path)

    with pytest.raises(KeyError):
        store.get("../secret")


def test_local_store_rejects_unsafe_category(tmp_path):
    store = LocalFileAssetStore(tmp_path)

    with pytest.raises(ValueError, match="category"):
        store.put(b"data", "image/png", "../outside")
