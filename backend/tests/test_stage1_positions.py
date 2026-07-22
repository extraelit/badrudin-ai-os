"""Этап 1 «Фундамент доступа и целостности»: персональные аккаунты по должностям.

Проверяет, что демо-фикстура создаёт:
- организационную структуру (подразделения) и профиль должности (позиция +
  уровень согласования);
- персональные учётные записи по должностям (без общих логинов, 1 пользователь —
  1 сотрудник — 1 роль);
- корректное разграничение прав (RBAC) и разделение полномочий (SoD): инициатор
  не совпадает с утверждающим по чувствительным действиям.

Права проверяются на серверной модели доступа (app.services.access), логин — через
реальный HTTP-эндпоинт /auth/login (сквозная проверка персонального входа).
"""

from __future__ import annotations

import pytest

import pyotp

from app.db.seed import (
    DEFAULT_DEMO_PASSWORD,
    DEMO_OWNER_TOTP_SECRET,
    load_fixtures,
)
from app.models import Employee, Position, User
from app.services.access import (
    get_permission_codes,
    get_role_codes,
    has_permission,
)


@pytest.fixture
def seeded(db_session):
    """Загружает демо-фикстуру в общий движок (виден и клиенту, и сессии)."""
    counts = load_fixtures(db_session)
    return counts


# ---------------------------------------------------------------------------
# Организационная структура и профиль должности
# ---------------------------------------------------------------------------

def test_departments_and_positions_seeded(seeded) -> None:
    assert seeded["departments"] >= 10
    assert seeded["positions"] >= 15


def test_each_position_account_has_full_profile(seeded, db_session) -> None:
    """У каждого сотрудника с должностью заполнены подразделение и позиция."""
    positions = {p.id for p in db_session.query(Position).all()}
    with_position = (
        db_session.query(Employee).filter(Employee.position_id.isnot(None)).all()
    )
    assert len(with_position) >= 15
    for emp in with_position:
        assert emp.position_id in positions
        assert emp.department_id is not None, f"{emp.full_name}: нет подразделения"
        assert emp.personnel_number, f"{emp.full_name}: нет табельного номера"


def test_positions_have_approval_levels(seeded, db_session) -> None:
    """Уровень согласования директоров выше, чем у рабочих (иерархия одобрения)."""
    by_code = {p.code: p for p in db_session.query(Position).all()}
    assert by_code["general_director"].approval_level > by_code["foreman"].approval_level
    assert by_code["executive_director"].approval_level > by_code["master"].approval_level
    assert by_code["executor"].approval_level == 0


# ---------------------------------------------------------------------------
# Персональные учётные записи (без общих логинов)
# ---------------------------------------------------------------------------

def test_personal_accounts_one_to_one(seeded, db_session) -> None:
    """Каждый пользователь привязан к отдельному сотруднику и ровно одной роли."""
    users = db_session.query(User).all()
    employee_ids = [u.employee_id for u in users]
    # общих логинов нет: у каждого свой сотрудник, дублей employee_id нет
    assert all(eid is not None for eid in employee_ids)
    assert len(employee_ids) == len(set(employee_ids))
    # ровно одна роль на пользователя
    for u in users:
        assert len(get_role_codes(db_session, u.id)) == 1


@pytest.mark.parametrize(
    "email,role,must_have",
    [
        ("foreman@extra-elit.demo", "foreman", "task.execute"),
        ("storekeeper@extra-elit.demo", "storekeeper", "warehouse.manage"),
        ("sitemanager@extra-elit.demo", "site_manager", "task.assign"),
        ("control@extra-elit.demo", "construction_control_engineer", "daily_report.approve"),
        ("contractor@extra-elit.demo", "external_contractor", "task.execute"),
    ],
)
def test_per_position_login_and_permissions(
    seeded, client, email, role, must_have
) -> None:
    """Сквозной персональный вход по должности + права из /auth/me (роли без MFA)."""
    resp = client.post(
        "/auth/login", json={"email": email, "password": DEFAULT_DEMO_PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == email
    assert role in body["roles"]
    assert must_have in body["permissions"]


def test_critical_role_login_requires_mfa(seeded, client) -> None:
    """Критическая роль (генеральный директор) не входит без кода MFA, но входит
    с корректным TOTP (ACCESS_CONTROL.md раздел 19)."""
    email = "gendirector@extra-elit.demo"
    # без кода — вход запрещён
    no_code = client.post(
        "/auth/login", json={"email": email, "password": DEFAULT_DEMO_PASSWORD}
    )
    assert no_code.status_code == 401
    # с корректным TOTP — вход разрешён
    code = pyotp.TOTP(DEMO_OWNER_TOTP_SECRET).now()
    ok = client.post(
        "/auth/login",
        json={"email": email, "password": DEFAULT_DEMO_PASSWORD, "mfa_code": code},
    )
    assert ok.status_code == 200, ok.text
    token = ok.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    body = me.json()
    assert "general_director" in body["roles"]
    assert "budget.approve" in body["permissions"]


# ---------------------------------------------------------------------------
# Разделение полномочий (SoD): инициатор ≠ утверждающий
# ---------------------------------------------------------------------------

def _perms(db_session, email: str) -> set[str]:
    user = db_session.query(User).filter(User.email == email).first()
    assert user is not None, f"нет пользователя {email}"
    return get_permission_codes(db_session, user.id)


@pytest.mark.parametrize(
    "email",
    [
        "foreman@extra-elit.demo",
        "master@extra-elit.demo",
        "executor@extra-elit.demo",
        "contractor@extra-elit.demo",
    ],
)
def test_executors_cannot_approve_tasks(seeded, db_session, email) -> None:
    """Исполнители выполняют задачи, но не утверждают их (SoD)."""
    perms = _perms(db_session, email)
    assert "task.execute" in perms
    assert "task.approve" not in perms
    assert "approval.decide" not in perms


def test_accountant_prepares_but_does_not_approve_payments(seeded, db_session) -> None:
    """Бухгалтер готовит платёж/счёт, но не утверждает выплату (SoD)."""
    perms = _perms(db_session, "accountant@extra-elit.demo")
    assert "invoice.manage" in perms
    assert "payment.request" in perms
    assert "payment.approve" not in perms
    assert "budget.approve" not in perms


def test_supply_manages_but_does_not_approve_procurement(seeded, db_session) -> None:
    """Снабжение ведёт закупки, но их согласует руководитель (SoD)."""
    perms = _perms(db_session, "supply@extra-elit.demo")
    assert "procurement.manage" in perms
    assert "procurement.approve" not in perms


def test_only_directors_can_approve_payments(seeded, db_session) -> None:
    """payment.approve — только у генерального и исполнительного директоров."""
    users = db_session.query(User).all()
    approvers = {
        u.email
        for u in users
        if "payment.approve" in get_permission_codes(db_session, u.id)
    }
    assert approvers == {
        "gendirector@extra-elit.demo",
        "execdirector@extra-elit.demo",
    }


def test_control_engineer_is_independent_of_production(seeded, db_session) -> None:
    """Строительный контроль принимает отчёты и фиксирует замечания, но не управляет
    производством (проверяющий отделён от исполняющего)."""
    perms = _perms(db_session, "control@extra-elit.demo")
    assert "daily_report.approve" in perms
    assert "audit.finding.manage" in perms
    assert "project.manage" not in perms
    assert "task.assign" not in perms


# ---------------------------------------------------------------------------
# Целостность модели прав
# ---------------------------------------------------------------------------

def test_system_owner_has_effective_full_access(seeded, db_session) -> None:
    """Владелец системы (SUPER_ROLE) проходит любую проверку разрешения."""
    owner = db_session.query(User).filter(
        User.email == "owner@extra-elit.demo"
    ).first()
    assert has_permission(db_session, owner.id, "budget.approve") is True
    assert has_permission(db_session, owner.id, "any.unknown.code") is True


def test_all_role_permissions_reference_known_codes(seeded, db_session) -> None:
    """Каждая назначенная роли привилегия существует в справочнике прав."""
    from app.models import Permission

    known = {p.code for p in db_session.query(Permission).all()}
    users = db_session.query(User).all()
    for u in users:
        for code in get_permission_codes(db_session, u.id):
            assert code in known
