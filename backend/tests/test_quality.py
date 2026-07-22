"""Тесты строительного контроля и качества (этап F, PR-F).

Проверяют: контрольная карта; фиксация проверки (pass/fail) с требованием
измерения; повторная проверка после устранения; итоговое решение выносит только
уполномоченный специалист (SoD: проверяющий не утверждает собственную проверку);
ИИ-подсказка не является решением; RBAC/ABAC и изоляция по организации.
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
    Organization,
    Permission,
    Project,
    ProjectMember,
    Role,
    RolePermission,
    User,
    UserRole,
)
from app.services import quality as svc


def _org(db):
    org = Organization(legal_name="ТЕСТ")
    db.add(org)
    db.flush()
    return org


def _user(db, org, *, perms=(), roles=(), project=None, member=True, email=None):
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
    for rc in roles:
        r = db.query(Role).filter(Role.code == rc).first()
        if r is None:
            r = Role(code=rc, name=rc)
            db.add(r)
            db.flush()
        db.add(UserRole(user_id=user.id, role_id=r.id))
    if project is not None and member:
        db.add(ProjectMember(project_id=project.id, employee_id=emp.id,
                             project_role="member"))
    db.commit()
    return user


def _card(db, org, **kw):
    return svc.create_card(
        db, org.id, work_type=kw.get("work_type", "welding"),
        name=kw.get("name", "Сварка труб"),
        controlled_parameter=kw.get("param", "Качество шва"),
        control_kind=kw.get("control_kind", "operational"),
        requires_measurement=kw.get("requires_measurement", False),
    )


# ---------------------------------------------------------------------------
# Карты и проверки
# ---------------------------------------------------------------------------

def test_create_card_and_record_pass(db_session) -> None:
    org = _org(db_session)
    card = _card(db_session, org)
    check = svc.record_check(db_session, card, result="pass", checked_by=uuid.uuid4())
    assert check.result == "pass" and check.recheck_required is False


def test_measurement_required(db_session) -> None:
    org = _org(db_session)
    card = _card(db_session, org, requires_measurement=True)
    with pytest.raises(svc.QualityError, match="измерени"):
        svc.record_check(db_session, card, result="pass", checked_by=uuid.uuid4())
    check = svc.record_check(db_session, card, result="pass", checked_by=uuid.uuid4(),
                             measured_value="12 мм")
    assert check.measured_value == "12 мм"


def test_fail_sets_recheck_and_recheck_flow(db_session) -> None:
    org = _org(db_session)
    card = _card(db_session, org)
    inspector = uuid.uuid4()
    fail = svc.record_check(db_session, card, result="fail", checked_by=inspector,
                            remark="дефект шва")
    assert fail.recheck_required is True
    # повторная проверка после устранения
    passed = svc.create_recheck(db_session, fail, result="pass", checked_by=inspector)
    assert passed.recheck_of_check_id == fail.id and passed.result == "pass"


# ---------------------------------------------------------------------------
# Итоговое решение — уполномоченный специалист + SoD
# ---------------------------------------------------------------------------

def test_finalize_requires_authorized_specialist(db_session) -> None:
    org = _org(db_session)
    card = _card(db_session, org)
    check = svc.record_check(db_session, card, result="pass", checked_by=uuid.uuid4())
    ordinary = _user(db_session, org, roles=("foreman",))
    with pytest.raises(svc.QualityError, match="специалист"):
        svc.finalize_check(db_session, check, decider_user_id=ordinary.id,
                           decision="accepted")


def test_finalize_by_control_engineer(db_session) -> None:
    org = _org(db_session)
    card = _card(db_session, org)
    check = svc.record_check(db_session, card, result="pass", checked_by=uuid.uuid4())
    controller = _user(db_session, org, roles=("construction_control_engineer",))
    svc.finalize_check(db_session, check, decider_user_id=controller.id,
                       decision="accepted", comment="соответствует")
    assert check.final_decision == "accepted"
    assert check.final_decision_by == controller.id


def test_inspector_cannot_selfaccept_sod(db_session) -> None:
    org = _org(db_session)
    card = _card(db_session, org)
    # проверяющий сам является уполномоченным специалистом, но проверял сам
    controller = _user(db_session, org, roles=("construction_control_engineer",))
    check = svc.record_check(db_session, card, result="pass", checked_by=controller.id)
    with pytest.raises(svc.QualityError, match="SoD"):
        svc.finalize_check(db_session, check, decider_user_id=controller.id,
                           decision="accepted")


def test_double_finalize_rejected(db_session) -> None:
    org = _org(db_session)
    card = _card(db_session, org)
    check = svc.record_check(db_session, card, result="pass", checked_by=uuid.uuid4())
    controller = _user(db_session, org, roles=("chief_engineer",))
    svc.finalize_check(db_session, check, decider_user_id=controller.id,
                       decision="accepted")
    with pytest.raises(svc.QualityError, match="уже вынесено"):
        svc.finalize_check(db_session, check, decider_user_id=controller.id,
                           decision="rejected")


def test_ai_suggestion_is_not_decision(db_session) -> None:
    org = _org(db_session)
    card = _card(db_session, org)
    check = svc.record_check(db_session, card, result="conditional",
                             checked_by=uuid.uuid4(),
                             ai_suggestion="возможное отклонение геометрии")
    # ИИ-подсказка есть, но итогового решения нет — его выносит человек
    assert check.ai_suggestion and check.final_decision is None


# ---------------------------------------------------------------------------
# API: RBAC / ABAC / изоляция
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


def test_api_create_card_requires_manage(db_engine, db_session) -> None:
    org = _org(db_session)
    db_session.commit()
    user = _user(db_session, org, perms=["audit.finding.view"])
    client = _client(db_engine, user)
    resp = client.post("/quality/cards", json={
        "work_type": "welding", "name": "Сварка", "controlled_parameter": "шов"})
    assert resp.status_code == 403


def test_api_list_requires_view(db_engine, db_session) -> None:
    org = _org(db_session)
    db_session.commit()
    user = _user(db_session, org, perms=[])
    client = _client(db_engine, user)
    assert client.get("/quality/cards").status_code == 403


def test_api_cards_isolated_by_org(db_engine, db_session) -> None:
    org_a = _org(db_session)
    org_b = _org(db_session)
    db_session.commit()
    user_a = _user(db_session, org_a,
                   perms=["audit.finding.view", "audit.finding.manage"], email="a@ex.com")
    client_a = _client(db_engine, user_a)
    client_a.post("/quality/cards", json={
        "work_type": "welding", "name": "Сварка", "controlled_parameter": "шов"})
    app.dependency_overrides.clear()
    user_b = _user(db_session, org_b,
                   perms=["audit.finding.view", "audit.finding.manage"], email="b@ex.com")
    client_b = _client(db_engine, user_b)
    assert client_b.get("/quality/cards").json() == []
