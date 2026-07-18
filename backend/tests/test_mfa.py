"""Тесты обязательности MFA по ролям (T-1.C2)."""

import uuid

import pyotp

from app.core.security import hash_password
from app.models import Role, User, UserRole


def _make_user(session, *, mfa_enabled=False, secret=None, email="d@example.com"):
    user = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password("Secret123!"),
        status="active",
        mfa_enabled=mfa_enabled,
        mfa_secret=secret,
    )
    session.add(user)
    session.commit()
    return user


def _grant_role(session, user, code):
    role = Role(code=code, name=code)
    session.add(role)
    session.flush()
    session.add(UserRole(user_id=user.id, role_id=role.id))
    session.commit()


def test_critical_role_without_mfa_denied(client, db_session) -> None:
    user = _make_user(db_session)
    _grant_role(db_session, user, "general_director")
    resp = client.post(
        "/auth/login", json={"email": user.email, "password": "Secret123!"}
    )
    assert resp.status_code == 401
    assert "многофактор" in resp.json()["detail"].lower()


def test_critical_role_with_mfa_code(client, db_session) -> None:
    secret = pyotp.random_base32()
    user = _make_user(db_session, mfa_enabled=True, secret=secret)
    _grant_role(db_session, user, "general_director")
    # без кода — отказ
    r1 = client.post(
        "/auth/login", json={"email": user.email, "password": "Secret123!"}
    )
    assert r1.status_code == 401
    # с корректным кодом — успех
    code = pyotp.TOTP(secret).now()
    r2 = client.post(
        "/auth/login",
        json={"email": user.email, "password": "Secret123!", "mfa_code": code},
    )
    assert r2.status_code == 200
    assert "access_token" in r2.json()


def test_non_critical_role_no_mfa(client, db_session) -> None:
    user = _make_user(db_session, email="foreman2@example.com")
    _grant_role(db_session, user, "foreman")
    resp = client.post(
        "/auth/login", json={"email": user.email, "password": "Secret123!"}
    )
    assert resp.status_code == 200
