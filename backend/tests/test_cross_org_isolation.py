"""Позитивные тесты межтенантной изоляции (§18, §19).

В отличие от `test_detail_notfound_matrix` (случайные id), здесь создаются РЕАЛЬНЫЕ
объекты в организации A, после чего полностью авторизованный пользователь другой
организации B пытается их прочитать. Ожидается `404`/пустой список — данные одной
организации недоступны пользователю другой, даже если он знает идентификатор.

Закрепляет, в частности, исправление утечки складских остатков
(`/procurement/warehouses/{id}/balances`).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
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
    Employee,
    IntegrationConnector,
    InventoryBalance,
    Material,
    Organization,
    Permission,
    Role,
    RolePermission,
    SocialPublication,
    User,
    UserRole,
    Warehouse,
)

PERMS = [
    "procurement.view", "procurement.manage",
    "integration.view", "integration.manage", "integration.approve",
    "smm.view", "smm.manage",
]


def _org(db, name):
    o = Organization(legal_name=name)
    db.add(o)
    db.flush()
    return o


def _user_in(db, org, perms):
    emp = Employee(organization_id=org.id, full_name="U")
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
    return user


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


def _seed(db):
    """Организация A с ресурсами + пользователь организации B."""
    org_a = _org(db, "ORG-A")
    org_b = _org(db, "ORG-B")
    # склад + материал + остаток в организации A
    wh = Warehouse(organization_id=org_a.id, name="Склад A", status="active")
    db.add(wh)
    mat = Material(organization_id=org_a.id, name="Материал A")
    db.add(mat)
    db.flush()
    db.add(InventoryBalance(organization_id=org_a.id, warehouse_id=wh.id, material_id=mat.id,
                            quantity=Decimal("100"), reserved_quantity=Decimal("0"),
                            average_unit_cost=Decimal("10")))
    # коннектор интеграций в организации A
    conn = IntegrationConnector(organization_id=org_a.id, code="a-conn", name="A", channel="internal",
                                status="draft")
    db.add(conn)
    # публикация SMM в организации A
    pub = SocialPublication(organization_id=org_a.id, channel="internal", title="A", status="draft")
    db.add(pub)
    db.flush()
    ids = {"warehouse": wh.id, "connector": conn.id, "publication": pub.id}
    user_b = _user_in(db, org_b, PERMS)
    db.commit()
    return ids, user_b


def test_warehouse_balances_not_leaked_across_org(db_engine, db_session) -> None:
    ids, user_b = _seed(db_session)
    client = _client(db_engine, user_b)
    # пользователь организации B знает id склада организации A, но не видит остатки
    assert client.get(f"/procurement/warehouses/{ids['warehouse']}/balances").status_code == 404


def test_connector_not_visible_or_mutable_across_org(db_engine, db_session) -> None:
    ids, user_b = _seed(db_session)
    client = _client(db_engine, user_b)
    # в списке коннекторов организации B нет коннектора организации A
    assert ids["connector"] not in [c["id"] for c in client.get("/integrations/connectors").json()]
    # и его нельзя изменить, зная id
    r = client.post(f"/integrations/connectors/{ids['connector']}/status", json={"status": "configured"})
    assert r.status_code == 404


def test_publication_not_visible_across_org(db_engine, db_session) -> None:
    ids, user_b = _seed(db_session)
    client = _client(db_engine, user_b)
    assert ids["publication"] not in [p["id"] for p in client.get("/smm/publications").json()]
    # доступ к материалам чужой публикации по id запрещён
    assert client.get(f"/smm/publications/{ids['publication']}/assets").status_code == 404
