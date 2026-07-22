"""Тесты настраиваемых порогов согласований (этап G, PR-G).

Проверяют: пороги задаются по организации/проекту/виду процесса; расчёт уровня
риска подбирает наиболее специфичное применимое правило; по умолчанию R1; RBAC и
изоляция по организации.
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
    Organization,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)
from app.services import risk_threshold as svc


def _org(db):
    org = Organization(legal_name="ТЕСТ")
    db.add(org)
    db.flush()
    return org


def _user(db, org, *, perms=(), email=None):
    emp = Employee(organization_id=org.id, full_name="Сотрудник")
    db.add(emp)
    db.flush()
    user = User(email=email or f"u{uuid.uuid4().hex[:8]}@ex.com",
                password_hash=hash_password("x"), status="active", employee_id=emp.id)
    db.add(user)
    db.flush()
    role = Role(code=f"r{uuid.uuid4().hex[:6]}", name="r")
    db.add(role)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    for pc in perms:
        p = db.query(Permission).filter(Permission.code == pc).first()
        if p is None:
            p = Permission(code=pc)
            db.add(p)
            db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=p.id))
    db.commit()
    return user


# ---------------------------------------------------------------------------
# Расчёт уровня риска
# ---------------------------------------------------------------------------

def test_default_is_r1_when_no_thresholds(db_session) -> None:
    org = _org(db_session)
    res = svc.resolve(db_session, org.id, process_kind="finance_payment",
                      amount=Decimal("1000000"))
    assert res["risk_level"] == "R1"


def test_amount_threshold_matches_range(db_session) -> None:
    org = _org(db_session)
    svc.set_threshold(db_session, org.id, metric="amount", risk_level="R3",
                      min_value=Decimal("500000"), process_kind="finance_payment",
                      required_approvals=2)
    # ниже порога — правило не срабатывает → R1
    low = svc.resolve(db_session, org.id, process_kind="finance_payment",
                      amount=Decimal("100000"))
    assert low["risk_level"] == "R1"
    # выше порога — R3, 2 согласующих
    high = svc.resolve(db_session, org.id, process_kind="finance_payment",
                       amount=Decimal("900000"))
    assert high["risk_level"] == "R3" and high["required_approvals"] == 2


def test_more_specific_rule_wins(db_session) -> None:
    org = _org(db_session)
    project = uuid.uuid4()
    # общее правило по виду
    svc.set_threshold(db_session, org.id, metric="default", risk_level="R2",
                      process_kind="contract")
    # более специфичное правило по проекту+виду
    svc.set_threshold(db_session, org.id, metric="default", risk_level="R4",
                      process_kind="contract", project_id=project,
                      requires_mfa=True)
    res = svc.resolve(db_session, org.id, process_kind="contract", project_id=project)
    assert res["risk_level"] == "R4" and res["requires_mfa"] is True


def test_duration_threshold(db_session) -> None:
    org = _org(db_session)
    svc.set_threshold(db_session, org.id, metric="duration_days", risk_level="R2",
                      min_value=Decimal("30"), process_kind="task")
    res = svc.resolve(db_session, org.id, process_kind="task", duration_days=45)
    assert res["risk_level"] == "R2"


def test_invalid_metric_and_level_rejected(db_session) -> None:
    org = _org(db_session)
    with pytest.raises(svc.RiskThresholdError):
        svc.set_threshold(db_session, org.id, metric="bogus", risk_level="R2")
    with pytest.raises(svc.RiskThresholdError):
        svc.set_threshold(db_session, org.id, metric="amount", risk_level="R9")


# ---------------------------------------------------------------------------
# API: RBAC / изоляция
# ---------------------------------------------------------------------------

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


def test_api_set_requires_manage(db_engine, db_session) -> None:
    org = _org(db_session)
    db_session.commit()
    user = _user(db_session, org, perms=["risk.view"])
    client = _client(db_engine, user)
    resp = client.post("/risk-thresholds",
                       json={"metric": "default", "risk_level": "R2"})
    assert resp.status_code == 403


def test_api_resolve_and_isolation(db_engine, db_session) -> None:
    org_a = _org(db_session)
    org_b = _org(db_session)
    db_session.commit()
    user_a = _user(db_session, org_a, perms=["risk.view", "risk.manage"], email="a@ex.com")
    client_a = _client(db_engine, user_a)
    client_a.post("/risk-thresholds", json={
        "metric": "default", "risk_level": "R3", "process_kind": "contract"})
    r = client_a.get("/risk-thresholds/resolve", params={"process_kind": "contract"})
    assert r.status_code == 200 and r.json()["risk_level"] == "R3"
    app.dependency_overrides.clear()
    # другая организация не видит чужие пороги
    user_b = _user(db_session, org_b, perms=["risk.view", "risk.manage"], email="b@ex.com")
    client_b = _client(db_engine, user_b)
    assert client_b.get("/risk-thresholds").json() == []
    rb = client_b.get("/risk-thresholds/resolve", params={"process_kind": "contract"})
    assert rb.json()["risk_level"] == "R1"
