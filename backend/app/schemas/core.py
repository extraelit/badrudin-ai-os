"""Pydantic-схемы рабочего ядра (проекты, объекты, задачи, согласования, отчёты)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


# ------------------------------ Проекты --------------------------------- #


class ProjectIn(BaseModel):
    name: str
    project_type: str = "construction"
    code: str | None = None
    description: str | None = None


class ProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    project_type: str
    code: str | None
    status: str
    completion_percent: int


class SiteIn(BaseModel):
    name: str
    address: str | None = None
    code: str | None = None


class SiteOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    address: str | None
    code: str | None
    status: str


# ------------------------------- Задачи --------------------------------- #


class TaskIn(BaseModel):
    title: str
    description: str | None = None
    site_id: uuid.UUID | None = None
    owner_employee_id: uuid.UUID | None = None
    due_at: datetime | None = None
    priority: str = "normal"


class TaskOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    site_id: uuid.UUID | None
    title: str
    description: str | None
    status: str
    priority: str
    risk_level: str
    due_at: datetime | None
    owner_employee_id: uuid.UUID | None


class AssignIn(BaseModel):
    employee_id: uuid.UUID
    role: str = "executor"


class ProgressIn(BaseModel):
    progress_percent: int | None = Field(None, ge=0, le=100)
    message: str | None = None


class CompleteIn(BaseModel):
    note: str | None = None


# ----------------------------- Согласования ----------------------------- #


class ApprovalOut(BaseModel):
    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    approval_type: str
    status: str
    title: str | None = None


class ApprovalDecisionIn(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    comment: str | None = None


# --------------------------- Ежедневные отчёты -------------------------- #


class DailyReportIn(BaseModel):
    report_date: date
    site_id: uuid.UUID | None = None
    workers_count: int | None = Field(None, ge=0)
    summary: str | None = None
    work_completed: str | None = None
    problems: str | None = None
    plan_next_day: str | None = None


class DailyReportOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    site_id: uuid.UUID | None
    report_date: date
    workers_count: int | None
    summary: str | None
    status: str


# ------------------------------ Дашборд --------------------------------- #


class DashboardOut(BaseModel):
    projects: int
    sites: int
    tasks_open: int
    tasks_overdue: int
    tasks_completed: int
    approvals_pending: int
    reports_today: int
