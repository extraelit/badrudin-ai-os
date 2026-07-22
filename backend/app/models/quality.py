"""Строительный контроль и качество: контрольные карты и проверки (этап F, PR-F).

Соответствует PROCESS_CORE_PLAN.md §5. Контрольная карта — настраиваемый шаблон по
виду работ (входной/операционный/приёмочный контроль, скрытые работы) с нормативным
основанием (ссылка на позицию нормативного профиля), контролируемым параметром,
методом, требованием документа/фото/измерения. Проверка — фактический результат с
измерением, прибором и сведениями о его поверке, замечанием, сроком устранения,
повторной проверкой и итоговым решением уполномоченного специалиста.

ИИ только подсказывает возможное отклонение; признать работу соответствующей норме —
право уполномоченного специалиста (человек в контуре).
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

# Виды контроля (PROCESS_CORE_PLAN.md §1.4/§5).
CONTROL_KINDS = (
    "incoming", "operational", "acceptance", "hidden_works", "general",
)
# Итог проверки.
CHECK_RESULTS = ("pending", "pass", "fail", "conditional")
FINAL_DECISIONS = ("accepted", "rejected")


class QualityControlCard(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "quality_control_cards"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True, index=True
    )
    work_type: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(512))
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    control_kind: Mapped[str] = mapped_column(String(24), default="operational")
    # нормативное основание — ссылка на позицию нормативного профиля проекта
    normative_item_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    controlled_parameter: Mapped[str] = mapped_column(String(512))
    allowed_value: Mapped[str | None] = mapped_column(String(512), nullable=True)
    check_method: Mapped[str | None] = mapped_column(String(512), nullable=True)
    responsible_position: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requires_document: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    requires_photo: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=false(), nullable=False
    )
    requires_measurement: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), default="active")


class QualityControlCheck(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "quality_control_checks"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    card_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quality_control_cards.id"), index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    # связь с процессом (например, вида acceptance_control/defect) — без дублирования
    process_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    checked_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    measured_value: Mapped[str | None] = mapped_column(String(512), nullable=True)
    instrument: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # сведения о поверке прибора
    instrument_verification: Mapped[str | None] = mapped_column(String(255), nullable=True)
    result: Mapped[str] = mapped_column(String(16), default="pending")
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    # срок устранения замечания и повторная проверка
    defect_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    recheck_required: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    recheck_of_check_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    # ИИ подсказывает отклонение, но не решает
    ai_suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    # итоговое решение уполномоченного специалиста
    final_decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    final_decision_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    final_decision_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
