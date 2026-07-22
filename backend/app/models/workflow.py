"""Универсальное процессное ядро: `workflow_processes` (этап D, PR-D1).

Единая запись процесса для любого вида работ (поручения/задачи как эталонный
носитель, далее — прочие модули). История изменений и согласований ведётся через
`AuditEvent` и `Approval`/`ApprovalStep` — отдельные таблицы не дублируются.

Признак `overdue` не хранится, а вычисляется (`due_at < now` и статус не
терминальный), чтобы не портить модель данных (PROCESS_CORE_PLAN.md §1.2).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

# Единый справочник видов процессов (PROCESS_CORE_PLAN.md §1.4).
PROCESS_KINDS = (
    "project", "task", "design", "construction", "construction_control",
    "incoming_control", "operational_control", "acceptance_control",
    "executive_docs", "contract", "procurement", "warehouse_movement",
    "equipment", "finance_payment", "closing_docs", "correspondence",
    "claim_work", "personnel_clearance", "labor_safety", "daily_report",
    "defect", "prescription", "approval", "risk", "ai_proposal",
)

RISK_LEVELS = ("R1", "R2", "R3", "R4")

# Профиль риска по умолчанию для вида процесса (пороги настраиваются в 0038).
DEFAULT_RISK_BY_KIND: dict[str, str] = {
    "finance_payment": "R3",
    "closing_docs": "R3",
    "contract": "R3",
    "claim_work": "R3",
    "acceptance_control": "R3",
    "construction_control": "R3",
    "defect": "R2",
    "prescription": "R2",
    "operational_control": "R2",
    "incoming_control": "R2",
    "labor_safety": "R3",
    "correspondence": "R2",
}

# Терминальные состояния — далее допустимо только архивирование.
TERMINAL_STATUSES = ("completed", "cancelled", "rejected", "archived")


class WorkflowProcess(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "workflow_processes"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True, index=True
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sites.id"), nullable=True
    )
    process_kind: Mapped[str] = mapped_column(String(48))
    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_level: Mapped[str] = mapped_column(String(2), default="R1")
    priority: Mapped[str] = mapped_column(String(16), default="normal")
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    executor_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    # разделение ответственности (PROCESS_CORE_PLAN.md §1.1, §1.3)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    initiator_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    responsible_manager_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    primary_executor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    co_executor_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    watcher_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # сроки и вехи
    start_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reschedule_count: Mapped[int] = mapped_column(Integer, default=0)

    # связи с исходными сущностями модулей (без дублирования данных)
    related_document_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    related_material_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    source_kind: Mapped[str | None] = mapped_column(String(48), nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
