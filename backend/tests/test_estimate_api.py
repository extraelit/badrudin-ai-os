"""API-тесты модуля «Сметы и ценообразование»: RBAC, ABAC, утверждение, КП R3/R4."""

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
    Organization,
    Permission,
    PricingSettings,
    Project,
    ProjectMember,
    Role,
    RolePermission,
    UnitOfMeasure,
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
    emp = Employee(organization_id=org.id, full_name="Сметчик Тест")
    db.add(emp)
    db.flush()
    unit = UnitOfMeasure(code="м2", name="кв. метр", category="area")
    db.add(unit)
    db.flush()
    if low_threshold:
        db.add(PricingSettings(organization_id=org.id, offer_r4_amount_threshold=Decimal("100")))
    secret = pyotp.random_base32() if mfa else None
    user = User(email=f"u{uuid.uuid4().hex[:8]}@ex.com", password_hash=hash_password("x"),
                status="active", employee_id=emp.id, mfa_enabled=mfa, mfa_secret=secret)
    db.add(user)
    db.flush()
    role = Role(code="est_role", name="r")
    db.add(role)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    for pc in perms:
        p = Permission(code=pc)
        db.add(p)
        db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=p.id))
    db.add(ProjectMember(project_id=project.id, employee_id=emp.id, project_role="estimator"))
    db.commit()
    return org, project, unit, user, secret


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


def _add_valid_position(client, eid, unit_id):
    return client.post(f"/estimates/{eid}/positions", json={
        "name": "Кладка стен", "unit_id": str(unit_id), "quantity": 10,
        "material_unit_cost": 100, "labor_unit_cost": 50, "machine_unit_cost": 20,
        "overhead_percent": 15, "profit_percent": 8,
    })


def test_requires_permission(db_engine, db_session) -> None:
    _, project, _, user, _ = _make_user(db_session, perms=["supplier.view"])
    client = _client(db_engine, user)
    assert client.get(f"/estimates/projects/{project.id}/estimates").status_code == 403


def test_abac_denies_foreign_project(db_engine, db_session) -> None:
    _, _, _, user, _ = _make_user(db_session, perms=["estimate.view"])
    other = Project(organization_id=uuid.uuid4(), name="Чужой")
    db_session.add(other)
    db_session.commit()
    client = _client(db_engine, user)
    assert client.get(f"/estimates/projects/{other.id}/estimates").status_code == 403


def test_create_recalc_and_totals(db_engine, db_session) -> None:
    _, project, unit, user, _ = _make_user(db_session, perms=["estimate.view", "estimate.manage"])
    client = _client(db_engine, user)
    e = client.post(f"/estimates/projects/{project.id}/estimates",
                    json={"name": "Локальная смета", "number": "СМ-1", "vat_rate": 20})
    assert e.status_code == 201
    eid = e.json()["id"]
    r = _add_valid_position(client, eid, unit.id)
    assert r.status_code == 201
    body = r.json()
    assert body["grand_total"] == "2533.68"
    assert body["direct_total"] == "1700.00"


def test_approve_empty_rejected(db_engine, db_session) -> None:
    _, project, _, user, _ = _make_user(db_session, perms=["estimate.view", "estimate.manage", "estimate.approve"])
    client = _client(db_engine, user)
    e = client.post(f"/estimates/projects/{project.id}/estimates", json={"name": "Пустая", "number": "СМ-2"})
    eid = e.json()["id"]
    ap = client.post(f"/estimates/{eid}/approve")
    assert ap.status_code == 422  # пустая смета — утверждение запрещено


def test_forbid_position_on_approved(db_engine, db_session) -> None:
    _, project, unit, user, _ = _make_user(db_session, perms=["estimate.view", "estimate.manage", "estimate.approve"])
    client = _client(db_engine, user)
    eid = client.post(f"/estimates/projects/{project.id}/estimates", json={"name": "С", "number": "СМ-3"}).json()["id"]
    _add_valid_position(client, eid, unit.id)
    assert client.post(f"/estimates/{eid}/approve").status_code == 200
    # прямое изменение утверждённой сметы запрещено
    assert _add_valid_position(client, eid, unit.id).status_code == 409


def test_new_version_flow(db_engine, db_session) -> None:
    _, project, unit, user, _ = _make_user(db_session, perms=["estimate.view", "estimate.manage", "estimate.approve"])
    client = _client(db_engine, user)
    eid = client.post(f"/estimates/projects/{project.id}/estimates", json={"name": "С", "number": "СМ-4"}).json()["id"]
    _add_valid_position(client, eid, unit.id)
    client.post(f"/estimates/{eid}/approve")
    v2 = client.post(f"/estimates/{eid}/new-version", json={"reason": "изменение объёмов"})
    assert v2.status_code == 201
    assert v2.json()["version"] == 2
    assert v2.json()["status"] == "draft"


def test_offer_r3_flow(db_engine, db_session) -> None:
    _, project, unit, user, _ = _make_user(
        db_session, perms=["estimate.view", "estimate.manage", "estimate.approve", "offer.approve"]
    )
    client = _client(db_engine, user)
    eid = client.post(f"/estimates/projects/{project.id}/estimates", json={"name": "С", "number": "СМ-5"}).json()["id"]
    _add_valid_position(client, eid, unit.id)
    client.post(f"/estimates/{eid}/approve")
    offer = client.post(f"/estimates/{eid}/offers", json={"markup_percent": 10})
    assert offer.status_code == 201
    assert offer.json()["risk_level"] == "R3"
    oid = offer.json()["id"]
    client.post(f"/estimates/offers/{oid}/request-approval")
    dec = client.post(f"/estimates/offers/{oid}/decision", json={"decision": "approved"})
    assert dec.status_code == 200
    assert dec.json()["status"] == "approved"


def test_offer_r4_requires_mfa(db_engine, db_session) -> None:
    _, project, unit, user, secret = _make_user(
        db_session,
        perms=["estimate.view", "estimate.manage", "estimate.approve", "offer.approve"],
        mfa=True, low_threshold=True,
    )
    client = _client(db_engine, user)
    eid = client.post(f"/estimates/projects/{project.id}/estimates", json={"name": "С", "number": "СМ-6"}).json()["id"]
    _add_valid_position(client, eid, unit.id)
    client.post(f"/estimates/{eid}/approve")
    offer = client.post(f"/estimates/{eid}/offers", json={"markup_percent": 10})
    assert offer.json()["risk_level"] == "R4"  # порог организации низкий
    oid = offer.json()["id"]
    client.post(f"/estimates/offers/{oid}/request-approval")
    denied = client.post(f"/estimates/offers/{oid}/decision", json={"decision": "approved"})
    assert denied.status_code == 401
    code = pyotp.TOTP(secret).now()
    ok = client.post(f"/estimates/offers/{oid}/decision", json={"decision": "approved", "mfa_code": code})
    assert ok.status_code == 200
    assert ok.json()["status"] == "approved"


def test_plan_fact_and_summary(db_engine, db_session) -> None:
    _, project, unit, user, _ = _make_user(db_session, perms=["estimate.view", "estimate.manage"])
    client = _client(db_engine, user)
    eid = client.post(f"/estimates/projects/{project.id}/estimates", json={"name": "С", "number": "СМ-7"}).json()["id"]
    _add_valid_position(client, eid, unit.id)
    pf = client.get(f"/estimates/{eid}/plan-fact")
    assert pf.status_code == 200
    assert pf.json()["planned_total"] == "2111.40"
    s = client.get(f"/estimates/projects/{project.id}/summary")
    assert s.status_code == 200
    assert s.json()["estimates_total"] == 1
