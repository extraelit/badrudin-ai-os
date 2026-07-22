"""Тесты резервных кодов восстановления MFA (этап 1).

Проверяют жизненный цикл кодов на уровне сервиса (генерация, одноразовость,
перевыпуск, счётчик) и сквозные сценарии через HTTP: вход по коду восстановления
при недоступном TOTP, step-up при генерации, отсутствие кодов в журнале аудита.
"""

from __future__ import annotations

import uuid

import pyotp

from app.core.security import hash_password
from app.models import AuditEvent, Role, User, UserRole
from app.services.mfa_recovery import (
    generate_recovery_codes,
    remaining_count,
    verify_and_consume,
)

DEMO_SECRET = "JBSWY3DPEHPK3PXP"


def _make_user(session, *, mfa_enabled=False, secret=None, email="rc@example.com"):
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


# ---------------------------------------------------------------------------
# Уровень сервиса
# ---------------------------------------------------------------------------

def test_generate_returns_codes_and_counts(db_session) -> None:
    user = _make_user(db_session)
    codes = generate_recovery_codes(db_session, user.id, count=8)
    assert len(codes) == 8
    assert len(set(codes)) == 8  # коды уникальны
    assert remaining_count(db_session, user.id) == 8


def test_code_is_single_use(db_session) -> None:
    user = _make_user(db_session)
    codes = generate_recovery_codes(db_session, user.id, count=5)
    one = codes[0]
    assert verify_and_consume(db_session, user.id, one) is True
    assert remaining_count(db_session, user.id) == 4
    # повторно тот же код не принимается
    assert verify_and_consume(db_session, user.id, one) is False
    assert remaining_count(db_session, user.id) == 4


def test_code_accepted_regardless_of_formatting(db_session) -> None:
    user = _make_user(db_session)
    codes = generate_recovery_codes(db_session, user.id, count=3)
    messy = f"  {codes[0].lower().replace('-', ' ')}  "
    assert verify_and_consume(db_session, user.id, messy) is True


def test_wrong_and_empty_codes_rejected(db_session) -> None:
    user = _make_user(db_session)
    generate_recovery_codes(db_session, user.id, count=3)
    assert verify_and_consume(db_session, user.id, "ZZZZ-ZZZZ") is False
    assert verify_and_consume(db_session, user.id, "") is False
    assert remaining_count(db_session, user.id) == 3


def test_regenerate_invalidates_previous_set(db_session) -> None:
    user = _make_user(db_session)
    old = generate_recovery_codes(db_session, user.id, count=5)
    new = generate_recovery_codes(db_session, user.id, count=5)
    # старые коды больше не действуют
    assert verify_and_consume(db_session, user.id, old[0]) is False
    # новые — действуют
    assert verify_and_consume(db_session, user.id, new[0]) is True
    assert remaining_count(db_session, user.id) == 4


def test_codes_isolated_per_user(db_session) -> None:
    u1 = _make_user(db_session, email="a@example.com")
    u2 = _make_user(db_session, email="b@example.com")
    codes1 = generate_recovery_codes(db_session, u1.id, count=3)
    # код одного пользователя не подходит другому
    assert verify_and_consume(db_session, u2.id, codes1[0]) is False


# ---------------------------------------------------------------------------
# Сквозные сценарии (HTTP)
# ---------------------------------------------------------------------------

def test_login_with_recovery_code_when_totp_unavailable(client, db_session) -> None:
    """Критическая роль входит по коду восстановления, если нет доступа к TOTP."""
    user = _make_user(db_session, mfa_enabled=True, secret=DEMO_SECRET)
    _grant_role(db_session, user, "general_director")
    codes = generate_recovery_codes(db_session, user.id, count=6)

    # вход по коду восстановления (в поле mfa_code)
    ok = client.post(
        "/auth/login",
        json={"email": user.email, "password": "Secret123!", "mfa_code": codes[0]},
    )
    assert ok.status_code == 200, ok.text
    assert "access_token" in ok.json()
    # код погашен — повторный вход тем же кодом отклонён
    again = client.post(
        "/auth/login",
        json={"email": user.email, "password": "Secret123!", "mfa_code": codes[0]},
    )
    assert again.status_code == 401
    assert remaining_count(db_session, user.id) == 5


def test_generate_endpoint_requires_valid_totp_stepup(client, db_session) -> None:
    """Эндпоинт генерации требует step-up действующим TOTP и не выдаёт коды без него."""
    user = _make_user(db_session, mfa_enabled=True, secret=DEMO_SECRET)
    _grant_role(db_session, user, "general_director")
    code = pyotp.TOTP(DEMO_SECRET).now()
    token = client.post(
        "/auth/login",
        json={"email": user.email, "password": "Secret123!", "mfa_code": code},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # неверный TOTP → отказ
    bad = client.post(
        "/auth/mfa/recovery-codes", json={"code": "000000"}, headers=headers
    )
    assert bad.status_code == 401

    # верный TOTP → выдан комплект кодов
    good_code = pyotp.TOTP(DEMO_SECRET).now()
    good = client.post(
        "/auth/mfa/recovery-codes", json={"code": good_code}, headers=headers
    )
    assert good.status_code == 200, good.text
    body = good.json()
    assert body["count"] == len(body["codes"]) == 10

    # статус показывает остаток, но не сами коды
    status_resp = client.get("/auth/mfa/recovery-codes", headers=headers)
    assert status_resp.status_code == 200
    assert status_resp.json() == {"mfa_enabled": True, "remaining": 10}


def test_generate_denied_without_mfa(client, db_session) -> None:
    """Без настроенной MFA генерация резервных кодов недоступна."""
    user = _make_user(db_session, email="nomfa@example.com")
    _grant_role(db_session, user, "foreman")
    token = client.post(
        "/auth/login", json={"email": user.email, "password": "Secret123!"}
    ).json()["access_token"]
    resp = client.post(
        "/auth/mfa/recovery-codes",
        json={"code": "123456"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_audit_records_generation_without_codes(client, db_session) -> None:
    """Аудит фиксирует перевыпуск и число кодов, но не сами коды."""
    user = _make_user(db_session, mfa_enabled=True, secret=DEMO_SECRET)
    _grant_role(db_session, user, "general_director")
    code = pyotp.TOTP(DEMO_SECRET).now()
    token = client.post(
        "/auth/login",
        json={"email": user.email, "password": "Secret123!", "mfa_code": code},
    ).json()["access_token"]
    gen_code = pyotp.TOTP(DEMO_SECRET).now()
    resp = client.post(
        "/auth/mfa/recovery-codes",
        json={"code": gen_code},
        headers={"Authorization": f"Bearer {token}"},
    )
    issued = resp.json()["codes"]

    event = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.action == "auth.mfa.recovery_codes.generate")
        .first()
    )
    assert event is not None
    assert event.new_values_json == {"count": 10}
    # ни один выданный код не встречается в журнале
    serialized = str(event.new_values_json)
    for code_value in issued:
        assert code_value not in serialized
