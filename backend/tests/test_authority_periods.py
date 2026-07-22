"""Тесты периодов полномочий и немедленного отзыва доступа (этап 1).

Проверяют, что права зависят от периода действия назначения роли (просроченные и
будущие назначения прав не дают), что смена должности сохраняет историю и
переключает права, и что при отзыве доступа учётная запись не может войти.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.core.security import hash_password
from app.models import (
    AuditEvent,
    Employee,
    Organization,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)
from app.services.access import get_permission_codes, get_role_codes, has_permission
from app.services.identity import (
    assign_role,
    change_role,
    end_role,
    revoke_user_access,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _seed_roles(session):
    """Две роли с разными правами для проверки переключения."""
    org = Organization(legal_name="ТЕСТ")
    session.add(org)
    perm_a = Permission(code="alpha.act")
    perm_b = Permission(code="beta.act")
    role_a = Role(code="role_a", name="A")
    role_b = Role(code="role_b", name="B")
    session.add_all([perm_a, perm_b, role_a, role_b])
    session.flush()
    session.add(RolePermission(role_id=role_a.id, permission_id=perm_a.id))
    session.add(RolePermission(role_id=role_b.id, permission_id=perm_b.id))
    session.commit()
    return org, role_a, role_b


def _make_user(session, org, *, email="p@example.com", with_position=None):
    emp = Employee(
        organization_id=org.id, full_name="Сотрудник", position_id=with_position
    )
    session.add(emp)
    session.flush()
    user = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password("Secret123!"),
        status="active",
        employee_id=emp.id,
    )
    session.add(user)
    session.commit()
    return user, emp


# ---------------------------------------------------------------------------
# Период полномочий в разрешении прав
# ---------------------------------------------------------------------------

def test_active_assignment_grants_permissions(db_session) -> None:
    org, role_a, _ = _seed_roles(db_session)
    user, _ = _make_user(db_session, org)
    assign_role(db_session, user.id, "role_a")
    assert "role_a" in get_role_codes(db_session, user.id)
    assert "alpha.act" in get_permission_codes(db_session, user.id)
    assert has_permission(db_session, user.id, "alpha.act") is True


def test_expired_assignment_grants_nothing(db_session) -> None:
    org, role_a, _ = _seed_roles(db_session)
    user, _ = _make_user(db_session, org)
    # назначение уже истекло
    db_session.add(
        UserRole(
            user_id=user.id,
            role_id=role_a.id,
            valid_from=_now() - timedelta(days=10),
            valid_until=_now() - timedelta(days=1),
        )
    )
    db_session.commit()
    assert get_role_codes(db_session, user.id) == set()
    assert get_permission_codes(db_session, user.id) == set()
    assert has_permission(db_session, user.id, "alpha.act") is False


def test_future_assignment_grants_nothing_yet(db_session) -> None:
    org, role_a, _ = _seed_roles(db_session)
    user, _ = _make_user(db_session, org)
    db_session.add(
        UserRole(
            user_id=user.id,
            role_id=role_a.id,
            valid_from=_now() + timedelta(days=1),
        )
    )
    db_session.commit()
    assert get_permission_codes(db_session, user.id) == set()


def test_null_bounds_are_always_active(db_session) -> None:
    org, role_a, _ = _seed_roles(db_session)
    user, _ = _make_user(db_session, org)
    db_session.add(
        UserRole(user_id=user.id, role_id=role_a.id, valid_from=None, valid_until=None)
    )
    db_session.commit()
    assert "alpha.act" in get_permission_codes(db_session, user.id)


def test_end_role_revokes_permission(db_session) -> None:
    org, role_a, _ = _seed_roles(db_session)
    user, _ = _make_user(db_session, org)
    assign_role(db_session, user.id, "role_a")
    assert has_permission(db_session, user.id, "alpha.act") is True
    end_role(db_session, user.id, "role_a")
    assert has_permission(db_session, user.id, "alpha.act") is False


def test_reassign_reopens_ended_role(db_session) -> None:
    org, role_a, _ = _seed_roles(db_session)
    user, _ = _make_user(db_session, org)
    assign_role(db_session, user.id, "role_a")
    end_role(db_session, user.id, "role_a")
    assert has_permission(db_session, user.id, "alpha.act") is False
    # повторное назначение переоткрывает существующую запись (уникальность user+role)
    assign_role(db_session, user.id, "role_a")
    assert has_permission(db_session, user.id, "alpha.act") is True
    assert db_session.query(UserRole).filter_by(user_id=user.id).count() == 1


# ---------------------------------------------------------------------------
# Смена должности сохраняет историю и переключает права
# ---------------------------------------------------------------------------

def test_change_role_switches_permissions_and_updates_position(db_session) -> None:
    org, role_a, role_b = _seed_roles(db_session)
    user, emp = _make_user(db_session, org)
    assign_role(db_session, user.id, "role_a")
    new_position = uuid.uuid4()

    change_role(db_session, user.id, "role_b", new_position_id=new_position)

    perms = get_permission_codes(db_session, user.id)
    assert "beta.act" in perms
    assert "alpha.act" not in perms  # прежняя роль закрыта
    db_session.refresh(emp)
    assert emp.position_id == new_position
    # история сохранена: обе записи ролей существуют (старая закрыта датой)
    assert db_session.query(UserRole).filter_by(user_id=user.id).count() == 2
    old = (
        db_session.query(UserRole)
        .filter_by(user_id=user.id, role_id=role_a.id)
        .one()
    )
    assert old.valid_until is not None  # старое назначение закрыто, но не удалено


def test_change_role_records_audit(db_session) -> None:
    org, role_a, role_b = _seed_roles(db_session)
    user, _ = _make_user(db_session, org)
    assign_role(db_session, user.id, "role_a")
    change_role(db_session, user.id, "role_b", reason="перевод")
    event = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.action == "identity.role.change")
        .first()
    )
    assert event is not None
    assert event.new_values_json["role"] == "role_b"


# ---------------------------------------------------------------------------
# Немедленный отзыв доступа (увольнение/отстранение)
# ---------------------------------------------------------------------------

def test_revoke_blocks_login_and_permissions(client, db_session) -> None:
    org, role_a, _ = _seed_roles(db_session)
    user, _ = _make_user(db_session, org, email="revoke@example.com")
    assign_role(db_session, user.id, "role_a")

    # до отзыва — вход успешен
    ok = client.post(
        "/auth/login", json={"email": user.email, "password": "Secret123!"}
    )
    assert ok.status_code == 200

    revoke_user_access(db_session, user.id, reason="увольнение")

    # статус переведён в revoked, роли закрыты, прав нет
    db_session.refresh(user)
    assert user.status == "revoked"
    assert get_permission_codes(db_session, user.id) == set()

    # вход после отзыва невозможен
    denied = client.post(
        "/auth/login", json={"email": user.email, "password": "Secret123!"}
    )
    assert denied.status_code == 401


def test_revoke_records_audit(db_session) -> None:
    org, _, _ = _seed_roles(db_session)
    user, _ = _make_user(db_session, org, email="rv2@example.com")
    revoke_user_access(db_session, user.id, reason="отстранение")
    event = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.action == "identity.access.revoke")
        .first()
    )
    assert event is not None
    assert event.new_values_json == {"status": "revoked"}


# ---------------------------------------------------------------------------
# Роль полного доступа тоже подчиняется периоду
# ---------------------------------------------------------------------------

def test_super_role_respects_period(db_session) -> None:
    org = Organization(legal_name="ТЕСТ")
    db_session.add(org)
    owner_role = Role(code="system_owner", name="Владелец", is_system=True)
    db_session.add(owner_role)
    db_session.commit()
    user, _ = _make_user(db_session, org, email="owner2@example.com")

    # активное назначение super-роли — полный доступ
    assign_role(db_session, user.id, "system_owner")
    assert has_permission(db_session, user.id, "anything.at.all") is True

    # по истечении периода super-доступ прекращается
    end_role(db_session, user.id, "system_owner")
    assert has_permission(db_session, user.id, "anything.at.all") is False
