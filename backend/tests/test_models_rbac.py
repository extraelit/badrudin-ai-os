"""Тесты ролевой модели (T-1.B3)."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, Permission, Role, RolePermission, User, UserRole


def _engine():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return engine


def test_assign_role_and_permission() -> None:
    engine = _engine()
    with Session(engine) as s:
        role = Role(code="foreman", name="Прораб")
        perm = Permission(code="task.create")
        user = User(email="f@example.com", password_hash="h")
        s.add_all([role, perm, user])
        s.flush()
        s.add(UserRole(user_id=user.id, role_id=role.id))
        s.add(RolePermission(role_id=role.id, permission_id=perm.id))
        s.commit()
        assert s.query(UserRole).count() == 1
        assert s.query(RolePermission).count() == 1


def test_role_code_unique() -> None:
    engine = _engine()
    with Session(engine) as s:
        s.add(Role(code="accountant", name="Бухгалтер"))
        s.commit()
        s.add(Role(code="accountant", name="Дубликат"))
        try:
            s.commit()
            raised = False
        except Exception:
            raised = True
        assert raised
