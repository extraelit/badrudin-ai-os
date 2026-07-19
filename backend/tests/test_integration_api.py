"""API-тесты «Масштабирование интеграций» — внутренний контур: реестр коннекторов,
очередь исходящих сообщений как черновиков на утверждение (без отправки), RBAC/ABAC.

Секреты не хранятся, сообщения не отправляются: статус «approved» означает
готовность к отправке вне модуля. Данные обезличены.
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

ALL = ["integration.view", "integration.manage", "integration.approve"]


def _make(db, *, perms=ALL, member=True):
    org = Organization(legal_name="ТЕСТ")
    db.add(org)
    db.flush()
    project = Project(organization_id=org.id, name="Объект", status="active")
    db.add(project)
    db.flush()
    emp = Employee(organization_id=org.id, full_name="Интегратор Тест")
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


def _draft(client, **kw):
    body = {"channel": "email", "subject": "Тема", "body_text": "Текст письма"}
    body.update(kw)
    return client.post("/integrations/outbound", json=body)


def test_register_connector_requires_manage(db_engine, db_session) -> None:
    *_, user = _make(db_session, perms=["integration.view"])
    client = _client(db_engine, user)
    assert client.post("/integrations/connectors", json={"code": "e", "name": "Email", "channel": "email"}).status_code == 403


def test_connector_registry(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    client = _client(db_engine, user)
    r = client.post("/integrations/connectors", json={"code": "email-main", "name": "Почта", "channel": "email"})
    assert r.status_code == 201 and r.json()["status"] == "draft"
    cid = r.json()["id"]
    # секреты не принимаются/не хранятся — конфигурация отмечается признаком
    s = client.post(f"/integrations/connectors/{cid}/status", json={"status": "configured", "credentials_configured_externally": True})
    assert s.json()["status"] == "configured" and s.json()["credentials_configured_externally"] is True
    # дубликат кода
    assert client.post("/integrations/connectors", json={"code": "email-main", "name": "X", "channel": "email"}).status_code == 409


def test_outbound_draft_approval_no_send(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    client = _client(db_engine, user)
    m = _draft(client, project_id=str(project.id)).json()
    assert m["status"] == "draft"
    mid = m["id"]
    # на утверждение → pending
    assert client.post(f"/integrations/outbound/{mid}/submit").json()["status"] == "pending_approval"
    # утверждение человеком → approved (готово к отправке вне модуля; отправки нет)
    d = client.post(f"/integrations/outbound/{mid}/decision", json={"decision": "approved"})
    assert d.json()["status"] == "approved" and d.json()["approved_at"] is not None
    # статуса «sent» в контуре нет — повторное решение недопустимо
    assert client.post(f"/integrations/outbound/{mid}/decision", json={"decision": "approved"}).status_code == 409


def test_outbound_reject(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    client = _client(db_engine, user)
    mid = _draft(client).json()["id"]
    client.post(f"/integrations/outbound/{mid}/submit")
    r = client.post(f"/integrations/outbound/{mid}/decision", json={"decision": "rejected", "comment": "не согласовано"})
    assert r.json()["status"] == "cancelled"


def test_decision_requires_approve(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session, perms=["integration.view", "integration.manage"])
    client = _client(db_engine, user)
    mid = _draft(client).json()["id"]
    client.post(f"/integrations/outbound/{mid}/submit")
    assert client.post(f"/integrations/outbound/{mid}/decision", json={"decision": "approved"}).status_code == 403


def test_empty_message_cannot_submit(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    client = _client(db_engine, user)
    mid = client.post("/integrations/outbound", json={"channel": "email"}).json()["id"]
    assert client.post(f"/integrations/outbound/{mid}/submit").status_code == 409


def test_summary(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    client = _client(db_engine, user)
    client.post("/integrations/connectors", json={"code": "tg", "name": "Telegram", "channel": "telegram"})
    _draft(client)
    s = client.get("/integrations/summary").json()
    assert s["connectors_total"] == 1 and s["outbound_draft"] == 1
