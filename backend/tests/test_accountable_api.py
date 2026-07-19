"""API-тесты модуля «Подотчётные средства».

Покрывают: RBAC/ABAC, полный жизненный цикл (выдача → согласование → расходы →
чек → проверка → авансовый отчёт → закрытие), крупную выдачу R4 + MFA, лимит
статьи, предотвращение повторного использования чека, обязательность документа,
возврат остатка и возмещение перерасхода, сводку.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date, timedelta
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
    ExpenseCategory,
    FinanceSettings,
    Organization,
    Permission,
    Project,
    ProjectMember,
    Role,
    RolePermission,
    User,
    UserRole,
)


def _make(db, *, perms=(), mfa=False, low_threshold=False):
    org = Organization(legal_name="ТЕСТ Подотчёт")
    db.add(org)
    db.flush()
    project = Project(organization_id=org.id, name="Проект", currency="RUB")
    db.add(project)
    db.flush()
    emp = Employee(organization_id=org.id, full_name="Подотчётное Лицо")
    db.add(emp)
    db.flush()
    cat = ExpenseCategory(organization_id=org.id, code="FUEL", name="Топливо", requires_receipt=True)
    db.add(cat)
    db.flush()
    if low_threshold:
        db.add(FinanceSettings(organization_id=org.id, large_operation_threshold=Decimal("100")))
    secret = pyotp.random_base32() if mfa else None
    user = User(email=f"u{uuid.uuid4().hex[:8]}@ex.com", password_hash=hash_password("x"),
                status="active", employee_id=emp.id, mfa_enabled=mfa, mfa_secret=secret)
    db.add(user)
    db.flush()
    role = Role(code=f"acc_{uuid.uuid4().hex[:6]}", name="r")
    db.add(role)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    for pc in perms:
        p = Permission(code=pc)
        db.add(p)
        db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=p.id))
    db.add(ProjectMember(project_id=project.id, employee_id=emp.id, project_role="accountable"))
    db.commit()
    return org, project, emp, cat, user, secret


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


ALL = ["accountable.view", "accountable.manage", "accountable.approve", "accountable.account"]


def _issued_advance(client, emp_id, amount=5000):
    a = client.post("/accountable/advances", json={
        "employee_id": str(emp_id), "purpose": "ГСМ на объект", "amount_issued": amount,
        "report_due_at": None,
    }).json()
    client.post(f"/accountable/advances/{a['id']}/request-approval")
    client.post(f"/accountable/advances/{a['id']}/decision", json={"decision": "approved"})
    client.post(f"/accountable/advances/{a['id']}/issue", json={})
    return a["id"]


# ------------------------------- RBAC/ABAC ------------------------------ #


def test_requires_permission(db_engine, db_session) -> None:
    _, _, emp, _, user, _ = _make(db_session, perms=["accountable.view"])
    client = _client(db_engine, user)
    r = client.post("/accountable/advances", json={"employee_id": str(emp.id), "purpose": "x", "amount_issued": 100})
    assert r.status_code == 403


# ------------------------------- Выдача --------------------------------- #


def test_advance_approval_r3(db_engine, db_session) -> None:
    _, _, emp, _, user, _ = _make(db_session, perms=ALL)
    client = _client(db_engine, user)
    a = client.post("/accountable/advances", json={"employee_id": str(emp.id), "purpose": "ГСМ", "amount_issued": 5000})
    assert a.status_code == 201 and a.json()["status"] == "draft"
    req = client.post(f"/accountable/advances/{a.json()['id']}/request-approval")
    assert req.json()["risk_level"] == "R3"
    dec = client.post(f"/accountable/advances/{a.json()['id']}/decision", json={"decision": "approved"})
    assert dec.json()["status"] == "approved"
    iss = client.post(f"/accountable/advances/{a.json()['id']}/issue", json={})
    assert iss.json()["status"] == "issued"


def test_large_advance_r4_requires_mfa(db_engine, db_session) -> None:
    _, _, emp, _, user, secret = _make(db_session, perms=ALL, mfa=True, low_threshold=True)
    client = _client(db_engine, user)
    aid = client.post("/accountable/advances", json={"employee_id": str(emp.id), "purpose": "крупная", "amount_issued": 5000}).json()["id"]
    assert client.post(f"/accountable/advances/{aid}/request-approval").json()["risk_level"] == "R4"
    denied = client.post(f"/accountable/advances/{aid}/decision", json={"decision": "approved"})
    assert denied.status_code == 401
    ok = client.post(f"/accountable/advances/{aid}/decision", json={"decision": "approved", "mfa_code": pyotp.TOTP(secret).now()})
    assert ok.status_code == 200 and ok.json()["status"] == "approved"


# ------------------------ Расходы, чеки, лимит -------------------------- #


def test_expense_limit_enforced(db_engine, db_session) -> None:
    org, _, emp, cat, user, _ = _make(db_session, perms=ALL)
    cat.default_limit = Decimal("1000")
    db_session.commit()
    client = _client(db_engine, user)
    aid = _issued_advance(client, emp.id)
    over = client.post(f"/accountable/advances/{aid}/expenses", json={
        "expense_category_id": str(cat.id), "amount": 1500, "expense_date": date.today().isoformat(), "description": "дорого",
    })
    assert over.status_code == 422


def test_receipt_dedup_and_required(db_engine, db_session) -> None:
    org, _, emp, cat, user, _ = _make(db_session, perms=ALL)
    client = _client(db_engine, user)
    aid = _issued_advance(client, emp.id)
    eid = client.post(f"/accountable/advances/{aid}/expenses", json={
        "expense_category_id": str(cat.id), "amount": 800, "expense_date": date.today().isoformat(), "description": "заправка",
    }).json()["id"]
    # обязателен чек: проверка без документа отклоняется
    denied = client.post(f"/accountable/expenses/{eid}/verify", json={"decision": "approved"})
    assert denied.status_code == 422
    # прикрепляем чек
    doc = client.post(f"/accountable/expenses/{eid}/documents", json={"duplicate_hash": "FISCAL-XYZ-1", "document_number": "0001"})
    assert doc.status_code == 201
    # повторное использование того же чека — запрещено
    eid2 = client.post(f"/accountable/advances/{aid}/expenses", json={
        "expense_category_id": str(cat.id), "amount": 200, "expense_date": date.today().isoformat(), "description": "ещё",
    }).json()["id"]
    dup = client.post(f"/accountable/expenses/{eid2}/documents", json={"duplicate_hash": "FISCAL-XYZ-1"})
    assert dup.status_code == 409
    # теперь проверка проходит
    assert client.post(f"/accountable/expenses/{eid}/verify", json={"decision": "approved"}).json()["verification_status"] == "approved"


# --------------------- Полный цикл: возврат остатка --------------------- #


def test_full_cycle_with_return(db_engine, db_session) -> None:
    org, _, emp, cat, user, _ = _make(db_session, perms=ALL)
    client = _client(db_engine, user)
    aid = _issued_advance(client, emp.id, amount=5000)
    eid = client.post(f"/accountable/advances/{aid}/expenses", json={
        "expense_category_id": str(cat.id), "amount": 3000, "expense_date": date.today().isoformat(), "description": "ГСМ",
    }).json()["id"]
    client.post(f"/accountable/expenses/{eid}/documents", json={"duplicate_hash": "H-1"})
    client.post(f"/accountable/expenses/{eid}/verify", json={"decision": "approved"})
    rep = client.post(f"/accountable/advances/{aid}/report", json={})
    assert rep.status_code == 201
    rid = rep.json()["id"]
    rev = client.post(f"/accountable/reports/{rid}/review", json={"decision": "approved"})
    assert rev.json()["amount_to_return"] == "2000.00"  # 5000 - 3000
    adv = client.get(f"/accountable/advances/{aid}").json()
    assert adv["status"] == "awaiting_return"
    # возврат остатка → закрытие
    st = client.post(f"/accountable/advances/{aid}/settlements", json={"settlement_type": "return", "amount": 2000})
    assert st.status_code == 201
    assert client.get(f"/accountable/advances/{aid}").json()["status"] == "closed"


def test_full_cycle_with_reimbursement(db_engine, db_session) -> None:
    org, _, emp, cat, user, _ = _make(db_session, perms=ALL)
    client = _client(db_engine, user)
    aid = _issued_advance(client, emp.id, amount=1000)
    eid = client.post(f"/accountable/advances/{aid}/expenses", json={
        "expense_category_id": str(cat.id), "amount": 1500, "expense_date": date.today().isoformat(), "description": "перерасход",
    }).json()["id"]
    client.post(f"/accountable/expenses/{eid}/documents", json={"duplicate_hash": "H-2"})
    client.post(f"/accountable/expenses/{eid}/verify", json={"decision": "approved"})
    rid = client.post(f"/accountable/advances/{aid}/report", json={}).json()["id"]
    rev = client.post(f"/accountable/reports/{rid}/review", json={"decision": "approved"})
    assert rev.json()["amount_to_reimburse"] == "500.00"  # 1500 - 1000
    assert client.get(f"/accountable/advances/{aid}").json()["status"] == "awaiting_reimbursement"
    client.post(f"/accountable/advances/{aid}/settlements", json={"settlement_type": "reimbursement", "amount": 500})
    assert client.get(f"/accountable/advances/{aid}").json()["status"] == "closed"


def test_settlement_idempotent(db_engine, db_session) -> None:
    org, _, emp, cat, user, _ = _make(db_session, perms=ALL)
    client = _client(db_engine, user)
    aid = _issued_advance(client, emp.id, amount=5000)
    eid = client.post(f"/accountable/advances/{aid}/expenses", json={
        "expense_category_id": str(cat.id), "amount": 3000, "expense_date": date.today().isoformat(), "description": "ГСМ",
    }).json()["id"]
    client.post(f"/accountable/expenses/{eid}/documents", json={"duplicate_hash": "H-3"})
    client.post(f"/accountable/expenses/{eid}/verify", json={"decision": "approved"})
    rid = client.post(f"/accountable/advances/{aid}/report", json={}).json()["id"]
    client.post(f"/accountable/reports/{rid}/review", json={"decision": "approved"})
    s1 = client.post(f"/accountable/advances/{aid}/settlements", json={"settlement_type": "return", "amount": 2000, "idempotency_key": "K"})
    s2 = client.post(f"/accountable/advances/{aid}/settlements", json={"settlement_type": "return", "amount": 2000, "idempotency_key": "K"})
    assert s1.json()["id"] == s2.json()["id"]  # повтор не создаёт дубликат


def test_summary(db_engine, db_session) -> None:
    org, _, emp, cat, user, _ = _make(db_session, perms=ALL)
    client = _client(db_engine, user)
    _issued_advance(client, emp.id, amount=5000)
    s = client.get("/accountable/summary").json()
    assert s["advances_open"] == 1
    assert s["total_issued"] == "5000.00"
    assert s["total_outstanding"] == "5000.00"
