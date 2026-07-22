"""Нормативный реестр и нормативный профиль проекта (этап 1).

Справочник нормативных документов (ФЗ, ГрК, СП, СНиП, СанПиН, ГОСТ, РД, приказы,
постановления, проектные/договорные/внутренние документы) — версионируемый.
Система хранит редакцию и статус, но **не утверждает автоматически** актуальность:
новая запись создаётся со статусом `needs_review`, перевод в `in_force` — действие
уполномоченного лица (главный инженер / ПТО / юрист) с фиксацией в аудите. При
изменении нормы прежние записи не переписываются (историческая привязка отчётов к
действовавшей редакции).

Нормативный профиль проекта — набор применимых к проекту нормативов с редакцией,
обязательностью и видами работ; применимость подтверждается человеком, не системой.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

# Виды нормативных документов и допустимые статусы (реестр не решает сам).
DOC_KINDS = (
    "federal_law", "code", "sp", "snip", "sanpin", "gost", "rd",
    "gov_resolution", "ministry_order", "project_doc", "contract", "internal",
)
DOC_STATUSES = ("in_force", "amended", "superseded", "repealed", "needs_review")


class NormativeDocument(
    UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base
):
    __tablename__ = "normative_documents"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    full_title: Mapped[str] = mapped_column(String(1024))
    number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    doc_kind: Mapped[str] = mapped_column(String(32))
    edition: Mapped[str | None] = mapped_column(String(128), nullable=True)
    amendment_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    # по умолчанию — «требует проверки»: система не подтверждает актуальность сама
    status: Mapped[str] = mapped_column(String(24), default="needs_review")
    official_source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    work_types: Mapped[list | None] = mapped_column(JSON, nullable=True)
    object_types: Mapped[list | None] = mapped_column(JSON, nullable=True)
    related_control_ops: Mapped[list | None] = mapped_column(JSON, nullable=True)
    responsible_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewer_comment: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProjectNormativeProfile(
    UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base
):
    __tablename__ = "project_normative_profiles"
    __table_args__ = (UniqueConstraint("project_id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    # draft | active — активацию профиля подтверждает уполномоченное лицо
    status: Mapped[str] = mapped_column(String(24), default="draft")
    approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProjectNormativeItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "project_normative_items"
    __table_args__ = (UniqueConstraint("profile_id", "normative_document_id"),)

    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_normative_profiles.id"), index=True
    )
    normative_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("normative_documents.id")
    )
    # редакция, применимая на данном проекте (историческая привязка)
    applicable_edition: Mapped[str | None] = mapped_column(String(128), nullable=True)
    mandatory: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(), nullable=False
    )
    work_types: Mapped[list | None] = mapped_column(JSON, nullable=True)
    special_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
