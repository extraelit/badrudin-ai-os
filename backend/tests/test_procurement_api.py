"""API-тесты модуля «Снабжение и закупки»: RBAC, ABAC, цикл заявка→заказ→приёмка→выдача."""

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
    Counterparty,
    Employee,
    Material,
    Organization,
    Permission,
    ProcurementSettings,
    Project,
    ProjectMember,
    Role,
    RolePermission,
    Supplier,
    User,
    UserRole,
)


def _make_user(db, *, perms=(), mfa=False, low_threshold=False):
    org = Organization(legal_name="ТЕСТ")
    db.add(org)
    db.flush()
    project = Project(organization_id=org.id, name="Проект")
    db.add(project)
    db.flush()
    emp = Employee(organization_id=org.id, full_name="Снабженец Тест")
    db.add(emp)
    db.flush()
    cp = Counterparty(organization_id=org.id, name="Поставщик")
    db.add(cp)
    db.flush()
    sup = Supplier(counterparty_id=cp.id)
    mat = Material(organization_id=org.id, name="Труба")
    db.add_all([sup, mat])
    db.flush()
    if low_threshold:
        db.add(ProcurementSettings(organization_id=org.id, order_r4_amount_threshold=Decimal("100")))
    secret = pyotp.random_base32() if mfa else None
    user = User(email=f"u{uuid.uuid4().hex[:8]}@ex.com", password_hash=hash_password("x"),
                status="active", employee_id=emp.id, mfa_enabled=mfa, mfa_secret=secret)
    db.add(user)
    db.flush()
    role = Role(code="proc_role", name="r")
    db.add(role)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    for pc in perms:
        p = Permission(code=pc)
        db.add(p)
        db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=p.id))
    db.add(ProjectMember(project_id=project.id, employee_id=emp.id, project_role="supply"))
    db.commit()
    return org, project, sup, mat, user, secret


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


ALL = ["procurement.view", "procurement.manage", "procurement.approve", "warehouse.manage"]


def test_requires_permission(db_engine, db_session) -> None:
    _, _, _, _, user, _ = _make_user(db_session, perms=["supplier.view"])
    client = _client(db_engine, user)
    assert client.get("/procurement/warehouses").status_code == 403


def test_request_create_and_approve(db_engine, db_session) -> None:
    _, project, _, mat, user, _ = _make_user(db_session, perms=ALL)
    client = _client(db_engine, user)
    r = client.post(f"/procurement/projects/{project.id}/requests",
                    json={"number": "З-1", "lines": [{"material_id": str(mat.id), "quantity": 100}]})
    assert r.status_code == 201
    rid = r.json()["id"]
    ap = client.post(f"/procurement/requests/{rid}/approve")
    assert ap.status_code == 200
    assert ap.json()["status"] == "approved"


def _warehouse(client):
    return client.post("/procurement/warehouses", json={"name": "Склад"}).json()["id"]


def test_order_r3_flow(db_engine, db_session) -> None:
    _, _, sup, mat, user, _ = _make_user(db_session, perms=ALL)
    client = _client(db_engine, user)
    wid = _warehouse(client)
    o = client.post("/procurement/orders", json={
        "supplier_id": str(sup.id), "warehouse_id": wid, "number": "ЗК-1",
        "lines": [{"material_id": str(mat.id), "quantity": 10, "unit_price": 100}],
    })
    assert o.status_code == 201
    assert o.json()["total_amount"] == "1000.00"
    oid = o.json()["id"]
    req = client.post(f"/procurement/orders/{oid}/request-approval")
    assert req.json()["risk_level"] == "R3"
    dec = client.post(f"/procurement/orders/{oid}/decision", json={"decision": "approved"})
    assert dec.status_code == 200
    assert dec.json()["status"] == "approved"


def test_order_r4_requires_mfa(db_engine, db_session) -> None:
    _, _, sup, mat, user, secret = _make_user(db_session, perms=ALL, mfa=True, low_threshold=True)
    client = _client(db_engine, user)
    wid = _warehouse(client)
    oid = client.post("/procurement/orders", json={
        "supplier_id": str(sup.id), "warehouse_id": wid,
        "lines": [{"material_id": str(mat.id), "quantity": 10, "unit_price": 100}],
    }).json()["id"]
    req = client.post(f"/procurement/orders/{oid}/request-approval")
    assert req.json()["risk_level"] == "R4"
    denied = client.post(f"/procurement/orders/{oid}/decision", json={"decision": "approved"})
    assert denied.status_code == 401
    code = pyotp.TOTP(secret).now()
    ok = client.post(f"/procurement/orders/{oid}/decision", json={"decision": "approved", "mfa_code": code})
    assert ok.status_code == 200


def test_receipt_then_issue_stock(db_engine, db_session) -> None:
    _, _, _, mat, user, _ = _make_user(db_session, perms=ALL)
    client = _client(db_engine, user)
    wid = _warehouse(client)
    rec = client.post("/procurement/receipts", json={
        "warehouse_id": wid, "number": "П-1",
        "lines": [{"material_id": str(mat.id), "quantity_received": 20, "quantity_accepted": 20}],
    }).json()["id"]
    assert client.post(f"/procurement/receipts/{rec}/post").json()["status"] == "posted"
    bal = client.get(f"/procurement/warehouses/{wid}/balances").json()
    assert bal[0]["quantity"] == "20.000"
    # выдача 8 → остаток 12
    iss = client.post("/procurement/issues", json={
        "warehouse_id": wid, "lines": [{"material_id": str(mat.id), "quantity": 8}],
    }).json()["id"]
    assert client.post(f"/procurement/issues/{iss}/post").json()["status"] == "posted"
    bal2 = client.get(f"/procurement/warehouses/{wid}/balances").json()
    assert bal2[0]["quantity"] == "12.000"


def test_issue_insufficient_409(db_engine, db_session) -> None:
    _, _, _, mat, user, _ = _make_user(db_session, perms=ALL)
    client = _client(db_engine, user)
    wid = _warehouse(client)
    iss = client.post("/procurement/issues", json={
        "warehouse_id": wid, "lines": [{"material_id": str(mat.id), "quantity": 5}],
    }).json()["id"]
    assert client.post(f"/procurement/issues/{iss}/post").status_code == 409


def test_writeoff_approval_and_post(db_engine, db_session) -> None:
    _, _, _, mat, user, _ = _make_user(db_session, perms=ALL)
    client = _client(db_engine, user)
    wid = _warehouse(client)
    rec = client.post("/procurement/receipts", json={
        "warehouse_id": wid, "lines": [{"material_id": str(mat.id), "quantity_received": 10, "quantity_accepted": 10}],
    }).json()["id"]
    client.post(f"/procurement/receipts/{rec}/post")
    wo = client.post("/procurement/write-offs", json={
        "warehouse_id": wid, "material_id": str(mat.id), "quantity": 3, "reason": "брак",
    }).json()["id"]
    req = client.post(f"/procurement/write-offs/{wo}/request-approval")
    assert req.json()["risk_level"] in ("R3", "R4")
    dec = client.post(f"/procurement/write-offs/{wo}/decision", json={"decision": "approved"})
    assert dec.status_code == 200
    assert dec.json()["status"] == "posted"
    bal = client.get(f"/procurement/warehouses/{wid}/balances").json()
    assert bal[0]["quantity"] == "7.000"


def test_inventory_count_and_summary(db_engine, db_session) -> None:
    _, _, _, mat, user, _ = _make_user(db_session, perms=ALL)
    client = _client(db_engine, user)
    wid = _warehouse(client)
    cnt = client.post("/procurement/inventory-counts", json={
        "warehouse_id": wid,
        "lines": [{"material_id": str(mat.id), "expected_quantity": 0, "counted_quantity": 5}],
    }).json()["id"]
    assert client.post(f"/procurement/inventory-counts/{cnt}/apply").json()["status"] == "posted"
    s = client.get("/procurement/summary")
    assert s.status_code == 200
    assert s.json()["warehouses"] == 1
