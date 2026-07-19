"""API-тесты «Оркестратор ИИ-агентов»: реестр, запуски, предложения агента с
обязательным человеческим утверждением и применением через общий сервис,
RBAC/ABAC.

Переиспользует существующие ai_agents, agent_runs и tasks без дубликатов. Данные
обезличены. Фактический вызов модели не производится — проверяется governance-контур.
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
    Task,
    User,
    UserRole,
)

VIEW = ["agent.view"]
ALL = ["agent.view", "agent.manage", "agent.approve", "task.create"]


def _make(db, *, perms=ALL, member=True):
    org = Organization(legal_name="ТЕСТ")
    db.add(org)
    db.flush()
    project = Project(organization_id=org.id, name="Объект", status="active")
    db.add(project)
    db.flush()
    emp = Employee(organization_id=org.id, full_name="Оператор Тест")
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
        db.add(ProjectMember(project_id=project.id, employee_id=emp.id, project_role="operator"))
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


def _agent(client, code="assistant"):
    return client.post("/agents", json={"code": f"{code}-{uuid.uuid4().hex[:6]}", "name": "Ассистент"}).json()["id"]


def test_register_requires_manage(db_engine, db_session) -> None:
    *_, user = _make(db_session, perms=VIEW)
    client = _client(db_engine, user)
    assert client.post("/agents", json={"code": "x", "name": "y"}).status_code == 403


def test_run_requires_active_agent(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    client = _client(db_engine, user)
    aid = _agent(client)
    # неактивный агент — запуск запрещён
    assert client.post(f"/agents/{aid}/runs", json={}).status_code == 409
    client.post(f"/agents/{aid}/status", json={"status": "active"})
    assert client.post(f"/agents/{aid}/runs", json={"input_summary": "анализ"}).status_code == 201


def test_proposal_requires_human_approval_before_apply(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    client = _client(db_engine, user)
    aid = _agent(client)
    client.post(f"/agents/{aid}/status", json={"status": "active"})
    run = client.post(f"/agents/{aid}/runs", json={"input_summary": "смена"}).json()
    client.post(f"/agents/runs/{run['id']}/result", json={"status": "completed", "output_summary": "готово"})
    prop = client.post(f"/agents/{aid}/proposals", json={
        "proposal_type": "task", "title": "Проверить объект", "project_id": str(project.id),
        "run_id": run["id"]}).json()
    pid = prop["id"]
    # применять неутверждённое предложение нельзя
    assert client.post(f"/agents/proposals/{pid}/apply").status_code == 409
    # утверждение человеком
    r = client.post(f"/agents/proposals/{pid}/review", json={"decision": "approved"})
    assert r.json()["status"] == "approved"
    # применение → создаётся поручение (переиспользование общего сервиса)
    ap = client.post(f"/agents/proposals/{pid}/apply")
    assert ap.status_code == 200
    assert ap.json()["status"] == "applied" and ap.json()["applied_entity_type"] == "task"
    tid = ap.json()["applied_entity_id"]
    assert db_session.get(Task, uuid.UUID(tid)) is not None


def test_reject_proposal(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    client = _client(db_engine, user)
    aid = _agent(client)
    client.post(f"/agents/{aid}/status", json={"status": "active"})
    pid = client.post(f"/agents/{aid}/proposals", json={
        "proposal_type": "warning", "title": "Риск срыва срока"}).json()["id"]
    r = client.post(f"/agents/proposals/{pid}/review", json={"decision": "rejected", "comment": "не подтверждено"})
    assert r.json()["status"] == "rejected"
    # применить отклонённое нельзя
    assert client.post(f"/agents/proposals/{pid}/apply").status_code == 409


def test_review_requires_approve_permission(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session, perms=["agent.view", "agent.manage"])
    client = _client(db_engine, user)
    aid = _agent(client)
    client.post(f"/agents/{aid}/status", json={"status": "active"})
    pid = client.post(f"/agents/{aid}/proposals", json={"proposal_type": "note", "title": "Заметка"}).json()["id"]
    assert client.post(f"/agents/proposals/{pid}/review", json={"decision": "approved"}).status_code == 403


def test_duplicate_agent_code_409(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    client = _client(db_engine, user)
    r = client.post("/agents", json={"code": "unique-code", "name": "A"})
    assert r.status_code == 201
    assert client.post("/agents", json={"code": "unique-code", "name": "B"}).status_code == 409


def test_summary_and_list(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    client = _client(db_engine, user)
    aid = _agent(client)
    client.post(f"/agents/{aid}/status", json={"status": "active"})
    client.post(f"/agents/{aid}/proposals", json={"proposal_type": "note", "title": "N1"})
    s = client.get("/agents/summary").json()
    assert s["agents_total"] == 1 and s["agents_active"] == 1 and s["proposals_pending"] == 1
    assert len(client.get("/agents/proposals?status=pending").json()) == 1
