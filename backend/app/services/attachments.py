"""Универсальный сервис вложений (PR-1).

Единая точка прикрепления файлов к любой основной сущности. Реально сохраняет
байты в хранилище (локальное или S3 — через `storage_adapter`), пишет метаданные
и SHA-256 в `files`, создаёт связь `attachments`, фиксирует неизменяемый аудит.

Гарантии:
- проверка типа и размера вложения (RBAC/ABAC — на уровне API);
- удаление физически не выполняется — только архивирование;
- вложение утверждённого (заблокированного) файла нельзя архивировать/заменять;
- новая версия не затирает старую (прежняя помечается `is_current=False`).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Attachment, File
from app.models.attachment import ATTACHABLE_ENTITIES, ATTACHMENT_TYPES
from app.services.audit import record_event
from app.services.storage import build_object_key, sha256_checksum, validate_upload
from app.services.storage_adapter import get_storage_adapter

# Реэкспорт для совместимого перехвата в API.
from app.services.storage import UploadValidationError  # noqa: F401


class AttachmentError(Exception):
    """Нарушение правил работы с вложением (сущность, версия, архив)."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def attach(
    session: Session,
    *,
    organization_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    original_name: str,
    content: bytes,
    mime_type: str | None,
    attachment_type: str = "document",
    description: str | None = None,
    project_id: uuid.UUID | None = None,
    uploaded_by: uuid.UUID | None = None,
    replaces_id: uuid.UUID | None = None,
) -> Attachment:
    """Прикрепляет файл к сущности: пишет байты, регистрирует файл, создаёт связь."""
    if entity_type not in ATTACHABLE_ENTITIES:
        raise AttachmentError(f"Недопустимый тип сущности: {entity_type}")
    if attachment_type not in ATTACHMENT_TYPES:
        raise AttachmentError(f"Недопустимый тип вложения: {attachment_type}")
    validate_upload(mime_type, len(content))  # бросает UploadValidationError

    adapter = get_storage_adapter()
    storage_key = build_object_key(original_name)
    adapter.put(storage_key, content, mime_type)

    file = File(
        organization_id=organization_id,
        project_id=project_id,
        storage_provider=adapter.provider,
        storage_key=storage_key,
        original_name=original_name,
        mime_type=mime_type,
        size_bytes=len(content),
        checksum_sha256=sha256_checksum(content),
        uploaded_by=uploaded_by,
        virus_scan_status="pending",
    )
    session.add(file)
    session.flush()

    version = 1
    if replaces_id is not None:
        prev = session.get(Attachment, replaces_id)
        if prev is None or prev.organization_id != organization_id:
            raise AttachmentError("Заменяемое вложение не найдено")
        if prev.entity_type != entity_type or prev.entity_id != entity_id:
            raise AttachmentError("Новая версия должна относиться к той же сущности")
        prev.is_current = False
        version = prev.version + 1

    att = Attachment(
        organization_id=organization_id,
        file_id=file.id,
        entity_type=entity_type,
        entity_id=entity_id,
        project_id=project_id,
        attachment_type=attachment_type,
        description=description,
        uploaded_by=uploaded_by,
        version=version,
        replaces_id=replaces_id,
        is_current=True,
    )
    session.add(att)
    session.flush()
    record_event(
        session, actor_type="user", action="attachment.add",
        actor_user_id=uploaded_by, organization_id=organization_id,
        entity_type=entity_type, entity_id=entity_id,
        new_values={
            "attachment_id": str(att.id), "file_id": str(file.id),
            "attachment_type": attachment_type, "version": version,
            "checksum_sha256": file.checksum_sha256,
        },
        risk_level="R1", commit=True,
    )
    return att


def list_for(
    session: Session, entity_type: str, entity_id: uuid.UUID,
    *, include_archived: bool = False, current_only: bool = True,
) -> list[Attachment]:
    """Вложения сущности (по умолчанию — только актуальные, без архивных)."""
    stmt = select(Attachment).where(
        Attachment.entity_type == entity_type,
        Attachment.entity_id == entity_id,
        Attachment.deleted_at.is_(None),
    )
    if not include_archived:
        stmt = stmt.where(Attachment.is_archived.is_(False))
    # При запросе с архивом показываем все версии; иначе — только актуальные.
    if current_only and not include_archived:
        stmt = stmt.where(Attachment.is_current.is_(True))
    return list(session.execute(stmt.order_by(Attachment.created_at)).scalars())


def get(session: Session, attachment_id: uuid.UUID) -> Attachment | None:
    att = session.get(Attachment, attachment_id)
    if att is None or att.deleted_at is not None:
        return None
    return att


def download(session: Session, attachment: Attachment) -> tuple[bytes | None, str | None, File]:
    """Готовит скачивание: (байты | None, presigned_url | None, метаданные файла).

    Для S3 отдаём временную ссылку; для локального хранилища — байты (стрим в API).
    """
    file = session.get(File, attachment.file_id)
    if file is None or file.deleted_at is not None:
        raise AttachmentError("Файл вложения не найден")
    adapter = get_storage_adapter()
    url = adapter.presigned_url(file.storage_key)
    if url is not None:
        return None, url, file
    return adapter.open(file.storage_key), None, file


def archive(
    session: Session, attachment: Attachment, *, actor_user_id: uuid.UUID | None,
    reason: str,
) -> Attachment:
    """Архивирует вложение (не удаляет). Утверждённый (заблокированный) файл нельзя."""
    if not reason or not reason.strip():
        raise AttachmentError("Архивирование требует указания причины")
    if attachment.is_archived:
        return attachment
    file = session.get(File, attachment.file_id)
    if file is not None and file.locked_at is not None:
        raise AttachmentError(
            "Нельзя архивировать вложение утверждённого (заблокированного) файла"
        )
    attachment.is_archived = True
    attachment.is_current = False
    attachment.archived_at = _now()
    attachment.archived_by = actor_user_id
    attachment.archive_reason = reason
    record_event(
        session, actor_type="user", action="attachment.archive",
        actor_user_id=actor_user_id, organization_id=attachment.organization_id,
        entity_type=attachment.entity_type, entity_id=attachment.entity_id,
        new_values={"attachment_id": str(attachment.id), "is_archived": True},
        reason=reason, risk_level="R1", commit=True,
    )
    return attachment
