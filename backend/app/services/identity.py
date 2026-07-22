"""Управление полномочиями сотрудника: назначение/смена роли, отзыв доступа.

Права зависят не только от роли, но и от периода полномочий (ACCESS_CONTROL.md
разделы 4, 19). Перевод/смена должности не переписывает историю: старое
назначение закрывается по дате (`valid_until`), а не удаляется; каждое изменение
фиксируется в журнале аудита. При увольнении/отстранении доступ отзывается
немедленно: учётная запись переводится в статус `revoked` и все действующие роли
закрываются — вход после этого невозможен.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Role, User, UserRole
from app.services.audit import record_event


class IdentityError(Exception):
    """Ошибка операции с полномочиями (нет роли, нет пользователя и т. п.)."""


def _now() -> datetime:
    return datetime.now(UTC)


def _role_by_code(session: Session, code: str) -> Role:
    role = session.scalar(select(Role).where(Role.code == code))
    if role is None:
        raise IdentityError(f"Роль не найдена: {code}")
    return role


def assign_role(
    session: Session,
    user_id: uuid.UUID,
    role_code: str,
    *,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
    actor_user_id: uuid.UUID | None = None,
    reason: str | None = None,
    commit: bool = True,
) -> UserRole:
    """Назначает роль с периодом полномочий.

    Если назначение этой роли уже существует (уникальность user+role), оно
    переоткрывается на новый период; иначе создаётся новая запись.
    """
    role = _role_by_code(session, role_code)
    existing = session.scalar(
        select(UserRole).where(
            UserRole.user_id == user_id, UserRole.role_id == role.id
        )
    )
    if existing is not None:
        existing.valid_from = valid_from or _now()
        existing.valid_until = valid_until
        link = existing
    else:
        link = UserRole(
            user_id=user_id,
            role_id=role.id,
            valid_from=valid_from or _now(),
            valid_until=valid_until,
        )
        session.add(link)
    record_event(
        session,
        actor_type="user",
        action="identity.role.assign",
        actor_user_id=actor_user_id,
        entity_type="user",
        entity_id=user_id,
        new_values={"role": role_code},
        reason=reason,
        risk_level="R2",
        commit=commit,
    )
    return link


def end_role(
    session: Session,
    user_id: uuid.UUID,
    role_code: str,
    *,
    actor_user_id: uuid.UUID | None = None,
    reason: str | None = None,
    commit: bool = True,
) -> None:
    """Закрывает действующее назначение роли текущим моментом (без удаления)."""
    role = _role_by_code(session, role_code)
    link = session.scalar(
        select(UserRole).where(
            UserRole.user_id == user_id, UserRole.role_id == role.id
        )
    )
    if link is not None and (link.valid_until is None or link.valid_until > _now()):
        link.valid_until = _now()
    record_event(
        session,
        actor_type="user",
        action="identity.role.end",
        actor_user_id=actor_user_id,
        entity_type="user",
        entity_id=user_id,
        old_values={"role": role_code},
        reason=reason,
        risk_level="R2",
        commit=commit,
    )


def change_role(
    session: Session,
    user_id: uuid.UUID,
    new_role_code: str,
    *,
    new_position_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    reason: str | None = None,
) -> UserRole:
    """Перевод/смена должности: закрывает все действующие роли и назначает новую.

    По желанию обновляет должность связанного сотрудника (`new_position_id`).
    История сохраняется: прежние назначения закрываются датой, а не удаляются.
    """
    now = _now()
    # закрываем все действующие роли (кроме назначаемой — её переоткроем ниже)
    for ur in session.execute(
        select(UserRole).where(UserRole.user_id == user_id)
    ).scalars():
        if ur.valid_until is None or ur.valid_until > now:
            ur.valid_until = now

    old_position_id: uuid.UUID | None = None
    if new_position_id is not None:
        user = session.get(User, user_id)
        if user is not None and user.employee_id is not None:
            from app.models import Employee

            emp = session.get(Employee, user.employee_id)
            if emp is not None:
                old_position_id = emp.position_id
                emp.position_id = new_position_id

    link = assign_role(
        session,
        user_id,
        new_role_code,
        valid_from=now,
        actor_user_id=actor_user_id,
        reason=reason,
        commit=False,
    )
    record_event(
        session,
        actor_type="user",
        action="identity.role.change",
        actor_user_id=actor_user_id,
        entity_type="user",
        entity_id=user_id,
        old_values={"position_id": str(old_position_id) if old_position_id else None},
        new_values={
            "role": new_role_code,
            "position_id": str(new_position_id) if new_position_id else None,
        },
        reason=reason,
        risk_level="R3",
        commit=True,
    )
    return link


def revoke_user_access(
    session: Session,
    user_id: uuid.UUID,
    *,
    actor_user_id: uuid.UUID | None = None,
    reason: str | None = None,
) -> None:
    """Немедленный отзыв доступа (увольнение/отстранение).

    Учётная запись переводится в статус `revoked`, все действующие роли
    закрываются. Вход после этого невозможен (проверка статуса при аутентификации).
    """
    user = session.get(User, user_id)
    if user is None:
        raise IdentityError("Пользователь не найден")
    now = _now()
    for ur in session.execute(
        select(UserRole).where(UserRole.user_id == user_id)
    ).scalars():
        if ur.valid_until is None or ur.valid_until > now:
            ur.valid_until = now
    prev_status = user.status
    user.status = "revoked"
    record_event(
        session,
        actor_type="user",
        action="identity.access.revoke",
        actor_user_id=actor_user_id,
        entity_type="user",
        entity_id=user_id,
        old_values={"status": prev_status},
        new_values={"status": "revoked"},
        reason=reason,
        risk_level="R3",
        commit=True,
    )
