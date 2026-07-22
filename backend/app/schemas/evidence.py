"""Схемы Evidence Gate (этап D, PR-D2)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class RequirementIn(BaseModel):
    process_kind: str
    evidence_type: str
    required: bool = True
    min_count: int = Field(default=1, ge=1)
    phase: str = "after"
    condition: str | None = None


class RequirementOut(BaseModel):
    id: uuid.UUID
    process_kind: str
    evidence_type: str
    required: bool
    min_count: int
    phase: str
    condition: str | None


class EvidenceIn(BaseModel):
    evidence_type: str
    file_id: uuid.UUID
    note: str | None = None
    captured_phase: str | None = None


class EvidenceOut(BaseModel):
    id: uuid.UUID
    evidence_type: str
    file_id: uuid.UUID
    note: str | None
    captured_phase: str | None
    added_by: uuid.UUID | None
    added_at: datetime


class ExceptionRequestIn(BaseModel):
    evidence_type: str
    reason: str = Field(min_length=1)


class ExceptionDecisionIn(BaseModel):
    approve: bool
    comment: str | None = None


class ExceptionOut(BaseModel):
    id: uuid.UUID
    evidence_type: str
    reason: str
    status: str
    requested_by: uuid.UUID | None
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    decision_comment: str | None


class GateStatusOut(BaseModel):
    satisfied: bool
    missing: list[str]
