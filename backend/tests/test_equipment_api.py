"""API-тесты «Техника, транспорт и инструмент»: реестр, назначение, эксплуатация
(моточасы/пробег/простой), техобслуживание с блокировкой выдачи, топливо,
осмотры, инструмент выдача/возврат, RBAC/ABAC.

Переиспользует существующие сущности (projects, sites, employees, suppliers,
files, warehouses) без дубликатов. Данные обезличены.
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
    Site,
    User,
    UserRole,
)

ALL = ["equipment.view", "equipment.manage", "equipment.maintain"]


def _make(db, *, perms=ALL, member=True):
    org = Organization(legal_name="ТЕСТ")
    db.add(org)
    db.flush()
    project = Project(organization_id=org.id, name="Объект", status="active")
    db.add(project)
    db.flush()
    site = Site(organization_id=org.id, project_id=project.id, name="Участок")
    emp = Employee(organization_id=org.id, full_name="Механик Тест")
    db.add_all([site, emp])
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
        db.add(ProjectMember(project_id=project.id, employee_id=emp.id, project_role="mechanic"))
    db.commit()
    return org, project, site, emp, user


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


def _register(client, name="Экскаватор", asset_type="excavator"):
    return client.post("/equipment", json={"name": name, "asset_type": asset_type, "fuel_type": "diesel"}).json()["id"]


# ------------------------------- RBAC/ABAC ------------------------------- #


def test_register_requires_manage(db_engine, db_session) -> None:
    *_, user = _make(db_session, perms=["equipment.view"])
    client = _client(db_engine, user)
    assert client.post("/equipment", json={"name": "Кран"}).status_code == 403


def test_view_requires_permission(db_engine, db_session) -> None:
    *_, user = _make(db_session, perms=["project.view"])
    client = _client(db_engine, user)
    assert client.get("/equipment/summary").status_code == 403


def test_abac_denies_assign_to_foreign_project(db_engine, db_session) -> None:
    org, _, _, _, user = _make(db_session)
    client = _client(db_engine, user)
    eid = _register(client)
    other = Project(organization_id=org.id, name="Чужой", status="active")
    db_session.add(other)
    db_session.commit()
    r = client.post(f"/equipment/{eid}/assign", json={"project_id": str(other.id)})
    assert r.status_code == 403


# --------------------------- Жизненный цикл ------------------------------ #


def test_assign_usage_return(db_engine, db_session) -> None:
    org, project, site, emp, user = _make(db_session)
    client = _client(db_engine, user)
    eid = _register(client)
    a = client.post(f"/equipment/{eid}/assign", json={
        "project_id": str(project.id), "site_id": str(site.id),
        "responsible_employee_id": str(emp.id)})
    assert a.status_code == 201
    assert client.get(f"/equipment/{eid}").json()["current_status"] == "assigned"
    # повторное назначение запрещено
    assert client.post(f"/equipment/{eid}/assign", json={"project_id": str(project.id)}).status_code == 409
    # эксплуатация: моточасы растут
    u = client.post(f"/equipment/{eid}/usage", json={
        "usage_date": "2026-07-20", "engine_hours_end": 12.5, "downtime_hours": 1.5,
        "downtime_reason": "ремонт", "fuel_consumed": 30})
    assert u.status_code == 201
    eq = client.get(f"/equipment/{eid}").json()
    assert eq["engine_hours"] == "12.5" and eq["current_status"] == "in_use"
    # моточасы не могут уменьшиться
    bad = client.post(f"/equipment/{eid}/usage", json={"usage_date": "2026-07-21", "engine_hours_end": 5})
    assert bad.status_code == 409
    # возврат
    assert client.post(f"/equipment/{eid}/return").json()["current_status"] == "available"


def test_maintenance_blocks_assign(db_engine, db_session) -> None:
    org, project, _, _, user = _make(db_session)
    client = _client(db_engine, user)
    eid = _register(client)
    mo = client.post("/equipment/maintenance", json={
        "asset_type": "equipment", "asset_id": eid, "maintenance_type": "repair",
        "problem_description": "гидравлика"})
    assert mo.status_code == 201
    assert client.get(f"/equipment/{eid}").json()["current_status"] == "under_repair"
    # в ремонте выдавать нельзя
    assert client.post(f"/equipment/{eid}/assign", json={"project_id": str(project.id)}).status_code == 409
    # завершение ремонта возвращает в доступное состояние
    done = client.post(f"/equipment/maintenance/{mo.json()['id']}/complete", json={"actual_cost": 15000})
    assert done.json()["status"] == "completed"
    assert client.get(f"/equipment/{eid}").json()["current_status"] == "available"
    # теперь можно назначить
    assert client.post(f"/equipment/{eid}/assign", json={"project_id": str(project.id)}).status_code == 201


def test_inspection_failure_blocks(db_engine, db_session) -> None:
    org, project, _, _, user = _make(db_session)
    client = _client(db_engine, user)
    eid = _register(client)
    r = client.post(f"/equipment/{eid}/inspection", json={
        "inspection_type": "pre_shift", "result": "failed", "operation_allowed": False,
        "defects": "тормоза"})
    assert r.status_code == 201 and r.json()["operation_allowed"] is False
    assert client.get(f"/equipment/{eid}").json()["current_status"] == "under_inspection"


def test_fuel_recording(db_engine, db_session) -> None:
    org, project, _, _, user = _make(db_session)
    client = _client(db_engine, user)
    eid = _register(client)
    f = client.post("/equipment/fuel", json={
        "transaction_type": "issue", "fuel_type": "diesel", "quantity": 50,
        "unit_price": 60, "equipment_id": eid, "project_id": str(project.id)})
    assert f.status_code == 201
    assert f.json()["total_amount"] == "3000.00"


# ------------------------------ Инструмент ------------------------------- #


def test_tool_issue_return(db_engine, db_session) -> None:
    org, project, site, emp, user = _make(db_session)
    client = _client(db_engine, user)
    tid = client.post("/equipment/tools", json={"name": "Перфоратор", "tool_type": "power"}).json()["id"]
    a = client.post(f"/equipment/tools/{tid}/issue", json={
        "employee_id": str(emp.id), "project_id": str(project.id), "condition_at_issue": "ok"})
    assert a.status_code == 201
    tools = client.get("/equipment/tools/list").json()
    assert tools[0]["current_status"] == "issued"
    # повторная выдача запрещена
    assert client.post(f"/equipment/tools/{tid}/issue", json={"employee_id": str(emp.id)}).status_code == 409
    # возврат с фиксацией состояния
    r = client.post(f"/equipment/tools/{tid}/return", json={"condition_at_return": "worn"})
    assert r.json()["current_status"] == "available" and r.json()["condition_status"] == "worn"


def test_summary(db_engine, db_session) -> None:
    org, project, _, _, user = _make(db_session)
    client = _client(db_engine, user)
    eid = _register(client)
    client.post(f"/equipment/{eid}/assign", json={"project_id": str(project.id)})
    client.post("/equipment/tools", json={"name": "Болгарка"})
    s = client.get("/equipment/summary").json()
    assert s["equipment_total"] == 1 and s["equipment_assigned"] == 1
    assert s["tools_total"] == 1
