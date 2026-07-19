"""Модуль «Единый входящий поток» (ROADMAP этап 5, DATABASE.md разделы 10, 18).

Единая очередь сортировки (triage) входящих обращений из разрешённых источников:
письма, официальные каналы мессенджеров, веб-форма, звонки, внутренние заметки.
Элемент проходит классификацию и превращается в задачу, документ, заявку или
риск — **без дублирования** существующих сущностей: связь с исходной
коммуникацией (`communications`) и с созданной задачей (`tasks`) ведётся
идентификаторами, конверсия переиспользует общие сервисы. Внешние интеграции
(реальный приём писем/сообщений) подключаются отдельными коннекторами и требуют
секретов — здесь заложен только внутренний контур сортировки и маршрутизации.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class InboxItem(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Элемент единого входящего потока (обращение на сортировку)."""

    __tablename__ = "inbox_items"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    # communication | web_form | email | messenger | manual | system
    source_type: Mapped[str] = mapped_column(String(32), default="manual")
    # ссылка на исходную запись (например, communications.id) — без дублирования
    source_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    communication_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("communications.id"), nullable=True
    )
    # email | whatsapp | telegram | web_form | phone | internal | manual
    channel: Mapped[str] = mapped_column(String(32), default="manual")
    external_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sender_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sender_contact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    counterparty_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("counterparties.id"), nullable=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sites.id"), nullable=True
    )
    # request | complaint | inquiry | document | risk | lead | invoice | other
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    priority: Mapped[str] = mapped_column(String(16), default="normal")
    # new | classified | in_progress | converted | dismissed
    status: Mapped[str] = mapped_column(String(16), default="new")
    assigned_to_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    # task | document | material_request | risk | lead
    converted_entity_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    converted_entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    dismissed_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    triaged_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    triaged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
