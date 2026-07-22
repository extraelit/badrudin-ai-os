"""Защита целостности документов после утверждения (этап 1).

Принципы (ACCESS_CONTROL.md разделы 20–21, план целостности):
- утверждённая версия документа неизменяема; изменить содержание можно только
  выпуском новой версии (append-only история версий);
- файл-носитель утверждённой версии блокируется (`locked_at`/`locked_by`) — его
  нельзя удалить на уровне сессии (защита от подделки задним числом);
- документ не удаляется, а архивируется (`is_archived`);
- каждое утверждение/выпуск версии/архивирование фиксируется в журнале аудита.

Сервис не хранит секретов и не выполняет внешних действий.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Document, DocumentVersion, File
from app.services.audit import record_event


class DocumentIntegrityError(RuntimeError):
    """Нарушение правил целостности документа (правка/удаление утверждённого)."""


def _now() -> datetime:
    return datetime.now(UTC)


def create_new_version(
    session: Session,
    document_id: uuid.UUID,
    *,
    file_id: uuid.UUID | None = None,
    change_summary: str | None = None,
    prepared_by: uuid.UUID | None = None,
    commit: bool = True,
) -> DocumentVersion:
    """Создаёт новую черновую версию с номером на единицу больше максимального.

    Единственный допустимый способ изменить содержание после утверждения —
    выпуск новой версии (прежние утверждённые версии остаются неизменными).
    """
    max_no = session.execute(
        select(func.max(DocumentVersion.version_number)).where(
            DocumentVersion.document_id == document_id
        )
    ).scalar()
    version = DocumentVersion(
        document_id=document_id,
        version_number=(max_no or 0) + 1,
        file_id=file_id,
        change_summary=change_summary,
        prepared_by=prepared_by,
        status="draft",
    )
    session.add(version)
    if commit:
        session.commit()
    return version


def approve_version(
    session: Session,
    version_id: uuid.UUID,
    *,
    approver_id: uuid.UUID | None = None,
    reason: str | None = None,
) -> DocumentVersion:
    """Утверждает версию: блокирует её и файл-носитель, делает её текущей.

    Повторное утверждение уже заблокированной версии запрещено.
    """
    version = session.get(DocumentVersion, version_id)
    if version is None:
        raise DocumentIntegrityError("Версия документа не найдена")
    if version.locked_at is not None:
        raise DocumentIntegrityError("Версия уже утверждена и заблокирована")

    now = _now()
    version.status = "approved"
    version.approved_by = approver_id
    version.approved_at = now
    version.locked_at = now
    version.locked_by = approver_id

    # блокируем файл-носитель (нельзя удалить/подменить после утверждения)
    if version.file_id is not None:
        file = session.get(File, version.file_id)
        if file is not None and file.locked_at is None:
            file.locked_at = now
            file.locked_by = approver_id

    # версия становится текущей у документа; документ переходит в approved
    document = session.get(Document, version.document_id)
    if document is not None:
        document.current_version_id = version.id
        document.status = "approved"
        if document.locked_at is None:
            document.locked_at = now
            document.locked_by = approver_id

    record_event(
        session,
        actor_type="user",
        action="document.version.approve",
        actor_user_id=approver_id,
        entity_type="document_version",
        entity_id=version.id,
        new_values={
            "document_id": str(version.document_id),
            "version_number": version.version_number,
        },
        reason=reason,
        risk_level="R2",
        commit=True,
    )
    return version


def assert_version_editable(version: DocumentVersion) -> None:
    """Гарантирует, что версия ещё редактируема (не утверждена/не заблокирована)."""
    if version.locked_at is not None or version.status == "approved":
        raise DocumentIntegrityError(
            "Утверждённая версия неизменяема — выпустите новую версию."
        )


def archive_document(
    session: Session,
    document_id: uuid.UUID,
    *,
    actor_user_id: uuid.UUID | None = None,
    reason: str | None = None,
) -> Document:
    """Архивирует документ (`is_archived`), не удаляя его (сохранение истории)."""
    document = session.get(Document, document_id)
    if document is None:
        raise DocumentIntegrityError("Документ не найден")
    document.is_archived = True
    record_event(
        session,
        actor_type="user",
        action="document.archive",
        actor_user_id=actor_user_id,
        entity_type="document",
        entity_id=document.id,
        new_values={"is_archived": True},
        reason=reason,
        risk_level="R1",
        commit=True,
    )
    return document
