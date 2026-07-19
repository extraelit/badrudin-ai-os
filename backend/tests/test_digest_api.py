"""API-тесты «Управленческие сводки руководителю»: утренняя/вечерняя сводка на
реальных данных (задачи, просрочки, препятствия, согласования, финансы,
снабжение, склад, отчёты, риски), RBAC и ABAC.

Переиспользует существующие сущности без дубликатов. Данные обезличены.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_current_user
from app.core import token_store
from app.core.security import hash_password
from app.db.session import get_db
from app.main import app
from app.models import (
    Approval,
    Budget,
    DailyReport,
    Employee,
    InventoryBalance,
    Material,
    Organization,
    Project,
    ProjectMember,
    Permission,
    Role,
    RolePermission,
    Task,
    User,
    UserRole,
    Warehouse,
)


def _make(db, *, perms=("management.view",), member=True):
    org = Organization(legal_name="ТЕСТ")
    db.add(org)
    db.flush()
    project = Project(organization_id=org.id, name="Объект", status="active")
    db.add(project)
    db.flush()
    emp = Employee(organization_id=org.id, full_name="Директор Тест")
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
        db.add(ProjectMember(project_id=project.id, employee_id=emp.id, project_role="director"))
    db.commit()
    return org, project, emp, user


def _seed_data(db, org, project, emp):
    now = datetime.now(UTC)
    # просроченная, заблокированная, выполненная сегодня, высокорисковая
    db.add(Task(organization_id=org.id, project_id=project.id, title="Просрочка",
                status="in_progress", due_at=now - timedelta(days=1), owner_employee_id=emp.id))
    db.add(Task(organization_id=org.id, project_id=project.id, title="Блок",
                status="blocked", owner_employee_id=emp.id))
    db.add(Task(organization_id=org.id, project_id=project.id, title="Готово",
                status="completed", completed_at=now, owner_employee_id=emp.id))
    db.add(Task(organization_id=org.id, project_id=project.id, title="Крит",
                status="in_progress", risk_level="R4", owner_employee_id=emp.id))
    # согласование в ожидании
    db.add(Approval(organization_id=org.id, entity_type="purchase_order",
                    entity_id=uuid.uuid4(), approval_type="purchase_order_approval",
                    status="pending", current_step=1))
    # бюджет на согласовании
    db.add(Budget(organization_id=org.id, project_id=project.id, name="Бюджет", status="pending_approval"))
    # отчёт прораба отправлен сегодня
    db.add(DailyReport(project_id=project.id, report_date=now.date(), status="submitted",
                       submitted_at=now, reporting_employee_id=emp.id))
    # низкий остаток на складе
    wh = Warehouse(organization_id=org.id, name="Склад")
    mat = Material(organization_id=org.id, name="Цемент")
    db.add_all([wh, mat])
    db.flush()
    db.add(InventoryBalance(organization_id=org.id, warehouse_id=wh.id, material_id=mat.id,
                            quantity=Decimal("5"), reserved_quantity=Decimal("0"),
                            minimum_quantity=Decimal("20"), average_unit_cost=Decimal("100")))
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


def test_requires_management_view(db_engine, db_session) -> None:
    _, _, _, user = _make(db_session, perms=["project.view"])
    client = _client(db_engine, user)
    assert client.get("/management/digest").status_code == 403


def test_morning_digest_content(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    _seed_data(db_session, org, project, emp)
    client = _client(db_engine, user)
    r = client.get("/management/digest?kind=morning")
    assert r.status_code == 200
    d = r.json()
    assert d["kind"] == "morning" and d["period_label"] == "Утренняя сводка"
    assert d["projects_active"] == 1
    assert d["tasks"]["overdue"] == 1
    assert d["tasks"]["blocked"] == 1
    assert d["approvals_pending"] == 1
    assert len(d["approvals"]) == 1
    assert d["finance"]["budgets_pending"] == 1
    assert "payment_requests_pending" in d["finance"]
    assert d["warehouse"]["low_stock"] == 1
    assert d["risks"]["high_risk_tasks"] == 1
    assert d["risks"]["overdue"] == 1
    # верхние просрочки перечислены
    assert any(t["title"] == "Просрочка" for t in d["top_overdue"])


def test_evening_digest_daily_totals(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    _seed_data(db_session, org, project, emp)
    client = _client(db_engine, user)
    d = client.get("/management/digest?kind=evening").json()
    assert d["period_label"] == "Вечерняя сводка"
    assert d["tasks"]["completed_today"] == 1
    assert d["field_reports"]["submitted"] == 1
    assert d["field_reports"]["submitted_today"] == 1


def test_abac_excludes_foreign_project_tasks(db_engine, db_session) -> None:
    # директор без членства в проекте не видит его задачи в контроле (ABAC)
    org, project, emp, user = _make(db_session, member=False)
    _seed_data(db_session, org, project, emp)
    client = _client(db_engine, user)
    d = client.get("/management/digest").json()
    assert d["tasks"]["overdue"] == 0
    assert d["tasks"]["blocked"] == 0
    # операционные сводки организации остаются видимыми
    assert d["warehouse"]["low_stock"] == 1
