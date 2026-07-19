"""API-тесты «Складской учёт и остатки»: чтение остатков/журнала/резервов,
ручные резервы, точка дозаказа, места хранения, RBAC/ABAC и сквозной цикл
поступление → остаток → резерв → выдача → возврат → списание → инвентаризация.

Переиспользует существующие сущности (warehouses, materials, inventory_*,
stock_reservations) без дубликатов. Данные обезличены.
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
    Material,
    Organization,
    Permission,
    Project,
    ProjectMember,
    Role,
    RolePermission,
    Site,
    User,
    Warehouse,
)

READ = ["warehouse.view"]
ALL = ["warehouse.view", "warehouse.manage", "procurement.view", "procurement.manage", "procurement.approve"]


def _make(db, *, perms=ALL):
    org = Organization(legal_name="ТЕСТ")
    db.add(org)
    db.flush()
    project = Project(organization_id=org.id, name="Объект")
    db.add(project)
    db.flush()
    emp = Employee(organization_id=org.id, full_name="Кладовщик Тест")
    mat = Material(organization_id=org.id, name="Цемент М500")
    db.add_all([emp, mat])
    db.flush()
    user = User(email=f"u{uuid.uuid4().hex[:8]}@ex.com", password_hash=hash_password("x"),
                status="active", employee_id=emp.id)
    db.add(user)
    db.flush()
    role = Role(code=f"r{uuid.uuid4().hex[:6]}", name="r")
    db.add(role)
    db.flush()
    from app.models import UserRole
    db.add(UserRole(user_id=user.id, role_id=role.id))
    for pc in perms:
        p = Permission(code=pc)
        db.add(p)
        db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=p.id))
    db.add(ProjectMember(project_id=project.id, employee_id=emp.id, project_role="warehouse"))
    db.commit()
    return org, project, emp, mat, user


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


def _warehouse(client) -> str:
    return client.post("/procurement/warehouses", json={"name": "Центральный склад"}).json()["id"]


def _receipt(client, wid, mat, qty):
    rec = client.post("/procurement/receipts", json={
        "warehouse_id": wid,
        "lines": [{"material_id": str(mat), "quantity_received": qty, "quantity_accepted": qty}],
    }).json()["id"]
    client.post(f"/procurement/receipts/{rec}/post")


# ------------------------------- RBAC/ABAC ------------------------------- #


def test_read_requires_warehouse_view(db_engine, db_session) -> None:
    _, _, _, _, user = _make(db_session, perms=["procurement.view"])
    client = _client(db_engine, user)
    assert client.get("/warehouse/summary").status_code == 403


def test_manage_requires_warehouse_manage(db_engine, db_session) -> None:
    _, _, _, mat, user = _make(db_session, perms=["warehouse.view"])
    client = _client(db_engine, user)
    # чтение доступно, изменение — нет
    assert client.get("/warehouse/stock").status_code == 200
    r = client.post("/warehouse/reservations", json={
        "warehouse_id": str(uuid.uuid4()), "material_id": str(mat.id), "quantity": 1})
    assert r.status_code == 403


def test_abac_denies_foreign_warehouse(db_engine, db_session) -> None:
    org, _, _, mat, user = _make(db_session)
    client = _client(db_engine, user)
    # склад привязан к объекту чужого проекта (нет членства) → 403
    other = Project(organization_id=org.id, name="Чужой")
    db_session.add(other)
    db_session.flush()
    site = Site(organization_id=org.id, project_id=other.id, name="Чужой участок")
    db_session.add(site)
    db_session.flush()
    wh = Warehouse(organization_id=org.id, site_id=site.id, name="Склад чужого объекта")
    db_session.add(wh)
    db_session.commit()
    r = client.get(f"/warehouse/{wh.id}/locations")
    assert r.status_code == 403


# --------------------------- Остатки и резервы --------------------------- #


def test_stock_and_manual_reservation(db_engine, db_session) -> None:
    _, _, _, mat, user = _make(db_session)
    client = _client(db_engine, user)
    wid = _warehouse(client)
    _receipt(client, wid, mat.id, 100)
    stock = client.get("/warehouse/stock").json()
    assert stock[0]["quantity"] == "100.000"
    assert stock[0]["available_quantity"] == "100.000"
    assert stock[0]["material_name"] == "Цемент М500"
    # ручной резерв 30 → доступно 70
    res = client.post("/warehouse/reservations", json={
        "warehouse_id": wid, "material_id": str(mat.id), "quantity": 30, "reason": "под монтаж"})
    assert res.status_code == 201
    rid = res.json()["id"]
    stock = client.get("/warehouse/stock").json()
    assert stock[0]["reserved_quantity"] == "30.000"
    assert stock[0]["available_quantity"] == "70.000"
    # резерв больше свободного → 409
    over = client.post("/warehouse/reservations", json={
        "warehouse_id": wid, "material_id": str(mat.id), "quantity": 100})
    assert over.status_code == 409
    # снятие резерва → доступно снова 100
    rel = client.post(f"/warehouse/reservations/{rid}/release")
    assert rel.json()["status"] == "released"
    stock = client.get("/warehouse/stock").json()
    assert stock[0]["available_quantity"] == "100.000"


def test_low_stock_signal(db_engine, db_session) -> None:
    _, _, _, mat, user = _make(db_session)
    client = _client(db_engine, user)
    wid = _warehouse(client)
    _receipt(client, wid, mat.id, 10)
    client.post("/warehouse/stock/min-quantity", json={
        "warehouse_id": wid, "material_id": str(mat.id), "minimum_quantity": 20})
    stock = client.get("/warehouse/stock?low_only=true").json()
    assert len(stock) == 1 and stock[0]["low"] is True
    assert client.get("/warehouse/summary").json()["low_stock"] == 1


def test_locations_crud(db_engine, db_session) -> None:
    _, _, _, _, user = _make(db_session)
    client = _client(db_engine, user)
    wid = _warehouse(client)
    loc = client.post(f"/warehouse/{wid}/locations", json={"name": "Стеллаж А1", "code": "A-01"})
    assert loc.status_code == 201
    assert client.get(f"/warehouse/{wid}/locations").json()[0]["name"] == "Стеллаж А1"


def test_stock_card(db_engine, db_session) -> None:
    _, _, _, mat, user = _make(db_session)
    client = _client(db_engine, user)
    wid = _warehouse(client)
    _receipt(client, wid, mat.id, 15)
    card = client.get(f"/warehouse/stock-card?warehouse_id={wid}&material_id={mat.id}").json()
    assert card["balance"]["quantity"] == "15.000"
    assert any(t["transaction_type"] == "receipt" for t in card["transactions"])


# --------------------------- Сквозной цикл ------------------------------- #


def test_full_lifecycle_ledger(db_engine, db_session) -> None:
    """поступление → остаток → резерв → выдача → возврат → списание → инвентаризация."""
    _, _, _, mat, user = _make(db_session)
    client = _client(db_engine, user)
    wid = _warehouse(client)

    # 1. поступление 100
    _receipt(client, wid, mat.id, 100)
    assert client.get("/warehouse/stock").json()[0]["quantity"] == "100.000"

    # 2. резерв 20
    client.post("/warehouse/reservations", json={"warehouse_id": wid, "material_id": str(mat.id), "quantity": 20})
    assert client.get("/warehouse/stock").json()[0]["available_quantity"] == "80.000"

    # 3. выдача 30 → остаток 70
    iss = client.post("/procurement/issues", json={
        "warehouse_id": wid, "lines": [{"material_id": str(mat.id), "quantity": 30}]}).json()["id"]
    client.post(f"/procurement/issues/{iss}/post")
    assert client.get("/warehouse/stock").json()[0]["quantity"] == "70.000"

    # 4. возврат 10 → остаток 80
    client.post("/procurement/returns", json={
        "warehouse_id": wid, "material_id": str(mat.id), "quantity": 10, "return_type": "from_site"})
    assert client.get("/warehouse/stock").json()[0]["quantity"] == "80.000"

    # 5. списание 5 (через согласование) → остаток 75
    wo = client.post("/procurement/write-offs", json={
        "warehouse_id": wid, "material_id": str(mat.id), "quantity": 5, "reason": "брак"}).json()["id"]
    client.post(f"/procurement/write-offs/{wo}/request-approval")
    client.post(f"/procurement/write-offs/{wo}/decision", json={"decision": "approved"})
    assert client.get("/warehouse/stock").json()[0]["quantity"] == "75.000"

    # 6. инвентаризация: факт 70 → корректировка −5 → остаток 70
    cnt = client.post("/procurement/inventory-counts", json={
        "warehouse_id": wid,
        "lines": [{"material_id": str(mat.id), "expected_quantity": 75, "counted_quantity": 70}]}).json()["id"]
    client.post(f"/procurement/inventory-counts/{cnt}/apply")
    assert client.get("/warehouse/stock").json()[0]["quantity"] == "70.000"

    # журнал отражает все типы движений
    types = {t["transaction_type"] for t in client.get("/warehouse/ledger").json()}
    assert {"receipt", "issue", "return", "write_off", "adjustment"} <= types
    # сводка склада
    s = client.get("/warehouse/summary").json()
    assert s["positions"] == 1 and s["warehouses_with_stock"] == 1
