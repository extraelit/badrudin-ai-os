"""Универсальные вложения: связь файла с любой основной сущностью (PR-1).

Единый механизм прикрепления файлов ко всем сущностям системы (поручения и
процессы, ежедневные отчёты, сообщения, согласования, документы, проверки
качества, замечания, закупки/поставки/склад, техника/инструмент/ремонты,
входящие/исходящие письма). Сам файл и его метаданные (SHA-256, размер, MIME,
блокировка после утверждения) хранятся в `files`; `attachments` — это связь
файла с сущностью с описанием, типом доказательства, версией и признаком архива.

Инварианты:
- удаление физически не выполняется — только архивирование (`is_archived`);
- вложение утверждённого (заблокированного) файла нельзя архивировать/менять;
- новая версия не затирает старую: прежняя помечается `is_current=False`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    false,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

# Сущности, к которым допустимо прикреплять файлы (белый список — защита от
# произвольных ссылок). Значения совпадают с `entity_type` в аудите.
ATTACHABLE_ENTITIES = (
    "workflow_process",
    "daily_report",
    "message",
    "broadcast",
    "approval",
    "document",
    "document_version",
    "quality_control_card",
    "quality_control_check",
    "audit_finding",
    "incident",
    "procurement_request",
    "delivery",
    "inventory_operation",
    "equipment",
    "tool",
    "repair",
    "inbound_letter",
    "outbound_letter",
    "task",
)

# Тип вложения / доказательства (совместим с EVIDENCE_TYPES процессного ядра плюс
# общие типы для писем и сообщений).
ATTACHMENT_TYPES = (
    "document", "photo", "video", "scan", "pdf", "act", "delivery_note",
    "invoice", "certificate", "quality_passport", "test_protocol",
    "as_built_scheme", "work_log", "correspondence", "electronic_original",
    "other",
)


class Attachment(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "attachments"
    __table_args__ = (
        Index("ix_attachments_entity", "entity_type", "entity_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("files.id"), index=True)
    entity_type: Mapped[str] = mapped_column(String(48), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True, index=True
    )
    attachment_type: Mapped[str] = mapped_column(String(48), default="document")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)

    # Версионирование: новая версия ссылается на предыдущую; актуальна одна.
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    replaces_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("attachments.id"), nullable=True
    )
    is_current: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(), nullable=False
    )

    # Архивирование вместо удаления (is_archived — из SoftDeleteMixin).
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    archived_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    archive_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
