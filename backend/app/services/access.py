"""Помощники доступа: роли и права пользователя (T-1.C2, T-1.C3).

Используется для проверки обязательности MFA (ACCESS_CONTROL.md раздел 19) и
для ролевой авторизации RBAC (раздел 4).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from datetime import UTC, datetime

from app.models import (
    Permission,
    ProjectAccess,
    ProjectMember,
    Role,
    RolePermission,
    User,
    UserRole,
)


def get_role_codes(session: Session, user_id: uuid.UUID) -> set[str]:
    rows = session.execute(
        select(Role.code)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
    ).all()
    return {r[0] for r in rows}


def get_permission_codes(session: Session, user_id: uuid.UUID) -> set[str]:
    rows = session.execute(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id)
    ).all()
    return {r[0] for r in rows}


# роль полного доступа (обходит проверку конкретного разрешения)
SUPER_ROLE = "system_owner"


def has_permission(session: Session, user_id: uuid.UUID, code: str) -> bool:
    """Проверяет наличие разрешения у пользователя (RBAC, серверная проверка)."""
    roles = get_role_codes(session, user_id)
    if SUPER_ROLE in roles:
        return True
    return code in get_permission_codes(session, user_id)


def accessible_project_ids(session: Session, user: User) -> set[uuid.UUID] | None:
    """Множество доступных пользователю проектов (ABAC, изоляция по объектам).

    Возвращает None, если доступ не ограничен (роль полного доступа).
    Основа доступа — членство в проекте (`project_members`); дополнительные
    правила временного доступа добавляются в T-1.C5.
    """
    if SUPER_ROLE in get_role_codes(session, user.id):
        return None
    ids: set[uuid.UUID] = set()
    if user.employee_id is not None:
        rows = session.execute(
            select(ProjectMember.project_id).where(
                ProjectMember.employee_id == user.employee_id
            )
        ).all()
        ids.update(r[0] for r in rows)
    # временный/дополнительный доступ с проверкой срока действия (T-1.C5)
    ids.update(_active_grant_project_ids(session, user.id))
    return ids


def _as_aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _active_grant_project_ids(
    session: Session, user_id: uuid.UUID
) -> set[uuid.UUID]:
    now = datetime.now(UTC)
    result: set[uuid.UUID] = set()
    for grant in session.execute(
        select(ProjectAccess).where(ProjectAccess.user_id == user_id)
    ).scalars():
        vf = _as_aware(grant.valid_from)
        vu = _as_aware(grant.valid_until)
        if (vf is None or vf <= now) and (vu is None or vu >= now):
            result.add(grant.project_id)
    return result


def can_access_project(
    session: Session, user: User, project_id: uuid.UUID
) -> bool:
    allowed = accessible_project_ids(session, user)
    return allowed is None or project_id in allowed
