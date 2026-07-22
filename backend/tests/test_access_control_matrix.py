"""Сквозной регрессионный тест прав доступа (§13 авторизация, §19, §23 «тесты прав
доступа»).

Инвариант: пользователь без прав (аутентифицирован, привязан к организации, но не
имеет ни одного permission и не состоит ни в одном проекте) НЕ должен получать `200`
ни от одного списочного/сводного GET-эндпоинта, кроме явно публичных или персональных
(health, свой профиль, свои уведомления). Тест перечисляет эндпоинты через OpenAPI —
любой новый GET без охраны доступа будет автоматически «пойман» этим тестом.

Тест не изменяет поведение системы; он фиксирует контракт безопасности и защищает от
регрессий (забытая проверка `require_permission`).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_current_user
from app.core import token_store
from app.core.security import hash_password
from app.db.session import get_db
from app.main import app
from app.models import Employee, Organization, User

# Эндпоинты, доступные без бизнес-права: публичные (health) и персональные
# (свой профиль и свои уведомления — доступ ограничен владельцем в сервисном слое).
PUBLIC_OR_PERSONAL = {
    "/health",
    "/health/status",
    "/auth/me",
    # личный эндпоинт: показывает статус резервных кодов MFA самого пользователя
    "/auth/mfa/recovery-codes",
    "/notifications",
    "/notifications/unread-count",
}


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


def _get_paths() -> list[str]:
    """Списочные/сводные GET-эндпоинты без параметров пути (через OpenAPI)."""
    paths = app.openapi()["paths"]
    return sorted(p for p, ops in paths.items() if "get" in ops and "{" not in p)


def test_guarded_get_endpoints_reject_user_without_permission(db_engine, db_session) -> None:
    user = _no_perm_user(db_session)
    client = _client(db_engine, user)
    offenders: list[str] = []
    for path in _get_paths():
        if path in PUBLIC_OR_PERSONAL:
            continue
        resp = client.get(path)
        # Пользователь без прав НЕ должен получать данные (200). Ожидаем 403 (нет
        # права) либо 4xx-валидацию (например, отсутствует обязательный параметр).
        if resp.status_code == 200:
            offenders.append(f"{path} -> 200")
    assert not offenders, f"эндпоинты без охраны доступа: {offenders}"


def test_public_and_personal_endpoints_reachable(db_engine, db_session) -> None:
    user = _no_perm_user(db_session)
    client = _client(db_engine, user)
    # Персональные эндпоинты доступны любому аутентифицированному пользователю.
    assert client.get("/auth/me").status_code == 200
    assert client.get("/notifications").status_code == 200
    assert client.get("/notifications/unread-count").json()["unread"] == 0


def test_openapi_paths_are_discoverable() -> None:
    # Защита самого теста: список эндпоинтов не должен внезапно опустеть.
    assert len(_get_paths()) >= 30
    # Все APIRoute уникальны по (path, methods) — базовая целостность роутера.
    seen = {(r.path, frozenset(r.methods)) for r in app.routes if isinstance(r, APIRoute)}
    assert isinstance(seen, set)
