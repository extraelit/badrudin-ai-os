"""Pydantic-схемы модуля «Управленческие сводки руководителю»."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ApprovalRefOut(BaseModel):
    id: uuid.UUID
    entity_type: str
    approval_type: str
    entity_id: uuid.UUID


class TaskRefOut(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    risk_level: str
    due_at: datetime | None
    escalation_level: int


class DigestOut(BaseModel):
    kind: str
    generated_at: datetime
    period_label: str
    projects_active: int
    tasks: dict[str, int]
    approvals_pending: int
    approvals: list[ApprovalRefOut] = Field(default_factory=list)
    finance: dict[str, int]
    procurement: dict[str, int]
    warehouse: dict[str, str | int]
    field_reports: dict[str, int]
    accountable: dict[str, str | int]
    risks: dict[str, int]
    top_overdue: list[TaskRefOut] = Field(default_factory=list)
