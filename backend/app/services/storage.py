"""Работа с объектным хранилищем MinIO и метаданными файлов (T-1.E1, T-1.E2).

Файлы хранятся вне БД (D-008; ARCHITECTURE.md раздел 5.6); в базе — метаданные
(`files`). Ссылки на скачивание — временные подписанные (T-1.E2).
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta
from functools import lru_cache

from minio import Minio
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import File


def sha256_checksum(data: bytes) -> str:
    """Контрольная сумma содержимого файла."""
    return hashlib.sha256(data).hexdigest()


class UploadValidationError(ValueError):
    """Недопустимый тип или размер вложения."""


def validate_upload(mime_type: str | None, size_bytes: int) -> None:
    """Проверяет тип и размер вложения (T-1.E2; ACCESS_CONTROL.md раздел 14)."""
    settings = get_settings()
    if size_bytes > settings.max_upload_bytes:
        raise UploadValidationError("Файл превышает допустимый размер")
    allowed = {m.strip() for m in settings.allowed_upload_mime.split(",") if m.strip()}
    if mime_type is None or mime_type not in allowed:
        raise UploadValidationError(f"Недопустимый тип файла: {mime_type}")


@lru_cache
def get_minio_client() -> Minio:
    settings = get_settings()
    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_use_ssl,
        region=settings.minio_region,
    )


def build_object_key(original_name: str, prefix: str = "files") -> str:
    """Формирует безопасный ключ хранения, не завязанный на исходное имя."""
    suffix = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    name = uuid.uuid4().hex
    return f"{prefix}/{name}.{suffix}" if suffix else f"{prefix}/{name}"


def presigned_get_url(
    object_key: str, expires_minutes: int = 15, client: Minio | None = None
) -> str:
    """Временная подписанная ссылка на скачивание (T-1.E2).

    Подпись вычисляется локально; ссылка имеет срок действия и не передаётся
    публично (ACCESS_CONTROL.md раздел 25).
    """
    settings = get_settings()
    mc = client or get_minio_client()
    return mc.presigned_get_object(
        settings.minio_bucket,
        object_key,
        expires=timedelta(minutes=expires_minutes),
    )


def register_file(
    session: Session,
    *,
    organization_id: uuid.UUID,
    original_name: str,
    content: bytes,
    mime_type: str | None,
    storage_key: str | None = None,
    uploaded_by: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    site_id: uuid.UUID | None = None,
    commit: bool = True,
) -> File:
    """Сохраняет метаданные файла после валидации (сам объект грузится в MinIO)."""
    validate_upload(mime_type, len(content))
    record = File(
        organization_id=organization_id,
        project_id=project_id,
        site_id=site_id,
        storage_provider="minio",
        storage_key=storage_key or build_object_key(original_name),
        original_name=original_name,
        mime_type=mime_type,
        size_bytes=len(content),
        checksum_sha256=sha256_checksum(content),
        uploaded_by=uploaded_by,
        virus_scan_status="pending",
    )
    session.add(record)
    if commit:
        session.commit()
    return record
