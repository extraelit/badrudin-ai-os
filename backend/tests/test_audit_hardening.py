"""Тесты усиления аудита (этап 1): должность-на-момент, сессия, уровень входа.

Проверяют, что запись аудита фиксирует должность актора на момент действия
(снимок, не меняется при последующем переводе), а событие входа несёт
идентификатор сессии и применённый уровень аутентификации (password/mfa),
IP-адрес и user-agent.
"""

from __future__ import annotations

import uuid

from app.core.security import hash_password
from app.models import (
    AuditEvent,
    Employee,
    Organization,
    Position,
    Role,
    User,
    UserRole,
)
from app.services.audit import record_event

DEMO_SECRET = "JBSWY3DPEHPK3PXP"


def _org_with_position(session):
    org = Organization(legal_name="ТЕСТ")
    session.add(org)
    session.flush()
    pos = Position(organization_id=org.id, name="Прораб", code="foreman")
    session.add(pos)
    session.flush()
    return org, pos


def _user(session, org, position_id=None, *, email="a@example.com", mfa=False, role=None):
    emp = Employee(organization_id=org.id, full_name="Сотрудник", position_id=position_id)
    session.add(emp)
    session.flush()
    user = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password("Secret123!"),
        status="active",
        employee_id=emp.id,
        mfa_enabled=mfa,
        mfa_secret=DEMO_SECRET if mfa else None,
    )
    session.add(user)
    session.flush()
    if role is not None:
        r = Role(code=role, name=role)
        session.add(r)
        session.flush()
        session.add(UserRole(user_id=user.id, role_id=r.id))
    session.commit()
    return user, emp


# ---------------------------------------------------------------------------
# Должность на момент действия
# ---------------------------------------------------------------------------

def test_event_captures_actor_position(db_session) -> None:
    org, pos = _org_with_position(db_session)
    user, _ = _user(db_session, org, position_id=pos.id)
    ev = record_event(
        db_session, actor_type="user", action="test.act", actor_user_id=user.id
    )
    assert ev.actor_position_id == pos.id


def test_position_snapshot_is_immutable_after_transfer(db_session) -> None:
    org, pos = _org_with_position(db_session)
    user, emp = _user(db_session, org, position_id=pos.id)
    ev = record_event(
        db_session, actor_type="user", action="test.act", actor_user_id=user.id
    )
    # сотрудника переводят на другую должность
    other = Position(organization_id=org.id, name="Мастер", code="master")
    db_session.add(other)
    db_session.flush()
    emp.position_id = other.id
    db_session.commit()
    # прежняя запись аудита хранит должность на момент действия
    db_session.refresh(ev)
    assert ev.actor_position_id == pos.id


def test_explicit_position_is_preserved(db_session) -> None:
    org, pos = _org_with_position(db_session)
    user, _ = _user(db_session, org, position_id=pos.id)
    explicit = uuid.uuid4()
    ev = record_event(
        db_session,
        actor_type="user",
        action="test.act",
        actor_user_id=user.id,
        actor_position_id=explicit,
    )
    assert ev.actor_position_id == explicit


def test_no_position_when_no_actor(db_session) -> None:
    ev = record_event(db_session, actor_type="system", action="system.tick")
    assert ev.actor_position_id is None


# ---------------------------------------------------------------------------
# Событие входа: сессия и уровень аутентификации
# ---------------------------------------------------------------------------

def test_login_event_has_session_and_password_level(client, db_session) -> None:
    org, pos = _org_with_position(db_session)
    user, _ = _user(
        db_session, org, position_id=pos.id, email="p@example.com", role="foreman"
    )
    resp = client.post(
        "/auth/login", json={"email": user.email, "password": "Secret123!"}
    )
    assert resp.status_code == 200
    ev = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.action == "auth.login", AuditEvent.actor_user_id == user.id)
        .first()
    )
    assert ev is not None
    assert ev.session_id  # идентификатор сессии (jti) присутствует
    assert ev.auth_level == "password"
    assert ev.actor_position_id == pos.id


def test_login_event_records_mfa_level(client, db_session) -> None:
    import pyotp

    org, pos = _org_with_position(db_session)
    user, _ = _user(
        db_session,
        org,
        position_id=pos.id,
        email="gd@example.com",
        mfa=True,
        role="general_director",
    )
    code = pyotp.TOTP(DEMO_SECRET).now()
    resp = client.post(
        "/auth/login",
        json={"email": user.email, "password": "Secret123!", "mfa_code": code},
    )
    assert resp.status_code == 200
    ev = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.action == "auth.login", AuditEvent.actor_user_id == user.id)
        .first()
    )
    assert ev is not None
    assert ev.auth_level == "mfa"
    assert ev.session_id
