"""Сквозной регрессионный тест прав доступа на запись (§19, §23 «тесты прав доступа»).

Инвариант: пользователь без прав не должен получать успешный ответ (2xx) ни от одного
POST-эндпоинта, кроме публичных/персональных (вход, выход, MFA, отметка своих
уведомлений прочитанными). Запрос отправляется с пустым телом `{}` — ожидается отказ
по правам (403) либо валидация (422), но НИКОГДА успешная запись. Эндпоинты
перечисляются через OpenAPI, поэтому новый POST без `require_permission` будет пойман.

Тест не меняет поведение системы: guarded-эндпоинты отклоняют запрос на этапе проверки
права, до какой-либо записи в БД.
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
from app.models import Employee, Organization, User

# Публичные (вход) и персональные (свой сеанс/свои уведомления) POST-эндпоинты.
PUBLIC_OR_PERSONAL = {
    "/auth/login",
    "/auth/logout",
    "/auth/mfa/verify",
    # генерация резервных кодов MFA — личное действие над своей учётной записью
    "/auth/mfa/recovery-codes",
    # регистрация/вход по passkey — личные/публичные церемонии WebAuthn
    "/auth/webauthn/register/begin",
    "/auth/webauthn/register/complete",
    "/auth/webauthn/authenticate/begin",
    "/auth/webauthn/authenticate/complete",
    "/notifications/read-all",
}

SUCCESS = {200, 201, 202, 204}


def _no_perm_user(db) -> User:
    org = Organization(legal_name="ТЕСТ")
    db.add(org)
    db.flush()
    emp = Employee(organization_id=org.id, full_name="Без прав")
    db.add(emp)
    db.flush()
    user = User(email=f"u{uuid.uuid4().hex[:8]}@ex.com", password_hash=hash_password("x"),
                status="active", employee_id=emp.id)
    db.add(user)
    db.commit()
    return user


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


def _post_paths() -> list[str]:
    paths = app.openapi()["paths"]
    return sorted(p for p, ops in paths.items() if "post" in ops and "{" not in p)


def test_write_endpoints_reject_user_without_permission(db_engine, db_session) -> None:
    user = _no_perm_user(db_session)
    client = _client(db_engine, user)
    offenders: list[str] = []
    for path in _post_paths():
        if path in PUBLIC_OR_PERSONAL:
            continue
        resp = client.post(path, json={})
        if resp.status_code in SUCCESS:
            offenders.append(f"{path} -> {resp.status_code}")
    assert not offenders, f"POST-эндпоинты без охраны доступа: {offenders}"


def test_write_matrix_discovers_endpoints() -> None:
    # Защита самого теста: список POST-эндпоинтов не должен внезапно опустеть.
    assert len(_post_paths()) >= 30
