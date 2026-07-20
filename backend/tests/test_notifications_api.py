"""API-тесты центра уведомлений (in-app).

Пользователь видит и отмечает прочитанными только свои уведомления; счётчик
непрочитанных; создание внутренних уведомлений — по праву notification.manage;
канал только in_app. Данные обезличены.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_current_user
from app.core import token_store
from app.core.security import hash_password
from app.db.session import get_db
from app.main import app
from app.models import (
    Employee,
    Notification,
    Organization,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)


def _user(db, org, *, perms=()):
    emp = Employee(organization_id=org.id, full_name="Получатель")
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
    for pc in perms:
        p = Permission(code=pc)
        db.add(p)
        db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=p.id))
    db.commit()
    return emp, user


def _notify(db, org, emp, *, title="Уведомление", read=False, channel="in_app"):
    n = Notification(organization_id=org.id, recipient_employee_id=emp.id, channel=channel,
                     title=title, message="текст", priority="normal", status="unread")
    db.add(n)
    db.flush()
    nid = n.id
    db.commit()
    return nid


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


def test_list_and_unread_count(db_engine, db_session) -> None:
    org = Organization(legal_name="ТЕСТ")
    db_session.add(org)
    db_session.flush()
    emp, user = _user(db_session, org)
    _notify(db_session, org, emp, title="A")
    _notify(db_session, org, emp, title="B")
    client = _client(db_engine, user)
    assert len(client.get("/notifications").json()) == 2
    assert client.get("/notifications/unread-count").json()["unread"] == 2


def test_mark_read(db_engine, db_session) -> None:
    org = Organization(legal_name="ТЕСТ")
    db_session.add(org)
    db_session.flush()
    emp, user = _user(db_session, org)
    nid = _notify(db_session, org, emp)
    client = _client(db_engine, user)
    r = client.post(f"/notifications/{nid}/read")
    assert r.status_code == 200 and r.json()["read_at"] is not None
    assert client.get("/notifications/unread-count").json()["unread"] == 0
    assert len(client.get("/notifications?only_unread=true").json()) == 0


def test_cannot_read_others_notification(db_engine, db_session) -> None:
    org = Organization(legal_name="ТЕСТ")
    db_session.add(org)
    db_session.flush()
    emp_a, user_a = _user(db_session, org)
    emp_b, _user_b = _user(db_session, org)
    nid = _notify(db_session, org, emp_b, title="Чужое")
    client = _client(db_engine, user_a)
    # чужое уведомление не видно и недоступно для отметки
    assert nid not in [n["id"] for n in client.get("/notifications").json()]
    assert client.post(f"/notifications/{nid}/read").status_code == 404


def test_mark_all_read(db_engine, db_session) -> None:
    org = Organization(legal_name="ТЕСТ")
    db_session.add(org)
    db_session.flush()
    emp, user = _user(db_session, org)
    _notify(db_session, org, emp, title="A")
    _notify(db_session, org, emp, title="B")
    client = _client(db_engine, user)
    assert client.post("/notifications/read-all").json()["marked"] == 2
    assert client.get("/notifications/unread-count").json()["unread"] == 0


def test_create_requires_manage(db_engine, db_session) -> None:
    org = Organization(legal_name="ТЕСТ")
    db_session.add(org)
    db_session.flush()
    emp, user = _user(db_session, org)
    client = _client(db_engine, user)
    assert client.post("/notifications", json={"title": "X", "recipient_employee_id": str(emp.id)}).status_code == 403


def test_create_internal_in_app(db_engine, db_session) -> None:
    org = Organization(legal_name="ТЕСТ")
    db_session.add(org)
    db_session.flush()
    emp, user = _user(db_session, org, perms=["notification.manage"])
    target_emp, target_user = _user(db_session, org)
    client = _client(db_engine, user)
    r = client.post("/notifications", json={"title": "Внимание", "recipient_employee_id": str(target_emp.id), "priority": "high"})
    assert r.status_code == 201 and r.json()["priority"] == "high"
    # адресат видит уведомление
    tclient = _client(db_engine, target_user)
    assert client is not tclient
    assert len(tclient.get("/notifications").json()) == 1


def test_create_requires_recipient(db_engine, db_session) -> None:
    org = Organization(legal_name="ТЕСТ")
    db_session.add(org)
    db_session.flush()
    emp, user = _user(db_session, org, perms=["notification.manage"])
    client = _client(db_engine, user)
    assert client.post("/notifications", json={"title": "Без адресата"}).status_code == 409
