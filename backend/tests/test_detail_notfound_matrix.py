"""Сквозной тест устойчивости и изоляции detail-эндпоинтов (§18, §24).

Инвариант: полностью авторизованный пользователь, запрашивающий любой GET-эндпоинт
вида `/.../{id}` со СЛУЧАЙНЫМ идентификатором, не должен:
  • получить `200` — то есть чужие/произвольные данные не «просачиваются»
    (несуществующий или недоступный объект → `404`/`403`);
  • получить `5xx` — то есть отсутствие объекта не приводит к сбою сервера.

Эндпоинты перечисляются через OpenAPI, поэтому новый detail-эндпоинт без корректной
обработки «не найдено» будет автоматически пойман. Тест не меняет поведение системы.
"""

from __future__ import annotations

import re
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
    Role,
    RolePermission,
    User,
    UserRole,
)

# Все коды прав, используемые API (см. require_permission в app/api/*.py).
ALL_PERMS = [
    "accountable.account", "accountable.approve", "accountable.manage", "accountable.view",
    "agent.approve", "agent.manage", "agent.view", "approval.decide", "approval.view",
    "audit.finding.manage", "audit.finding.resolve", "audit.finding.view",
    "budget.approve", "budget.manage", "crm.manage", "crm.view",
    "daily_report.approve", "daily_report.manage", "daily_report.view", "deal.approve",
    "design.brief.approve", "design.issue.manage", "design.manage", "design.release",
    "design.view", "equipment.maintain", "equipment.manage", "equipment.view",
    "estimate.approve", "estimate.manage", "estimate.view", "finance.view",
    "inbox.manage", "inbox.view", "integration.approve", "integration.manage",
    "integration.view", "invoice.manage", "kpi.view", "management.view",
    "notification.manage", "offer.approve", "payment.approve", "payment.request",
    "payroll.approve", "payroll.manage", "payroll.view", "personnel.manage",
    "personnel.view", "procurement.approve", "procurement.manage", "procurement.view",
    "project.create", "project.view", "pto.approve", "pto.manage", "pto.view",
    "risk.approve", "risk.manage", "risk.view", "site.manage", "smm.approve",
    "smm.manage", "smm.view", "supplier.view", "task.approve", "task.assign",
    "task.create", "task.execute", "task.view", "warehouse.manage", "warehouse.view",
]


def _superuser(db) -> User:
    org = Organization(legal_name="ТЕСТ")
    db.add(org)
    db.flush()
    emp = Employee(organization_id=org.id, full_name="Полномочный")
    db.add(emp)
    db.flush()
    user = User(email=f"u{uuid.uuid4().hex[:8]}@ex.com", password_hash=hash_password("x"),
                status="active", employee_id=emp.id)
    db.add(user)
    db.flush()
    role = Role(code=f"r{uuid.uuid4().hex[:6]}", name="r")
    db.add(role)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    for pc in ALL_PERMS:
        p = Permission(code=pc)
        db.add(p)
        db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=p.id))
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


def _detail_get_paths() -> list[str]:
    """GET-эндпоинты ровно с одним path-параметром."""
    paths = app.openapi()["paths"]
    return sorted(p for p, ops in paths.items() if "get" in ops and p.count("{") == 1)


def _fill(path: str) -> str:
    return re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)


def test_detail_endpoints_no_leak_no_crash(db_engine, db_session) -> None:
    user = _superuser(db_session)
    client = _client(db_engine, user)
    leaks: list[str] = []
    crashes: list[str] = []
    for path in _detail_get_paths():
        resp = client.get(_fill(path))
        if resp.status_code == 200:
            leaks.append(f"{path} -> 200")
        elif resp.status_code >= 500:
            crashes.append(f"{path} -> {resp.status_code}")
    assert not leaks, f"detail-эндпоинты выдают данные по случайному id: {leaks}"
    assert not crashes, f"detail-эндпоинты падают при отсутствии объекта: {crashes}"


def test_detail_matrix_discovers_endpoints() -> None:
    assert len(_detail_get_paths()) >= 20
