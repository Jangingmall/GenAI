"""Build a provenance-aware image/caption dataset for image-model fine-tuning.

The builder is intentionally conservative: source images can enter train/val when
they are explicitly approved, model-generated images stay in ``candidates`` until
human review, and deterministic source-preserving composites require an explicit
automated invariant check before entering train/val.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "flux-image-caption-v1"
TRAINING_FIDELITY = {"SOURCE", "VERIFIED"}
VALID_SPLITS = {"train", "val"}
VALID_BUCKETS = ("train", "val", "candidates", "rejected")


@dataclass(frozen=True)
class DatasetBuildSummary:
    """Counts and location of one dataset build."""

    output_dir: Path
    train_count: int
    val_count: int
    candidate_count: int
    rejected_count: int
    product_splits: dict[str, str]

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["output_dir"] = str(self.output_dir)
        return data


def build_training_dataset(
    manifest: Mapping[str, Any] | Path,
    output_dir: Path,
    *,
    project_root: Path,
) -> DatasetBuildSummary:
    """Copy curated assets and write trainer-friendly metadata.

    ``manifest`` is deliberately explicit.  It records the source path, the
    intended communication role, and whether a human approved a generated asset.
    This prevents a previous model's hallucinated product details from silently
    becoming fine-tuning ground truth.
    """

    manifest_data = _load_manifest(manifest)
    dataset_id = _required_text(manifest_data, "dataset_id")
    dataset_version = _required_text(manifest_data, "dataset_version")
    root = project_root.resolve()
    destination = output_dir.resolve()
    destination.mkdir(parents=True, exist_ok=True)

    products = manifest_data.get("products")
    if not isinstance(products, list):
        raise ValueError("manifest.products must be a list")

    product_splits: dict[str, str] = {}
    records: dict[str, list[dict[str, Any]]] = {bucket: [] for bucket in VALID_BUCKETS}

    for product in products:
        if not isinstance(product, Mapping):
            raise ValueError("each product entry must be an object")
        product_id = _required_text(product, "product_id")
        product_type = _required_text(product, "product_type")
        split = _required_text(product, "split")
        if split not in VALID_SPLITS:
            raise ValueError(f"unsupported split for {product_id}: {split}")
        previous_split = product_splits.setdefault(product_id, split)
        if previous_split != split:
            raise ValueError(f"product {product_id} appears in multiple splits")

        assets = product.get("assets")
        if not isinstance(assets, list):
            raise ValueError(f"assets must be a list for {product_id}")
        for asset in assets:
            if not isinstance(asset, Mapping):
                raise ValueError(f"each asset entry must be an object for {product_id}")
            record, bucket = _prepare_record(
                product=product,
                product_id=product_id,
                product_type=product_type,
                split=split,
                asset=asset,
                project_root=root,
                output_dir=destination,
                dataset_id=dataset_id,
                dataset_version=dataset_version,
            )
            records[bucket].append(record)

    for bucket, bucket_records in records.items():
        _write_bucket(destination, bucket, bucket_records)

    summary = DatasetBuildSummary(
        output_dir=destination,
        train_count=len(records["train"]),
        val_count=len(records["val"]),
        candidate_count=len(records["candidates"]),
        rejected_count=len(records["rejected"]),
        product_splits=product_splits,
    )
    _write_json(destination / "dataset_summary.json", {
        "schema_version": SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "counts": {
            "train": summary.train_count,
            "val": summary.val_count,
            "candidates": summary.candidate_count,
            "rejected": summary.rejected_count,
        },
        "product_splits": product_splits,
        "source_policy": {
            "generated_assets_require_human_approval": True,
            "synthetic_assets_require_automated_invariant_check": True,
            "rejected_assets_are_never_training_data": True,
            "product_level_split": True,
        },
    })
    _write_dataset_card(
        destination,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        summary=summary,
    )
    return summary


def _prepare_record(
    *,
    product: Mapping[str, Any],
    product_id: str,
    product_type: str,
    split: str,
    asset: Mapping[str, Any],
    project_root: Path,
    output_dir: Path,
    dataset_id: str,
    dataset_version: str,
) -> tuple[dict[str, Any], str]:
    asset_id = _required_text(asset, "asset_id")
    relative_source = _required_text(asset, "path")
    role = _required_text(asset, "role")
    asset_mode = _required_text(asset, "asset_mode")
    fidelity_status = _required_text(asset, "fidelity_status")
    caption = _required_text(asset, "caption")
    negative_prompt = _required_text(asset, "negative_prompt")
    source_path = _required_text(asset, "source_path", default=relative_source)

    source_file = _safe_source_path(project_root, relative_source)
    source_hash = _sha256(source_file)
    source_origin_file = _safe_source_path(project_root, source_path)
    origin_hash = _sha256(source_origin_file)

    if fidelity_status == "REJECTED":
        bucket = "rejected"
    elif _is_training_eligible(asset, fidelity_status):
        bucket = split
    else:
        bucket = "candidates"

    filename = f"{_slug(product_id)}__{_slug(asset_id)}{source_file.suffix.lower()}"
    image_destination = output_dir / bucket / "images" / filename
    image_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_file, image_destination)
    sidecar = image_destination.with_suffix(".txt")
    sidecar.write_text(caption, encoding="utf-8")

    relative_image = image_destination.relative_to(output_dir).as_posix()
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "id": f"{_slug(product_id)}__{_slug(asset_id)}",
        "image": relative_image,
        "text": caption,
        "caption": caption,
        "negative_prompt": negative_prompt,
        "product_id": product_id,
        "product_type": product_type,
        "role": role,
        "split": split if bucket in VALID_SPLITS else None,
        "asset_mode": asset_mode,
        "fidelity_status": fidelity_status,
        "training_eligible": bucket in VALID_SPLITS,
        "human_approved": bool(asset.get("human_approved", False)),
        "approved_for_training": bool(asset.get("approved_for_training", False)),
        "automated_invariant_check": bool(asset.get("automated_invariant_check", False)),
        "source_image": source_path,
        "source_sha256": origin_hash,
        "asset_sha256": source_hash,
        "source_path": relative_source,
        "rejection_reason": asset.get("rejection_reason"),
        "model": asset.get("model"),
        "prompt_version": asset.get("prompt_version"),
        "notes": asset.get("notes"),
    }
    return record, bucket


def _is_training_eligible(asset: Mapping[str, Any], fidelity_status: str) -> bool:
    if fidelity_status == "SYNTHETIC":
        return bool(asset.get("approved_for_training", False)) and bool(
            asset.get("automated_invariant_check", False)
        )
    if not bool(asset.get("human_approved", False)):
        return False
    if fidelity_status in TRAINING_FIDELITY:
        return True
    return fidelity_status == "GENERATED" and bool(asset.get("approved_for_training", False))


def _write_bucket(output_dir: Path, bucket: str, records: list[dict[str, Any]]) -> None:
    if not records:
        return
    records.sort(key=lambda item: item["id"])
    _write_jsonl(output_dir / bucket / "metadata.jsonl", records)


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records
    )
    path.write_text(content, encoding="utf-8")


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_dataset_card(
    output_dir: Path,
    *,
    dataset_id: str,
    dataset_version: str,
    summary: DatasetBuildSummary,
) -> None:
    split_lines = "\n".join(
        f"- `{product_id}` → `{split}`" for product_id, split in sorted(summary.product_splits.items())
    ) or "- 없음"
    card = f"""# {dataset_id}

버전: `{dataset_version}`  
스키마: `{SCHEMA_VERSION}`

## 목적

현재 상세페이지 이미지 생성 파이프라인의 제품 보존, 제품별 배경, 실사용 장면,
구도 변형 프롬프트를 학습·평가하기 위한 파일럿 데이터셋입니다.

## 구성

- `train/`: 검수 정책을 통과한 학습 가능 이미지와 caption sidecar (`.txt`)
- `val/`: 제품 단위로 분리한 검증 이미지
- `candidates/`: 생성 결과 중 아직 학습 정답으로 승인하지 않은 후보
- `rejected/`: 제품 형태·색·무늬·구성품이 바뀌어 학습에서 제외한 이미지
- 각 bucket의 `metadata.jsonl`: `image`, `caption`, `negative_prompt`와 provenance

## 제품 단위 분할

{split_lines}

## 현재 카운트

- train: `{summary.train_count}`
- val: `{summary.val_count}`
- candidates: `{summary.candidate_count}`
- rejected: `{summary.rejected_count}`

## 검수 정책

1. 원본 픽셀과 제품의 형태·색·무늬·구성품을 확인하지 못한 이미지는 `train`에 넣지 않습니다.
2. `GENERATED` 자산은 `human_approved=true`와 `approved_for_training=true`가 모두 있어야 합니다.
3. `SYNTHETIC` 자산은 자동 보존 불변식 검사와 `approved_for_training=true`가 모두 있어야 합니다.
4. 생성 이미지의 연출·배경은 학습 가능하지만, 환각된 제품 세부는 정답으로 취급하지 않습니다.
5. 같은 제품의 이미지는 `train`과 `val`에 나누지 않아 데이터 누수를 막습니다.
6. 상품의 브랜드·제작자·원산지·정확한 소재·성능·인증은 이미지 caption에 사실처럼 쓰지 않습니다.

## 사용 방법

학습 프레임워크에서는 `train/metadata.jsonl`의 `image` 경로와 `caption`을 사용하고,
검증에는 `val/metadata.jsonl`을 사용합니다. `candidates`는 사람 검수 후 manifest에서
승격하여 데이터셋을 다시 생성합니다. `4-bit MLX 서빙 체크포인트`는 추론 검증용으로
분리하고, 실제 LoRA 학습은 학습을 지원하는 원본/학습용 체크포인트에 연결해야 합니다.
"""
    (output_dir / "dataset-card.md").write_text(card, encoding="utf-8")


def _load_manifest(manifest: Mapping[str, Any] | Path) -> Mapping[str, Any]:
    if isinstance(manifest, Path):
        return json.loads(manifest.read_text(encoding="utf-8"))
    return manifest


def _required_text(
    value: Mapping[str, Any], key: str, *, default: str | None = None
) -> str:
    candidate = value.get(key, default)
    if not isinstance(candidate, str) or not candidate.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return candidate.strip()


def _safe_source_path(project_root: Path, relative_path: str) -> Path:
    candidate = (project_root / relative_path).resolve()
    try:
        candidate.relative_to(project_root)
    except ValueError as error:
        raise ValueError(f"asset path escapes project root: {relative_path}") from error
    if not candidate.is_file():
        raise FileNotFoundError(f"asset file does not exist: {relative_path}")
    return candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug or "asset"


__all__ = ["DatasetBuildSummary", "SCHEMA_VERSION", "build_training_dataset"]
