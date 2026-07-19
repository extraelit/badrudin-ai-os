"""Pydantic-схемы модуля «Персонал объектов» (запросы и ответы API)."""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, Field


# ------------------------------ Работники -------------------------------- #


class WorkerAssignmentIn(BaseModel):
    employee_id: uuid.UUID
    brigade: str | None = None
    profession: str | None = None
    is_responsible: bool = False
    start_date: date | None = None


class WorkerAssignmentOut(BaseModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    full_name: str | None = None
    brigade: str | None = None
    profession: str | None = None
    is_responsible: bool
    status: str
    clearance_status: str | None = None


# -------------------------------- Смены ---------------------------------- #


class ShiftIn(BaseModel):
    employee_id: uuid.UUID
    work_date: date
    shift_type: str = "day"
    arrival_time: str | None = None
    departure_time: str | None = None
    hours_worked: float = Field(0, ge=0)
    overtime_hours: float = Field(0, ge=0)
    idle_hours: float = Field(0, ge=0)
    absence_type: str | None = None
    required_permits: list[str] = Field(default_factory=list)


class ShiftOut(BaseModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    work_date: date
    shift_type: str
    hours_worked: float
    overtime_hours: float
    idle_hours: float
    absence_type: str | None
    status: str


# ------------------------------ Начисления ------------------------------- #


class PayrollLineOut(BaseModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    scheme: str
    rate: str
    quantity: str
    unit: str | None
    accrued: str
    advance: str
    deduction: str
    to_pay: str
    status: str


class PayrollDraftOut(BaseModel):
    id: uuid.UUID
    site_id: uuid.UUID
    period_start: date
    period_end: date
    status: str
    total_accrued: str
    total_advance: str
    total_deduction: str
    total_to_pay: str
    currency: str
    risk_level: str
    approval_id: uuid.UUID | None
    lines: list[PayrollLineOut] = Field(default_factory=list)


class PayoutDecisionIn(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    comment: str | None = None
    # код MFA обязателен для подтверждения выплаты уровня R4 (D-002)
    mfa_code: str | None = None


# ------------------------------- Охрана труда ---------------------------- #


class SafetyClearanceOut(BaseModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    full_name: str | None = None
    intro_briefing_at: date | None
    primary_briefing_at: date | None
    targeted_briefing_at: date | None
    signed_by_worker: bool
    medical_valid_until: date | None
    status: str
    permits: list[dict] = Field(default_factory=list)


# ------------------------------- Журналы --------------------------------- #


class JournalOut(BaseModel):
    id: uuid.UUID
    site_id: uuid.UUID
    journal_type: str
    responsible_employee_id: uuid.UUID | None
    status: str
    due_date: date | None
    attachments_count: int


# ------------------------------ Сводка ----------------------------------- #


class SiteSummaryRow(BaseModel):
    site_id: uuid.UUID
    site_name: str
    workers: int
    on_site: int
    hours_day: float
    overtime: float
    idle: float
    without_clearance: int
    unfilled_journals: int


class DirectorSummaryOut(BaseModel):
    sites: list[SiteSummaryRow]
    total_workers: int
    total_on_site: int
    total_without_clearance: int
    total_unfilled_journals: int
