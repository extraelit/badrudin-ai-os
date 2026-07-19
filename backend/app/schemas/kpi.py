"""Pydantic-схемы модуля «KPI и независимый аудит»."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class KpiSummaryOut(BaseModel):
    tasks_total: int
    tasks_completed: int
    tasks_overdue: int
    overdue_ratio: float
    risks_open: int
    risks_high: int
    daily_reports_7d: int
    findings_open: int
    findings_high: int


class FindingIn(BaseModel):
    category: str
    title: str = Field(min_length=1, max_length=500)
    severity: str = Field(default="medium", pattern="^(low|medium|high)$")
    detail: str | None = None
    project_id: uuid.UUID | None = None
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None


class FindingResolveIn(BaseModel):
    status: str = Field(pattern="^(acknowledged|resolved|false_positive)$")
    note: str | None = None


class FindingOut(BaseModel):
    id: uuid.UUID
    category: str
    severity: str
    title: str
    detail: str | None
    entity_type: str | None
    entity_id: uuid.UUID | None
    status: str
    detected_by: str
    project_id: uuid.UUID | None
    owner_user_id: uuid.UUID | None
    resolution_note: str | None
    created_at: datetime


class ScanResultOut(BaseModel):
    created: int
