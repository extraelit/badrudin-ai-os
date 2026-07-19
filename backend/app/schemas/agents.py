"""Pydantic-схемы модуля «Оркестратор ИИ-агентов»."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AgentIn(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str
    agent_type: str | None = None
    description: str | None = None
    default_risk_level: str = "R1"
    requires_human_approval: bool = True


class AgentStatusIn(BaseModel):
    status: str = Field(pattern="^(active|inactive|suspended)$")


class AgentOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    agent_type: str | None
    status: str
    default_risk_level: str
    requires_human_approval: bool


class RunIn(BaseModel):
    trigger_type: str = "manual"
    input_summary: str | None = None
    project_id: uuid.UUID | None = None


class RunResultIn(BaseModel):
    status: str = Field(pattern="^(completed|failed)$")
    output_summary: str | None = None
    error_message: str | None = None


class RunOut(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    status: str
    trigger_type: str | None
    input_summary: str | None
    output_summary: str | None
    risk_level: str


class ProposalIn(BaseModel):
    proposal_type: str = Field(pattern="^(task|document|warning|material_request|risk|note)$")
    title: str
    summary: str | None = None
    run_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    risk_level: str | None = None


class ReviewIn(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    comment: str | None = None


class ProposalOut(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    run_id: uuid.UUID | None
    proposal_type: str
    title: str
    summary: str | None
    risk_level: str
    status: str
    project_id: uuid.UUID | None
    applied_entity_type: str | None
    applied_entity_id: uuid.UUID | None
    decided_at: datetime | None


class SummaryOut(BaseModel):
    agents_total: int
    agents_active: int
    proposals_pending: int
    proposals_approved: int
    proposals_rejected: int
