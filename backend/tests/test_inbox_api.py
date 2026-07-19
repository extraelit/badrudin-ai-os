"""API-тесты «Единый входящий поток»: приём, классификация, назначение,
конверсия в задачу, отклонение, сводка, RBAC/ABAC.

Переиспользует существующие сущности (communications, tasks, projects,
employees, counterparties) без дубликатов. Данные обезличены.
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
    Organization,
    Permission,
    Project,
    ProjectMember,
    Role,
    RolePermission,
    User,
    UserRole,
)

VIEW = ["inbox.view"]
ALL = ["inbox.view", "inbox.manage", "task.create", "task.view"]


def _make(db, *, perms=ALL, member=True):
    org = Organization(legal_name="ТЕСТ")
    db.add(org)
    db.flush()
    project = Project(organization_id=org.id, name="Объект", status="active")
    db.add(project)
    db.flush()
    emp = Employee(organization_id=org.id, full_name="Диспетчер Тест")
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
    if member:
        db.add(ProjectMember(project_id=project.id, employee_id=emp.id, project_role="dispatcher"))
    db.commit()
    return org, project, emp, user


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


def _capture(client, subject="Заявка от заказчика", channel="email"):
    return client.post("/inbox", json={"subject": subject, "body_text": "нужен монтаж", "channel": channel})


def test_capture_requires_manage(db_engine, db_session) -> None:
    *_, user = _make(db_session, perms=VIEW)
    client = _client(db_engine, user)
    assert _capture(client).status_code == 403


def test_view_requires_permission(db_engine, db_session) -> None:
    *_, user = _make(db_session, perms=["project.view"])
    client = _client(db_engine, user)
    assert client.get("/inbox/summary").status_code == 403


def test_capture_classify_convert(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    client = _client(db_engine, user)
    item = _capture(client).json()
    assert item["status"] == "new"
    iid = item["id"]
    # классификация с проектом
    c = client.post(f"/inbox/{iid}/classify", json={
        "category": "request", "priority": "high", "project_id": str(project.id),
        "assigned_to_employee_id": str(emp.id)})
    assert c.json()["status"] == "classified" and c.json()["category"] == "request"
    # конверсия в задачу
    t = client.post(f"/inbox/{iid}/convert-to-task", json={"title": "Монтаж по обращению"})
    assert t.status_code == 201
    got = client.get(f"/inbox/{iid}").json()
    assert got["status"] == "converted" and got["converted_entity_type"] == "task"
    assert got["converted_entity_id"] == t.json()["id"]


def test_convert_without_project_409(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    client = _client(db_engine, user)
    iid = _capture(client).json()["id"]
    # без проекта задачу создать нельзя
    assert client.post(f"/inbox/{iid}/convert-to-task", json={}).status_code == 409


def test_dismiss_and_reprocess_guard(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    client = _client(db_engine, user)
    iid = _capture(client).json()["id"]
    d = client.post(f"/inbox/{iid}/dismiss", json={"reason": "спам"})
    assert d.json()["status"] == "dismissed"
    # повторная обработка запрещена
    assert client.post(f"/inbox/{iid}/classify", json={"category": "other"}).status_code == 409


def test_mark_converted_other_target(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    client = _client(db_engine, user)
    iid = _capture(client).json()["id"]
    r = client.post(f"/inbox/{iid}/mark-converted", json={"entity_type": "risk", "note": "риск срыва"})
    assert r.json()["status"] == "converted" and r.json()["converted_entity_type"] == "risk"


def test_summary_and_list(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    client = _client(db_engine, user)
    _capture(client)
    iid = _capture(client, subject="Вопрос").json()["id"]
    client.post(f"/inbox/{iid}/dismiss", json={"reason": "дубль"})
    s = client.get("/inbox/summary").json()
    assert s["new"] == 1 and s["dismissed"] == 1 and s["unresolved"] == 1
    assert len(client.get("/inbox?status=new").json()) == 1


def test_abac_hides_foreign_project_items(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session, member=False)
    client = _client(db_engine, user)
    iid = _capture(client).json()["id"]
    # привяжем к проекту, к которому нет доступа
    client.post(f"/inbox/{iid}/classify", json={"category": "request", "project_id": str(project.id)})
    # элемент с чужим проектом не виден в списке
    assert all(i["id"] != iid for i in client.get("/inbox").json())
