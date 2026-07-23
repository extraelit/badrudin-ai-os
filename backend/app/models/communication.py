"""Центр коммуникаций: единая модель сообщений, контактов, шаблонов и журнала
доставки (PR-2, production-ready).

Единый контур внешних и внутренних коммуникаций компании. Каналы (email,
WhatsApp Business Cloud, Instagram Messaging, Telegram Bot, внутренние
уведомления) регистрируются как `integration_connectors` (переиспользуем);
вложения — через универсальные `attachments` (entity_type="message").

Безопасность (ARCHITECTURE.md, CLAUDE.md §14):
- реальная отправка по умолчанию выключена; до подключения ключей работает
  безопасный sandbox без внешних вызовов;
- внешняя отправка требует прав и, где предусмотрено, согласования человеком;
- учитываются согласие получателя и стоп-лист;
- полный неизменяемый аудит и журнал доставки (история попыток, внешний
  идентификатор, причина ошибки).
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
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

# Поддерживаемые каналы (официальные API; неофициальные боты запрещены).
COMM_CHANNELS = ("email", "whatsapp", "instagram", "telegram", "internal")
MESSAGE_DIRECTIONS = ("in", "out")
# Жизненный цикл исходящего сообщения.
MESSAGE_STATUSES = (
    "draft", "pending_approval", "approved", "scheduled", "sending",
    "sent", "delivered", "read", "failed", "cancelled",
)
RECIPIENT_STATUSES = (
    "pending", "sending", "sent", "delivered", "read", "failed", "skipped",
)
DELIVERY_EVENTS = (
    "queued", "sending", "sent", "delivered", "read", "failed", "skipped",
)


class CommunicationContact(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "communication_contacts"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    display_name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    telegram: Mapped[str | None] = mapped_column(String(128), nullable=True)
    whatsapp: Mapped[str | None] = mapped_column(String(64), nullable=True)
    instagram: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Ссылка на контрагента (без жёсткого FK — межмодульная развязка).
    counterparty_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True, index=True
    )
    # Согласие на коммуникации и стоп-лист (защита от спама, требования каналов).
    consent: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    stop_listed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(String(512), nullable=True)


class MessageTemplate(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "message_templates"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    channel: Mapped[str] = mapped_column(String(16), default="email")
    subject: Mapped[str | None] = mapped_column(String(512), nullable=True)
    body_text: Mapped[str] = mapped_column(Text)
    # Утверждение шаблона (для WhatsApp — обязательное требование канала).
    is_approved: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(512), nullable=True)


class CommunicationMessage(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "communication_messages"
    __table_args__ = (
        Index("ix_comm_messages_dir_status", "direction", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    direction: Mapped[str] = mapped_column(String(3), default="out")
    channel: Mapped[str] = mapped_column(String(16), default="email")
    connector_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("integration_connectors.id"), nullable=True
    )
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("message_templates.id"), nullable=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True, index=True
    )
    subject: Mapped[str | None] = mapped_column(String(512), nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    author_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    responsible_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), default="draft")
    # Внешний идентификатор сообщения у провайдера (в sandbox — синтетический).
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    approval_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Принадлежность рассылке (PR-7) — без жёсткого FK на будущую таблицу.
    broadcast_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    # Необязательная привязка к деловой сущности (поручение, процесс и т. п.).
    entity_type: Mapped[str | None] = mapped_column(String(48), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class MessageRecipient(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "message_recipients"
    __table_args__ = (
        Index("ix_message_recipients_message", "message_id"),
    )

    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("communication_messages.id")
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("communication_contacts.id"), nullable=True
    )
    # Адрес назначения (email/телефон/handle) на момент отправки.
    address: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(4), default="to")  # to | cc
    status: Mapped[str] = mapped_column(String(16), default="pending")
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class MessageDeliveryEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "message_delivery_events"
    __table_args__ = (
        Index("ix_delivery_events_message", "message_id"),
    )

    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("communication_messages.id")
    )
    recipient_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("message_recipients.id"), nullable=True
    )
    event: Mapped[str] = mapped_column(String(16))
    detail: Mapped[str | None] = mapped_column(String(512), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
