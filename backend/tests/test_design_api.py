"""API-тесты модуля «Проектирование и дизайн»: RBAC, ABAC, выпуск R3/R4, замечания."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_current_user
from app.core import token_store
from app.core.security import hash_password
from app.db.session import get_db
from app.main import app
from app.models import (
    Document,
    Employee,
    Organization,
    Permission,
    Project,
    ProjectDiscipline,
    ProjectMember,
    Role,
    RolePermission,
    User,
    UserRole,
)


def _make_user(db, *, perms=(), mfa=False):
    org = Organization(legal_name="ТЕСТ")
    db.add(org)
    db.flush()
    project = Project(organization_id=org.id, name="Проект")
    db.add(project)
    db.flush()
    emp = Employee(organization_id=org.id, full_name="ГИП Тест")
    db.add(emp)
    db.flush()
    secret = pyotp.random_base32() if mfa else None
    user = User(email=f"u{uuid.uuid4().hex[:8]}@ex.com", password_hash=hash_password("x"),
                status="active", employee_id=emp.id, mfa_enabled=mfa, mfa_secret=secret)
    db.add(user)
    db.flush()
    role = Role(code="design_role", name="r")
    db.add(role)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    for pc in perms:
        p = Permission(code=pc)
        db.add(p)
        db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=p.id))
    db.add(ProjectMember(project_id=project.id, employee_id=emp.id, project_role="gip"))
    db.commit()
    return org, project, emp, user, secret


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


def test_disciplines_requires_permission(db_engine, db_session) -> None:
    _, project, _, user, _ = _make_user(db_session, perms=["supplier.view"])
    client = _client(db_engine, user)
    assert client.get(f"/design/projects/{project.id}/disciplines").status_code == 403


def test_abac_denies_foreign_project(db_engine, db_session) -> None:
    _, _, _, user, _ = _make_user(db_session, perms=["design.view"])
    other = Project(organization_id=uuid.uuid4(), name="Чужой")
    db_session.add(other)
    db_session.commit()
    client = _client(db_engine, user)
    assert client.get(f"/design/projects/{other.id}/disciplines").status_code == 403


def test_create_discipline_and_overview(db_engine, db_session) -> None:
    _, project, _, user, _ = _make_user(db_session, perms=["design.view", "design.manage"])
    client = _client(db_engine, user)
    r = client.post(f"/design/projects/{project.id}/disciplines",
                    json={"name": "Раздел ВК", "discipline_type": "water_supply", "completion_percent": 40})
    assert r.status_code == 201
    ov = client.get(f"/design/projects/{project.id}/overview")
    assert ov.status_code == 200
    assert ov.json()["disciplines_total"] == 1
    assert ov.json()["avg_completion"] == 40


def test_issue_creates_task(db_engine, db_session) -> None:
    org, project, emp, user, _ = _make_user(
        db_session, perms=["design.view", "design.issue.manage"]
    )
    client = _client(db_engine, user)
    r = client.post(f"/design/projects/{project.id}/issues",
                    json={"title": "Замечание заказчика", "severity": "high",
                          "responsible_employee_id": str(emp.id)})
    assert r.status_code == 201
    assert r.json()["linked_task_id"] is not None


def test_brief_create_and_approve(db_engine, db_session) -> None:
    _, project, _, user, _ = _make_user(
        db_session, perms=["design.view", "design.manage", "design.brief.approve"]
    )
    client = _client(db_engine, user)
    b = client.post(f"/design/projects/{project.id}/brief", json={"title": "ТЗ на интерьер"})
    assert b.status_code == 201
    bid = b.json()["id"]
    ap = client.post(f"/design/briefs/{bid}/approve")
    assert ap.status_code == 200
    assert ap.json()["status"] == "approved"


def test_release_flow_r3(db_engine, db_session) -> None:
    org, project, _, user, _ = _make_user(db_session, perms=["design.view", "design.release"])
    disc = ProjectDiscipline(project_id=project.id, name="Раздел ВК")
    doc_draft = Document(organization_id=org.id, project_id=project.id,
                         title="РД", status="draft")
    db_session.add_all([disc, doc_draft])
    db_session.commit()
    client = _client(db_engine, user)

    # черновик документа → выпуск запрещён (409)
    bad = client.post(f"/design/disciplines/{disc.id}/request-release",
                      json={"document_id": str(doc_draft.id)})
    assert bad.status_code == 409

    doc_draft.status = "approved"
    db_session.commit()
    req = client.post(f"/design/disciplines/{disc.id}/request-release",
                      json={"document_id": str(doc_draft.id)})
    assert req.status_code == 200
    assert req.json()["risk_level"] == "R3"
    approval_id = req.json()["approval_id"]

    dec = client.post(f"/design/disciplines/{disc.id}/release-decision",
                      json={"approval_id": approval_id, "decision": "approved"})
    assert dec.status_code == 200
    assert dec.json()["status"] == "issued"


def test_annul_requires_mfa_r4(db_engine, db_session) -> None:
    _, project, _, user, secret = _make_user(
        db_session, perms=["design.view", "design.release"], mfa=True
    )
    disc = ProjectDiscipline(project_id=project.id, name="Раздел", status="issued")
    db_session.add(disc)
    db_session.commit()
    client = _client(db_engine, user)

    denied = client.post(f"/design/disciplines/{disc.id}/annul", json={"reason": "ошибка"})
    assert denied.status_code == 401

    code = pyotp.TOTP(secret).now()
    ok = client.post(f"/design/disciplines/{disc.id}/annul",
                     json={"reason": "ошибка проекта", "mfa_code": code})
    assert ok.status_code == 200
    assert ok.json()["status"] == "cancelled"


def test_realizability_endpoint(db_engine, db_session) -> None:
    _, project, _, user, _ = _make_user(db_session, perms=["design.view", "design.manage"])
    client = _client(db_engine, user)
    spec = client.post(f"/design/projects/{project.id}/specifications",
                       json={"category": "furniture", "quantity": 5})
    assert spec.status_code == 201
    sid = spec.json()["id"]
    rc = client.post(f"/design/specifications/{sid}/realizability")
    assert rc.status_code == 200
    assert rc.json()["availability_status"] in ("available", "limited", "unknown")


def test_catalog_endpoints(db_engine, db_session) -> None:
    _, _, _, user, _ = _make_user(db_session, perms=["supplier.view"])
    client = _client(db_engine, user)
    assert client.get("/design/suppliers").status_code == 200
    assert client.get("/design/materials").status_code == 200
