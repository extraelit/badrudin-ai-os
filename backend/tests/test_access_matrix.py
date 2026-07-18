"""Сквозные тесты авторизации: RBAC-зависимость на маршруте (T-1.C6).

Проверяет серверную проверку прав: доступ разрешается только при наличии
разрешения; отсутствие прав → 403 (позитивные и негативные сценарии).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_current_user, require_permission
from app.core.security import hash_password
from app.db.session import get_db
from app.models import Permission, Role, RolePermission, User, UserRole


def _mk_user(session, role_code, perms=()):
    user = User(id=uuid.uuid4(), email=f"{role_code}@ex.com", password_hash=hash_password("x"))
    role = Role(code=role_code, name=role_code)
    session.add_all([user, role])
    session.flush()
    session.add(UserRole(user_id=user.id, role_id=role.id))
    for pc in perms:
        p = Permission(code=pc)
        session.add(p)
        session.flush()
        session.add(RolePermission(role_id=role.id, permission_id=p.id))
    session.commit()
    return user


def _client_for(db_engine, user) -> TestClient:
    factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)

    def override_db() -> Iterator[Session]:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    guarded = FastAPI()

    @guarded.get("/guarded", dependencies=[Depends(require_permission("task.approve"))])
    def _guarded() -> dict[str, str]:
        return {"status": "ok"}

    guarded.dependency_overrides[get_db] = override_db
    guarded.dependency_overrides[get_current_user] = lambda: user
    return TestClient(guarded)


def test_denied_without_permission(db_engine, db_session) -> None:
    user = _mk_user(db_session, "foreman", perms=["task.create"])
    client = _client_for(db_engine, user)
    assert client.get("/guarded").status_code == 403


def test_allowed_with_permission(db_engine, db_session) -> None:
    user = _mk_user(db_session, "production_director", perms=["task.approve"])
    client = _client_for(db_engine, user)
    assert client.get("/guarded").status_code == 200


def test_system_owner_allowed(db_engine, db_session) -> None:
    user = _mk_user(db_session, "system_owner")
    client = _client_for(db_engine, user)
    assert client.get("/guarded").status_code == 200
