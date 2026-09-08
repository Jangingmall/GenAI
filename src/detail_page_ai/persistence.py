import base64
import copy
import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Literal, Protocol

from .dto import (
    AiBePersistAck,
    AiBeProductPersistRequest,
    AiFeDraftResultDto,
    AiFeResultDto,
    ErrorDto,
    GenerationOptions,
    ProductProfileDto,
    UserHintsDto,
)
from .models import (
    GeneratedImage,
    GeneratedSection,
    PhotoTransform,
    ProductPhoto,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class LeaseOwnershipError(RuntimeError):
    """Raised when a stale or unclaimed worker tries to commit state."""


def _encode_bytes(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _decode_bytes(data: str) -> bytes:
    return base64.b64decode(data.encode("ascii"), validate=True)


@dataclass(slots=True)
class JobRecord:
    job_id: str
    request_id: str
    source_image: bytes
    source_mime_type: str
    options: GenerationOptions
    product_id: str | None = None
    source_asset_id: str | None = None
    user_hints: UserHintsDto = field(default_factory=UserHintsDto)
    generation_id: str | None = None
    additional_source_images: tuple[tuple[bytes, str], ...] = ()
    status: str = "QUEUED"
    progress: int = 0
    draft: AiFeDraftResultDto | None = None
    draft_profile: ProductProfileDto | None = None
    result: AiFeResultDto | None = None
    idempotency_key: str | None = None
    request_fingerprint: str | None = None
    approval_idempotency_key: str | None = None
    approval_fingerprint: str | None = None
    approval_be_ack: AiBePersistAck | None = None
    approval_backend_delivery_pending: bool = False
    approval_warning: str | None = None
    error: ErrorDto | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)


class JobRepository(Protocol):
    def create(self, record: JobRecord) -> None:
        ...

    def save(
        self,
        record: JobRecord,
        worker_id: str | None = None,
        lease_seconds: int = 300,
    ) -> None:
        ...

    def get(self, job_id: str) -> JobRecord:
        ...

    def find_by_idempotency(
        self, product_id: str | None, idempotency_key: str
    ) -> JobRecord | None:
        ...

    def count_active(self) -> int:
        ...

    def recover_interrupted(self) -> list[str]:
        ...

    def claim_recoverable(
        self, worker_id: str, lease_seconds: int = 300
    ) -> list[str]:
        ...

    def claim(
        self, job_id: str, worker_id: str, lease_seconds: int = 300
    ) -> JobRecord | None:
        ...

    def renew_lease(
        self, job_id: str, worker_id: str, lease_seconds: int = 300
    ) -> bool:
        ...


def _serialize_job(record: JobRecord) -> str:
    payload = {
        "job_id": record.job_id,
        "request_id": record.request_id,
        "generation_id": record.generation_id,
        "product_id": record.product_id,
        "source_asset_id": record.source_asset_id,
        "source_image": _encode_bytes(record.source_image),
        "source_mime_type": record.source_mime_type,
        "options": record.options.model_dump(mode="json"),
        "user_hints": record.user_hints.model_dump(mode="json"),
        "additional_source_images": [
            {"data": _encode_bytes(data), "mime_type": mime_type}
            for data, mime_type in record.additional_source_images
        ],
        "status": record.status,
        "progress": record.progress,
        "draft": record.draft.model_dump(mode="json") if record.draft else None,
        "draft_profile": record.draft_profile.model_dump(mode="json") if record.draft_profile else None,
        "result": record.result.model_dump(mode="json") if record.result else None,
        "idempotency_key": record.idempotency_key,
        "request_fingerprint": record.request_fingerprint,
        "approval_idempotency_key": record.approval_idempotency_key,
        "approval_fingerprint": record.approval_fingerprint,
        "approval_be_ack": record.approval_be_ack.model_dump(mode="json") if record.approval_be_ack else None,
        "approval_backend_delivery_pending": record.approval_backend_delivery_pending,
        "approval_warning": record.approval_warning,
        "error": record.error.model_dump(mode="json") if record.error else None,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _deserialize_job(value: str) -> JobRecord:
    payload = json.loads(value)
    return JobRecord(
        job_id=payload["job_id"],
        request_id=payload["request_id"],
        generation_id=payload.get("generation_id"),
        product_id=payload.get("product_id"),
        source_asset_id=payload.get("source_asset_id"),
        source_image=_decode_bytes(payload["source_image"]),
        source_mime_type=payload["source_mime_type"],
        options=GenerationOptions.model_validate(payload["options"]),
        user_hints=UserHintsDto.model_validate(payload.get("user_hints", {})),
        additional_source_images=tuple(
            (_decode_bytes(item["data"]), item["mime_type"])
            for item in payload.get("additional_source_images", [])
        ),
        status=payload["status"],
        progress=int(payload["progress"]),
        result=(
            AiFeResultDto.model_validate(payload["result"])
            if payload.get("result") is not None
            else None
        ),
        draft=(
            AiFeDraftResultDto.model_validate(payload["draft"])
            if payload.get("draft") is not None
            else None
        ),
        draft_profile=(
            ProductProfileDto.model_validate(payload["draft_profile"])
            if payload.get("draft_profile") is not None
            else None
        ),
        idempotency_key=payload.get("idempotency_key"),
        request_fingerprint=payload.get("request_fingerprint"),
        approval_idempotency_key=payload.get("approval_idempotency_key"),
        approval_fingerprint=payload.get("approval_fingerprint"),
        approval_be_ack=(
            AiBePersistAck.model_validate(payload["approval_be_ack"])
            if payload.get("approval_be_ack") is not None
            else None
        ),
        approval_backend_delivery_pending=bool(payload.get("approval_backend_delivery_pending", False)),
        approval_warning=payload.get("approval_warning"),
        error=(
            ErrorDto.model_validate(payload["error"])
            if payload.get("error") is not None
            else None
        ),
        created_at=datetime.fromisoformat(payload["created_at"]),
        updated_at=datetime.fromisoformat(payload["updated_at"]),
    )


class MemoryJobRepository:
    def __init__(self):
        self._records: dict[str, JobRecord] = {}
        self._claimed: dict[str, str] = {}
        self._lock = Lock()

    def create(self, record: JobRecord) -> None:
        with self._lock:
            if record.job_id in self._records:
                raise ValueError(f"Job already exists: {record.job_id}")
            self._records[record.job_id] = copy.deepcopy(record)

    def save(
        self,
        record: JobRecord,
        worker_id: str | None = None,
        lease_seconds: int = 300,
    ) -> None:
        del lease_seconds
        with self._lock:
            if record.job_id not in self._records:
                raise KeyError(record.job_id)
            owner = self._claimed.get(record.job_id)
            if owner != worker_id:
                raise LeaseOwnershipError(record.job_id)
            self._records[record.job_id] = copy.deepcopy(record)
            if record.status in {"COMPLETED", "FAILED", "DRAFT_READY"}:
                self._claimed.pop(record.job_id, None)

    def get(self, job_id: str) -> JobRecord:
        with self._lock:
            try:
                return copy.deepcopy(self._records[job_id])
            except KeyError as exc:
                raise KeyError(job_id) from exc

    def find_by_idempotency(
        self, product_id: str | None, idempotency_key: str
    ) -> JobRecord | None:
        with self._lock:
            for record in self._records.values():
                if (
                    record.product_id == product_id
                    and record.idempotency_key == idempotency_key
                ):
                    return copy.deepcopy(record)
        return None

    def count_active(self) -> int:
        with self._lock:
            return sum(
                record.status not in {"COMPLETED", "FAILED", "DRAFT_READY"}
                for record in self._records.values()
            )

    def recover_interrupted(self) -> list[str]:
        return self.claim_recoverable(f"recovery-{uuid.uuid4()}")

    def claim_recoverable(self, worker_id: str, lease_seconds: int = 300) -> list[str]:
        del lease_seconds
        recoverable = {
            "QUEUED",
            "ANALYZING",
            "EXTRACTING",
            "GENERATING_BACKGROUNDS",
            "COMPOSING",
            "VERIFYING",
            "RENDERING",
            "DELIVERING",
        }
        recovered = []
        with self._lock:
            for record in self._records.values():
                if record.status in recoverable and record.job_id not in self._claimed:
                    record.status = "QUEUED"
                    record.progress = 0
                    record.updated_at = _now()
                    self._claimed[record.job_id] = worker_id
                    recovered.append(record.job_id)
        return sorted(recovered)

    def claim(self, job_id: str, worker_id: str, lease_seconds: int = 300) -> JobRecord | None:
        del lease_seconds
        with self._lock:
            record = self._records.get(job_id)
            if (
                record is None
                or record.status in {"COMPLETED", "FAILED", "DRAFT_READY"}
                or job_id in self._claimed
            ):
                return None
            self._claimed[job_id] = worker_id
            return copy.deepcopy(record)

    def renew_lease(
        self, job_id: str, worker_id: str, lease_seconds: int = 300
    ) -> bool:
        del lease_seconds
        with self._lock:
            return self._claimed.get(job_id) == worker_id


class SQLiteJobRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS detail_page_jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    worker_id TEXT,
                    lease_until TEXT
                )
                """
            )
            self._ensure_column(connection, "detail_page_jobs", "worker_id", "TEXT")
            self._ensure_column(connection, "detail_page_jobs", "lease_until", "TEXT")

    def create(self, record: JobRecord) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO detail_page_jobs(job_id, status, updated_at, payload_json) VALUES (?, ?, ?, ?)",
                    (
                        record.job_id,
                        record.status,
                        record.updated_at.isoformat(),
                        _serialize_job(record),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Job already exists: {record.job_id}") from exc

    def save(
        self,
        record: JobRecord,
        worker_id: str | None = None,
        lease_seconds: int = 300,
    ) -> None:
        now = _now()
        renewed_until = datetime.fromtimestamp(
            now.timestamp() + lease_seconds, tz=timezone.utc
        ).isoformat()
        with self._connect() as connection:
            terminal = record.status in {"COMPLETED", "FAILED", "DRAFT_READY"}
            if worker_id is None:
                cursor = connection.execute(
                    """
                    UPDATE detail_page_jobs
                    SET status = ?, updated_at = ?, payload_json = ?,
                        worker_id = NULL, lease_until = NULL
                    WHERE job_id = ? AND worker_id IS NULL
                    """,
                    (
                        record.status,
                        record.updated_at.isoformat(),
                        _serialize_job(record),
                        record.job_id,
                    ),
                )
            else:
                cursor = connection.execute(
                    """
                    UPDATE detail_page_jobs
                    SET status = ?, updated_at = ?, payload_json = ?,
                        worker_id = CASE WHEN ? THEN NULL ELSE worker_id END,
                        lease_until = CASE WHEN ? THEN NULL ELSE ? END
                    WHERE job_id = ? AND worker_id = ? AND lease_until > ?
                    """,
                    (
                        record.status,
                        record.updated_at.isoformat(),
                        _serialize_job(record),
                        terminal,
                        terminal,
                        renewed_until,
                        record.job_id,
                        worker_id,
                        now.isoformat(),
                    ),
                )
            if cursor.rowcount != 1:
                if self._exists(connection, record.job_id):
                    raise LeaseOwnershipError(record.job_id)
                raise KeyError(record.job_id)

    def get(self, job_id: str) -> JobRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM detail_page_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            raise KeyError(job_id)
        return _deserialize_job(row[0])

    def find_by_idempotency(
        self, product_id: str | None, idempotency_key: str
    ) -> JobRecord | None:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM detail_page_jobs"
            ).fetchall()
        for (payload_json,) in rows:
            record = _deserialize_job(payload_json)
            if (
                record.product_id == product_id
                and record.idempotency_key == idempotency_key
            ):
                return record
        return None

    def count_active(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT COUNT(*) FROM detail_page_jobs
                   WHERE status NOT IN ('COMPLETED', 'FAILED', 'DRAFT_READY')"""
            ).fetchone()
        return int(row[0]) if row else 0

    def recover_interrupted(self) -> list[str]:
        return self.claim_recoverable(f"recovery-{uuid.uuid4()}")

    def claim_recoverable(
        self, worker_id: str, lease_seconds: int = 300
    ) -> list[str]:
        recoverable = (
            "QUEUED",
            "ANALYZING",
            "EXTRACTING",
            "GENERATING_BACKGROUNDS",
            "COMPOSING",
            "VERIFYING",
            "RENDERING",
            "DELIVERING",
        )
        placeholders = ",".join("?" for _ in recoverable)
        now = _now()
        lease_until = datetime.fromtimestamp(
            now.timestamp() + lease_seconds, tz=timezone.utc
        ).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                f"""
                SELECT job_id, payload_json FROM detail_page_jobs
                WHERE status IN ({placeholders})
                  AND (worker_id IS NULL OR lease_until IS NULL OR lease_until <= ?)
                ORDER BY job_id
                """,
                (*recoverable, now.isoformat()),
            ).fetchall()
            recovered = []
            for job_id, payload_json in rows:
                record = _deserialize_job(payload_json)
                record.status = "QUEUED"
                record.progress = 0
                record.updated_at = _now()
                connection.execute(
                    """
                    UPDATE detail_page_jobs
                    SET status = ?, updated_at = ?, payload_json = ?, worker_id = ?, lease_until = ?
                    WHERE job_id = ?
                      AND (worker_id IS NULL OR lease_until IS NULL OR lease_until <= ?)
                    """,
                    (
                        record.status,
                        record.updated_at.isoformat(),
                        _serialize_job(record),
                        worker_id,
                        lease_until,
                        job_id,
                        now.isoformat(),
                    ),
                )
                recovered.append(job_id)
        return recovered

    def claim(
        self, job_id: str, worker_id: str, lease_seconds: int = 300
    ) -> JobRecord | None:
        now = _now()
        lease_until = datetime.fromtimestamp(
            now.timestamp() + lease_seconds, tz=timezone.utc
        ).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE detail_page_jobs
                SET worker_id = ?, lease_until = ?
                WHERE job_id = ? AND status NOT IN ('COMPLETED', 'FAILED', 'DRAFT_READY')
                  AND (
                    worker_id IS NULL OR lease_until IS NULL OR lease_until <= ?
                  )
                """,
                (worker_id, lease_until, job_id, now.isoformat()),
            )
            if cursor.rowcount != 1:
                return None
            row = connection.execute(
                "SELECT payload_json FROM detail_page_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        return _deserialize_job(row[0]) if row else None

    def renew_lease(
        self, job_id: str, worker_id: str, lease_seconds: int = 300
    ) -> bool:
        now = _now()
        lease_until = datetime.fromtimestamp(
            now.timestamp() + lease_seconds, tz=timezone.utc
        ).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE detail_page_jobs SET lease_until = ?
                WHERE job_id = ? AND worker_id = ?
                  AND status NOT IN ('COMPLETED', 'FAILED', 'DRAFT_READY') AND lease_until > ?
                """,
                (lease_until, job_id, worker_id, now.isoformat()),
            )
        return cursor.rowcount == 1

    @staticmethod
    def _exists(connection: sqlite3.Connection, job_id: str) -> bool:
        return (
            connection.execute(
                "SELECT 1 FROM detail_page_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            is not None
        )

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection, table: str, column: str, declaration: str
    ) -> None:
        columns = {
            row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=30)


OutboxStatus = Literal["PENDING", "DELIVERING", "DELIVERED", "FAILED"]


@dataclass(slots=True)
class OutboxRecord:
    generation_id: str
    request: AiBeProductPersistRequest
    image: GeneratedImage
    status: OutboxStatus = "PENDING"
    attempts: int = 0
    last_error: str | None = None
    worker_id: str | None = None
    updated_at: datetime = field(default_factory=_now)


class DeliveryOutbox(Protocol):
    def enqueue(
        self,
        request: AiBeProductPersistRequest,
        image: GeneratedImage,
        error: str,
    ) -> None:
        ...

    def get(self, generation_id: str) -> OutboxRecord:
        ...

    def mark_delivering(self, generation_id: str) -> None:
        ...

    def mark_delivered(self, generation_id: str, worker_id: str) -> None:
        ...

    def mark_failed(self, generation_id: str, error: str, worker_id: str) -> None:
        ...

    def claim(
        self, generation_id: str, worker_id: str, lease_seconds: int = 300
    ) -> OutboxRecord | None:
        ...

    def list_retryable(self) -> list[str]:
        ...

    def renew_lease(
        self, generation_id: str, worker_id: str, lease_seconds: int = 300
    ) -> bool:
        ...

    def seconds_until_retryable(self) -> float | None:
        ...


def _serialize_section(section: GeneratedSection) -> dict:
    return {
        "section_id": section.section_id,
        "order": section.order,
        "label": section.label,
        "data": _encode_bytes(section.data),
        "mime_type": section.mime_type,
        "width": section.width,
        "height": section.height,
    }


def _serialize_photo(photo: ProductPhoto) -> dict:
    payload = asdict(photo)
    payload["data"] = _encode_bytes(photo.data)
    return payload


def _serialize_generated_image(image: GeneratedImage) -> dict:
    return {
        "data": _encode_bytes(image.data),
        "mime_type": image.mime_type,
        "width": image.width,
        "height": image.height,
        "sections": [_serialize_section(section) for section in image.sections],
        "photos": [_serialize_photo(photo) for photo in image.photos],
    }


def _deserialize_generated_image(payload: dict) -> GeneratedImage:
    sections = tuple(
        GeneratedSection(
            section_id=item["section_id"],
            order=int(item["order"]),
            label=item["label"],
            data=_decode_bytes(item["data"]),
            mime_type=item["mime_type"],
            width=item.get("width"),
            height=item.get("height"),
        )
        for item in payload.get("sections", [])
    )
    photos = []
    for item in payload.get("photos", []):
        photo_payload = dict(item)
        photo_payload["data"] = _decode_bytes(photo_payload["data"])
        transform_payload = photo_payload.pop("transform", {})
        crop = transform_payload.get("crop")
        photo_payload["transform"] = PhotoTransform(
            scale=float(transform_payload.get("scale", 1.0)),
            x=int(transform_payload.get("x", 0)),
            y=int(transform_payload.get("y", 0)),
            crop=tuple(crop) if crop is not None else None,
        )
        photos.append(ProductPhoto(**photo_payload))
    return GeneratedImage(
        data=_decode_bytes(payload["data"]),
        mime_type=payload["mime_type"],
        width=payload.get("width"),
        height=payload.get("height"),
        sections=sections,
        photos=tuple(photos),
    )


def _serialize_outbox_payload(
    request: AiBeProductPersistRequest, image: GeneratedImage
) -> str:
    return json.dumps(
        {
            "request": request.model_dump(mode="json"),
            "image": _serialize_generated_image(image),
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _deserialize_outbox_row(row: tuple) -> OutboxRecord:
    generation_id, status, attempts, last_error, updated_at, payload_json, worker_id = row
    payload = json.loads(payload_json)
    return OutboxRecord(
        generation_id=generation_id,
        request=AiBeProductPersistRequest.model_validate(payload["request"]),
        image=_deserialize_generated_image(payload["image"]),
        status=status,
        attempts=int(attempts),
        last_error=last_error,
        worker_id=worker_id,
        updated_at=datetime.fromisoformat(updated_at),
    )


class MemoryDeliveryOutbox:
    def __init__(self):
        self._records: dict[str, OutboxRecord] = {}
        self._lock = Lock()

    def enqueue(self, request, image, error: str) -> None:
        with self._lock:
            if request.generation_id in self._records:
                return
            self._records[request.generation_id] = OutboxRecord(
                generation_id=request.generation_id,
                request=copy.deepcopy(request),
                image=copy.deepcopy(image),
                status="PENDING",
                attempts=0,
                last_error=error,
            )

    def get(self, generation_id: str) -> OutboxRecord:
        with self._lock:
            try:
                return copy.deepcopy(self._records[generation_id])
            except KeyError as exc:
                raise KeyError(generation_id) from exc

    def mark_delivering(self, generation_id: str) -> None:
        if self.claim(generation_id, "legacy-worker") is None:
            raise KeyError(generation_id)

    def claim(
        self, generation_id: str, worker_id: str, lease_seconds: int = 300
    ) -> OutboxRecord | None:
        del lease_seconds
        with self._lock:
            record = self._records.get(generation_id)
            if record is None or record.status not in {"PENDING", "FAILED"}:
                return None
            record.status = "DELIVERING"
            record.attempts += 1
            record.worker_id = worker_id
            record.updated_at = _now()
            return copy.deepcopy(record)

    def list_retryable(self) -> list[str]:
        with self._lock:
            return sorted(
                generation_id
                for generation_id, record in self._records.items()
                if record.status in {"PENDING", "FAILED"}
            )

    def mark_delivered(self, generation_id: str, worker_id: str) -> None:
        with self._lock:
            record = self._required(generation_id)
            if record.status != "DELIVERING" or record.worker_id != worker_id:
                raise LeaseOwnershipError(generation_id)
            record.status = "DELIVERED"
            record.last_error = None
            record.worker_id = None
            record.updated_at = _now()

    def mark_failed(self, generation_id: str, error: str, worker_id: str) -> None:
        with self._lock:
            record = self._required(generation_id)
            if record.status != "DELIVERING" or record.worker_id != worker_id:
                raise LeaseOwnershipError(generation_id)
            record.status = "FAILED"
            record.last_error = error
            record.worker_id = None
            record.updated_at = _now()

    def renew_lease(
        self, generation_id: str, worker_id: str, lease_seconds: int = 300
    ) -> bool:
        del lease_seconds
        with self._lock:
            record = self._records.get(generation_id)
            return bool(
                record
                and record.status == "DELIVERING"
                and record.worker_id == worker_id
            )

    def seconds_until_retryable(self) -> float | None:
        return None

    def _required(self, generation_id: str) -> OutboxRecord:
        try:
            return self._records[generation_id]
        except KeyError as exc:
            raise KeyError(generation_id) from exc


class SQLiteDeliveryOutbox:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS delivery_outbox (
                    generation_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL,
                    last_error TEXT,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    worker_id TEXT,
                    lease_until TEXT
                )
                """
            )
            self._ensure_column(connection, "delivery_outbox", "worker_id", "TEXT")
            self._ensure_column(connection, "delivery_outbox", "lease_until", "TEXT")

    def enqueue(self, request, image, error: str) -> None:
        now = _now().isoformat()
        payload = _serialize_outbox_payload(request, image)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO delivery_outbox(
                    generation_id, status, attempts, last_error, updated_at, payload_json
                ) VALUES (?, 'PENDING', 0, ?, ?, ?)
                ON CONFLICT(generation_id) DO NOTHING
                """,
                (request.generation_id, error, now, payload),
            )

    def get(self, generation_id: str) -> OutboxRecord:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT generation_id, status, attempts, last_error, updated_at, payload_json
                     , worker_id
                FROM delivery_outbox WHERE generation_id = ?
                """,
                (generation_id,),
            ).fetchone()
        if row is None:
            raise KeyError(generation_id)
        return _deserialize_outbox_row(row)

    def mark_delivering(self, generation_id: str) -> None:
        if self.claim(generation_id, "legacy-worker") is None:
            raise KeyError(generation_id)

    def claim(
        self, generation_id: str, worker_id: str, lease_seconds: int = 300
    ) -> OutboxRecord | None:
        now = _now()
        lease_until = datetime.fromtimestamp(
            now.timestamp() + lease_seconds, tz=timezone.utc
        ).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE delivery_outbox
                SET status = 'DELIVERING', attempts = attempts + 1,
                    worker_id = ?, lease_until = ?, updated_at = ?
                WHERE generation_id = ?
                  AND (
                    status IN ('PENDING', 'FAILED')
                    OR (
                      status = 'DELIVERING'
                      AND (worker_id IS NULL OR lease_until IS NULL OR lease_until <= ?)
                    )
                  )
                """,
                (
                    worker_id,
                    lease_until,
                    now.isoformat(),
                    generation_id,
                    now.isoformat(),
                ),
            )
            if cursor.rowcount != 1:
                return None
            row = connection.execute(
                """
                SELECT generation_id, status, attempts, last_error, updated_at, payload_json
                     , worker_id
                FROM delivery_outbox WHERE generation_id = ?
                """,
                (generation_id,),
            ).fetchone()
        return _deserialize_outbox_row(row) if row else None

    def list_retryable(self) -> list[str]:
        now = _now().isoformat()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT generation_id FROM delivery_outbox
                WHERE status IN ('PENDING', 'FAILED')
                   OR (
                     status = 'DELIVERING'
                     AND (worker_id IS NULL OR lease_until IS NULL OR lease_until <= ?)
                   )
                ORDER BY generation_id
                """,
                (now,),
            ).fetchall()
        return [row[0] for row in rows]

    def mark_delivered(self, generation_id: str, worker_id: str) -> None:
        self._update(
            generation_id,
            "DELIVERED",
            clear_error=True,
            worker_id=worker_id,
        )

    def mark_failed(self, generation_id: str, error: str, worker_id: str) -> None:
        now = _now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE delivery_outbox
                SET status = 'FAILED', last_error = ?, updated_at = ?,
                    worker_id = NULL, lease_until = NULL
                WHERE generation_id = ? AND status = 'DELIVERING'
                  AND worker_id = ? AND lease_until > ?
                """,
                (
                    error,
                    now.isoformat(),
                    generation_id,
                    worker_id,
                    now.isoformat(),
                ),
            )
            if cursor.rowcount != 1:
                if self._exists(connection, generation_id):
                    raise LeaseOwnershipError(generation_id)
                raise KeyError(generation_id)

    def _update(
        self,
        generation_id: str,
        status: OutboxStatus,
        *,
        clear_error: bool,
        worker_id: str,
    ) -> None:
        error_sql = "NULL" if clear_error else "last_error"
        now = _now()
        with self._connect() as connection:
            cursor = connection.execute(
                f"""
                UPDATE delivery_outbox SET status = ?, attempts = attempts,
                    last_error = {error_sql},
                    updated_at = ?, worker_id = NULL, lease_until = NULL
                WHERE generation_id = ? AND status = 'DELIVERING'
                  AND worker_id = ? AND lease_until > ?
                """,
                (
                    status,
                    now.isoformat(),
                    generation_id,
                    worker_id,
                    now.isoformat(),
                ),
            )
            if cursor.rowcount != 1:
                if self._exists(connection, generation_id):
                    raise LeaseOwnershipError(generation_id)
                raise KeyError(generation_id)

    def renew_lease(
        self, generation_id: str, worker_id: str, lease_seconds: int = 300
    ) -> bool:
        now = _now()
        lease_until = datetime.fromtimestamp(
            now.timestamp() + lease_seconds, tz=timezone.utc
        ).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE delivery_outbox SET lease_until = ?
                WHERE generation_id = ? AND status = 'DELIVERING'
                  AND worker_id = ? AND lease_until > ?
                """,
                (lease_until, generation_id, worker_id, now.isoformat()),
            )
        return cursor.rowcount == 1

    def seconds_until_retryable(self) -> float | None:
        now = _now()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT MIN(lease_until) FROM delivery_outbox
                WHERE status = 'DELIVERING' AND lease_until IS NOT NULL
                  AND lease_until > ?
                """,
                (now.isoformat(),),
            ).fetchone()
        if row is None or row[0] is None:
            return None
        lease_until = datetime.fromisoformat(row[0])
        return max(0.0, (lease_until - now).total_seconds())

    @staticmethod
    def _exists(connection: sqlite3.Connection, generation_id: str) -> bool:
        return (
            connection.execute(
                "SELECT 1 FROM delivery_outbox WHERE generation_id = ?",
                (generation_id,),
            ).fetchone()
            is not None
        )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=30)

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection, table: str, column: str, declaration: str
    ) -> None:
        columns = {
            row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
