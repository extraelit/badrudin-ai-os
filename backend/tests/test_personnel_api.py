"""API-тесты модуля «Персонал объектов»: RBAC, ABAC, гейт ОТ, выплаты R3/R4."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date
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
    AuditEvent,
    Employee,
    Organization,
    PayrollDraft,
    PayrollLine,
    Permission,
    Project,
    ProjectMember,
    Role,
    RolePermission,
    SafetyClearance,
    Site,
    User,
    UserRole,
)


def _make_user(db, *, perms=(), system=False, mfa=False):
    org = Organization(legal_name="ТЕСТ")
    db.add(org)
    db.flush()
    project = Project(organization_id=org.id, name="Проект")
    db.add(project)
    db.flush()
    site = Site(organization_id=org.id, project_id=project.id, name="Объект")
    db.add(site)
    db.flush()
    employee = Employee(organization_id=org.id, full_name="Работник Тест")
    db.add(employee)
    db.flush()
    secret = pyotp.random_base32() if mfa else None
    user = User(
        email=f"u{uuid.uuid4().hex[:8]}@ex.com",
        password_hash=hash_password("x"),
        status="active",
        employee_id=employee.id,
        mfa_enabled=mfa,
        mfa_secret=secret,
    )
    db.add(user)
    db.flush()
    role = Role(code="system_owner" if system else "test_role", name="r")
    db.add(role)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    if not system:
        for pc in perms:
            p = Permission(code=pc)
            db.add(p)
            db.flush()
            db.add(RolePermission(role_id=role.id, permission_id=p.id))
    # членство в проекте даёт доступ к объекту (ABAC)
    db.add(
        ProjectMember(
            project_id=project.id, employee_id=employee.id, project_role="foreman"
        )
    )
    db.commit()
    return org, project, site, user, secret


def _client(db_engine, user) -> Iterator[TestClient]:
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
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_workers_requires_permission(db_engine, db_session) -> None:
    _, _, site, user, _ = _make_user(db_session, perms=["finance.view"])
    client = _client(db_engine, user)
    resp = client.get(f"/personnel/sites/{site.id}/workers")
    assert resp.status_code == 403


def test_workers_abac_denies_foreign_site(db_engine, db_session) -> None:
    # пользователь с правом, но не член чужого проекта → нет доступа к объекту
    _, _, _, user, _ = _make_user(db_session, perms=["personnel.view"])
    other = Site(
        organization_id=uuid.uuid4(), project_id=uuid.uuid4(), name="Чужой объект"
    )
    db_session.add(other)
    db_session.commit()
    client = _client(db_engine, user)
    resp = client.get(f"/personnel/sites/{other.id}/workers")
    assert resp.status_code == 403


def test_add_and_list_workers(db_engine, db_session) -> None:
    org, _, site, user, _ = _make_user(
        db_session, perms=["personnel.view", "personnel.manage"]
    )
    emp = Employee(organization_id=org.id, full_name="Магомедов А.")
    db_session.add(emp)
    db_session.commit()
    client = _client(db_engine, user)
    r = client.post(
        f"/personnel/sites/{site.id}/workers",
        json={"employee_id": str(emp.id), "brigade": "Бригада №1", "profession": "Монтажник"},
    )
    assert r.status_code == 201
    lst = client.get(f"/personnel/sites/{site.id}/workers")
    assert lst.status_code == 200
    assert any(w["full_name"] == "Магомедов А." for w in lst.json())


def test_shift_blocked_without_clearance(db_engine, db_session) -> None:
    org, _, site, user, _ = _make_user(
        db_session, perms=["personnel.view", "personnel.manage"]
    )
    emp = Employee(organization_id=org.id, full_name="Без допуска")
    db_session.add(emp)
    db_session.commit()
    client = _client(db_engine, user)
    r = client.post(
        f"/personnel/sites/{site.id}/shifts",
        json={
            "employee_id": str(emp.id),
            "work_date": "2026-07-18",
            "hours_worked": 8,
        },
    )
    assert r.status_code == 409  # гейт охраны труда


def test_shift_allowed_with_clearance(db_engine, db_session) -> None:
    org, _, site, user, _ = _make_user(
        db_session, perms=["personnel.view", "personnel.manage"]
    )
    emp = Employee(organization_id=org.id, full_name="С допуском")
    db_session.add(emp)
    db_session.flush()
    db_session.add(
        SafetyClearance(
            organization_id=org.id,
            employee_id=emp.id,
            site_id=site.id,
            intro_briefing_at=date(2025, 1, 1),
            primary_briefing_at=date(2026, 6, 1),
            signed_by_worker=True,
            medical_valid_until=date(2026, 12, 31),
            status="cleared",
        )
    )
    db_session.commit()
    client = _client(db_engine, user)
    r = client.post(
        f"/personnel/sites/{site.id}/shifts",
        json={
            "employee_id": str(emp.id),
            "work_date": "2026-07-18",
            "hours_worked": 8,
        },
    )
    assert r.status_code == 201


def _make_draft(db, org, site, *, to_pay_rate="2000") -> PayrollDraft:
    draft = PayrollDraft(
        organization_id=org.id,
        site_id=site.id,
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 31),
    )
    db.add(draft)
    db.flush()
    db.add(
        PayrollLine(
            payroll_draft_id=draft.id,
            employee_id=uuid.uuid4(),
            scheme="hourly",
            rate=Decimal(to_pay_rate),
            quantity=Decimal("100"),
        )
    )
    db.commit()
    return draft


def test_payout_r3_flow_with_audit(db_engine, db_session) -> None:
    org, _, site, user, _ = _make_user(
        db_session, perms=["payroll.view", "payroll.manage", "payroll.approve"]
    )
    draft = _make_draft(db_session, org, site, to_pay_rate="2000")  # 200 000 → R3
    client = _client(db_engine, user)

    req = client.post(f"/personnel/payroll/{draft.id}/request-payout")
    assert req.status_code == 200
    body = req.json()
    assert body["risk_level"] == "R3"
    assert body["status"] == "pending_approval"

    dec = client.post(
        f"/personnel/payroll/{draft.id}/decision",
        json={"decision": "approved", "comment": "проверено"},
    )
    assert dec.status_code == 200
    assert dec.json()["status"] == "approved"

    events = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.action == "payroll.payout.approved")
        .all()
    )
    assert len(events) == 1
    assert events[0].risk_level == "R3"


def test_payout_r4_requires_mfa(db_engine, db_session) -> None:
    org, _, site, user, secret = _make_user(
        db_session,
        perms=["payroll.view", "payroll.manage", "payroll.approve"],
        mfa=True,
    )
    # ставка 20000 × 100 = 2 000 000 → R4
    draft = _make_draft(db_session, org, site, to_pay_rate="20000")
    client = _client(db_engine, user)

    req = client.post(f"/personnel/payroll/{draft.id}/request-payout")
    assert req.json()["risk_level"] == "R4"

    # без кода MFA подтверждение R4 запрещено
    denied = client.post(
        f"/personnel/payroll/{draft.id}/decision",
        json={"decision": "approved"},
    )
    assert denied.status_code == 401

    # с корректным кодом MFA — выплата согласована
    code = pyotp.TOTP(secret).now()
    ok = client.post(
        f"/personnel/payroll/{draft.id}/decision",
        json={"decision": "approved", "mfa_code": code},
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "approved"


def test_director_summary(db_engine, db_session) -> None:
    _, _, site, user, _ = _make_user(db_session, perms=["personnel.view"])
    client = _client(db_engine, user)
    resp = client.get("/personnel/director/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "sites" in data
    assert any(s["site_id"] == str(site.id) for s in data["sites"])
