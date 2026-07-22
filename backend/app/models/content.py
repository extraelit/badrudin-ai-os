"""Ежедневные отчёты, документы, файлы и уведомления (T-1.B6).

Соответствует DATABASE.md разделы 9–10, 19. Файлы хранятся вне БД; здесь —
только метаданные (D-008; ARCHITECTURE.md раздел 5.6).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy import event
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class DocumentIntegrityError(RuntimeError):
    """Попытка удалить утверждённый (заблокированный) документ/версию/файл."""


class File(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "files"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sites.id"), nullable=True
    )
    storage_provider: Mapped[str] = mapped_column(String(32), default="minio")
    storage_key: Mapped[str] = mapped_column(String(1024))
    original_name: Mapped[str] = mapped_column(String(512))
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    virus_scan_status: Mapped[str] = mapped_column(String(32), default="pending")
    confidentiality_level: Mapped[str] = mapped_column(String(32), default="internal")
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Блокировка целостности: после утверждения файл-носитель неизменяем и
    # неудаляем (защита от подделки; ACCESS_CONTROL.md разделы 20–21). NULL —
    # не заблокирован; заполняется при утверждении версии документа.
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    locked_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class Document(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "documents"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    document_type: Mapped[str] = mapped_column(String(64), default="other")
    number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_employee_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    confidentiality_level: Mapped[str] = mapped_column(String(32), default="internal")
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    # Блокировка после утверждения: содержимое меняется только новой версией,
    # запись не удаляется (только архивируется, is_archived). NULL — не заблокирован.
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    locked_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    registered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)


class DocumentVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_versions"

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"))
    version_number: Mapped[int] = mapped_column(Integer, default=1)
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("files.id"), nullable=True
    )
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    prepared_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Утверждённая версия неизменяема и неудаляема (append-only история версий).
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    locked_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class DailyReport(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "daily_reports"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sites.id"), nullable=True
    )
    report_date: Mapped[date] = mapped_column(Date)
    reporting_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True
    )
    # идемпотентность повторной отправки мобильной формы (§18/§23): клиент
    # генерирует уникальный ключ на отправку; повтор с тем же ключом не создаёт дубль
    client_request_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    weather_summary: Mapped[str | None] = mapped_column(String(255), nullable=True)
    workers_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    work_completed: Mapped[str | None] = mapped_column(Text, nullable=True)
    problems: Mapped[str | None] = mapped_column(Text, nullable=True)
    materials_needed: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan_next_day: Mapped[str | None] = mapped_column(Text, nullable=True)
    # draft | submitted | approved | rejected | correction_required
    status: Mapped[str] = mapped_column(String(32), default="draft")
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # проверка руководителем (ПТО): кто и с каким комментарием
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)


class DailyReportWorkItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Фактически выполненные объёмы работ (DATABASE.md раздел 9.2).

    Каждая фактическая работа связывается с позицией сметы (план-факт), проектом,
    объектом, зоной/участком, датой, количеством, единицей, прорабом,
    подтверждающим файлом и статусом проверки.
    """

    __tablename__ = "daily_report_work_items"

    daily_report_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("daily_reports.id"), nullable=True
    )
    # связь выполненной работы с задачей-поручением (§18)
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id"), nullable=True
    )
    estimate_position_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("estimate_positions.id"), nullable=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sites.id"), nullable=True
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_locations.id"), nullable=True
    )
    work_date: Mapped[date] = mapped_column(Date)
    work_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    unit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("units_of_measure.id"), nullable=True
    )
    planned_quantity: Mapped[float | None] = mapped_column(
        Numeric(14, 3), nullable=True
    )
    actual_quantity: Mapped[float] = mapped_column(Numeric(14, 3), default=0)
    cumulative_quantity: Mapped[float | None] = mapped_column(
        Numeric(14, 3), nullable=True
    )
    foreman_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    evidence_file_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("files.id"), nullable=True
    )
    # pending | verified | rejected
    verification_status: Mapped[str] = mapped_column(String(16), default="pending")
    verified_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)


class Notification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "notifications"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    recipient_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    recipient_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True
    )
    channel: Mapped[str] = mapped_column(String(32), default="in_app")
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    priority: Mapped[str] = mapped_column(String(16), default="normal")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


# --- Защита целостности утверждённых документов (ACCESS_CONTROL.md 20–21) ---
# Заблокированные (утверждённые) файл, версия и документ не удаляются на уровне
# сессии ORM — это защита от подделки задним числом. Изменение допускается только
# через выпуск новой версии; сам документ архивируется (is_archived), а не удаляется.


def _forbid_locked_delete(mapper: Mapper, connection, target) -> None:
    if getattr(target, "locked_at", None) is not None:
        raise DocumentIntegrityError(
            "Утверждённый документ/версия/файл нельзя удалить: заблокирован "
            "(допустимы только новая версия или архивирование)."
        )


event.listen(File, "before_delete", _forbid_locked_delete)
event.listen(Document, "before_delete", _forbid_locked_delete)
event.listen(DocumentVersion, "before_delete", _forbid_locked_delete)
