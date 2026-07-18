"""Тесты подписанных ссылок и проверки вложений (T-1.E2)."""

import pytest
from minio import Minio

from app.services.storage import (
    UploadValidationError,
    presigned_get_url,
    validate_upload,
)


def test_presigned_url_signed_offline_with_expiry() -> None:
    client = Minio(
        "minio:9000", access_key="k", secret_key="s", secure=False, region="ru-central"
    )
    url = presigned_get_url("files/abc.png", expires_minutes=15, client=client)
    assert "files/abc.png" in url
    assert "X-Amz-Signature=" in url
    assert "X-Amz-Expires=" in url  # ссылка имеет срок действия


def test_attachment_validation_rejects_bad_types() -> None:
    validate_upload("application/pdf", 2048)  # разрешено
    with pytest.raises(UploadValidationError):
        validate_upload("text/x-python", 100)  # запрещённый тип
