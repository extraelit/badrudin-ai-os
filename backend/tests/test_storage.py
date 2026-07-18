"""Тесты файлового хранилища и метаданных (T-1.E1, T-1.E2)."""

import uuid

import pytest

from app.models import Organization
from app.services.storage import (
    UploadValidationError,
    build_object_key,
    register_file,
    sha256_checksum,
    validate_upload,
)


def test_checksum_and_key() -> None:
    assert len(sha256_checksum(b"hello")) == 64
    key = build_object_key("Чек.JPG")
    assert key.startswith("files/")
    assert key.endswith(".jpg")
    assert "Чек" not in key  # ключ не завязан на исходное имя


def test_validate_upload() -> None:
    validate_upload("image/png", 1000)  # ок
    with pytest.raises(UploadValidationError):
        validate_upload("application/x-msdownload", 1000)  # запрещённый тип
    with pytest.raises(UploadValidationError):
        validate_upload("image/png", 10**12)  # слишком большой


def test_register_file_metadata(db_session) -> None:
    org = Organization(legal_name="ООО «Экстра-Элит»")
    db_session.add(org)
    db_session.flush()
    rec = register_file(
        db_session,
        organization_id=org.id,
        original_name="receipt.png",
        content=b"binarydata",
        mime_type="image/png",
    )
    assert rec.size_bytes == len(b"binarydata")
    assert rec.checksum_sha256 == sha256_checksum(b"binarydata")
    assert rec.storage_provider == "minio"
