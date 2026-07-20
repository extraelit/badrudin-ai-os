"""API-тесты «Исполнительная документация ПТО» — ROADMAP этап 12.

Жизненный цикл документа (draft→under_review→approved|rejected), версионирование с
пометкой предыдущей версии `superseded`, контроль обязательного комплекта, RBAC/ABAC.
Утверждение выполняет человек. Данные обезличены.
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
    File,
    Organization,
    Permission,
    Project,
    ProjectMember,
    Role,
    RolePermission,
    User,
    UserRole,
)

ALL = ["pto.view", "pto.manage", "pto.approve"]


def _make(db, *, perms=ALL, member=True):
    org = Organization(legal_name="ТЕСТ")
    db.add(org)
    db.flush()
    project = Project(organization_id=org.id, name="Объект", status="active")
    db.add(project)
    db.flush()
    emp = Employee(organization_id=org.id, full_name="Инженер ПТО Тест")
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
    f = File(organization_id=org.id, storage_key="k/1", original_name="act.pdf")
    db.add(f)
    db.flush()
    file_id = f.id
    db.commit()
    return org, project, emp, user, file_id


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


def _create(client, project_id, file_id, **kw):
    body = {"project_id": str(project_id), "doc_type": "hidden_work_act",
            "title": "Акт скрытых работ №1", "file_id": str(file_id)}
    body.update(kw)
    return client.post("/pto/documents", json=body)


def test_create_requires_manage(db_engine, db_session) -> None:
    org, project, emp, user, fid = _make(db_session, perms=["pto.view"])
    client = _client(db_engine, user)
    assert _create(client, project.id, fid).status_code == 403


def test_lifecycle_approve(db_engine, db_session) -> None:
    org, project, emp, user, fid = _make(db_session)
    client = _client(db_engine, user)
    d = _create(client, project.id, fid).json()
    assert d["status"] == "draft" and d["version_number"] == 1
    did = d["id"]
    assert client.post(f"/pto/documents/{did}/submit").json()["status"] == "under_review"
    r = client.post(f"/pto/documents/{did}/decision", json={"decision": "approved"})
    assert r.json()["status"] == "approved" and r.json()["approved_at"] is not None
    # повторное решение недопустимо
    assert client.post(f"/pto/documents/{did}/decision", json={"decision": "approved"}).status_code == 409


def test_submit_requires_file(db_engine, db_session) -> None:
    org, project, emp, user, fid = _make(db_session)
    client = _client(db_engine, user)
    did = client.post("/pto/documents", json={
        "project_id": str(project.id), "doc_type": "work_log", "title": "Журнал"}).json()["id"]
    assert client.post(f"/pto/documents/{did}/submit").status_code == 409


def test_versioning_supersedes(db_engine, db_session) -> None:
    org, project, emp, user, fid = _make(db_session)
    client = _client(db_engine, user)
    # первая версия — утверждена
    v1 = _create(client, project.id, fid).json()["id"]
    client.post(f"/pto/documents/{v1}/submit")
    client.post(f"/pto/documents/{v1}/decision", json={"decision": "approved"})
    # вторая версия ссылается на первую
    v2 = _create(client, project.id, fid, supersedes_id=v1, title="Акт скрытых работ №1 (ред.)").json()
    assert v2["version_number"] == 2
    client.post(f"/pto/documents/{v2['id']}/submit")
    client.post(f"/pto/documents/{v2['id']}/decision", json={"decision": "approved"})
    # первая версия помечена superseded
    docs = {d["id"]: d for d in client.get("/pto/documents").json()}
    assert docs[v1]["status"] == "superseded"
    assert docs[v2["id"]]["status"] == "approved"


def test_decision_requires_approve(db_engine, db_session) -> None:
    org, project, emp, user, fid = _make(db_session, perms=["pto.view", "pto.manage"])
    client = _client(db_engine, user)
    did = _create(client, project.id, fid).json()["id"]
    client.post(f"/pto/documents/{did}/submit")
    assert client.post(f"/pto/documents/{did}/decision", json={"decision": "approved"}).status_code == 403


def test_completeness(db_engine, db_session) -> None:
    org, project, emp, user, fid = _make(db_session)
    client = _client(db_engine, user)
    c0 = client.get(f"/pto/completeness?project_id={project.id}").json()
    assert c0["complete"] is False and "hidden_work_act" in c0["missing"]
    # утверждаем один обязательный тип
    did = _create(client, project.id, fid).json()["id"]
    client.post(f"/pto/documents/{did}/submit")
    client.post(f"/pto/documents/{did}/decision", json={"decision": "approved"})
    c1 = client.get(f"/pto/completeness?project_id={project.id}").json()
    assert "hidden_work_act" in c1["present"] and "hidden_work_act" not in c1["missing"]


def test_summary(db_engine, db_session) -> None:
    org, project, emp, user, fid = _make(db_session)
    client = _client(db_engine, user)
    _create(client, project.id, fid)
    s = client.get("/pto/summary").json()
    assert s["documents_total"] == 1 and s["documents_draft"] == 1
