"""Тесты слоя ИИ-провайдеров (PR-8).

Проверяют: выбор адаптера; эхо-режим по умолчанию (реальные вызовы выключены);
реальный режим через поддельный http-транспорт с usage; fallback при
недоступности основного провайдера; назначение модели агенту и запись расхода
БЕЗ промптов; проверку подключения (health); RBAC (403 без прав); ключи не
попадают в ответ API (маскирование).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_current_user
from app.core import token_store
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import get_db
from app.main import app
from app.models import (
    AgentAIAssignment,
    AIAgent,
    AIProvider,
    AIUsageRecord,
    Employee,
    Organization,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)
from app.services import ai_provider as svc


def _org(db, name="ТЕСТ") -> Organization:
    org = Organization(legal_name=name)
    db.add(org)
    db.flush()
    return org


def _user(db, org, *, perms=(), email=None) -> User:
    emp = Employee(organization_id=org.id, full_name="Сотрудник")
    db.add(emp)
    db.flush()
    user = User(email=email or f"u{uuid.uuid4().hex[:8]}@ex.com",
                password_hash=hash_password("x"), status="active", employee_id=emp.id)
    db.add(user)
    db.flush()
    if perms:
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
    db.commit()
    return user


def _agent(db, org) -> AIAgent:
    a = AIAgent(organization_id=org.id, code=f"ag{uuid.uuid4().hex[:6]}", name="Агент")
    db.add(a)
    db.flush()
    return a


def _provider(db, org, code, *, enabled=True, default_model="m1") -> AIProvider:
    p = AIProvider(organization_id=org.id, code=code, name=code, enabled=enabled,
                   default_model=default_model)
    db.add(p)
    db.flush()
    return p


# --------------------------- Сервисный уровень --------------------------- #

def test_mask_secret() -> None:
    assert svc.mask_secret("sk-1234567890") == "sk••••••90"
    assert svc.mask_secret("") == ""


def test_echo_mode_by_default(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "ai_real_calls", False)
    a = svc.get_adapter("openai")
    res = a.generate(prompt="привет мир", model="gpt", params={})
    assert res.ok and res.mode == "echo" and "эхо" in res.text


def test_real_mode_via_fake_transport(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "ai_real_calls", True)
    monkeypatch.setattr(get_settings(), "openai_api_key", "sk-test")
    calls = []

    def fake_post(url, key, payload):
        calls.append({"url": url, "key": key, "payload": payload})
        return {"choices": [{"message": {"content": "ответ"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3}}

    a = svc.OpenAIAdapter(http_post=fake_post)
    res = a.generate(prompt="вопрос", model="gpt-4", params={})
    assert res.ok and res.mode == "real" and res.text == "ответ"
    assert res.usage.tokens_in == 5 and res.usage.tokens_out == 3
    assert calls and "chat/completions" in calls[0]["url"]


def test_run_for_agent_fallback(db_session, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "ai_real_calls", False)
    org = _org(db_session)
    agent = _agent(db_session, org)
    primary = _provider(db_session, org, "openai", enabled=False)  # недоступен
    fallback = _provider(db_session, org, "anthropic", enabled=True)
    db_session.add(AgentAIAssignment(
        organization_id=org.id, agent_id=agent.id,
        primary_provider_id=primary.id, primary_model="gpt",
        fallback_provider_id=fallback.id, fallback_model="claude",
    ))
    db_session.flush()
    res = svc.run_for_agent(db_session, organization_id=org.id, agent_id=agent.id,
                            prompt="черновик отчёта", request_id="req-1")
    assert res.ok and res.provider == "anthropic"  # ушли на резерв
    rec = db_session.query(AIUsageRecord).filter_by(agent_id=agent.id).first()
    assert rec is not None and rec.provider_id == fallback.id
    # в записи расхода нет промпта — только метаданные
    assert not hasattr(rec, "prompt")


def test_run_for_agent_requires_assignment(db_session) -> None:
    org = _org(db_session)
    agent = _agent(db_session, org)
    with pytest.raises(svc.AIProviderError, match="не назначен"):
        svc.run_for_agent(db_session, organization_id=org.id, agent_id=agent.id, prompt="x")


def test_health_check_unknown_without_keys(db_session, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "ai_real_calls", False)
    org = _org(db_session)
    p = _provider(db_session, org, "openai")
    h = svc.check_health(db_session, p)
    assert h.status == "unknown"


# ------------------------------- API/RBAC -------------------------------- #

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


def test_api_create_and_keys_masked(db_engine, db_session, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "openai_api_key", "sk-supersecret-value")
    org = _org(db_session)
    admin = _user(db_session, org, perms=("ai.provider.view", "ai.provider.manage"))
    c = _client(db_engine, admin)
    r = c.post("/ai-providers/", json={"code": "openai", "name": "OpenAI", "default_model": "gpt-4"})
    assert r.status_code == 201, r.text
    body = r.json()
    # ключ не возвращается целиком; только маскированный индикатор
    assert "sk-supersecret-value" not in str(body)
    assert body["credentials_configured_externally"] is True
    assert body["key_hint"] and "•" in body["key_hint"]
    lst = c.get("/ai-providers/")
    assert lst.status_code == 200 and "sk-supersecret-value" not in str(lst.json())


def test_api_requires_permission(db_engine, db_session) -> None:
    org = _org(db_session)
    viewer = _user(db_session, org, perms=("ai.provider.view",))
    c = _client(db_engine, viewer)
    r = c.post("/ai-providers/", json={"code": "openai", "name": "X"})
    assert r.status_code == 403


def test_api_assign_model_to_agent(db_engine, db_session) -> None:
    org = _org(db_session)
    admin = _user(db_session, org, perms=("ai.provider.view", "ai.provider.manage"))
    agent = _agent(db_session, org)
    prov = _provider(db_session, org, "anthropic")
    db_session.commit()
    c = _client(db_engine, admin)
    r = c.put(f"/ai-providers/agents/{agent.id}/assignment", json={
        "primary_provider_id": str(prov.id), "primary_model": "claude", "max_tokens": 512,
    })
    assert r.status_code == 200 and r.json()["primary_model"] == "claude"
    g = c.get(f"/ai-providers/agents/{agent.id}/assignment")
    assert g.status_code == 200 and g.json()["primary_provider_id"] == str(prov.id)
