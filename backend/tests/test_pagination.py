"""Тесты пагинации списков (§13 «пагинация больших списков», §25).

Проверяем аддитивность и безопасность: без параметров возвращается весь список;
`limit`/`offset` дают предсказуемый срез; выход за границы (limit>200, отрицательные)
отклоняется с 422 на границе API. Проверяем на реестре коннекторов интеграций
(список без внутреннего ограничения сервиса).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_current_user
from app.api.pagination import PageParams, paginate
from app.core import token_store
from app.core.security import hash_password
from app.db.session import get_db
from app.main import app
from app.models import (
    Employee,
    Organization,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)

PERMS = ["integration.view", "integration.manage"]


def _make(db):
    org = Organization(legal_name="ТЕСТ")
    db.add(org)
    db.flush()
    emp = Employee(organization_id=org.id, full_name="Интегратор")
    db.add(emp)
    db.flush()
    user = User(email=f"u{uuid.uuid4().hex[:8]}@ex.com", password_hash=hash_password("x"),
                status="active", employee_id=emp.id)
    db.add(user)
    db.flush()
    role = Role(code=f"r{uuid.uuid4().hex[:6]}", name="r")
    db.add(role)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    for pc in PERMS:
        p = Permission(code=pc)
        db.add(p)
        db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=p.id))
    db.commit()
    return org, user


def _client(db_engine, user) -> TestClient:
    factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)

    def override_db() -> Iterator[Session]:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    token_store.clear()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.clear()


# ------------------------- Юнит-тесты помощника -------------------------- #


def test_paginate_helper_default_returns_all() -> None:
    items = list(range(10))
    assert paginate(items, PageParams(limit=None, offset=0)) == items


def test_paginate_helper_limit_offset() -> None:
    items = list(range(10))
    assert paginate(items, PageParams(limit=3, offset=2)) == [2, 3, 4]
    assert paginate(items, PageParams(limit=100, offset=8)) == [8, 9]
    assert paginate(items, PageParams(limit=None, offset=20)) == []


# ------------------------- API-поведение --------------------------------- #


def _seed_connectors(client, n):
    for i in range(n):
        r = client.post("/integrations/connectors", json={"code": f"c{i}", "name": f"К{i}", "channel": "internal"})
        assert r.status_code == 201


def test_api_default_returns_all(db_engine, db_session) -> None:
    org, user = _make(db_session)
    client = _client(db_engine, user)
    _seed_connectors(client, 5)
    assert len(client.get("/integrations/connectors").json()) == 5


def test_api_limit_and_offset(db_engine, db_session) -> None:
    org, user = _make(db_session)
    client = _client(db_engine, user)
    _seed_connectors(client, 5)
    assert len(client.get("/integrations/connectors?limit=2").json()) == 2
    # offset за пределами — пустая страница, а не ошибка
    assert client.get("/integrations/connectors?limit=2&offset=4").json().__len__() == 1
    assert client.get("/integrations/connectors?offset=10").json() == []


def test_api_rejects_out_of_range_limit(db_engine, db_session) -> None:
    org, user = _make(db_session)
    client = _client(db_engine, user)
    assert client.get("/integrations/connectors?limit=0").status_code == 422
    assert client.get("/integrations/connectors?limit=201").status_code == 422
    assert client.get("/integrations/connectors?offset=-1").status_code == 422
