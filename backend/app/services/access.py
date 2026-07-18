"""Помощники доступа: роли и права пользователя (T-1.C2, T-1.C3).

Используется для проверки обязательности MFA (ACCESS_CONTROL.md раздел 19) и
для ролевой авторизации RBAC (раздел 4).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Permission, Role, RolePermission, UserRole


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
