"""API-тесты модуля «Финансы и бюджеты».

Покрывают: RBAC и ABAC, формирование бюджета из утверждённой сметы, ручную
статью (обязателен источник + согласование), утверждение бюджета (R3) и крупного
бюджета (R4 + MFA), ручные обязательства, финансовую сводку проекта (агрегация
заказов, договоров и ФОТ без дублирования) и экспорт CSV/JSON.
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
    Contract,
    Counterparty,
    Employee,
    Estimate,
    FinanceSettings,
    Organization,
    PayrollDraft,
    Permission,
    Project,
    ProjectMember,
    PurchaseOrder,
    Role,
    RolePermission,
    Site,
    Supplier,
    User,
    UserRole,
)


def _make(db, *, perms=(), mfa=False, low_threshold=False):
    org = Organization(legal_name="ТЕСТ Финансы")
    db.add(org)
    db.flush()
    project = Project(organization_id=org.id, name="Проект", currency="RUB")
    db.add(project)
    db.flush()
    emp = Employee(organization_id=org.id, full_name="Финансист Тест")
    db.add(emp)
    db.flush()
    if low_threshold:
        db.add(FinanceSettings(organization_id=org.id, large_operation_threshold=Decimal("100")))
    secret = pyotp.random_base32() if mfa else None
    user = User(
        email=f"u{uuid.uuid4().hex[:8]}@ex.com", password_hash=hash_password("x"),
        status="active", employee_id=emp.id, mfa_enabled=mfa, mfa_secret=secret,
    )
    db.add(user)
    db.flush()
    role = Role(code=f"fin_{uuid.uuid4().hex[:6]}", name="r")
    db.add(role)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    for pc in perms:
        p = Permission(code=pc)
        db.add(p)
        db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=p.id))
    db.add(ProjectMember(project_id=project.id, employee_id=emp.id, project_role="finance"))
    db.commit()
    return org, project, emp, user, secret


def _approved_estimate(db, org, project, *, mat=200000, lab=100000, mch=50000, ovh=20000, prf=30000):
    est = Estimate(
        organization_id=org.id, project_id=project.id, name="Смета", number="СМ-1",
        status="approved", currency="RUB",
        material_total=Decimal(mat), labor_total=Decimal(lab), machine_total=Decimal(mch),
        overhead_total=Decimal(ovh), profit_total=Decimal(prf),
        grand_total=Decimal(mat + lab + mch + ovh + prf),
    )
    db.add(est)
    db.commit()
    return est


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


ALL = ["finance.view", "budget.manage", "budget.approve"]


# ------------------------------- RBAC/ABAC ------------------------------ #


def test_requires_permission(db_engine, db_session) -> None:
    _, project, _, user, _ = _make(db_session, perms=["supplier.view"])
    client = _client(db_engine, user)
    assert client.get(f"/finance/projects/{project.id}/budgets").status_code == 403


def test_abac_denies_foreign_project(db_engine, db_session) -> None:
    _, _, _, user, _ = _make(db_session, perms=["finance.view"])
    other = Project(organization_id=uuid.uuid4(), name="Чужой")
    db_session.add(other)
    db_session.commit()
    client = _client(db_engine, user)
    assert client.get(f"/finance/projects/{other.id}/financial-summary").status_code == 403


# --------------------------- Бюджет из сметы ---------------------------- #


def test_budget_from_estimate(db_engine, db_session) -> None:
    org, project, _, user, _ = _make(db_session, perms=ALL)
    est = _approved_estimate(db_session, org, project)
    client = _client(db_engine, user)
    r = client.post(f"/finance/projects/{project.id}/budgets/from-estimate",
                    json={"estimate_id": str(est.id)})
    assert r.status_code == 201
    body = r.json()
    assert body["planned_total"] == "400000.00"  # 200k+100k+50k+20k+30k
    assert len(body["lines"]) == 5
    assert body["status"] == "draft"
    # повторно из той же сметы — запрещено
    assert client.post(f"/finance/projects/{project.id}/budgets/from-estimate",
                       json={"estimate_id": str(est.id)}).status_code == 409


def test_budget_from_unapproved_estimate_rejected(db_engine, db_session) -> None:
    org, project, _, user, _ = _make(db_session, perms=ALL)
    est = _approved_estimate(db_session, org, project)
    est.status = "draft"
    db_session.commit()
    client = _client(db_engine, user)
    assert client.post(f"/finance/projects/{project.id}/budgets/from-estimate",
                       json={"estimate_id": str(est.id)}).status_code == 422


# --------------------------- Ручная статья ------------------------------ #


def test_manual_line_requires_source(db_engine, db_session) -> None:
    org, project, _, user, _ = _make(db_session, perms=ALL)
    est = _approved_estimate(db_session, org, project)
    client = _client(db_engine, user)
    bid = client.post(f"/finance/projects/{project.id}/budgets/from-estimate",
                      json={"estimate_id": str(est.id)}).json()["id"]
    # без источника — 422
    r = client.post(f"/finance/budgets/{bid}/manual-lines",
                    json={"description": "Аренда крана", "amount": 50000, "source_reference": ""})
    assert r.status_code == 422


def test_manual_line_approval_flow(db_engine, db_session) -> None:
    org, project, _, user, _ = _make(db_session, perms=ALL)
    est = _approved_estimate(db_session, org, project)
    client = _client(db_engine, user)
    bid = client.post(f"/finance/projects/{project.id}/budgets/from-estimate",
                      json={"estimate_id": str(est.id)}).json()["id"]
    line = client.post(f"/finance/budgets/{bid}/manual-lines", json={
        "description": "Аренда крана", "amount": 50000, "source_reference": "Служебная записка №7",
    })
    assert line.status_code == 201
    assert line.json()["status"] == "pending_approval"
    assert line.json()["is_manual"] is True
    lid = line.json()["id"]
    dec = client.post(f"/finance/budget-lines/{lid}/decision", json={"decision": "approved"})
    assert dec.status_code == 200
    assert dec.json()["status"] == "approved"
    # план бюджета вырос на ручную статью
    b = client.get(f"/finance/budgets/{bid}").json()
    assert b["planned_total"] == "450000.00"


# --------------------------- Утверждение -------------------------------- #


def test_budget_approval_r3(db_engine, db_session) -> None:
    org, project, _, user, _ = _make(db_session, perms=ALL)
    est = _approved_estimate(db_session, org, project)
    client = _client(db_engine, user)
    bid = client.post(f"/finance/projects/{project.id}/budgets/from-estimate",
                      json={"estimate_id": str(est.id)}).json()["id"]
    req = client.post(f"/finance/budgets/{bid}/request-approval")
    assert req.status_code == 200
    assert req.json()["risk_level"] == "R3"
    dec = client.post(f"/finance/budgets/{bid}/decision", json={"decision": "approved"})
    assert dec.status_code == 200
    assert dec.json()["status"] == "approved"
    assert dec.json()["approved_total"] == "400000.00"


def test_large_budget_r4_requires_mfa(db_engine, db_session) -> None:
    org, project, _, user, secret = _make(db_session, perms=ALL, mfa=True, low_threshold=True)
    est = _approved_estimate(db_session, org, project)
    client = _client(db_engine, user)
    bid = client.post(f"/finance/projects/{project.id}/budgets/from-estimate",
                      json={"estimate_id": str(est.id)}).json()["id"]
    req = client.post(f"/finance/budgets/{bid}/request-approval")
    assert req.json()["risk_level"] == "R4"  # порог низкий → крупный бюджет
    denied = client.post(f"/finance/budgets/{bid}/decision", json={"decision": "approved"})
    assert denied.status_code == 401
    code = pyotp.TOTP(secret).now()
    ok = client.post(f"/finance/budgets/{bid}/decision", json={"decision": "approved", "mfa_code": code})
    assert ok.status_code == 200
    assert ok.json()["status"] == "approved"


# --------------------- Сводка проекта (агрегация) ----------------------- #


def _supplier(db, org):
    cp = Counterparty(organization_id=org.id, name="Поставщик", counterparty_type="supplier")
    db.add(cp)
    db.flush()
    s = Supplier(counterparty_id=cp.id)
    db.add(s)
    db.flush()
    return s


def test_financial_summary_aggregation(db_engine, db_session) -> None:
    org, project, _, user, _ = _make(db_session, perms=ALL)
    est = _approved_estimate(db_session, org, project)
    # объект проекта + ФОТ (факт)
    site = Site(organization_id=org.id, project_id=project.id, name="Объект")
    db_session.add(site)
    db_session.flush()
    db_session.add(PayrollDraft(
        organization_id=org.id, site_id=site.id, period_start=est.created_at.date(),
        period_end=est.created_at.date(), status="approved", total_to_pay=Decimal("30000"),
    ))
    # заказы: обязательство (approved) и факт (received)
    sup = _supplier(db_session, org)
    db_session.add(PurchaseOrder(
        organization_id=org.id, project_id=project.id, supplier_id=sup.id,
        status="approved", total_amount=Decimal("100000"),
    ))
    db_session.add(PurchaseOrder(
        organization_id=org.id, project_id=project.id, supplier_id=sup.id,
        status="received", total_amount=Decimal("50000"),
    ))
    db_session.commit()

    client = _client(db_engine, user)
    bid = client.post(f"/finance/projects/{project.id}/budgets/from-estimate",
                      json={"estimate_id": str(est.id)}).json()["id"]
    client.post(f"/finance/budgets/{bid}/request-approval")
    client.post(f"/finance/budgets/{bid}/decision", json={"decision": "approved"})

    s = client.get(f"/finance/projects/{project.id}/financial-summary").json()
    assert s["approved_budget"] == "400000.00"
    assert s["committed"] == "100000.00"          # заказ approved
    assert s["actual"] == "80000.00"              # 50k received + 30k payroll
    assert s["remaining"] == "320000.00"          # 400k − 80k
    assert s["forecast"] == "180000.00"           # 80k + 100k
    assert s["has_approved_budget"] is True


def test_manual_commitment_and_summary(db_engine, db_session) -> None:
    org, project, _, user, _ = _make(db_session, perms=ALL)
    client = _client(db_engine, user)
    c = client.post(f"/finance/projects/{project.id}/commitments", json={
        "description": "Аренда офиса", "amount": 20000, "source_reference": "Решение директора",
    })
    assert c.status_code == 201
    assert c.json()["status"] == "open"
    s = client.get(f"/finance/projects/{project.id}/financial-summary").json()
    assert s["committed"] == "20000.00"


# ------------------------------- Экспорт -------------------------------- #


def test_export_csv_and_json(db_engine, db_session) -> None:
    org, project, _, user, _ = _make(db_session, perms=ALL)
    client = _client(db_engine, user)
    csv_r = client.get(f"/finance/projects/{project.id}/financial-summary/export?format=csv")
    assert csv_r.status_code == 200
    assert "text/csv" in csv_r.headers["content-type"]
    assert "approved_budget" in csv_r.text
    json_r = client.get(f"/finance/projects/{project.id}/financial-summary/export?format=json")
    assert json_r.status_code == 200
    assert json_r.json()["currency"] == "RUB"
