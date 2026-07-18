"""Тесты RBAC — серверная проверка разрешений (T-1.C3)."""

import uuid

from app.core.security import hash_password
from app.models import Permission, Role, RolePermission, User, UserRole
from app.services.access import get_permission_codes, has_permission


def _user_with_role(session, role_code, perm_codes=()):
    user = User(id=uuid.uuid4(), email=f"{role_code}@ex.com", password_hash=hash_password("x"))
    role = Role(code=role_code, name=role_code)
    session.add_all([user, role])
    session.flush()
    session.add(UserRole(user_id=user.id, role_id=role.id))
    for pc in perm_codes:
        perm = Permission(code=pc)
        session.add(perm)
        session.flush()
        session.add(RolePermission(role_id=role.id, permission_id=perm.id))
    session.commit()
    return user


def test_has_permission_positive_and_negative(db_session) -> None:
    user = _user_with_role(db_session, "foreman", ["task.create"])
    assert has_permission(db_session, user.id, "task.create") is True
    assert has_permission(db_session, user.id, "finance.approve") is False
    assert "task.create" in get_permission_codes(db_session, user.id)


def test_system_owner_bypasses(db_session) -> None:
    owner = _user_with_role(db_session, "system_owner")
    # системный владелец имеет доступ ко всем разрешениям
    assert has_permission(db_session, owner.id, "anything.at.all") is True
