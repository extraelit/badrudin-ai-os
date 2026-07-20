"""Бизнес-логика модуля «Мобильный ежедневный отчёт прораба».

Сквозной цикл (§18, DATABASE.md разделы 9, 20, 21): прораб составляет отчёт по
объекту (выполненные работы и объёмы, численность по профессиям, техника,
проблемы и риски, фото/файлы-доказательства, связь с задачами), отправляет на
проверку; руководитель (ПТО) проверяет — утверждает, отклоняет или возвращает на
доработку. Все значимые действия — в `audit_events`; изоляция по проекту (ABAC).

Переиспуются существующие сущности без дублирования: `daily_reports`,
`daily_report_work_items`, `daily_report_headcount`, `daily_report_issues`,
`files` (через `app.services.storage.register_file`, MinIO), `approvals`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Approval,
    ApprovalStep,
    DailyReport,
    DailyReportEquipment,
    DailyReportFile,
    DailyReportHeadcount,
    DailyReportIssue,
    DailyReportWorkItem,
    Project,
    User,
)
from app.services.access import can_access_project
from app.services.audit import record_event
from app.services.storage import UploadValidationError, register_file


class FieldReportError(RuntimeError):
    """Нарушение правил жизненного цикла отчёта прораба."""


# ------------------------------ Доступ (ABAC) ---------------------------- #


def can_access_report(session: Session, user: User, report: DailyReport) -> bool:
    return can_access_project(session, user, report.project_id)


def _project(session: Session, report: DailyReport) -> Project:
    return session.get(Project, report.project_id)


def _require_editable(report: DailyReport) -> None:
    if report.status not in ("draft", "correction_required"):
        raise FieldReportError(
            f"нельзя изменять отчёт в статусе '{report.status}'"
        )


# ------------------------------ Отчёт ------------------------------------ #


def create_report(
    session: Session, project: Project, *, user: User, report_date: date,
    site_id: uuid.UUID | None = None, weather_summary: str | None = None,
    summary: str | None = None, work_completed: str | None = None,
    problems: str | None = None, plan_next_day: str | None = None,
    client_request_id: str | None = None,
) -> DailyReport:
    """Создаёт отчёт прораба. Идемпотентно по `client_request_id` (§18/§23):

    при нестабильной связи мобильная форма может отправиться повторно — повтор с тем
    же ключом не создаёт дубль, а возвращает ранее созданный отчёт того же объекта.
    """
    if client_request_id:
        existing = session.execute(
            select(DailyReport).where(
                DailyReport.project_id == project.id,
                DailyReport.client_request_id == client_request_id,
                DailyReport.deleted_at.is_(None),
            )
        ).scalars().first()
        if existing is not None:
            return existing
    report = DailyReport(
        project_id=project.id, site_id=site_id, report_date=report_date,
        reporting_employee_id=user.employee_id, weather_summary=weather_summary,
        summary=summary, work_completed=work_completed, problems=problems,
        plan_next_day=plan_next_day, status="draft", created_by=user.id,
        client_request_id=client_request_id,
    )
    session.add(report)
    session.flush()
    _audit(session, user, "field_report.created", project.organization_id, report.id,
           {"date": str(report_date)})
    session.commit()
    return report


def add_work_item(
    session: Session, report: DailyReport, *, user: User,
    work_type: str | None = None, task_id: uuid.UUID | None = None,
    estimate_position_id: uuid.UUID | None = None, unit_id: uuid.UUID | None = None,
    planned_quantity: Decimal | None = None, actual_quantity: Decimal = Decimal("0"),
    notes: str | None = None,
) -> DailyReportWorkItem:
    _require_editable(report)
    item = DailyReportWorkItem(
        daily_report_id=report.id, project_id=report.project_id, site_id=report.site_id,
        task_id=task_id, estimate_position_id=estimate_position_id, unit_id=unit_id,
        work_date=report.report_date, work_type=work_type,
        planned_quantity=planned_quantity, actual_quantity=actual_quantity,
        foreman_employee_id=report.reporting_employee_id, notes=notes,
        verification_status="pending",
    )
    session.add(item)
    session.flush()
    _audit(session, user, "field_report.work_item.added", _org(session, report), report.id,
           {"work_type": work_type, "actual_quantity": str(actual_quantity)})
    session.commit()
    return item


def add_headcount(
    session: Session, report: DailyReport, *, user: User, profession: str,
    count: int, employee_id: uuid.UUID | None = None,
) -> DailyReportHeadcount:
    _require_editable(report)
    hc = DailyReportHeadcount(
        daily_report_id=report.id, profession=profession, count=count,
        employee_id=employee_id,
    )
    session.add(hc)
    session.flush()
    _audit(session, user, "field_report.headcount.added", _org(session, report), report.id,
           {"profession": profession, "count": count})
    session.commit()
    return hc


def add_equipment(
    session: Session, report: DailyReport, *, user: User, name: str,
    equipment_type: str | None = None, count: int = 1,
    hours: Decimal = Decimal("0"), status: str = "working", note: str | None = None,
) -> DailyReportEquipment:
    _require_editable(report)
    eq = DailyReportEquipment(
        daily_report_id=report.id, name=name, equipment_type=equipment_type,
        count=count, hours=hours, status=status, note=note,
    )
    session.add(eq)
    session.flush()
    _audit(session, user, "field_report.equipment.added", _org(session, report), report.id,
           {"name": name, "hours": str(hours)})
    session.commit()
    return eq


def add_issue(
    session: Session, report: DailyReport, *, user: User, issue_type: str,
    description: str, severity: str = "info",
) -> DailyReportIssue:
    _require_editable(report)
    issue = DailyReportIssue(
        daily_report_id=report.id, issue_type=issue_type, description=description,
        severity=severity,
    )
    session.add(issue)
    session.flush()
    _audit(session, user, "field_report.issue.added", _org(session, report), report.id,
           {"issue_type": issue_type, "severity": severity})
    session.commit()
    return issue


def attach_evidence(
    session: Session, report: DailyReport, *, user: User, original_name: str,
    content: bytes, mime_type: str | None, kind: str = "photo",
    caption: str | None = None, work_item_id: uuid.UUID | None = None,
    captured_at: datetime | None = None,
) -> DailyReportFile:
    """Регистрирует фото/файл-доказательство (MinIO) и связывает с отчётом."""
    _require_editable(report)
    org_id = _org(session, report)
    file_record = register_file(
        session, organization_id=org_id, original_name=original_name,
        content=content, mime_type=mime_type, uploaded_by=user.id,
        project_id=report.project_id, site_id=report.site_id, commit=False,
    )
    session.flush()
    link = DailyReportFile(
        daily_report_id=report.id, work_item_id=work_item_id, file_id=file_record.id,
        kind=kind, caption=caption, captured_at=captured_at or datetime.now(UTC),
    )
    session.add(link)
    session.flush()
    _audit(session, user, "field_report.evidence.attached", org_id, report.id,
           {"file_id": str(file_record.id), "kind": kind})
    session.commit()
    return link


def submit_report(session: Session, report: DailyReport, *, user: User) -> Approval:
    """Отправляет отчёт на проверку руководителю (ПТО)."""
    if report.status not in ("draft", "correction_required"):
        raise FieldReportError(f"нельзя отправить отчёт из '{report.status}'")
    if not _has_content(session, report):
        raise FieldReportError("отчёт пуст: добавьте работы, численность или проблемы")
    org_id = _org(session, report)
    approval = Approval(
        organization_id=org_id, entity_type="daily_report", entity_id=report.id,
        approval_type="daily_report_review", requested_by_user_id=user.id,
        status="pending", current_step=1,
    )
    session.add(approval)
    session.flush()
    report.status = "submitted"
    report.submitted_at = datetime.now(UTC)
    _audit(session, user, "field_report.submitted", org_id, report.id,
           {"approval_id": str(approval.id)}, approval_id=approval.id)
    session.commit()
    return approval


def review_report(
    session: Session, report: DailyReport, *, user: User, decision: str,
    comment: str | None = None,
) -> DailyReport:
    """Проверка руководителем: approved | rejected | correction_required."""
    if decision not in ("approved", "rejected", "correction_required"):
        raise FieldReportError(f"неизвестное решение '{decision}'")
    if report.status != "submitted":
        raise FieldReportError("проверить можно только отправленный отчёт")
    org_id = _org(session, report)
    approval = session.execute(
        select(Approval).where(
            Approval.entity_type == "daily_report", Approval.entity_id == report.id,
            Approval.status == "pending",
        )
    ).scalars().first()
    if approval is not None:
        approval.status = "approved" if decision == "approved" else "rejected"
        approval.completed_at = datetime.now(UTC)
        session.add(ApprovalStep(
            approval_id=approval.id, step_number=approval.current_step,
            approver_user_id=user.id,
            decision="approved" if decision == "approved" else "rejected",
            comment=comment, decided_at=datetime.now(UTC),
        ))
    report.status = decision
    report.reviewed_by_user_id = user.id
    report.review_comment = comment
    if decision == "approved":
        report.approved_at = datetime.now(UTC)
    _audit(session, user, f"field_report.{decision}", org_id, report.id,
           {"decision": decision},
           approval_id=approval.id if approval is not None else None)
    session.commit()
    return report


# ------------------------------ Чтение ----------------------------------- #


def get_children(session: Session, report: DailyReport) -> dict:
    def _all(model, fk):
        return list(session.execute(select(model).where(fk == report.id)).scalars())

    return {
        "work_items": _all(DailyReportWorkItem, DailyReportWorkItem.daily_report_id),
        "headcount": _all(DailyReportHeadcount, DailyReportHeadcount.daily_report_id),
        "equipment": _all(DailyReportEquipment, DailyReportEquipment.daily_report_id),
        "issues": _all(DailyReportIssue, DailyReportIssue.daily_report_id),
        "files": _all(DailyReportFile, DailyReportFile.daily_report_id),
    }


def report_summary(session: Session, organization_id: uuid.UUID) -> dict:
    def _cnt(*where):
        return int(session.scalar(
            select(func.count()).select_from(DailyReport).where(
                DailyReport.deleted_at.is_(None), *where
            )
        ) or 0)

    # отчёты организации — через проекты организации
    org_projects = select(Project.id).where(Project.organization_id == organization_id)
    return {
        "draft": _cnt(DailyReport.status == "draft", DailyReport.project_id.in_(org_projects)),
        "submitted": _cnt(DailyReport.status == "submitted", DailyReport.project_id.in_(org_projects)),
        "correction_required": _cnt(DailyReport.status == "correction_required", DailyReport.project_id.in_(org_projects)),
        "approved": _cnt(DailyReport.status == "approved", DailyReport.project_id.in_(org_projects)),
    }


# ------------------------------ Помощники -------------------------------- #


def _has_content(session: Session, report: DailyReport) -> bool:
    for model, fk in (
        (DailyReportWorkItem, DailyReportWorkItem.daily_report_id),
        (DailyReportHeadcount, DailyReportHeadcount.daily_report_id),
        (DailyReportIssue, DailyReportIssue.daily_report_id),
    ):
        if session.scalar(select(func.count()).select_from(model).where(fk == report.id)):
            return True
    return bool(report.summary or report.work_completed)


def _org(session: Session, report: DailyReport) -> uuid.UUID:
    project = session.get(Project, report.project_id)
    return project.organization_id


def _audit(session, user, action, org_id, report_id, new_values, *, approval_id=None):
    record_event(
        session, actor_type="user", action=action, actor_user_id=user.id,
        organization_id=org_id, entity_type="daily_report", entity_id=report_id,
        new_values=new_values, approval_id=approval_id, risk_level="R1", commit=False,
    )


__all__ = ["FieldReportError", "UploadValidationError"]
