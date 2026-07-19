"""Бизнес-логика рабочего ядра Badrudin AI OS.

Минимальный управленческий цикл (CLAUDE.md §31): проекты и объекты → задачи и
поручения → согласование руководителем → исполнение → ежедневный отчёт →
отражение в сводке. Переиспользует существующие сущности `projects`, `sites`,
`project_members`, `tasks`, `task_assignments`, `task_updates`, `approvals`,
`approval_steps`, `daily_reports`; все значимые действия — в `audit_events`.
Согласование поручения — R2 (человек в контуре).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Approval,
    ApprovalStep,
    DailyReport,
    Project,
    ProjectMember,
    Site,
    Task,
    TaskAssignment,
    TaskUpdate,
    User,
)
from app.services.access import accessible_project_ids, can_access_project
from app.services.audit import record_event

APPROVAL_RISK = "R2"


class CoreStateError(RuntimeError):
    """Недопустимый переход состояния сущности ядра."""


class CoreValidationError(RuntimeError):
    """Нарушение бизнес-правила ядра."""


# ------------------------------ Проекты --------------------------------- #


def create_project(
    session: Session,
    *,
    user: User,
    organization_id: uuid.UUID,
    name: str,
    project_type: str = "construction",
    code: str | None = None,
    description: str | None = None,
) -> Project:
    """Создаёт проект; автор (сотрудник) становится участником-владельцем (ABAC)."""
    project = Project(
        organization_id=organization_id, name=name, project_type=project_type,
        code=code, description=description, status="active", created_by=user.id,
    )
    session.add(project)
    session.flush()
    if user.employee_id is not None:
        session.add(
            ProjectMember(
                project_id=project.id, employee_id=user.employee_id,
                project_role="owner", responsibility="Ответственный за проект",
            )
        )
    record_event(
        session, actor_type="user", action="project.created", actor_user_id=user.id,
        organization_id=organization_id, entity_type="project", entity_id=project.id,
        new_values={"name": name}, commit=False,
    )
    session.commit()
    return project


def create_site(
    session: Session, project: Project, *, user: User, name: str,
    address: str | None = None, code: str | None = None,
) -> Site:
    """Создаёт объект (площадку) в рамках проекта."""
    site = Site(
        organization_id=project.organization_id, project_id=project.id,
        name=name, address=address, code=code, status="active", created_by=user.id,
    )
    session.add(site)
    session.flush()
    record_event(
        session, actor_type="user", action="site.created", actor_user_id=user.id,
        organization_id=project.organization_id, entity_type="site", entity_id=site.id,
        new_values={"name": name, "project_id": str(project.id)}, commit=False,
    )
    session.commit()
    return site


# ------------------------------- Задачи --------------------------------- #


def create_task(
    session: Session, project: Project, *, user: User, title: str,
    description: str | None = None, site_id: uuid.UUID | None = None,
    owner_employee_id: uuid.UUID | None = None, due_at: datetime | None = None,
    priority: str = "normal",
) -> Task:
    """Создаёт поручение (черновик)."""
    task = Task(
        organization_id=project.organization_id, project_id=project.id, site_id=site_id,
        title=title, description=description, status="draft", priority=priority,
        risk_level=APPROVAL_RISK, due_at=due_at, owner_employee_id=owner_employee_id,
        approval_required=True, created_by_user_id=user.id, created_by=user.id,
    )
    session.add(task)
    session.flush()
    record_event(
        session, actor_type="user", action="task.created", actor_user_id=user.id,
        organization_id=project.organization_id, entity_type="task", entity_id=task.id,
        new_values={"title": title}, commit=False,
    )
    session.commit()
    return task


def submit_task(session: Session, task: Task, *, user: User) -> Approval:
    """Отправляет поручение на согласование руководителю (R2)."""
    if task.status not in ("draft",):
        raise CoreStateError(f"нельзя отправить на согласование из '{task.status}'")
    approval = Approval(
        organization_id=task.organization_id, entity_type="task", entity_id=task.id,
        approval_type="task_approval", requested_by_user_id=user.id,
        status="pending", current_step=1,
    )
    session.add(approval)
    session.flush()
    task.status = "pending_approval"
    record_event(
        session, actor_type="user", action="task.submitted", actor_user_id=user.id,
        organization_id=task.organization_id, entity_type="task", entity_id=task.id,
        approval_id=approval.id, risk_level=APPROVAL_RISK, commit=False,
    )
    session.commit()
    return approval


def assign_task(
    session: Session, task: Task, *, user: User, employee_id: uuid.UUID,
    role: str = "executor",
) -> TaskAssignment:
    """Назначает исполнителя утверждённого поручения."""
    if task.status not in ("approved", "assigned", "sent"):
        raise CoreStateError("назначать исполнителя можно после согласования")
    assignment = TaskAssignment(
        task_id=task.id, employee_id=employee_id, assignment_role=role,
        status="assigned", assigned_by=user.id,
    )
    session.add(assignment)
    task.status = "assigned"
    record_event(
        session, actor_type="user", action="task.assigned", actor_user_id=user.id,
        organization_id=task.organization_id, entity_type="task", entity_id=task.id,
        new_values={"employee_id": str(employee_id)}, commit=False,
    )
    session.commit()
    return assignment


def accept_task(session: Session, task: Task, *, user: User) -> Task:
    """Исполнитель подтверждает получение поручения."""
    if task.status not in ("assigned", "sent"):
        raise CoreStateError("подтвердить получение можно только назначенного поручения")
    task.status = "accepted"
    session.add(TaskUpdate(task_id=task.id, author_user_id=user.id, update_type="status_change", message="Поручение принято"))
    record_event(
        session, actor_type="user", action="task.accepted", actor_user_id=user.id,
        organization_id=task.organization_id, entity_type="task", entity_id=task.id, commit=False,
    )
    session.commit()
    return task


def update_task_progress(
    session: Session, task: Task, *, user: User, progress_percent: int | None = None,
    message: str | None = None,
) -> Task:
    """Фиксирует ход исполнения поручения."""
    if task.status in ("completed", "closed", "cancelled"):
        raise CoreStateError("нельзя менять завершённое поручение")
    if task.status in ("accepted", "assigned"):
        task.status = "in_progress"
    session.add(TaskUpdate(
        task_id=task.id, author_user_id=user.id, update_type="progress",
        message=message, progress_percent=progress_percent,
    ))
    record_event(
        session, actor_type="user", action="task.progress", actor_user_id=user.id,
        organization_id=task.organization_id, entity_type="task", entity_id=task.id,
        new_values={"progress": progress_percent}, commit=False,
    )
    session.commit()
    return task


def complete_task(session: Session, task: Task, *, user: User, note: str | None = None) -> Task:
    """Завершает поручение (с отметкой о результате)."""
    if task.status not in ("in_progress", "accepted", "pending_review"):
        raise CoreStateError(f"нельзя завершить из состояния '{task.status}'")
    task.status = "completed"
    task.completed_at = datetime.now(UTC)
    session.add(TaskUpdate(
        task_id=task.id, author_user_id=user.id, update_type="completion_report",
        message=note or "Поручение выполнено", progress_percent=100,
    ))
    record_event(
        session, actor_type="user", action="task.completed", actor_user_id=user.id,
        organization_id=task.organization_id, entity_type="task", entity_id=task.id, commit=False,
    )
    session.commit()
    return task


# ----------------------------- Согласования ----------------------------- #


def decide_approval(
    session: Session, approval: Approval, *, user: User, decision: str,
    comment: str | None = None,
) -> Approval:
    """Решение руководителя по согласованию (поручение/отчёт). Человек в контуре."""
    if decision not in ("approved", "rejected"):
        raise CoreStateError(f"неизвестное решение '{decision}'")
    if approval.status != "pending":
        raise CoreStateError("согласование уже завершено")
    session.add(ApprovalStep(
        approval_id=approval.id, step_number=approval.current_step,
        approver_user_id=user.id, decision=decision, comment=comment,
        decided_at=datetime.now(UTC),
    ))
    approval.status = decision
    approval.completed_at = datetime.now(UTC)
    # Отражаем решение в связанной сущности.
    if approval.entity_type == "task":
        task = session.get(Task, approval.entity_id)
        if task is not None:
            task.status = "approved" if decision == "approved" else "returned_for_revision"
    elif approval.entity_type == "daily_report":
        report = session.get(DailyReport, approval.entity_id)
        if report is not None:
            report.status = "approved" if decision == "approved" else "draft"
            if decision == "approved":
                report.approved_at = datetime.now(UTC)
    record_event(
        session, actor_type="user", action=f"approval.{decision}", actor_user_id=user.id,
        organization_id=approval.organization_id, entity_type=approval.entity_type,
        entity_id=approval.entity_id, approval_id=approval.id, reason=comment,
        risk_level=APPROVAL_RISK, commit=False,
    )
    session.commit()
    return approval


# --------------------------- Ежедневные отчёты -------------------------- #


def create_daily_report(
    session: Session, project: Project, *, user: User, report_date: date,
    site_id: uuid.UUID | None = None, workers_count: int | None = None,
    summary: str | None = None, work_completed: str | None = None,
    problems: str | None = None, plan_next_day: str | None = None,
) -> DailyReport:
    """Создаёт ежедневный отчёт прораба (черновик)."""
    report = DailyReport(
        project_id=project.id, site_id=site_id, report_date=report_date,
        reporting_employee_id=user.employee_id, workers_count=workers_count,
        summary=summary, work_completed=work_completed, problems=problems,
        plan_next_day=plan_next_day, status="draft", created_by=user.id,
    )
    session.add(report)
    session.flush()
    record_event(
        session, actor_type="user", action="daily_report.created", actor_user_id=user.id,
        organization_id=project.organization_id, entity_type="daily_report",
        entity_id=report.id, commit=False,
    )
    session.commit()
    return report


def submit_daily_report(session: Session, report: DailyReport, project: Project, *, user: User) -> Approval:
    """Отправляет ежедневный отчёт на проверку руководителю."""
    if report.status not in ("draft",):
        raise CoreStateError(f"нельзя отправить отчёт из '{report.status}'")
    approval = Approval(
        organization_id=project.organization_id, entity_type="daily_report",
        entity_id=report.id, approval_type="daily_report_review",
        requested_by_user_id=user.id, status="pending", current_step=1,
    )
    session.add(approval)
    session.flush()
    report.status = "submitted"
    report.submitted_at = datetime.now(UTC)
    record_event(
        session, actor_type="user", action="daily_report.submitted", actor_user_id=user.id,
        organization_id=project.organization_id, entity_type="daily_report",
        entity_id=report.id, approval_id=approval.id, commit=False,
    )
    session.commit()
    return approval


# ------------------------------ Дашборд --------------------------------- #


@dataclass
class DashboardSummary:
    projects: int
    sites: int
    tasks_open: int
    tasks_overdue: int
    approvals_pending: int
    reports_today: int
    tasks_completed: int


def _accessible_filter(session: Session, user: User):
    """Возвращает множество доступных проектов (None — без ограничения)."""
    return accessible_project_ids(session, user)


def dashboard_summary(session: Session, user: User, organization_id: uuid.UUID) -> DashboardSummary:
    """Сводка директора по доступным проектам (агрегация текущего состояния)."""
    allowed = _accessible_filter(session, user)

    projects_q = select(Project).where(
        Project.organization_id == organization_id, Project.deleted_at.is_(None)
    )
    if allowed is not None:
        projects_q = projects_q.where(Project.id.in_(allowed or [uuid.uuid4()]))
    projects = list(session.execute(projects_q).scalars())
    project_ids = [p.id for p in projects]

    def _by_projects(model, col):
        if not project_ids:
            return []
        return list(session.execute(select(model).where(col.in_(project_ids))).scalars())

    sites = _by_projects(Site, Site.project_id)
    tasks = _by_projects(Task, Task.project_id)
    now = datetime.now(UTC)

    def _overdue(t: Task) -> bool:
        if t.due_at is None or t.status in ("completed", "closed", "cancelled"):
            return False
        due = t.due_at if t.due_at.tzinfo else t.due_at.replace(tzinfo=UTC)
        return due < now

    open_tasks = [t for t in tasks if t.status not in ("completed", "closed", "cancelled")]
    completed = [t for t in tasks if t.status == "completed"]
    overdue = [t for t in tasks if _overdue(t)]
    reports_today = [
        r for r in _by_projects(DailyReport, DailyReport.project_id)
        if r.report_date == date.today()
    ]
    pending = list(session.execute(
        select(Approval).where(
            Approval.organization_id == organization_id, Approval.status == "pending"
        )
    ).scalars())
    if allowed is not None:
        pending = [a for a in pending if _approval_in_scope(session, a, project_ids)]

    return DashboardSummary(
        projects=len(projects), sites=len(sites), tasks_open=len(open_tasks),
        tasks_overdue=len(overdue), approvals_pending=len(pending),
        reports_today=len(reports_today), tasks_completed=len(completed),
    )


def _approval_in_scope(session: Session, approval: Approval, project_ids: list[uuid.UUID]) -> bool:
    if approval.entity_type == "task":
        t = session.get(Task, approval.entity_id)
        return t is not None and t.project_id in project_ids
    if approval.entity_type == "daily_report":
        r = session.get(DailyReport, approval.entity_id)
        return r is not None and r.project_id in project_ids
    return True


def can_access(session: Session, user: User, project_id: uuid.UUID) -> bool:
    return can_access_project(session, user, project_id)
