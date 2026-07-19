"""API-тесты модуля «Ядро CRM».

Покрывают: RBAC и ABAC, настраиваемую воронку, конвертацию lead → deal,
перемещение по этапам, выигрыш сделки (R3) и крупной сделки (R4 + MFA),
согласование и подписание договора, создание проекта из выигранной сделки,
маскирование ПДн контактов и сводную аналитику продаж.
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
    Counterparty,
    CrmSettings,
    Employee,
    Organization,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)


def _make_user(db, *, perms=(), mfa=False, low_threshold=False):
    org = Organization(legal_name="ТЕСТ CRM")
    db.add(org)
    db.flush()
    emp = Employee(organization_id=org.id, full_name="Менеджер Тест")
    db.add(emp)
    db.flush()
    cp = Counterparty(organization_id=org.id, name="ООО «Клиент»", counterparty_type="customer")
    db.add(cp)
    db.flush()
    if low_threshold:
        db.add(CrmSettings(organization_id=org.id, deal_r4_amount_threshold=Decimal("100")))
    secret = pyotp.random_base32() if mfa else None
    user = User(
        email=f"u{uuid.uuid4().hex[:8]}@ex.com", password_hash=hash_password("x"),
        status="active", employee_id=emp.id, mfa_enabled=mfa, mfa_secret=secret,
    )
    db.add(user)
    db.flush()
    role = Role(code=f"crm_role_{uuid.uuid4().hex[:6]}", name="r")
    db.add(role)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    for pc in perms:
        p = Permission(code=pc)
        db.add(p)
        db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=p.id))
    db.commit()
    return org, emp, cp, user, secret


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


ALL = ["crm.view", "crm.manage", "deal.approve"]


def _init_pipeline(client) -> list[dict]:
    r = client.post("/crm/pipeline/init")
    assert r.status_code == 200
    return r.json()


def _open_deal(client, cp_id, amount=500000):
    return client.post("/crm/deals", json={
        "title": "Сделка", "counterparty_id": str(cp_id), "amount": amount,
    })


# ------------------------------- RBAC/ABAC ------------------------------ #


def test_requires_permission(db_engine, db_session) -> None:
    _, _, cp, user, _ = _make_user(db_session, perms=["supplier.view"])
    client = _client(db_engine, user)
    assert client.get("/crm/deals").status_code == 403


def test_manage_requires_manage_perm(db_engine, db_session) -> None:
    _, _, cp, user, _ = _make_user(db_session, perms=["crm.view"])
    client = _client(db_engine, user)
    assert _open_deal(client, cp.id).status_code == 403


def test_user_without_employee_rejected(db_engine, db_session) -> None:
    user = User(email="noemp@ex.com", password_hash=hash_password("x"), status="active")
    db_session.add(user)
    db_session.commit()
    # даём право, но нет сотрудника → 400
    role = Role(code="r_noemp", name="r")
    db_session.add(role)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id=role.id))
    p = Permission(code="crm.view")
    db_session.add(p)
    db_session.flush()
    db_session.add(RolePermission(role_id=role.id, permission_id=p.id))
    db_session.commit()
    client = _client(db_engine, user)
    assert client.get("/crm/deals").status_code == 400


# ------------------------------- Воронка -------------------------------- #


def test_pipeline_init_and_configurable(db_engine, db_session) -> None:
    _, _, cp, user, _ = _make_user(db_session, perms=ALL)
    client = _client(db_engine, user)
    stages = _init_pipeline(client)
    assert len(stages) == 7
    assert any(s["is_won"] for s in stages)
    assert any(s["is_lost"] for s in stages)
    # повторный init не дублирует
    assert len(client.post("/crm/pipeline/init").json()) == 7
    # добавляем свой этап (настраиваемость)
    extra = client.post("/crm/pipeline/stages", json={
        "name": "Тендер", "sort_order": 3, "probability_percent": 40,
    })
    assert extra.status_code == 201
    assert len(client.get("/crm/pipeline/stages").json()) == 8


# --------------------------- Лиды и конверсия --------------------------- #


def test_lead_convert_to_deal(db_engine, db_session) -> None:
    _, _, cp, user, _ = _make_user(db_session, perms=ALL)
    client = _client(db_engine, user)
    _init_pipeline(client)
    lead = client.post("/crm/leads", json={
        "title": "Запрос с сайта", "counterparty_id": str(cp.id),
        "estimated_amount": 300000,
    })
    assert lead.status_code == 201
    lid = lead.json()["id"]
    conv = client.post(f"/crm/leads/{lid}/convert", json={})
    assert conv.status_code == 201
    assert conv.json()["status"] == "open"
    assert conv.json()["lead_id"] == lid
    # лид помечен converted, повторная конверсия запрещена
    assert client.post(f"/crm/leads/{lid}/convert", json={}).status_code == 409


def test_lead_convert_without_counterparty_rejected(db_engine, db_session) -> None:
    _, _, cp, user, _ = _make_user(db_session, perms=ALL)
    client = _client(db_engine, user)
    _init_pipeline(client)
    lead = client.post("/crm/leads", json={"title": "Без контрагента"})
    lid = lead.json()["id"]
    assert client.post(f"/crm/leads/{lid}/convert", json={}).status_code == 422


# ------------------------------- Сделки --------------------------------- #


def test_move_stage_and_history(db_engine, db_session) -> None:
    _, _, cp, user, _ = _make_user(db_session, perms=ALL)
    client = _client(db_engine, user)
    stages = _init_pipeline(client)
    normal = [s for s in stages if not s["is_won"] and not s["is_lost"]][2]
    deal = _open_deal(client, cp.id).json()
    r = client.post(f"/crm/deals/{deal['id']}/move-stage", json={"pipeline_stage_id": normal["id"]})
    assert r.status_code == 200
    assert r.json()["pipeline_stage_id"] == normal["id"]


def test_cannot_move_to_won_stage_directly(db_engine, db_session) -> None:
    _, _, cp, user, _ = _make_user(db_session, perms=ALL)
    client = _client(db_engine, user)
    stages = _init_pipeline(client)
    won = [s for s in stages if s["is_won"]][0]
    deal = _open_deal(client, cp.id).json()
    r = client.post(f"/crm/deals/{deal['id']}/move-stage", json={"pipeline_stage_id": won["id"]})
    assert r.status_code == 409


def test_deal_win_r3_flow(db_engine, db_session) -> None:
    _, _, cp, user, _ = _make_user(db_session, perms=ALL)
    client = _client(db_engine, user)
    _init_pipeline(client)
    deal = _open_deal(client, cp.id, amount=500000).json()
    req = client.post(f"/crm/deals/{deal['id']}/request-win")
    assert req.status_code == 200
    assert req.json()["risk_level"] == "R3"
    dec = client.post(f"/crm/deals/{deal['id']}/win-decision", json={"decision": "approved"})
    assert dec.status_code == 200
    assert dec.json()["status"] == "won"


def test_deal_win_r4_requires_mfa(db_engine, db_session) -> None:
    _, _, cp, user, secret = _make_user(db_session, perms=ALL, mfa=True, low_threshold=True)
    client = _client(db_engine, user)
    _init_pipeline(client)
    deal = _open_deal(client, cp.id, amount=5000).json()
    req = client.post(f"/crm/deals/{deal['id']}/request-win")
    assert req.json()["risk_level"] == "R4"  # порог организации низкий
    denied = client.post(f"/crm/deals/{deal['id']}/win-decision", json={"decision": "approved"})
    assert denied.status_code == 401
    code = pyotp.TOTP(secret).now()
    ok = client.post(f"/crm/deals/{deal['id']}/win-decision", json={"decision": "approved", "mfa_code": code})
    assert ok.status_code == 200
    assert ok.json()["status"] == "won"


def test_deal_lose_with_reason(db_engine, db_session) -> None:
    _, _, cp, user, _ = _make_user(db_session, perms=ALL)
    client = _client(db_engine, user)
    _init_pipeline(client)
    reason = client.post("/crm/loss-reasons", json={"name": "Дорого"}).json()
    deal = _open_deal(client, cp.id).json()
    r = client.post(f"/crm/deals/{deal['id']}/lose", json={
        "loss_reason_id": reason["id"], "comment": "клиент выбрал конкурента",
    })
    assert r.status_code == 200
    assert r.json()["status"] == "lost"
    assert r.json()["loss_reason_id"] == reason["id"]


# ------------------------ Договоры и проект ----------------------------- #


def test_contract_approval_and_project_chain(db_engine, db_session) -> None:
    _, _, cp, user, _ = _make_user(db_session, perms=ALL)
    client = _client(db_engine, user)
    _init_pipeline(client)
    # выигрываем сделку
    deal = _open_deal(client, cp.id, amount=800000).json()
    client.post(f"/crm/deals/{deal['id']}/request-win")
    client.post(f"/crm/deals/{deal['id']}/win-decision", json={"decision": "approved"})
    # договор → согласование (R3) → подписание
    contract = client.post("/crm/contracts", json={
        "counterparty_id": str(cp.id), "deal_id": deal["id"], "amount": 800000,
    }).json()
    ra = client.post(f"/crm/contracts/{contract['id']}/request-approval")
    assert ra.json()["risk_level"] == "R3"
    dec = client.post(f"/crm/contracts/{contract['id']}/decision", json={"decision": "approved"})
    assert dec.status_code == 200
    assert dec.json()["status"] == "approved"
    # проект создаётся только по выигранной сделке и утверждённому договору
    proj = client.post(f"/crm/deals/{deal['id']}/create-project", json={"contract_id": contract["id"]})
    assert proj.status_code == 201
    assert proj.json()["project_id"] is not None


def test_project_requires_won_deal(db_engine, db_session) -> None:
    _, _, cp, user, _ = _make_user(db_session, perms=ALL)
    client = _client(db_engine, user)
    _init_pipeline(client)
    deal = _open_deal(client, cp.id).json()  # остаётся open
    contract = client.post("/crm/contracts", json={
        "counterparty_id": str(cp.id), "deal_id": deal["id"], "amount": 500000,
    }).json()
    client.post(f"/crm/contracts/{contract['id']}/request-approval")
    client.post(f"/crm/contracts/{contract['id']}/decision", json={"decision": "approved"})
    r = client.post(f"/crm/deals/{deal['id']}/create-project", json={"contract_id": contract["id"]})
    assert r.status_code == 422  # сделка не выиграна


# ------------------------------- ПДн ------------------------------------ #


def test_contact_pii_masked_without_permission(db_engine, db_session) -> None:
    _, _, cp, user, _ = _make_user(db_session, perms=ALL)  # без crm.contact.pii
    client = _client(db_engine, user)
    client.post(f"/crm/counterparties/{cp.id}/contacts", json={
        "full_name": "Иван Петров", "email": "ivan@client.ru", "phone": "+79991234567",
        "consent_given": True,
    })
    contacts = client.get(f"/crm/counterparties/{cp.id}/contacts").json()
    assert contacts[0]["pii_masked"] is True
    assert "@client.ru" in contacts[0]["email"] and contacts[0]["email"].startswith("i***")
    assert contacts[0]["phone"].startswith("***") and contacts[0]["phone"].endswith("4567")


def test_contact_pii_visible_with_permission(db_engine, db_session) -> None:
    _, _, cp, user, _ = _make_user(db_session, perms=[*ALL, "crm.contact.pii"])
    client = _client(db_engine, user)
    client.post(f"/crm/counterparties/{cp.id}/contacts", json={
        "full_name": "Иван Петров", "email": "ivan@client.ru", "phone": "+79991234567",
    })
    contacts = client.get(f"/crm/counterparties/{cp.id}/contacts").json()
    assert contacts[0]["pii_masked"] is False
    assert contacts[0]["email"] == "ivan@client.ru"
    assert contacts[0]["phone"] == "+79991234567"


# ------------------------- Коммуникации → задачи ------------------------ #


def test_communication_creates_task(db_engine, db_session) -> None:
    _, _, cp, user, _ = _make_user(db_session, perms=ALL)
    client = _client(db_engine, user)
    comm = client.post("/crm/communications", json={
        "channel": "email", "direction": "inbound", "counterparty_id": str(cp.id),
        "subject": "Запрос КП",
    }).json()
    r = client.post(f"/crm/communications/{comm['id']}/create-task", json={"title": "Подготовить КП"})
    assert r.status_code == 200
    assert r.json()["processing_status"] == "task_created"
    assert r.json()["linked_task_id"] is not None


# ------------------------------ Аналитика ------------------------------- #


def test_sales_analytics(db_engine, db_session) -> None:
    _, emp, cp, user, _ = _make_user(db_session, perms=ALL)
    client = _client(db_engine, user)
    _init_pipeline(client)
    # цель менеджера
    client.post("/crm/sales-targets", json={
        "employee_id": str(emp.id), "period_year": 2026, "target_amount": 1000000,
    })
    # выигранная сделка на ответственного менеджера
    won = client.post("/crm/deals", json={
        "title": "Выигранная", "counterparty_id": str(cp.id), "amount": 600000,
        "responsible_employee_id": str(emp.id),
    }).json()
    client.post(f"/crm/deals/{won['id']}/request-win")
    client.post(f"/crm/deals/{won['id']}/win-decision", json={"decision": "approved"})
    # проигранная сделка
    lost = _open_deal(client, cp.id, amount=200000).json()
    client.post(f"/crm/deals/{lost['id']}/lose", json={})
    a = client.get("/crm/analytics/summary?period_year=2026").json()
    assert a["deals_total"] == 2
    assert a["won_count"] == 1 and a["lost_count"] == 1
    assert a["won_amount"] == "600000.00"
    assert a["conversion_percent"] == "50.00"
    assert len(a["funnel"]) == 7
    mgr = [m for m in a["managers"] if m["employee_id"] == str(emp.id)][0]
    assert mgr["target_amount"] == "1000000.00"
    assert mgr["plan_fact_percent"] == "60.00"
