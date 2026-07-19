"""Модуль «Масштабирование интеграций» — внутренний контур (ROADMAP этап 16, §13/§14).

Реестр интеграций-коннекторов и очередь исходящих сообщений. ВАЖНО (CLAUDE.md
§14/§27, решение владельца): модуль НЕ подключает реальные внешние API и НЕ
отправляет сообщения. Секреты здесь не хранятся — только неконфиденциальные
метаданные коннектора. Исходящие сообщения существуют только как черновики на
утверждение; их фактическая отправка выполняется отдельным утверждённым
коннектором после ручного утверждения и здесь не производится. Всё — под аудитом.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    Uuid,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class IntegrationConnector(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Коннектор интеграции (реестр). Секреты не хранятся."""

    __tablename__ = "integration_connectors"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    # email | telegram | whatsapp_business | instagram | webhook | internal
    channel: Mapped[str] = mapped_column(String(32), default="internal")
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # неконфиденциальное описание конфигурации (без ключей и паролей)
    config_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # draft | configured | disabled — «configured» означает готовность к настройке
    # реальных доступов отдельно; отправка отсюда не производится
    status: Mapped[str] = mapped_column(String(16), default="draft")
    # признак: реальные доступы настроены вне системы (не хранятся здесь)
    credentials_configured_externally: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)


class OutboundMessage(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Исходящее сообщение — только черновик на утверждение (§14).

    Никогда не отправляется этим модулем. Статусы отражают внутренний контур
    подготовки и утверждения; фактическая отправка — отдельный утверждённый
    коннектор после ручного утверждения (вне данного модуля).
    """

    __tablename__ = "outbound_messages"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    connector_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("integration_connectors.id"), nullable=True
    )
    channel: Mapped[str] = mapped_column(String(32), default="email")
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    counterparty_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("counterparties.id"), nullable=True
    )
    # обезличенный адресат (без реальных ПДн в тестах)
    recipient: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # связь с сущностью-основанием (task | daily_report | risk | inbox_item | ...)
    entity_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    # draft | pending_approval | approved | cancelled — «sent» отсутствует намеренно
    status: Mapped[str] = mapped_column(String(16), default="draft")
    risk_level: Mapped[str] = mapped_column(String(2), default="R2")
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("approvals.id"), nullable=True
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
