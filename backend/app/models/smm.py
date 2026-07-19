"""Модуль «SMM и внешние публикации» — внутренний контур (ROADMAP этап 17, §14).

Готовит контент-план и публикации для внешних каналов, НО НЕ публикует их.
Публикации существуют только как черновики на утверждение: подготовка → проверка
фактов/прав/ПДн → утверждение руководителем. Утверждённая публикация переходит в
статус `approved`/`scheduled` (готова к публикации официальным утверждённым
инструментом вне модуля) — фактическая публикация здесь НЕ выполняется. Права на
фотографии, персональные данные и конфиденциальность проверяются до утверждения.
Всё — под аудитом (§14/§20/§27; критерии перехода ROADMAP этапа 17).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    Uuid,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ContentPlanItem(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Позиция контент-плана (идея публикации)."""

    __tablename__ = "content_plan_items"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(255))
    theme: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # email | telegram | whatsapp_business | instagram | webhook | internal
    channel: Mapped[str] = mapped_column(String(32), default="internal")
    planned_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # idea | planned | in_progress | done | cancelled
    status: Mapped[str] = mapped_column(String(16), default="idea")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class SocialPublication(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Публикация — только черновик на утверждение (§14).

    Никогда не публикуется этим модулем. Статусы отражают внутренний контур
    подготовки, проверок и утверждения; фактическая публикация — отдельный
    официальный утверждённый инструмент после ручного утверждения (вне модуля).
    """

    __tablename__ = "social_publications"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    plan_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("content_plan_items.id"), nullable=True
    )
    connector_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("integration_connectors.id"), nullable=True
    )
    channel: Mapped[str] = mapped_column(String(32), default="internal")
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    hashtags: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # draft | fact_check | pending_approval | approved | scheduled | cancelled
    # «published» отсутствует намеренно — модуль не публикует
    status: Mapped[str] = mapped_column(String(16), default="draft")
    # обязательные проверки до утверждения (критерии перехода этапа 17)
    rights_confirmed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    pii_checked: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    legal_checked: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    scheduled_for: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    risk_level: Mapped[str] = mapped_column(String(2), default="R3")
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("approvals.id"), nullable=True
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class SocialPublicationAsset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Материал публикации (фото/видео) — метаданные + отметки проверки качества и прав.

    Файлы хранятся вне БД (D-008); здесь — только связь с `files` и отметки.
    """

    __tablename__ = "social_publication_assets"

    publication_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("social_publications.id")
    )
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("files.id"), nullable=True
    )
    caption: Mapped[str | None] = mapped_column(String(500), nullable=True)
    quality_ok: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    rights_ok: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
