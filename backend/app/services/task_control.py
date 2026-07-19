"""Бизнес-логика модуля «Контроль исполнения поручений» (ROADMAP этап 4).

Сквозной контроль исполнения задач-поручений (§18, §20, CLAUDE.md §31): запрос
препятствий (блокировка), вопросы и ответы, эскалация по сроку, возврат на
доработку, комментарии, лента активности и уведомления ответственным. Контроль
срока (просрочка) вычисляется по `due_at`. Все значимые действия — в
`audit_events`, лента — в `task_updates`, уведомления — в `notifications`.

Переиспользует существующие сущности без дублирования: `tasks`, `task_updates`,
`task_assignments`, `notifications`, `employees`. Новых таблиц не создаёт —
добавлены только служебные поля контроля (`blocked_reason`, `escalation_level`,
`escalated_at`) в `tasks` (миграция 0021).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Notification,
    Task,
    TaskAssignment,
    TaskUpdate,
    User,
)
from app.services.access import accessible_project_ids, can_access_project
from app.services.audit import record_event

ACTIVE = (
    "approved", "sent", "accepted", "in_progress", "waiting_for_information",
    "blocked", "pending_review", "returned_for_revision", "overdue",
)
CLOSED = ("completed", "closed", "cancelled")


class TaskControlError(RuntimeError):
    """Недопустимый переход состояния при контроле исполнения."""


# ------------------------------ Доступ ----------------------------------- #


def can_access_task(session: Session, user: User, task: Task) -> bool:
    if task.project_id is None:
        return True
    return can_access_project(session, user, task.project_id)


def is_overdue(task: Task, *, now: datetime | None = None) -> bool:
    if task.due_at is None or task.status in CLOSED:
        return False
    due = task.due_at if task.due_at.tzinfo else task.due_at.replace(tzinfo=UTC)
    return due < (now or datetime.now(UTC))


# ------------------------------ Действия --------------------------------- #


def raise_blocker(
    session: Session, task: Task, *, user: User, category: str, message: str,
) -> Task:
    """Прораб/исполнитель фиксирует препятствие → задача блокируется."""
    if task.status not in ("accepted", "in_progress", "sent", "waiting_for_information"):
        raise TaskControlError(f"нельзя заявить препятствие из статуса '{task.status}'")
    task.status = "blocked"
    task.blocked_reason = message
    _log(session, task, user, "blocker", message, blocker_category=category)
    _notify_owner(session, task, "Препятствие по поручению",
                  f"{task.title}: {message}", priority="high")
    _audit(session, user, "task.blocked", task, {"category": category})
    session.commit()
    return task


def resolve_blocker(session: Session, task: Task, *, user: User, message: str | None = None) -> Task:
    if task.status != "blocked":
        raise TaskControlError("снять препятствие можно только у заблокированной задачи")
    task.status = "in_progress"
    task.blocked_reason = None
    _log(session, task, user, "status_change", message or "Препятствие устранено")
    _audit(session, user, "task.blocker_resolved", task, {})
    session.commit()
    return task


def ask_question(session: Session, task: Task, *, user: User, message: str) -> Task:
    if task.status not in ("accepted", "in_progress", "sent"):
        raise TaskControlError(f"нельзя задать вопрос из статуса '{task.status}'")
    task.status = "waiting_for_information"
    _log(session, task, user, "question", message)
    _notify_owner(session, task, "Вопрос по поручению", f"{task.title}: {message}")
    _audit(session, user, "task.question_raised", task, {})
    session.commit()
    return task


def answer_question(session: Session, task: Task, *, user: User, message: str) -> Task:
    if task.status != "waiting_for_information":
        raise TaskControlError("ответить можно только на задачу, ожидающую информацию")
    task.status = "in_progress"
    _log(session, task, user, "answer", message)
    _notify_assignees(session, task, "Получен ответ по поручению", f"{task.title}: {message}")
    _audit(session, user, "task.question_answered", task, {})
    session.commit()
    return task


def escalate(session: Session, task: Task, *, user: User, message: str | None = None) -> Task:
    """Эскалация поручения (просрочка/затянувшееся препятствие) руководителю."""
    if task.status in CLOSED:
        raise TaskControlError("нельзя эскалировать завершённое поручение")
    task.escalation_level = int(task.escalation_level or 0) + 1
    task.escalated_at = datetime.now(UTC)
    if is_overdue(task) and task.status not in ("blocked", "waiting_for_information"):
        task.status = "overdue"
    reason = message or f"Эскалация уровня {task.escalation_level}"
    _log(session, task, user, "escalation", reason)
    _notify_owner(session, task, "Эскалация поручения",
                  f"{task.title}: {reason}", priority="high")
    _audit(session, user, "task.escalated", task, {"level": task.escalation_level})
    session.commit()
    return task


def return_for_revision(session: Session, task: Task, *, user: User, message: str) -> Task:
    """Руководитель возвращает поручение на доработку."""
    if task.status not in ("pending_review", "completed"):
        raise TaskControlError("вернуть на доработку можно поручение на проверке или выполненное")
    task.status = "returned_for_revision"
    _log(session, task, user, "status_change", message)
    _notify_assignees(session, task, "Поручение возвращено на доработку",
                      f"{task.title}: {message}", priority="high")
    _audit(session, user, "task.returned_for_revision", task, {})
    session.commit()
    return task


def add_comment(session: Session, task: Task, *, user: User, message: str) -> TaskUpdate:
    upd = _log(session, task, user, "comment", message)
    _audit(session, user, "task.comment_added", task, {})
    session.commit()
    return upd


def list_activity(session: Session, task: Task) -> list[TaskUpdate]:
    return list(
        session.execute(
            select(TaskUpdate).where(TaskUpdate.task_id == task.id)
            .order_by(TaskUpdate.created_at.asc())
        ).scalars()
    )


# ------------------------------ Обзор ------------------------------------ #


def control_board(session: Session, user: User, organization_id: uuid.UUID) -> dict:
    tasks = _accessible_tasks(session, user, organization_id)
    buckets: dict[str, list[Task]] = {
        "overdue": [], "blocked": [], "waiting_for_information": [],
        "in_progress": [], "pending_review": [], "returned_for_revision": [],
    }
    for t in tasks:
        if is_overdue(t):
            buckets["overdue"].append(t)
        elif t.status in buckets:
            buckets[t.status].append(t)
    return buckets


def list_overdue(session: Session, user: User, organization_id: uuid.UUID) -> list[Task]:
    return [t for t in _accessible_tasks(session, user, organization_id) if is_overdue(t)]


def _accessible_tasks(session: Session, user: User, organization_id: uuid.UUID) -> list[Task]:
    allowed = accessible_project_ids(session, user)
    stmt = select(Task).where(
        Task.organization_id == organization_id, Task.deleted_at.is_(None),
        Task.status.notin_(CLOSED),
    )
    tasks = list(session.execute(stmt).scalars())
    if allowed is None:
        return tasks
    return [t for t in tasks if t.project_id is None or t.project_id in allowed]


# ------------------------------ Уведомления ------------------------------ #


def list_notifications(session: Session, user: User, *, unread_only: bool = False) -> list[Notification]:
    if user.employee_id is None:
        return []
    stmt = select(Notification).where(
        Notification.recipient_employee_id == user.employee_id
    )
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    return list(session.execute(stmt.order_by(Notification.created_at.desc())).scalars())


def mark_notification_read(session: Session, notification: Notification) -> Notification:
    if notification.read_at is None:
        notification.read_at = datetime.now(UTC)
        notification.status = "read"
        session.commit()
    return notification


# ------------------------------ Помощники -------------------------------- #


def _log(session, task, user, update_type, message, *, blocker_category=None, progress=None) -> TaskUpdate:
    upd = TaskUpdate(
        task_id=task.id, author_user_id=user.id, update_type=update_type,
        message=message, blocker_category=blocker_category, progress_percent=progress,
    )
    session.add(upd)
    session.flush()
    return upd


def _notify(session, task, *, employee_id, title, message, priority="normal") -> None:
    if employee_id is None:
        return
    session.add(Notification(
        organization_id=task.organization_id, recipient_employee_id=employee_id,
        channel="in_app", title=title, message=message, entity_type="task",
        entity_id=task.id, priority=priority, status="pending",
    ))


def _notify_owner(session, task, title, message, *, priority="normal") -> None:
    _notify(session, task, employee_id=task.owner_employee_id, title=title,
            message=message, priority=priority)


def _notify_assignees(session, task, title, message, *, priority="normal") -> None:
    for a in session.execute(
        select(TaskAssignment).where(TaskAssignment.task_id == task.id)
    ).scalars():
        _notify(session, task, employee_id=a.employee_id, title=title,
                message=message, priority=priority)


def _audit(session, user, action, task, new_values):
    record_event(
        session, actor_type="user", action=action, actor_user_id=user.id,
        organization_id=task.organization_id, entity_type="task", entity_id=task.id,
        new_values=new_values, risk_level=task.risk_level, commit=False,
    )
