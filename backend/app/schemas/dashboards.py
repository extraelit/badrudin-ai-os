"""Схемы руководительских панелей (этап H)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class ManagerOverviewOut(BaseModel):
    processes_total: int
    by_status: dict[str, int]
    overdue: int
    pending_approval: int
    submitted_for_review: int
    blocked: int
    evidence_exceptions_pending: int
    quality_pending_finalization: int


class OverdueItemOut(BaseModel):
    id: uuid.UUID
    title: str
    process_kind: str
    risk_level: str
    status: str
    due_at: datetime | None
    primary_executor_id: uuid.UUID | None
    responsible_manager_id: uuid.UUID | None


class ExceptionItemOut(BaseModel):
    id: uuid.UUID
    process_id: uuid.UUID
    evidence_type: str
    reason: str
    status: str


class EscalateOut(BaseModel):
    notifications_created: int
