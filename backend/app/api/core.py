"""API рабочего ядра Badrudin AI OS.

Минимальный управленческий цикл: проекты/объекты → задачи → согласование →
исполнение → ежедневный отчёт → сводка. Backend — единственная точка доступа;
RBAC (`require_permission`) и ABAC (доступ к проекту по членству) проверяются на
сервере; все значимые действия — в `audit_events`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.session import get_db
from app.models import (
    Approval,
    DailyReport,
    Employee,
    Project,
    Site,
    Task,
    User,
)
from app.schemas.core import (
    ApprovalDecisionIn,
    ApprovalOut,
    AssignIn,
    CompleteIn,
    DailyReportIn,
    DailyReportOut,
    DashboardOut,
    ProgressIn,
    ProjectIn,
    ProjectOut,
    SiteIn,
    SiteOut,
    TaskIn,
    TaskOut,
)
from app.services import core as svc

router = APIRouter(prefix="/core", tags=["core"])


# ------------------------------ Помощники ------------------------------- #


def _org_id(db: Session, user: User) -> uuid.UUID:
    if user.employee_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пользователь не связан с сотрудником")
    emp = db.get(Employee, user.employee_id)
    if emp is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Сотрудник не найден")
    return emp.organization_id


def _project(db: Session, user: User, project_id: uuid.UUID) -> Project:
    p = db.get(Project, project_id)
    if p is None or p.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Проект не найден")
    if not svc.can_access(db, user, project_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к проекту")
    return p


def _task(db: Session, user: User, task_id: uuid.UUID) -> Task:
    t = db.get(Task, task_id)
    if t is None or t.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Поручение не найдено")
    if t.project_id is not None:
        _project(db, user, t.project_id)
    return t


# ------------------------------ Проекты --------------------------------- #


def _project_out(p: Project) -> ProjectOut:
    return ProjectOut(id=p.id, name=p.name, project_type=p.project_type, code=p.code,
                      status=p.status, completion_percent=p.completion_percent)


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("project.view")),
) -> list[ProjectOut]:
    org = _org_id(db, user)
    allowed = svc.accessible_project_ids(db, user)
    rows = list(db.execute(
        select(Project).where(Project.organization_id == org, Project.deleted_at.is_(None))
    ).scalars())
    if allowed is not None:
        rows = [p for p in rows if p.id in allowed]
    return [_project_out(p) for p in rows]


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("project.create")),
) -> ProjectOut:
    org = _org_id(db, user)
    p = svc.create_project(
        db, user=user, organization_id=org, name=payload.name,
        project_type=payload.project_type, code=payload.code, description=payload.description,
    )
    return _project_out(p)


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("project.view")),
) -> ProjectOut:
    return _project_out(_project(db, user, project_id))


@router.get("/projects/{project_id}/sites", response_model=list[SiteOut])
def list_sites(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("project.view")),
) -> list[SiteOut]:
    _project(db, user, project_id)
    rows = db.execute(
        select(Site).where(Site.project_id == project_id, Site.deleted_at.is_(None))
    ).scalars()
    return [SiteOut(id=s.id, project_id=s.project_id, name=s.name, address=s.address,
                    code=s.code, status=s.status) for s in rows]


@router.post("/projects/{project_id}/sites", response_model=SiteOut, status_code=status.HTTP_201_CREATED)
def create_site(
    project_id: uuid.UUID,
    payload: SiteIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("site.manage")),
) -> SiteOut:
    project = _project(db, user, project_id)
    s = svc.create_site(db, project, user=user, name=payload.name,
                        address=payload.address, code=payload.code)
    return SiteOut(id=s.id, project_id=s.project_id, name=s.name, address=s.address,
                   code=s.code, status=s.status)


# ------------------------------- Задачи --------------------------------- #


def _task_out(t: Task) -> TaskOut:
    return TaskOut(id=t.id, project_id=t.project_id, site_id=t.site_id, title=t.title,
                   description=t.description, status=t.status, priority=t.priority,
                   risk_level=t.risk_level, due_at=t.due_at, owner_employee_id=t.owner_employee_id)


@router.get("/projects/{project_id}/tasks", response_model=list[TaskOut])
def list_tasks(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("task.view")),
) -> list[TaskOut]:
    _project(db, user, project_id)
    rows = db.execute(
        select(Task).where(Task.project_id == project_id, Task.deleted_at.is_(None))
        .order_by(Task.created_at.desc())
    ).scalars()
    return [_task_out(t) for t in rows]


@router.post("/projects/{project_id}/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    project_id: uuid.UUID,
    payload: TaskIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("task.create")),
) -> TaskOut:
    project = _project(db, user, project_id)
    t = svc.create_task(
        db, project, user=user, title=payload.title, description=payload.description,
        site_id=payload.site_id, owner_employee_id=payload.owner_employee_id,
        due_at=payload.due_at, priority=payload.priority,
    )
    return _task_out(t)


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("task.view")),
) -> TaskOut:
    return _task_out(_task(db, user, task_id))


@router.post("/tasks/{task_id}/submit", response_model=TaskOut)
def submit_task(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("task.create")),
) -> TaskOut:
    task = _task(db, user, task_id)
    try:
        svc.submit_task(db, task, user=user)
    except svc.CoreStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _task_out(task)


@router.post("/tasks/{task_id}/assign", response_model=TaskOut)
def assign_task(
    task_id: uuid.UUID,
    payload: AssignIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("task.assign")),
) -> TaskOut:
    task = _task(db, user, task_id)
    try:
        svc.assign_task(db, task, user=user, employee_id=payload.employee_id, role=payload.role)
    except svc.CoreStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _task_out(task)


@router.post("/tasks/{task_id}/accept", response_model=TaskOut)
def accept_task(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("task.execute")),
) -> TaskOut:
    task = _task(db, user, task_id)
    try:
        svc.accept_task(db, task, user=user)
    except svc.CoreStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _task_out(task)


@router.post("/tasks/{task_id}/progress", response_model=TaskOut)
def task_progress(
    task_id: uuid.UUID,
    payload: ProgressIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("task.execute")),
) -> TaskOut:
    task = _task(db, user, task_id)
    try:
        svc.update_task_progress(db, task, user=user,
                                 progress_percent=payload.progress_percent, message=payload.message)
    except svc.CoreStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _task_out(task)


@router.post("/tasks/{task_id}/complete", response_model=TaskOut)
def complete_task(
    task_id: uuid.UUID,
    payload: CompleteIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("task.execute")),
) -> TaskOut:
    task = _task(db, user, task_id)
    try:
        svc.complete_task(db, task, user=user, note=payload.note)
    except svc.CoreStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _task_out(task)


# ----------------------------- Согласования ----------------------------- #


def _approval_title(db: Session, a: Approval) -> str | None:
    if a.entity_type == "task":
        t = db.get(Task, a.entity_id)
        return t.title if t else None
    if a.entity_type == "daily_report":
        r = db.get(DailyReport, a.entity_id)
        return f"Отчёт от {r.report_date}" if r else None
    return None


@router.get("/approvals", response_model=list[ApprovalOut])
def list_approvals(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("approval.view")),
) -> list[ApprovalOut]:
    org = _org_id(db, user)
    allowed = svc.accessible_project_ids(db, user)
    rows = list(db.execute(
        select(Approval).where(Approval.organization_id == org, Approval.status == "pending")
        .order_by(Approval.created_at.desc())
    ).scalars())
    if allowed is not None:
        rows = [a for a in rows if svc._approval_in_scope(db, a, list(allowed))]
    return [
        ApprovalOut(id=a.id, entity_type=a.entity_type, entity_id=a.entity_id,
                    approval_type=a.approval_type, status=a.status, title=_approval_title(db, a))
        for a in rows
    ]


@router.post("/approvals/{approval_id}/decision", response_model=ApprovalOut)
def decide_approval(
    approval_id: uuid.UUID,
    payload: ApprovalDecisionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("approval.decide")),
) -> ApprovalOut:
    a = db.get(Approval, approval_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Согласование не найдено")
    _org_id(db, user)
    try:
        svc.decide_approval(db, a, user=user, decision=payload.decision, comment=payload.comment)
    except svc.CoreStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return ApprovalOut(id=a.id, entity_type=a.entity_type, entity_id=a.entity_id,
                       approval_type=a.approval_type, status=a.status, title=_approval_title(db, a))


# --------------------------- Ежедневные отчёты -------------------------- #


def _report_out(r: DailyReport) -> DailyReportOut:
    return DailyReportOut(id=r.id, project_id=r.project_id, site_id=r.site_id,
                          report_date=r.report_date, workers_count=r.workers_count,
                          summary=r.summary, status=r.status)


@router.get("/projects/{project_id}/daily-reports", response_model=list[DailyReportOut])
def list_daily_reports(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("daily_report.view")),
) -> list[DailyReportOut]:
    _project(db, user, project_id)
    rows = db.execute(
        select(DailyReport).where(DailyReport.project_id == project_id, DailyReport.deleted_at.is_(None))
        .order_by(DailyReport.report_date.desc())
    ).scalars()
    return [_report_out(r) for r in rows]


@router.post("/projects/{project_id}/daily-reports", response_model=DailyReportOut, status_code=status.HTTP_201_CREATED)
def create_daily_report(
    project_id: uuid.UUID,
    payload: DailyReportIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("daily_report.manage")),
) -> DailyReportOut:
    project = _project(db, user, project_id)
    r = svc.create_daily_report(
        db, project, user=user, report_date=payload.report_date, site_id=payload.site_id,
        workers_count=payload.workers_count, summary=payload.summary,
        work_completed=payload.work_completed, problems=payload.problems,
        plan_next_day=payload.plan_next_day,
    )
    return _report_out(r)


@router.post("/daily-reports/{report_id}/submit", response_model=DailyReportOut)
def submit_daily_report(
    report_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("daily_report.manage")),
) -> DailyReportOut:
    r = db.get(DailyReport, report_id)
    if r is None or r.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Отчёт не найден")
    project = _project(db, user, r.project_id)
    try:
        svc.submit_daily_report(db, r, project, user=user)
    except svc.CoreStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _report_out(r)


# ------------------------------ Дашборд --------------------------------- #


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("project.view")),
) -> DashboardOut:
    org = _org_id(db, user)
    s = svc.dashboard_summary(db, user, org)
    return DashboardOut(
        projects=s.projects, sites=s.sites, tasks_open=s.tasks_open,
        tasks_overdue=s.tasks_overdue, tasks_completed=s.tasks_completed,
        approvals_pending=s.approvals_pending, reports_today=s.reports_today,
    )
