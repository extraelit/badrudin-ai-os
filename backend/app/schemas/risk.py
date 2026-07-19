"""Pydantic-схемы модуля «Реестр рисков»."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

_LEVEL = "^(low|medium|high)$"


class RiskIn(BaseModel):
    title: str
    description: str | None = None
    category: str = "other"
    probability: str = Field("medium", pattern=_LEVEL)
    impact: str = Field("medium", pattern=_LEVEL)
    project_id: uuid.UUID | None = None
    site_id: uuid.UUID | None = None
    owner_employee_id: uuid.UUID | None = None
    source_type: str | None = None
    source_id: uuid.UUID | None = None
    number: str | None = None


class AssessIn(BaseModel):
    probability: str = Field(pattern=_LEVEL)
    impact: str = Field(pattern=_LEVEL)
    owner_employee_id: uuid.UUID | None = None


class MitigationIn(BaseModel):
    mitigation_plan: str = Field(min_length=1)
    due_at: datetime | None = None
    owner_employee_id: uuid.UUID | None = None


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(accepted|closed|realized)$")
    comment: str | None = None


class RiskOut(BaseModel):
    id: uuid.UUID
    number: str | None
    title: str
    description: str | None
    category: str
    probability: str
    impact: str
    severity: str
    status: str
    project_id: uuid.UUID | None
    owner_employee_id: uuid.UUID | None
    mitigation_plan: str | None
    due_at: datetime | None
    source_type: str | None


class SummaryOut(BaseModel):
    total: int
    open: int
    critical: int
    high: int
    accepted: int
    realized: int
