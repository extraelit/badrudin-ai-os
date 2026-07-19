"""API модуля «Контроль исполнения поручений».

Backend — единственная точка доступа к данным. RBAC: чтение доски/ленты/
уведомлений — `task.view`; препятствия/вопросы/комментарии (исполнитель) —
`task.execute`; ответы/снятие препятствия/эскалация (контролёр) — `task.assign`;
возврат на доработку (руководитель) — `task.approve`. ABAC: доступ к задаче через
проект. Лента — `task_updates`, уведомления — `notifications`, всё — в `audit_events`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.db.session import get_db
from app.models import Employee, Notification, Task, User
from app.schemas.task_control import (
    ActivityOut,
    BlockerIn,
    BoardOut,
    MessageIn,
    NotificationOut,
    OptionalMessageIn,
    TaskCard,
)
from app.services import task_control as svc

router = APIRouter(prefix="/task-control", tags=["task-control"])


def _org(db: Session, user: User) -> uuid.UUID:
    if user.employee_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пользователь не связан с сотрудником")
    emp = db.get(Employee, user.employee_id)
    return emp.organization_id


def _task(db: Session, user: User, task_id: uuid.UUID) -> Task:
    t = db.get(Task, task_id)
    if t is None or t.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Поручение не найдено")
    if not svc.can_access_task(db, user, t):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к поручению")
    return t


def _card(t: Task) -> TaskCard:
    return TaskCard(
        id=t.id, project_id=t.project_id, title=t.title, status=t.status,
        priority=t.priority, risk_level=t.risk_level, due_at=t.due_at,
        overdue=svc.is_overdue(t), blocked_reason=t.blocked_reason,
        escalation_level=int(t.escalation_level or 0), owner_employee_id=t.owner_employee_id,
    )


def _guard(exc: svc.TaskControlError) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


# ------------------------------- Обзор ----------------------------------- #


@router.get("/board", response_model=BoardOut)
def board(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("task.view")),
) -> BoardOut:
    buckets = svc.control_board(db, user, _org(db, user))
    return BoardOut(**{k: [_card(t) for t in v] for k, v in buckets.items()})


@router.get("/overdue", response_model=list[TaskCard])
def overdue(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("task.view")),
) -> list[TaskCard]:
    return [_card(t) for t in svc.list_overdue(db, user, _org(db, user))]


@router.get("/tasks/{task_id}/activity", response_model=list[ActivityOut])
def activity(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("task.view")),
) -> list[ActivityOut]:
    t = _task(db, user, task_id)
    return [
        ActivityOut(id=u.id, update_type=u.update_type, message=u.message,
                    blocker_category=u.blocker_category, progress_percent=u.progress_percent,
                    created_at=u.created_at)
        for u in svc.list_activity(db, t)
    ]


# ------------------------------ Действия --------------------------------- #


@router.post("/tasks/{task_id}/blocker", response_model=TaskCard)
def raise_blocker(
    task_id: uuid.UUID, payload: BlockerIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("task.execute")),
) -> TaskCard:
    t = _task(db, user, task_id)
    try:
        svc.raise_blocker(db, t, user=user, category=payload.category, message=payload.message)
    except svc.TaskControlError as exc:
        raise _guard(exc) from exc
    return _card(t)


@router.post("/tasks/{task_id}/resolve-blocker", response_model=TaskCard)
def resolve_blocker(
    task_id: uuid.UUID, payload: OptionalMessageIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("task.assign")),
) -> TaskCard:
    t = _task(db, user, task_id)
    try:
        svc.resolve_blocker(db, t, user=user, message=payload.message)
    except svc.TaskControlError as exc:
        raise _guard(exc) from exc
    return _card(t)


@router.post("/tasks/{task_id}/question", response_model=TaskCard)
def ask_question(
    task_id: uuid.UUID, payload: MessageIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("task.execute")),
) -> TaskCard:
    t = _task(db, user, task_id)
    try:
        svc.ask_question(db, t, user=user, message=payload.message)
    except svc.TaskControlError as exc:
        raise _guard(exc) from exc
    return _card(t)


@router.post("/tasks/{task_id}/answer", response_model=TaskCard)
def answer_question(
    task_id: uuid.UUID, payload: MessageIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("task.assign")),
) -> TaskCard:
    t = _task(db, user, task_id)
    try:
        svc.answer_question(db, t, user=user, message=payload.message)
    except svc.TaskControlError as exc:
        raise _guard(exc) from exc
    return _card(t)


@router.post("/tasks/{task_id}/escalate", response_model=TaskCard)
def escalate(
    task_id: uuid.UUID, payload: OptionalMessageIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("task.assign")),
) -> TaskCard:
    t = _task(db, user, task_id)
    try:
        svc.escalate(db, t, user=user, message=payload.message)
    except svc.TaskControlError as exc:
        raise _guard(exc) from exc
    return _card(t)


@router.post("/tasks/{task_id}/return", response_model=TaskCard)
def return_for_revision(
    task_id: uuid.UUID, payload: MessageIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("task.approve")),
) -> TaskCard:
    t = _task(db, user, task_id)
    try:
        svc.return_for_revision(db, t, user=user, message=payload.message)
    except svc.TaskControlError as exc:
        raise _guard(exc) from exc
    return _card(t)


@router.post("/tasks/{task_id}/comment", response_model=ActivityOut, status_code=status.HTTP_201_CREATED)
def add_comment(
    task_id: uuid.UUID, payload: MessageIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("task.execute")),
) -> ActivityOut:
    t = _task(db, user, task_id)
    u = svc.add_comment(db, t, user=user, message=payload.message)
    return ActivityOut(id=u.id, update_type=u.update_type, message=u.message,
                       blocker_category=u.blocker_category, progress_percent=u.progress_percent,
                       created_at=u.created_at)


# ------------------------------ Уведомления ------------------------------ #


def _notif_out(n: Notification) -> NotificationOut:
    return NotificationOut(
        id=n.id, title=n.title, message=n.message, entity_type=n.entity_type,
        entity_id=n.entity_id, priority=n.priority, status=n.status,
        read_at=n.read_at, created_at=n.created_at,
    )


@router.get("/notifications", response_model=list[NotificationOut])
def notifications(
    unread_only: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("task.view")),
) -> list[NotificationOut]:
    return [_notif_out(n) for n in svc.list_notifications(db, user, unread_only=unread_only)]


@router.post("/notifications/{notification_id}/read", response_model=NotificationOut)
def read_notification(
    notification_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("task.view")),
) -> NotificationOut:
    n = db.get(Notification, notification_id)
    if n is None or n.recipient_employee_id != user.employee_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Уведомление не найдено")
    svc.mark_notification_read(db, n)
    return _notif_out(n)
