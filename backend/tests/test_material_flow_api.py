"""API-тесты «Заявки и выдача материалов»: жизненный цикл, R2–R4 + MFA,
резерв, частичная выдача, подтверждение получения, возврат, отказы доступа.

Переиспользует существующие сущности (projects, sites, employees, tasks,
materials, warehouses, approvals) без создания дубликатов. Данные обезличены.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from decimal import Decimal

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
    Employee,
    Material,
    Organization,
    Permission,
    Project,
    ProjectMember,
    Role,
    RolePermission,
    Site,
    Task,
    User,
    UserRole,
)

ALL = ["procurement.view", "procurement.manage", "procurement.approve", "warehouse.manage"]


def _make(db, *, perms=ALL, mfa=False, member=True):
    org = Organization(legal_name="ТЕСТ")
    db.add(org)
    db.flush()
    project = Project(organization_id=org.id, name="Объект А")
    db.add(project)
    db.flush()
    site = Site(organization_id=org.id, project_id=project.id, name="Участок 1")
    emp = Employee(organization_id=org.id, full_name="Прораб Тест")
    mat = Material(organization_id=org.id, name="Кабель ВВГ")
    db.add_all([site, emp, mat])
    db.flush()
    task = Task(organization_id=org.id, project_id=project.id, title="Электромонтаж")
    db.add(task)
    db.flush()
    secret = pyotp.random_base32() if mfa else None
    user = User(email=f"u{uuid.uuid4().hex[:8]}@ex.com", password_hash=hash_password("x"),
                status="active", employee_id=emp.id, mfa_enabled=mfa, mfa_secret=secret)
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
        db.add(ProjectMember(project_id=project.id, employee_id=emp.id, project_role="supply"))
    db.commit()
    return org, project, site, task, emp, mat, user, secret


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


def _warehouse(client):
    return client.post("/procurement/warehouses", json={"name": "Склад Ц"}).json()["id"]


def _stock(client, wid, mat, qty):
    """Приходует остаток на склад через поступление."""
    rec = client.post("/procurement/receipts", json={
        "warehouse_id": wid,
        "lines": [{"material_id": str(mat), "quantity_received": qty, "quantity_accepted": qty}],
    }).json()["id"]
    client.post(f"/procurement/receipts/{rec}/post")


def _create_request(client, project, mat, *, qty=100, critical=False, task=None, site=None):
    body = {"number": "З-1", "priority": "normal", "is_critical": critical,
            "lines": [{"material_id": str(mat), "quantity": qty}]}
    if task:
        body["task_id"] = str(task)
    if site:
        body["site_id"] = str(site)
    return client.post(f"/procurement/projects/{project}/requests", json=body).json()


# ------------------------------- RBAC/ABAC ------------------------------- #


def test_requires_permission(db_engine, db_session) -> None:
    # пользователь с правом только на просмотр не может создавать заявки
    _, project, _, _, _, mat, user, _ = _make(db_session, perms=["procurement.view"])
    client = _client(db_engine, user)
    r = _create_request_raw(client, project.id, mat.id)
    assert r.status_code == 403


def test_abac_denies_foreign_project(db_engine, db_session) -> None:
    # пользователь без членства в проекте не имеет доступа (ABAC)
    _, project, _, _, _, mat, user, _ = _make(db_session, member=False)
    client = _client(db_engine, user)
    r = _create_request_raw(client, project.id, mat.id)
    assert r.status_code == 403


def _create_request_raw(client, project_id, mat_id):
    return client.post(f"/procurement/projects/{project_id}/requests",
                       json={"lines": [{"material_id": str(mat_id), "quantity": 5}]})


# --------------------------- Жизненный цикл ------------------------------ #


def test_request_lifecycle_r2(db_engine, db_session) -> None:
    _, project, site, task, _, mat, user, _ = _make(db_session)
    client = _client(db_engine, user)
    req = _create_request(client, project.id, mat.id, task=task.id, site=site.id)
    assert req["status"] == "draft"
    assert req["task_id"] == str(task.id)
    rid = req["id"]
    # черновик → submitted → на согласование (R2) → утверждено
    assert client.post(f"/procurement/requests/{rid}/submit").json()["status"] == "submitted"
    ra = client.post(f"/procurement/requests/{rid}/request-approval").json()
    assert ra["risk_level"] == "R2"
    assert ra["status"] == "pending_approval"
    dec = client.post(f"/procurement/requests/{rid}/decision", json={"decision": "approved"})
    assert dec.status_code == 200
    assert dec.json()["status"] == "approved"


def test_request_r3_high_priority(db_engine, db_session) -> None:
    _, project, _, _, _, mat, user, _ = _make(db_session)
    client = _client(db_engine, user)
    rid = client.post(f"/procurement/projects/{project.id}/requests", json={
        "priority": "high", "lines": [{"material_id": str(mat.id), "quantity": 10}],
    }).json()["id"]
    ra = client.post(f"/procurement/requests/{rid}/request-approval").json()
    assert ra["risk_level"] == "R3"
    assert client.post(f"/procurement/requests/{rid}/decision",
                       json={"decision": "approved"}).status_code == 200


def test_critical_request_r4_requires_mfa(db_engine, db_session) -> None:
    _, project, _, _, _, mat, user, secret = _make(db_session, mfa=True)
    client = _client(db_engine, user)
    rid = _create_request(client, project.id, mat.id, critical=True)["id"]
    ra = client.post(f"/procurement/requests/{rid}/request-approval").json()
    assert ra["risk_level"] == "R4"
    denied = client.post(f"/procurement/requests/{rid}/decision", json={"decision": "approved"})
    assert denied.status_code == 401
    code = pyotp.TOTP(secret).now()
    ok = client.post(f"/procurement/requests/{rid}/decision",
                     json={"decision": "approved", "mfa_code": code})
    assert ok.status_code == 200
    assert ok.json()["status"] == "approved"


def test_reject_request(db_engine, db_session) -> None:
    _, project, _, _, _, mat, user, _ = _make(db_session)
    client = _client(db_engine, user)
    rid = _create_request(client, project.id, mat.id)["id"]
    client.post(f"/procurement/requests/{rid}/request-approval")
    dec = client.post(f"/procurement/requests/{rid}/decision",
                      json={"decision": "rejected", "comment": "нет бюджета"})
    assert dec.json()["status"] == "rejected"
    detail = client.get(f"/procurement/requests/{rid}").json()
    assert detail["rejection_reason"] == "нет бюджета"


def test_reserve_insufficient_stock_409(db_engine, db_session) -> None:
    _, project, _, _, _, mat, user, _ = _make(db_session)
    client = _client(db_engine, user)
    wid = _warehouse(client)
    _stock(client, wid, mat.id, 30)
    rid = _create_request(client, project.id, mat.id, qty=100)["id"]
    client.post(f"/procurement/requests/{rid}/request-approval")
    client.post(f"/procurement/requests/{rid}/decision", json={"decision": "approved"})
    # свободный остаток 30 < 100 → 409
    r = client.post(f"/procurement/requests/{rid}/reserve", json={"warehouse_id": wid})
    assert r.status_code == 409


def test_full_cycle_reserve_partial_issue_acknowledge(db_engine, db_session) -> None:
    _, project, _, _, emp, mat, user, _ = _make(db_session)
    client = _client(db_engine, user)
    wid = _warehouse(client)
    _stock(client, wid, mat.id, 100)
    rid = _create_request(client, project.id, mat.id, qty=100)["id"]
    lines = client.get(f"/procurement/requests/{rid}").json()["lines"]
    line_id = lines[0]["id"]
    client.post(f"/procurement/requests/{rid}/request-approval")
    client.post(f"/procurement/requests/{rid}/decision", json={"decision": "approved"})
    # резерв всей заявки
    assert client.post(f"/procurement/requests/{rid}/reserve",
                       json={"warehouse_id": wid}).json()["status"] == "reserved"
    bal = client.get(f"/procurement/warehouses/{wid}/balances").json()[0]
    assert bal["reserved_quantity"] == "100.000"
    # частичная выдача 60 → partially_issued
    iss = client.post(f"/procurement/requests/{rid}/issue", json={
        "warehouse_id": wid, "issued_to": str(emp.id),
        "items": [{"request_line_id": line_id, "quantity": 60}],
    })
    assert iss.status_code == 201
    issue_id = iss.json()["id"]
    assert client.get(f"/procurement/requests/{rid}").json()["status"] == "partially_issued"
    bal = client.get(f"/procurement/warehouses/{wid}/balances").json()[0]
    assert bal["quantity"] == "40.000"          # 100 − 60
    assert bal["reserved_quantity"] == "40.000"  # снят резерв на выданное
    # подтверждение получения
    ack = client.post(f"/procurement/issues/{issue_id}/acknowledge", json={"confirmed": True})
    assert ack.json()["acknowledgement_status"] == "confirmed"
    # довыдача 40 → issued
    iss2 = client.post(f"/procurement/requests/{rid}/issue", json={
        "warehouse_id": wid, "items": [{"request_line_id": line_id, "quantity": 40}],
    })
    assert iss2.status_code == 201
    assert client.get(f"/procurement/requests/{rid}").json()["status"] == "issued"


def test_issue_over_request_409(db_engine, db_session) -> None:
    _, project, _, _, _, mat, user, _ = _make(db_session)
    client = _client(db_engine, user)
    wid = _warehouse(client)
    _stock(client, wid, mat.id, 100)
    rid = _create_request(client, project.id, mat.id, qty=50)["id"]
    line_id = client.get(f"/procurement/requests/{rid}").json()["lines"][0]["id"]
    client.post(f"/procurement/requests/{rid}/request-approval")
    client.post(f"/procurement/requests/{rid}/decision", json={"decision": "approved"})
    r = client.post(f"/procurement/requests/{rid}/issue", json={
        "warehouse_id": wid, "items": [{"request_line_id": line_id, "quantity": 80}],
    })
    assert r.status_code == 409


def test_return_and_confirm(db_engine, db_session) -> None:
    _, project, _, _, _, mat, user, _ = _make(db_session)
    client = _client(db_engine, user)
    wid = _warehouse(client)
    _stock(client, wid, mat.id, 100)
    rid = _create_request(client, project.id, mat.id, qty=100)["id"]
    line_id = client.get(f"/procurement/requests/{rid}").json()["lines"][0]["id"]
    client.post(f"/procurement/requests/{rid}/request-approval")
    client.post(f"/procurement/requests/{rid}/decision", json={"decision": "approved"})
    issue = client.post(f"/procurement/requests/{rid}/issue", json={
        "warehouse_id": wid, "items": [{"request_line_id": line_id, "quantity": 100}],
    }).json()
    # остаток 0 после выдачи
    assert client.get(f"/procurement/warehouses/{wid}/balances").json()[0]["quantity"] == "0.000"
    # возврат 25 с объекта → приход на склад
    ret = client.post(f"/procurement/requests/{rid}/return", json={
        "warehouse_id": wid, "material_id": str(mat.id), "quantity": 25,
        "request_line_id": line_id, "issue_id": issue["id"], "reason": "остаток",
    })
    assert ret.status_code == 201
    assert ret.json()["status"] == "posted"
    assert client.get(f"/procurement/warehouses/{wid}/balances").json()[0]["quantity"] == "25.000"
    # возврат больше выданного → 409
    over = client.post(f"/procurement/requests/{rid}/return", json={
        "warehouse_id": wid, "material_id": str(mat.id), "quantity": 200,
        "request_line_id": line_id,
    })
    assert over.status_code == 409
    # подтверждение возврата
    conf = client.post(f"/procurement/returns/{ret.json()['id']}/confirm", json={})
    assert conf.json()["status"] == "confirmed"


def test_reserve_requires_warehouse_permission(db_engine, db_session) -> None:
    # инициатор без warehouse.manage не может резервировать (разделение ролей)
    _, project, _, _, _, mat, user, _ = _make(db_session, perms=["procurement.view", "procurement.manage", "procurement.approve"])
    client = _client(db_engine, user)
    rid = _create_request(client, project.id, mat.id)["id"]
    client.post(f"/procurement/requests/{rid}/request-approval")
    client.post(f"/procurement/requests/{rid}/decision", json={"decision": "approved"})
    r = client.post(f"/procurement/requests/{rid}/reserve", json={"warehouse_id": str(uuid.uuid4())})
    assert r.status_code == 403
