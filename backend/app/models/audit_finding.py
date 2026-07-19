"""Модуль «KPI и независимый аудит» — реестр находок аудитора (ROADMAP этап 15, §20).

Независимый аудитор фиксирует выявленные противоречия и аномалии как отдельные
записи-находки. ВАЖНО (критерий перехода этапа 15): аудит НЕ может незаметно
изменить проверяемые данные — находки хранятся отдельно от проверяемых сущностей и
лишь ссылаются на них. Находки создаются вручную ролью аудита либо детерминированным
сканированием (без ИИ; правила воспроизводимы). Человек рассматривает и закрывает
находку; всё — под аудитом. KPI вычисляются только для чтения из существующих данных.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AuditFinding(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Находка независимого аудита (append-only реестр с человеческим разбором)."""

    __tablename__ = "audit_findings"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    # overdue_task | risk_no_owner | missing_evidence | bypassed_approval |
    # unusual_change | anomalous_expense | incomplete_log | agent_quality | other
    category: Mapped[str] = mapped_column(String(32), default="other")
    # low | medium | high
    severity: Mapped[str] = mapped_column(String(8), default="medium")
    title: Mapped[str] = mapped_column(String(500))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ссылка на проверяемую сущность (данные не меняются)
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    # open | acknowledged | resolved | false_positive
    status: Mapped[str] = mapped_column(String(16), default="open")
    # источник находки: scan (детерминированное сканирование) | manual
    detected_by: Mapped[str] = mapped_column(String(16), default="scan")
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
