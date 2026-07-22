"""API процессного ядра `/processes` (этап D, PR-D1).

Backend — единственная точка доступа. RBAC переиспользует права задач-поручений
(эталонный носитель процесса): `task.view` (просмотр), `task.create` (создание/
согласование/перенос), `task.assign` (назначение/смена исполнителя/отмена),
`task.execute` (принятие/старт/отправка на проверку), `task.approve` (согласование/
проверка результата). ABAC: процессы с проектом ограничены доступом к проекту.
Инварианты жизненного цикла и SoD проверяются в сервисном слое. Действия — в аудит.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.api.pagination import PageParams, page_params, paginate
from app.db.session import get_db
from app.models import Employee, User, WorkflowProcess
from app.schemas.workflow import (
    AssignIn,
    ChangeExecutorIn,
    CommentIn,
    ProcessIn,
    ProcessOut,
    ReasonIn,
    RescheduleIn,
    ReviewIn,
)
from app.services import workflow as svc
from app.services.access import can_access_project

router = APIRouter(prefix="/processes", tags=["processes"])


def _org(db: Session, user: User) -> uuid.UUID:
    if user.employee_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пользователь не связан с сотрудником")
    emp = db.get(Employee, user.employee_id)
    return emp.organization_id


def _out(p: WorkflowProcess) -> ProcessOut:
    return ProcessOut(
        id=p.id, organization_id=p.organization_id, project_id=p.project_id,
        process_kind=p.process_kind, title=p.title, description=p.description,
        risk_level=p.risk_level, status=p.status, overdue=svc.is_overdue(p),
        priority=p.priority, author_user_id=p.author_user_id,
        initiator_user_id=p.initiator_user_id,
        responsible_manager_id=p.responsible_manager_id,
        primary_executor_id=p.primary_executor_id, due_at=p.due_at,
        accepted_at=p.accepted_at, submitted_at=p.submitted_at,
        completed_at=p.completed_at, reschedule_count=p.reschedule_count,
        executor_comment=p.executor_comment, reviewer_comment=p.reviewer_comment,
    )


def _process(db: Session, user: User, pid: uuid.UUID) -> WorkflowProcess:
    p = db.get(WorkflowProcess, pid)
    if p is None or p.deleted_at is not None or p.organization_id != _org(db, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Процесс не найден")
    if p.project_id is not None and not can_access_project(db, user, p.project_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к проекту")
    return p


def _guard(exc: svc.WorkflowError) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


@router.get("/", response_model=list[ProcessOut])
def list_processes(
    current: User = Depends(require_permission("task.view")),
    db: Session = Depends(get_db),
    page: PageParams = Depends(page_params),
) -> list[ProcessOut]:
    org = _org(db, current)
    rows = (
        db.query(WorkflowProcess)
        .filter(
            WorkflowProcess.organization_id == org,
            WorkflowProcess.deleted_at.is_(None),
        )
        .order_by(WorkflowProcess.created_at.desc())
        .all()
    )
    visible = [
        p for p in rows
        if p.project_id is None or can_access_project(db, current, p.project_id)
    ]
    return [_out(p) for p in paginate(visible, page)]


@router.post("/", response_model=ProcessOut, status_code=201)
def create_process(
    payload: ProcessIn,
    current: User = Depends(require_permission("task.create")),
    db: Session = Depends(get_db),
) -> ProcessOut:
    if payload.project_id is not None and not can_access_project(db, current, payload.project_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к проекту")
    try:
        p = svc.create_process(
            db, _org(db, current), process_kind=payload.process_kind,
            title=payload.title, description=payload.description,
            project_id=payload.project_id, risk_level=payload.risk_level,
            due_at=payload.due_at, author_user_id=current.id,
        )
    except svc.WorkflowError as exc:
        raise _guard(exc) from exc
    db.commit()
    return _out(p)


@router.get("/{pid}", response_model=ProcessOut)
def get_process(
    pid: uuid.UUID,
    current: User = Depends(require_permission("task.view")),
    db: Session = Depends(get_db),
) -> ProcessOut:
    return _out(_process(db, current, pid))


def _act(db, p, fn, **kw):
    from app.services.evidence import EvidenceGateError

    try:
        fn(db, p, **kw)
    except (svc.WorkflowError, EvidenceGateError) as exc:
        raise _guard(exc) from exc
    db.commit()
    return _out(p)


@router.post("/{pid}/submit-approval", response_model=ProcessOut)
def submit_approval(pid: uuid.UUID,
                    current: User = Depends(require_permission("task.create")),
                    db: Session = Depends(get_db)) -> ProcessOut:
    p = _process(db, current, pid)
    return _act(db, p, svc.submit_for_approval, actor_user_id=current.id)


@router.post("/{pid}/approve", response_model=ProcessOut)
def approve(pid: uuid.UUID,
            current: User = Depends(require_permission("task.approve")),
            db: Session = Depends(get_db)) -> ProcessOut:
    p = _process(db, current, pid)
    return _act(db, p, svc.approve, approver_user_id=current.id)


@router.post("/{pid}/reject", response_model=ProcessOut)
def reject(pid: uuid.UUID, payload: ReasonIn,
           current: User = Depends(require_permission("task.approve")),
           db: Session = Depends(get_db)) -> ProcessOut:
    p = _process(db, current, pid)
    return _act(db, p, svc.reject, approver_user_id=current.id, reason=payload.reason)


@router.post("/{pid}/assign", response_model=ProcessOut)
def assign(pid: uuid.UUID, payload: AssignIn,
           current: User = Depends(require_permission("task.assign")),
           db: Session = Depends(get_db)) -> ProcessOut:
    p = _process(db, current, pid)
    return _act(db, p, svc.assign, initiator_user_id=current.id,
                executor_id=payload.executor_id,
                responsible_manager_id=payload.responsible_manager_id,
                due_at=payload.due_at)


@router.post("/{pid}/accept", response_model=ProcessOut)
def accept(pid: uuid.UUID,
           current: User = Depends(require_permission("task.execute")),
           db: Session = Depends(get_db)) -> ProcessOut:
    p = _process(db, current, pid)
    return _act(db, p, svc.accept, actor_user_id=current.id)


@router.post("/{pid}/start", response_model=ProcessOut)
def start(pid: uuid.UUID,
          current: User = Depends(require_permission("task.execute")),
          db: Session = Depends(get_db)) -> ProcessOut:
    p = _process(db, current, pid)
    return _act(db, p, svc.start, actor_user_id=current.id)


@router.post("/{pid}/submit-review", response_model=ProcessOut)
def submit_review(pid: uuid.UUID, payload: CommentIn,
                  current: User = Depends(require_permission("task.execute")),
                  db: Session = Depends(get_db)) -> ProcessOut:
    p = _process(db, current, pid)
    return _act(db, p, svc.submit_for_review, actor_user_id=current.id,
                executor_comment=payload.executor_comment)


@router.post("/{pid}/review", response_model=ProcessOut)
def review(pid: uuid.UUID, payload: ReviewIn,
           current: User = Depends(require_permission("task.approve")),
           db: Session = Depends(get_db)) -> ProcessOut:
    p = _process(db, current, pid)
    return _act(db, p, svc.review, reviewer_user_id=current.id,
                decision=payload.decision, comment=payload.comment)


@router.post("/{pid}/reschedule", response_model=ProcessOut)
def reschedule(pid: uuid.UUID, payload: RescheduleIn,
               current: User = Depends(require_permission("task.assign")),
               db: Session = Depends(get_db)) -> ProcessOut:
    p = _process(db, current, pid)
    return _act(db, p, svc.reschedule, actor_user_id=current.id,
                new_due_at=payload.new_due_at, reason=payload.reason,
                approved_by_manager=payload.approved_by_manager)


@router.post("/{pid}/change-executor", response_model=ProcessOut)
def change_executor(pid: uuid.UUID, payload: ChangeExecutorIn,
                    current: User = Depends(require_permission("task.assign")),
                    db: Session = Depends(get_db)) -> ProcessOut:
    p = _process(db, current, pid)
    return _act(db, p, svc.change_executor, actor_user_id=current.id,
                new_executor_id=payload.new_executor_id, reason=payload.reason)


@router.post("/{pid}/cancel", response_model=ProcessOut)
def cancel(pid: uuid.UUID, payload: ReasonIn,
           current: User = Depends(require_permission("task.assign")),
           db: Session = Depends(get_db)) -> ProcessOut:
    p = _process(db, current, pid)
    return _act(db, p, svc.cancel, actor_user_id=current.id, reason=payload.reason)


@router.post("/{pid}/archive", response_model=ProcessOut)
def archive(pid: uuid.UUID,
            current: User = Depends(require_permission("task.assign")),
            db: Session = Depends(get_db)) -> ProcessOut:
    p = _process(db, current, pid)
    return _act(db, p, svc.archive, actor_user_id=current.id)
