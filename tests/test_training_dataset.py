import json
from pathlib import Path

from PIL import Image

from detail_page_ai.training_dataset import build_training_dataset


def _write_image(path: Path, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (32, 24), color).save(path)


def test_build_training_dataset_copies_approved_assets_and_caption_sidecars(tmp_path: Path):
    source = tmp_path / "source" / "product.png"
    _write_image(source, (12, 34, 56))
    output = tmp_path / "dataset"
    manifest = {
        "dataset_id": "pilot",
        "dataset_version": "0.1.0",
        "products": [
            {
                "product_id": "p-001",
                "product_type": "metal object",
                "split": "train",
                "assets": [
                    {
                        "asset_id": "hero",
                        "path": "source/product.png",
                        "role": "preserve_original",
                        "asset_mode": "source",
                        "fidelity_status": "VERIFIED",
                        "human_approved": True,
                        "caption": "exact supplied product on a clean background",
                        "negative_prompt": "changed product shape",
                    }
                ],
            }
        ],
    }

    summary = build_training_dataset(manifest, output, project_root=tmp_path)

    assert summary.train_count == 1
    record = json.loads((output / "train" / "metadata.jsonl").read_text().splitlines()[0])
    copied = output / record["image"]
    assert copied.read_bytes() == source.read_bytes()
    assert record["product_id"] == "p-001"
    assert record["role"] == "preserve_original"
    assert record["asset_sha256"] == record["source_sha256"]
    assert (copied.with_suffix(".txt")).read_text() == record["caption"]


def test_unapproved_generated_asset_is_kept_as_candidate_not_training_data(tmp_path: Path):
    source = tmp_path / "generated.png"
    _write_image(source, (90, 80, 70))
    output = tmp_path / "dataset"
    manifest = {
        "dataset_id": "pilot",
        "dataset_version": "0.1.0",
        "products": [
            {
                "product_id": "p-002",
                "product_type": "textile",
                "split": "train",
                "assets": [
                    {
                        "asset_id": "scene-01",
                        "path": "generated.png",
                        "role": "generated_scene",
                        "asset_mode": "generated_scene",
                        "fidelity_status": "GENERATED",
                        "human_approved": False,
                        "caption": "exact supplied textile in a real usage scene",
                        "negative_prompt": "changed pattern",
                    }
                ],
            }
        ],
    }

    summary = build_training_dataset(manifest, output, project_root=tmp_path)

    assert summary.train_count == 0
    assert summary.candidate_count == 1
    assert not (output / "train" / "metadata.jsonl").exists()
    candidate = json.loads(
        (output / "candidates" / "metadata.jsonl").read_text().splitlines()[0]
    )
    assert candidate["training_eligible"] is False
    assert candidate["fidelity_status"] == "GENERATED"
    assert (output / candidate["image"]).is_file()


def test_approved_synthetic_composite_requires_automated_invariant_check(tmp_path: Path):
    source = tmp_path / "synthetic.png"
    _write_image(source, (120, 110, 100))
    output = tmp_path / "dataset"
    base_asset = {
        "asset_id": "scene-01",
        "path": "synthetic.png",
        "source_path": "synthetic.png",
        "role": "generated_scene",
        "asset_mode": "synthetic_composite",
        "fidelity_status": "SYNTHETIC",
        "human_approved": False,
        "approved_for_training": True,
        "caption": "the supplied product in an editorial scene",
        "negative_prompt": "changed product",
    }
    manifest = {
        "dataset_id": "pilot",
        "dataset_version": "0.2.0",
        "products": [
            {
                "product_id": "p-005",
                "product_type": "object",
                "split": "train",
                "assets": [base_asset],
            }
        ],
    }

    summary = build_training_dataset(manifest, output, project_root=tmp_path)

    assert summary.train_count == 0
    assert summary.candidate_count == 1

    base_asset["automated_invariant_check"] = True
    output = tmp_path / "dataset-approved"
    summary = build_training_dataset(manifest, output, project_root=tmp_path)

    assert summary.train_count == 1
    record = json.loads((output / "train" / "metadata.jsonl").read_text().splitlines()[0])
    assert record["fidelity_status"] == "SYNTHETIC"
    assert record["human_approved"] is False
    assert record["approved_for_training"] is True
    assert record["automated_invariant_check"] is True


def test_rejected_asset_is_not_promoted_to_candidate_or_training(tmp_path: Path):
    source = tmp_path / "rejected.png"
    _write_image(source, (1, 2, 3))
    output = tmp_path / "dataset"
    manifest = {
        "dataset_id": "pilot",
        "dataset_version": "0.1.0",
        "products": [
            {
                "product_id": "p-003",
                "product_type": "object",
                "split": "val",
                "assets": [
                    {
                        "asset_id": "bad-01",
                        "path": "rejected.png",
                        "role": "generated_view",
                        "asset_mode": "generated_view",
                        "fidelity_status": "REJECTED",
                        "human_approved": False,
                        "caption": "must not be trained",
                        "negative_prompt": "distortion",
                        "rejection_reason": "product silhouette changed",
                    }
                ],
            }
        ],
    }

    summary = build_training_dataset(manifest, output, project_root=tmp_path)

    assert summary.train_count == 0
    assert summary.val_count == 0
    assert summary.rejected_count == 1
    record = json.loads(
        (output / "rejected" / "metadata.jsonl").read_text().splitlines()[0]
    )
    assert record["rejection_reason"] == "product silhouette changed"
    assert (output / record["image"]).is_file()


def test_product_cannot_be_split_between_train_and_val(tmp_path: Path):
    source = tmp_path / "source.png"
    _write_image(source, (3, 4, 5))
    manifest = {
        "dataset_id": "pilot",
        "dataset_version": "0.1.0",
        "products": [
            {
                "product_id": "p-004",
                "product_type": "object",
                "split": "train",
                "assets": [
                    {
                        "asset_id": "train-01",
                        "path": "source.png",
                        "role": "preserve_original",
                        "asset_mode": "source",
                        "fidelity_status": "SOURCE",
                        "human_approved": True,
                        "caption": "product",
                        "negative_prompt": "distortion",
                    }
                ],
            },
            {
                "product_id": "p-004",
                "product_type": "object",
                "split": "val",
                "assets": [],
            },
        ],
    }

    try:
        build_training_dataset(manifest, tmp_path / "dataset", project_root=tmp_path)
    except ValueError as error:
        assert "multiple splits" in str(error)
    else:
        raise AssertionError("expected a product split validation error")
