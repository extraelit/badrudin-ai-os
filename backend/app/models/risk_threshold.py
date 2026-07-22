"""Настраиваемые пороги согласований `risk_thresholds` (этап G, PR-G).

Пороговые суммы, сроки и уровни согласования не зашиты в код, а настраиваются по
организации/проекту/виду процесса (PROCESS_CORE_PLAN.md §3, §9). Правило задаёт
диапазон метрики (сумма, длительность) → уровень риска, число согласующих и
необходимость MFA для действия. Наиболее специфичное применимое правило
определяет уровень риска процесса.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    Numeric,
    String,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

# Метрика, по которой оценивается порог.
THRESHOLD_METRICS = ("amount", "duration_days", "default")


class RiskThreshold(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "risk_thresholds"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    # NULL project_id/process_kind — правило по умолчанию для организации/вида
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    process_kind: Mapped[str | None] = mapped_column(String(48), nullable=True)
    metric: Mapped[str] = mapped_column(String(24), default="amount")
    # диапазон значения метрики [min_value, max_value); NULL — без ограничения
    min_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    max_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    risk_level: Mapped[str] = mapped_column(String(2), default="R1")
    required_approvals: Mapped[int] = mapped_column(Integer, default=1)
    requires_mfa: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=false(), nullable=False
    )
