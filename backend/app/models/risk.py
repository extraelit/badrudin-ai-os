"""Модуль «Реестр рисков» (ROADMAP этап 15, §20 KPI/риски/аудит).

Единый реестр рисков компании и проектов: идентификация → оценка (вероятность ×
влияние) → план снижения → принятие/закрытие/реализация. Риск может порождаться
из входящего обращения (`inbox_items`) или задачи (`tasks`) — связь через
`source_type`/`source_id`, без дублирования. Все значимые действия — в
`audit_events`; принятие высокого риска — решение человека.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Risk(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Запись реестра рисков."""

    __tablename__ = "risks"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sites.id"), nullable=True
    )
    number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # schedule | cost | quality | safety | supply | legal | hr | financial | other
    category: Mapped[str] = mapped_column(String(32), default="other")
    # low | medium | high
    probability: Mapped[str] = mapped_column(String(8), default="medium")
    impact: Mapped[str] = mapped_column(String(8), default="medium")
    # low | medium | high | critical (вычисляется из probability × impact)
    severity: Mapped[str] = mapped_column(String(8), default="medium")
    # identified | assessed | mitigating | accepted | closed | realized
    status: Mapped[str] = mapped_column(String(16), default="identified")
    owner_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    mitigation_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    identified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    # источник риска (inbox_item | task | manual | audit)
    source_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decision_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_due_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
