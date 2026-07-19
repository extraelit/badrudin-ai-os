"""Управленческие сводки руководителю (ROADMAP этап 7, §13 «Управленческие сводки»).

Формирует утреннюю и вечернюю сводку по всей организации на реальных данных,
агрегируя уже существующие модули **без дублирования логики**: задачи и контроль
исполнения (`services.core`, `services.task_control`), финансы, снабжение, склад
(`services.inventory`), отчёты прорабов (`services.field_report`), подотчётные
средства (`services.accountable`) и согласования. Сводка — только чтение; ничего
не изменяет. Доступ — управленческая роль (`management.view`); данные ограничены
организацией пользователя, задачи — доступными проектами (ABAC).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Approval,
    Budget,
    DailyReport,
    DailyReportIssue,
    MaterialRequest,
    PaymentRequest,
    Project,
    PurchaseOrder,
    Task,
    WriteOffDocument,
)
from app.services import accountable as acc_svc
from app.services import field_report as fr_svc
from app.services import inventory as inv_svc
from app.services import task_control as tc_svc
from app.services.access import accessible_project_ids


@dataclass
class ApprovalRef:
    id: uuid.UUID
    entity_type: str
    approval_type: str
    entity_id: uuid.UUID


@dataclass
class TaskRef:
    id: uuid.UUID
    title: str
    status: str
    risk_level: str
    due_at: datetime | None
    escalation_level: int


@dataclass
class Digest:
    kind: str
    generated_at: datetime
    period_label: str
    projects_active: int
    tasks: dict
    approvals_pending: int
    approvals: list[ApprovalRef]
    finance: dict
    procurement: dict
    warehouse: dict
    field_reports: dict
    accountable: dict
    risks: dict
    top_overdue: list[TaskRef] = field(default_factory=list)


def _today_bounds() -> tuple[datetime, datetime]:
    today = datetime.now(UTC).date()
    start = datetime(today.year, today.month, today.day, tzinfo=UTC)
    return start, start.replace(hour=23, minute=59, second=59)


def _count(session: Session, model, *where) -> int:
    return int(session.scalar(select(func.count()).select_from(model).where(*where)) or 0)


def build_digest(
    session: Session, user, organization_id: uuid.UUID, *, kind: str = "morning",
) -> Digest:
    if kind not in ("morning", "evening"):
        kind = "morning"

    org_projects = select(Project.id).where(Project.organization_id == organization_id)

    # --- Задачи и контроль исполнения (ABAC по доступным проектам) --- #
    board = tc_svc.control_board(session, user, organization_id)
    completed_today = _completed_today(session, user, organization_id)
    tasks = {
        "overdue": len(board["overdue"]),
        "blocked": len(board["blocked"]),
        "waiting": len(board["waiting_for_information"]),
        "in_progress": len(board["in_progress"]),
        "pending_review": len(board["pending_review"]),
        "returned_for_revision": len(board["returned_for_revision"]),
        "completed_today": completed_today,
    }
    top_overdue = [
        TaskRef(id=t.id, title=t.title, status=t.status, risk_level=t.risk_level,
                due_at=t.due_at, escalation_level=int(t.escalation_level or 0))
        for t in sorted(board["overdue"], key=lambda x: (x.due_at or datetime.max.replace(tzinfo=UTC)))[:5]
    ]

    # --- Согласования, требующие решения --- #
    pending_approvals = list(session.execute(
        select(Approval).where(
            Approval.organization_id == organization_id, Approval.status == "pending",
        ).order_by(Approval.created_at.desc())
    ).scalars())
    approvals = [
        ApprovalRef(id=a.id, entity_type=a.entity_type, approval_type=a.approval_type,
                    entity_id=a.entity_id)
        for a in pending_approvals[:8]
    ]

    # --- Финансы --- #
    finance = {
        "payment_requests_pending": _count(
            session, PaymentRequest, PaymentRequest.organization_id == organization_id,
            PaymentRequest.status == "pending",
        ),
        "budgets_pending": _count(
            session, Budget, Budget.project_id.in_(org_projects),
            Budget.status == "pending_approval", Budget.deleted_at.is_(None),
        ),
    }

    # --- Снабжение --- #
    procurement = {
        "requests_open": _count(
            session, MaterialRequest, MaterialRequest.organization_id == organization_id,
            MaterialRequest.status.in_(("submitted", "pending_approval", "approved", "reserved", "partially_issued")),
            MaterialRequest.deleted_at.is_(None),
        ),
        "orders_pending": _count(
            session, PurchaseOrder, PurchaseOrder.organization_id == organization_id,
            PurchaseOrder.status == "pending_approval", PurchaseOrder.deleted_at.is_(None),
        ),
        "writeoffs_pending": _count(
            session, WriteOffDocument, WriteOffDocument.organization_id == organization_id,
            WriteOffDocument.status == "pending_approval", WriteOffDocument.deleted_at.is_(None),
        ),
    }

    # --- Склад --- #
    stock = inv_svc.stock_summary(session, organization_id)
    warehouse = {
        "positions": stock["positions"],
        "low_stock": stock["low_stock"],
        "negative_stock": stock["negative_stock"],
        "total_value": str(stock["total_value"]),
    }

    # --- Отчёты прорабов --- #
    fr = fr_svc.report_summary(session, organization_id)
    field_reports = {
        "submitted": fr["submitted"],
        "correction_required": fr["correction_required"],
        "submitted_today": _reports_submitted_today(session, org_projects),
    }

    # --- Подотчётные средства --- #
    acc = acc_svc.accountable_summary(session, organization_id)
    accountable = {
        "advances_open": acc.advances_open,
        "advances_overdue": acc.advances_overdue,
        "outstanding": str(acc.total_outstanding),
    }

    # --- Риски --- #
    risks = {
        "overdue": tasks["overdue"],
        "blocked": tasks["blocked"],
        "high_risk_tasks": _count(
            session, Task, Task.organization_id == organization_id,
            Task.risk_level.in_(("R3", "R4")),
            Task.status.notin_(("completed", "closed", "cancelled")),
            Task.deleted_at.is_(None),
        ),
        "high_severity_issues": _high_severity_issues(session, org_projects),
    }

    label = "Утренняя сводка" if kind == "morning" else "Вечерняя сводка"
    active_projects = _count(
        session, Project, Project.organization_id == organization_id,
        Project.status.in_(("active", "in_progress")), Project.deleted_at.is_(None),
    )
    return Digest(
        kind=kind, generated_at=datetime.now(UTC), period_label=label,
        projects_active=active_projects, tasks=tasks,
        approvals_pending=len(pending_approvals), approvals=approvals,
        finance=finance, procurement=procurement, warehouse=warehouse,
        field_reports=field_reports, accountable=accountable, risks=risks,
        top_overdue=top_overdue,
    )


# ------------------------------ Помощники -------------------------------- #


def _scoped_project_filter(session: Session, user, organization_id: uuid.UUID):
    """Возвращает (условие project_id), учитывающее ABAC доступных проектов."""
    allowed = accessible_project_ids(session, user)
    if allowed is None:
        return Task.project_id.in_(select(Project.id).where(Project.organization_id == organization_id))
    if not allowed:
        return Task.id.is_(None)  # нет доступных проектов
    return Task.project_id.in_(list(allowed))


def _completed_today(session: Session, user, organization_id: uuid.UUID) -> int:
    start, end = _today_bounds()
    return _count(
        session, Task, Task.organization_id == organization_id,
        _scoped_project_filter(session, user, organization_id),
        Task.status == "completed", Task.completed_at.is_not(None),
        Task.completed_at >= start, Task.completed_at <= end,
        Task.deleted_at.is_(None),
    )


def _reports_submitted_today(session: Session, org_projects) -> int:
    start, end = _today_bounds()
    return _count(
        session, DailyReport, DailyReport.project_id.in_(org_projects),
        DailyReport.submitted_at.is_not(None),
        DailyReport.submitted_at >= start, DailyReport.submitted_at <= end,
        DailyReport.deleted_at.is_(None),
    )


def _high_severity_issues(session: Session, org_projects) -> int:
    return int(session.scalar(
        select(func.count()).select_from(DailyReportIssue)
        .join(DailyReport, DailyReportIssue.daily_report_id == DailyReport.id)
        .where(
            DailyReport.project_id.in_(org_projects),
            DailyReportIssue.severity.in_(("warning", "critical", "high")),
        )
    ) or 0)
