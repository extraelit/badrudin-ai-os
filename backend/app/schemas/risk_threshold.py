"""Схемы настраиваемых порогов согласований (этап G)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, Field


class ThresholdIn(BaseModel):
    metric: str
    risk_level: str
    min_value: Decimal | None = None
    max_value: Decimal | None = None
    process_kind: str | None = None
    project_id: uuid.UUID | None = None
    required_approvals: int = Field(default=1, ge=0)
    requires_mfa: bool = False
    description: str | None = None


class ThresholdOut(BaseModel):
    id: uuid.UUID
    metric: str
    risk_level: str
    min_value: Decimal | None
    max_value: Decimal | None
    process_kind: str | None
    project_id: uuid.UUID | None
    required_approvals: int
    requires_mfa: bool
    description: str | None


class ResolveOut(BaseModel):
    risk_level: str
    required_approvals: int
    requires_mfa: bool
