"""Задачи, назначения, доказательства и согласования (T-1.B5).

Соответствует DATABASE.md разделы 7–8. Поле `risk_level` использует единую
шкалу R0–R4 (D-001; ACCESS_CONTROL.md раздел 9).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
    false,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Task(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "tasks"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sites.id"), nullable=True
    )
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id"), nullable=True
    )
    source_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(String(16), default="normal")
    # draft | pending_approval | approved | sent | accepted | in_progress |
    # waiting_for_information | blocked | pending_review | completed |
    # returned_for_revision | overdue | closed | cancelled
    status: Mapped[str] = mapped_column(String(32), default="draft")
    # единая шкала риска R0–R4 (D-001)
    risk_level: Mapped[str] = mapped_column(String(2), default="R0")
    planned_start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # контроль исполнения: причина текущей блокировки, счётчик и время эскалации
    blocked_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    escalation_level: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    escalated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approval_required: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_by_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True
    )
    owner_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    confidentiality_level: Mapped[str] = mapped_column(String(32), default="internal")


class TaskAssignment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "task_assignments"

    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"))
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))
    # responsible | executor | co_executor | reviewer | observer
    assignment_role: Mapped[str] = mapped_column(String(32), default="executor")
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    response_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default="assigned")
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class TaskUpdate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "task_updates"

    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"))
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    author_agent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    # comment | status_change | progress | blocker | question | answer |
    # reminder | escalation | completion_report
    update_type: Mapped[str] = mapped_column(String(32), default="comment")
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    blocker_category: Mapped[str | None] = mapped_column(String(64), nullable=True)


class TaskEvidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "task_evidence"

    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"))
    # ссылка на файл (FK на files добавляется в T-1.B6)
    file_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    # photo | video | document | act | measurement | invoice | signed_letter |
    # system_record
    evidence_type: Mapped[str] = mapped_column(String(32), default="photo")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    captured_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    verification_status: Mapped[str] = mapped_column(String(32), default="pending")
    verified_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Approval(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "approvals"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    approval_type: Mapped[str] = mapped_column(String(64))
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True
    )
    requested_by_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True
    )
    # pending | in_review | approved | approved_with_conditions | rejected |
    # cancelled | expired
    status: Mapped[str] = mapped_column(String(32), default="pending")
    current_step: Mapped[int] = mapped_column(Integer, default=1)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ApprovalStep(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "approval_steps"

    approval_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("approvals.id"))
    step_number: Mapped[int] = mapped_column(Integer)
    approver_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    approver_role_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
