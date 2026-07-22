"""Схемы процессного ядра (этап D, PR-D1)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ProcessIn(BaseModel):
    process_kind: str
    title: str = Field(min_length=1, max_length=512)
    description: str | None = None
    project_id: uuid.UUID | None = None
    risk_level: str | None = None
    due_at: datetime | None = None


class AssignIn(BaseModel):
    executor_id: uuid.UUID
    responsible_manager_id: uuid.UUID | None = None
    due_at: datetime | None = None


class ReviewIn(BaseModel):
    decision: str  # completed | revision_required
    comment: str | None = None


class RescheduleIn(BaseModel):
    new_due_at: datetime
    reason: str
    approved_by_manager: bool = False


class ChangeExecutorIn(BaseModel):
    new_executor_id: uuid.UUID
    reason: str


class ReasonIn(BaseModel):
    reason: str | None = None


class CommentIn(BaseModel):
    comment: str | None = None
    executor_comment: str | None = None


class ProcessOut(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID | None
    process_kind: str
    title: str
    description: str | None
    risk_level: str
    status: str
    overdue: bool
    priority: str
    author_user_id: uuid.UUID | None
    initiator_user_id: uuid.UUID | None
    responsible_manager_id: uuid.UUID | None
    primary_executor_id: uuid.UUID | None
    due_at: datetime | None
    accepted_at: datetime | None
    submitted_at: datetime | None
    completed_at: datetime | None
    reschedule_count: int
    executor_comment: str | None
    reviewer_comment: str | None
