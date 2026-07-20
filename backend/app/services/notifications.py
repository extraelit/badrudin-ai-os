"""Бизнес-логика центра уведомлений (in-app), ROADMAP MVP §18/§24/§31.

Персональные уведомления пользователя (канал `in_app`) поверх существующей таблицы
`notifications` — отдельная миграция не требуется. Модуль НЕ отправляет внешних
сообщений: канал только `in_app` (внешняя рассылка — отдельный утверждённый контур,
§14). Пользователь видит и отмечает прочитанными ТОЛЬКО свои уведомления. Внутренние
уведомления другим адресатам создаёт роль с правом `notification.manage`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Employee, Notification, User
from app.services.audit import record_event

UNREAD_STATUSES = ("pending", "delivered", "unread")


class NotificationError(RuntimeError):
    """Нарушение правил центра уведомлений."""


def _recipient_filter(user: User):
    """Условие «уведомление адресовано этому пользователю» (по user_id и employee_id)."""
    conds = [Notification.recipient_user_id == user.id]
    if user.employee_id is not None:
        conds.append(Notification.recipient_employee_id == user.employee_id)
    return or_(*conds)


def list_my(
    session: Session, user: User, *, only_unread: bool = False, limit: int = 100,
) -> list[Notification]:
    stmt = select(Notification).where(
        Notification.channel == "in_app",
        _recipient_filter(user),
    )
    if only_unread:
        stmt = stmt.where(Notification.read_at.is_(None))
    return list(session.execute(
        stmt.order_by(Notification.created_at.desc()).limit(limit)
    ).scalars())


def unread_count(session: Session, user: User) -> int:
    return len(list(session.execute(
        select(Notification.id).where(
            Notification.channel == "in_app",
            Notification.read_at.is_(None),
            _recipient_filter(user),
        )
    ).scalars()))


def _owned(session: Session, user: User, notification_id: uuid.UUID) -> Notification:
    n = session.get(Notification, notification_id)
    if n is None or n.channel != "in_app":
        raise NotificationError("уведомление не найдено")
    is_mine = n.recipient_user_id == user.id or (
        user.employee_id is not None and n.recipient_employee_id == user.employee_id
    )
    if not is_mine:
        raise NotificationError("чужое уведомление")
    return n


def mark_read(session: Session, user: User, notification_id: uuid.UUID) -> Notification:
    n = _owned(session, user, notification_id)
    if n.read_at is None:
        n.read_at = datetime.now(UTC)
        n.status = "read"
    session.commit()
    return n


def mark_all_read(session: Session, user: User) -> int:
    now = datetime.now(UTC)
    count = 0
    for n in list_my(session, user, only_unread=True, limit=1000):
        n.read_at = now
        n.status = "read"
        count += 1
    session.commit()
    return count


def create_internal(
    session: Session, *, organization_id: uuid.UUID, user: User, title: str,
    message: str | None = None, recipient_user_id: uuid.UUID | None = None,
    recipient_employee_id: uuid.UUID | None = None, priority: str = "normal",
    entity_type: str | None = None, entity_id: uuid.UUID | None = None,
) -> Notification:
    """Создаёт внутреннее (in_app) уведомление. Внешняя рассылка здесь не выполняется."""
    if recipient_user_id is None and recipient_employee_id is None:
        raise NotificationError("не указан адресат")
    if priority not in ("low", "normal", "high", "critical"):
        raise NotificationError(f"недопустимый приоритет '{priority}'")
    n = Notification(
        organization_id=organization_id, recipient_user_id=recipient_user_id,
        recipient_employee_id=recipient_employee_id, channel="in_app", title=title,
        message=message, entity_type=entity_type, entity_id=entity_id, priority=priority,
        status="unread",
    )
    session.add(n)
    session.flush()
    record_event(
        session, actor_type="user", action="notification.created", actor_user_id=user.id,
        organization_id=organization_id, entity_type="notification", entity_id=n.id,
        new_values={"priority": priority}, risk_level="R0", commit=False,
    )
    session.commit()
    return n


def org_of(session: Session, user: User) -> uuid.UUID | None:
    if user.employee_id is None:
        return None
    emp = session.get(Employee, user.employee_id)
    return emp.organization_id if emp is not None else None
