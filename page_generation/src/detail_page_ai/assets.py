import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path


_ASSET_ID = re.compile(r"^[0-9a-f]{64}$")
_CATEGORY = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")
_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "application/json": "json",
}


@dataclass(frozen=True, slots=True)
class StoredAsset:
    asset_id: str
    mime_type: str
    size: int
    sha256: str
    category: str
    location: str
    url: str | None = None


def _asset_id(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_asset_id(asset_id: str) -> None:
    if not _ASSET_ID.fullmatch(asset_id):
        raise KeyError(asset_id)


def _validate_category(category: str) -> None:
    if not _CATEGORY.fullmatch(category):
        raise ValueError("category must be a safe lowercase identifier")


class MemoryAssetStore:
    def __init__(self):
        self._data: dict[str, bytes] = {}
        self._records: dict[str, StoredAsset] = {}

    def put(self, data: bytes, mime_type: str, category: str) -> StoredAsset:
        if not data:
            raise ValueError("asset data must not be empty")
        _validate_category(category)
        asset_id = _asset_id(data)
        existing = self._records.get(asset_id)
        if existing is not None:
            return existing
        record = StoredAsset(
            asset_id=asset_id,
            mime_type=mime_type,
            size=len(data),
            sha256=asset_id,
            category=category,
            location=f"memory:{asset_id}",
        )
        self._data[asset_id] = bytes(data)
        self._records[asset_id] = record
        return record

    def get(self, asset_id: str) -> bytes:
        _validate_asset_id(asset_id)
        try:
            return self._data[asset_id]
        except KeyError as exc:
            raise KeyError(asset_id) from exc

    def get_record(self, asset_id: str) -> StoredAsset:
        _validate_asset_id(asset_id)
        try:
            return self._records[asset_id]
        except KeyError as exc:
            raise KeyError(asset_id) from exc

    def exists(self, asset_id: str) -> bool:
        try:
            _validate_asset_id(asset_id)
        except KeyError:
            return False
        return asset_id in self._data


class LocalFileAssetStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.objects_dir = self.root / "objects"
        self.metadata_dir = self.root / "metadata"
        self.objects_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)

    def put(self, data: bytes, mime_type: str, category: str) -> StoredAsset:
        if not data:
            raise ValueError("asset data must not be empty")
        _validate_category(category)
        asset_id = _asset_id(data)
        if self.exists(asset_id):
            return self.get_record(asset_id)

        extension = _EXTENSIONS.get(mime_type, "bin")
        object_dir = self.objects_dir / asset_id[:2]
        object_dir.mkdir(parents=True, exist_ok=True)
        object_path = object_dir / f"{asset_id}.{extension}"
        self._atomic_write(object_path, data)
        record = StoredAsset(
            asset_id=asset_id,
            mime_type=mime_type,
            size=len(data),
            sha256=asset_id,
            category=category,
            location=str(object_path),
        )
        metadata = json.dumps(asdict(record), ensure_ascii=False, sort_keys=True).encode(
            "utf-8"
        )
        self._atomic_write(self._metadata_path(asset_id), metadata)
        return record

    def get(self, asset_id: str) -> bytes:
        record = self.get_record(asset_id)
        path = Path(record.location).resolve()
        if self.root not in path.parents:
            raise KeyError(asset_id)
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise KeyError(asset_id) from exc
        if _asset_id(data) != asset_id:
            raise ValueError(f"Stored asset checksum mismatch: {asset_id}")
        return data

    def get_record(self, asset_id: str) -> StoredAsset:
        _validate_asset_id(asset_id)
        try:
            payload = json.loads(self._metadata_path(asset_id).read_text(encoding="utf-8"))
            record = StoredAsset(**payload)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise KeyError(asset_id) from exc
        if record.asset_id != asset_id or record.sha256 != asset_id:
            raise ValueError(f"Stored asset metadata checksum mismatch: {asset_id}")
        return record

    def exists(self, asset_id: str) -> bool:
        try:
            _validate_asset_id(asset_id)
        except KeyError:
            return False
        return self._metadata_path(asset_id).is_file()

    def _metadata_path(self, asset_id: str) -> Path:
        return self.metadata_dir / f"{asset_id}.json"

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary_path = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
