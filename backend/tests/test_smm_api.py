"""API-тесты «SMM и внешние публикации» — внутренний контур: контент-план,
публикации как черновики на утверждение (без публикации), обязательные проверки,
RBAC/ABAC.

Публикация модулем не выполняется: статусы «approved»/«scheduled» означают
готовность к публикации официальным инструментом вне модуля. Данные обезличены.
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

ALL = ["smm.view", "smm.manage", "smm.approve"]


def _make(db, *, perms=ALL, member=True):
    org = Organization(legal_name="ТЕСТ")
    db.add(org)
    db.flush()
    project = Project(organization_id=org.id, name="Объект", status="active")
    db.add(project)
    db.flush()
    emp = Employee(organization_id=org.id, full_name="SMM Тест")
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
        db.add(ProjectMember(project_id=project.id, employee_id=emp.id, project_role="pm"))
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


def _pub(client, **kw):
    body = {"channel": "instagram", "title": "Ход работ", "body_text": "Смонтировали фасад."}
    body.update(kw)
    return client.post("/smm/publications", json=body)


def _pass_checks(client, pid):
    return client.post(f"/smm/publications/{pid}/checks", json={
        "rights_confirmed": True, "pii_checked": True, "legal_checked": True})


def test_create_plan_requires_manage(db_engine, db_session) -> None:
    *_, user = _make(db_session, perms=["smm.view"])
    client = _client(db_engine, user)
    assert client.post("/smm/plan", json={"title": "Идея"}).status_code == 403


def test_content_plan(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    client = _client(db_engine, user)
    r = client.post("/smm/plan", json={"title": "Серия про объект", "channel": "instagram", "project_id": str(project.id)})
    assert r.status_code == 201 and r.json()["status"] == "idea"
    pid = r.json()["id"]
    s = client.post(f"/smm/plan/{pid}/status", json={"status": "planned"})
    assert s.json()["status"] == "planned"
    assert len(client.get("/smm/plan").json()) == 1


def test_publication_requires_checks_before_submit(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    client = _client(db_engine, user)
    p = _pub(client).json()
    assert p["status"] == "draft"
    pid = p["id"]
    # без пройденных проверок отправка на утверждение запрещена
    assert client.post(f"/smm/publications/{pid}/submit").status_code == 409
    _pass_checks(client, pid)
    assert client.post(f"/smm/publications/{pid}/submit").json()["status"] == "pending_approval"


def test_publication_approval_no_publish(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    client = _client(db_engine, user)
    pid = _pub(client).json()["id"]
    _pass_checks(client, pid)
    client.post(f"/smm/publications/{pid}/submit")
    d = client.post(f"/smm/publications/{pid}/decision", json={"decision": "approved"})
    # статуса «published» нет — «approved» = готово к публикации вне модуля
    assert d.json()["status"] == "approved" and d.json()["approved_at"] is not None
    # повторное решение недопустимо
    assert client.post(f"/smm/publications/{pid}/decision", json={"decision": "approved"}).status_code == 409


def test_scheduled_publication(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    client = _client(db_engine, user)
    pid = _pub(client, scheduled_for="2030-01-01T10:00:00Z").json()["id"]
    _pass_checks(client, pid)
    client.post(f"/smm/publications/{pid}/submit")
    d = client.post(f"/smm/publications/{pid}/decision", json={"decision": "approved"})
    # запланировано — но всё ещё не опубликовано модулем
    assert d.json()["status"] == "scheduled"


def test_publication_reject(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    client = _client(db_engine, user)
    pid = _pub(client).json()["id"]
    _pass_checks(client, pid)
    client.post(f"/smm/publications/{pid}/submit")
    r = client.post(f"/smm/publications/{pid}/decision", json={"decision": "rejected", "comment": "факты не подтверждены"})
    assert r.json()["status"] == "cancelled"


def test_decision_requires_approve(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session, perms=["smm.view", "smm.manage"])
    client = _client(db_engine, user)
    pid = _pub(client).json()["id"]
    _pass_checks(client, pid)
    client.post(f"/smm/publications/{pid}/submit")
    assert client.post(f"/smm/publications/{pid}/decision", json={"decision": "approved"}).status_code == 403


def test_assets_and_summary(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    client = _client(db_engine, user)
    client.post("/smm/plan", json={"title": "План"})
    pid = _pub(client).json()["id"]
    a = client.post(f"/smm/publications/{pid}/assets", json={"caption": "Фасад", "quality_ok": True, "rights_ok": True})
    assert a.status_code == 201 and a.json()["quality_ok"] is True
    assert len(client.get(f"/smm/publications/{pid}/assets").json()) == 1
    s = client.get("/smm/summary").json()
    assert s["plan_total"] == 1 and s["publications_draft"] == 1
