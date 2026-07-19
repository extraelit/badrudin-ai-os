"""API-тесты «KPI и независимый аудит» — ROADMAP этап 15.

KPI считаются только для чтения; независимый аудит фиксирует находки как отдельные
записи (проверяемые данные не изменяются), сканирование идемпотентно. RBAC/ABAC.
Данные обезличены.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

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
    Risk,
    Role,
    RolePermission,
    Task,
    User,
    UserRole,
)

ALL = ["kpi.view", "audit.finding.view", "audit.finding.manage", "audit.finding.resolve"]


def _make(db, *, perms=ALL, member=True):
    org = Organization(legal_name="ТЕСТ")
    db.add(org)
    db.flush()
    project = Project(organization_id=org.id, name="Объект", status="active")
    db.add(project)
    db.flush()
    emp = Employee(organization_id=org.id, full_name="Аудитор Тест")
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


def _seed_anomalies(db, org, project):
    # просроченная задача
    db.add(Task(
        organization_id=org.id, project_id=project.id, title="Смонтировать узел",
        status="in_progress", due_at=datetime.now(UTC) - timedelta(days=3),
    ))
    # риск без ответственного
    db.add(Risk(
        organization_id=org.id, project_id=project.id, title="Задержка поставки",
        status="identified", severity="high", owner_employee_id=None,
    ))
    db.commit()


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


def test_summary_requires_view(db_engine, db_session) -> None:
    *_, user = _make(db_session, perms=["audit.finding.view"])
    client = _client(db_engine, user)
    assert client.get("/kpi/summary").status_code == 403


def test_kpi_summary(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    _seed_anomalies(db_session, org, project)
    client = _client(db_engine, user)
    s = client.get("/kpi/summary").json()
    assert s["tasks_total"] == 1 and s["tasks_overdue"] == 1
    assert s["overdue_ratio"] == 1.0
    assert s["risks_open"] == 1 and s["risks_high"] == 1


def test_scan_creates_findings_idempotent(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    _seed_anomalies(db_session, org, project)
    client = _client(db_engine, user)
    r1 = client.post("/kpi/scan")
    assert r1.status_code == 200 and r1.json()["created"] == 2
    # повторный запуск не создаёт дублей открытых находок
    assert client.post("/kpi/scan").json()["created"] == 0
    findings = client.get("/kpi/findings").json()
    cats = sorted(f["category"] for f in findings)
    assert cats == ["overdue_task", "risk_no_owner"]


def test_scan_requires_manage(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session, perms=["kpi.view", "audit.finding.view"])
    client = _client(db_engine, user)
    assert client.post("/kpi/scan").status_code == 403


def test_finding_manual_and_resolve(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    client = _client(db_engine, user)
    r = client.post("/kpi/findings", json={
        "category": "anomalous_expense", "title": "Необычное списание", "severity": "high"})
    assert r.status_code == 201 and r.json()["detected_by"] == "manual"
    fid = r.json()["id"]
    d = client.post(f"/kpi/findings/{fid}/resolve", json={"status": "resolved", "note": "проверено"})
    assert d.json()["status"] == "resolved"
    # повторный разбор закрытой находки недопустим
    assert client.post(f"/kpi/findings/{fid}/resolve", json={"status": "resolved"}).status_code == 409


def test_resolve_requires_resolve_perm(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session, perms=["kpi.view", "audit.finding.view", "audit.finding.manage"])
    client = _client(db_engine, user)
    fid = client.post("/kpi/findings", json={"category": "other", "title": "X"}).json()["id"]
    assert client.post(f"/kpi/findings/{fid}/resolve", json={"status": "resolved"}).status_code == 403


def test_bad_category_rejected(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    client = _client(db_engine, user)
    assert client.post("/kpi/findings", json={"category": "nonsense", "title": "X"}).status_code == 409
