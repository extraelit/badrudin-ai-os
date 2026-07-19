"""Pydantic-схемы модуля «Мобильный ежедневный отчёт прораба»."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class ReportIn(BaseModel):
    report_date: date
    site_id: uuid.UUID | None = None
    weather_summary: str | None = None
    summary: str | None = None
    work_completed: str | None = None
    problems: str | None = None
    plan_next_day: str | None = None


class ReportOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    site_id: uuid.UUID | None
    report_date: date
    status: str
    summary: str | None
    reviewed_by_user_id: uuid.UUID | None = None
    review_comment: str | None = None
    submitted_at: datetime | None = None


class WorkItemIn(BaseModel):
    work_type: str | None = None
    task_id: uuid.UUID | None = None
    estimate_position_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None
    planned_quantity: float | None = None
    actual_quantity: float = Field(0, ge=0)
    notes: str | None = None


class WorkItemOut(BaseModel):
    id: uuid.UUID
    work_type: str | None
    task_id: uuid.UUID | None
    actual_quantity: str
    planned_quantity: str | None
    verification_status: str


class HeadcountIn(BaseModel):
    profession: str
    count: int = Field(0, ge=0)
    employee_id: uuid.UUID | None = None


class HeadcountOut(BaseModel):
    id: uuid.UUID
    profession: str
    count: int


class EquipmentIn(BaseModel):
    name: str
    equipment_type: str | None = None
    count: int = Field(1, ge=0)
    hours: float = Field(0, ge=0)
    status: str = "working"
    note: str | None = None


class EquipmentOut(BaseModel):
    id: uuid.UUID
    name: str
    equipment_type: str | None
    count: int
    hours: str
    status: str


class IssueIn(BaseModel):
    issue_type: str = Field(pattern="^(idle|materials|incident|equipment|risk)$")
    description: str
    severity: str = "info"


class IssueOut(BaseModel):
    id: uuid.UUID
    issue_type: str
    description: str
    severity: str


class EvidenceIn(BaseModel):
    original_name: str
    mime_type: str
    content_base64: str
    kind: str = "photo"
    caption: str | None = None
    work_item_id: uuid.UUID | None = None


class EvidenceOut(BaseModel):
    id: uuid.UUID
    file_id: uuid.UUID
    kind: str
    caption: str | None
    original_name: str | None = None


class ReviewIn(BaseModel):
    decision: str = Field(pattern="^(approved|rejected|correction_required)$")
    comment: str | None = None


class ReportDetailOut(ReportOut):
    weather_summary: str | None = None
    work_completed: str | None = None
    problems: str | None = None
    plan_next_day: str | None = None
    work_items: list[WorkItemOut] = Field(default_factory=list)
    headcount: list[HeadcountOut] = Field(default_factory=list)
    equipment: list[EquipmentOut] = Field(default_factory=list)
    issues: list[IssueOut] = Field(default_factory=list)
    evidence: list[EvidenceOut] = Field(default_factory=list)


class ReportSummaryOut(BaseModel):
    draft: int
    submitted: int
    correction_required: int
    approved: int
