"""API-тесты «Реестр рисков»: регистрация, оценка (матрица серьёзности), план
снижения, принятие/закрытие, RBAC/ABAC.

Переиспользует projects/sites/employees без дубликатов. Данные обезличены.
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

ALL = ["risk.view", "risk.manage", "risk.approve"]


def _make(db, *, perms=ALL, member=True):
    org = Organization(legal_name="ТЕСТ")
    db.add(org)
    db.flush()
    project = Project(organization_id=org.id, name="Объект", status="active")
    db.add(project)
    db.flush()
    emp = Employee(organization_id=org.id, full_name="Риск-менеджер Тест")
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


def _register(client, project, **kw):
    body = {"title": "Срыв поставки", "category": "supply", "probability": "high",
            "impact": "high", "project_id": str(project.id)}
    body.update(kw)
    return client.post("/risks", json=body)


def test_register_requires_manage(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session, perms=["risk.view"])
    client = _client(db_engine, user)
    assert _register(client, project).status_code == 403


def test_view_requires_permission(db_engine, db_session) -> None:
    *_, user = _make(db_session, perms=["project.view"])
    client = _client(db_engine, user)
    assert client.get("/risks/summary").status_code == 403


def test_severity_matrix(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    client = _client(db_engine, user)
    # high×high → critical
    assert _register(client, project, probability="high", impact="high").json()["severity"] == "critical"
    # low×low → low
    assert _register(client, project, probability="low", impact="low").json()["severity"] == "low"
    # medium×high → high
    assert _register(client, project, probability="medium", impact="high").json()["severity"] == "high"


def test_lifecycle_assess_mitigate_decide(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    client = _client(db_engine, user)
    rid = _register(client, project, probability="low", impact="low").json()["id"]
    assert client.get(f"/risks/{rid}").json()["status"] == "identified"
    # переоценка повышает серьёзность
    a = client.post(f"/risks/{rid}/assess", json={"probability": "high", "impact": "high"})
    assert a.json()["severity"] == "critical" and a.json()["status"] == "assessed"
    # план снижения
    m = client.post(f"/risks/{rid}/mitigation", json={"mitigation_plan": "резервный поставщик"})
    assert m.json()["status"] == "mitigating"
    # принятие человеком
    d = client.post(f"/risks/{rid}/decision", json={"decision": "accepted", "comment": "под контролем"})
    assert d.json()["status"] == "accepted"
    # повторное решение по закрытому нельзя (сначала закроем)
    client.post(f"/risks/{rid}/decision", json={"decision": "closed"})
    assert client.post(f"/risks/{rid}/decision", json={"decision": "closed"}).status_code == 409


def test_decision_requires_approve(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session, perms=["risk.view", "risk.manage"])
    client = _client(db_engine, user)
    rid = _register(client, project).json()["id"]
    assert client.post(f"/risks/{rid}/decision", json={"decision": "accepted"}).status_code == 403


def test_summary_and_filter(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    client = _client(db_engine, user)
    _register(client, project, probability="high", impact="high")
    _register(client, project, title="Мелочь", probability="low", impact="low")
    s = client.get("/risks/summary").json()
    assert s["total"] == 2 and s["open"] == 2 and s["critical"] == 1
    assert len(client.get("/risks?severity=critical").json()) == 1


def test_abac_hides_foreign_project(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session, member=False)
    client = _client(db_engine, user)
    # регистрация на проект без доступа запрещена
    assert _register(client, project).status_code == 403
