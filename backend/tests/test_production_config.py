"""Тесты production-контура (PR-9).

Проверяют: мягкий rate-limiter (превышение → 429); readiness-проба /health/ready;
идемпотентность фоновой отправки (повтор не создаёт дубль); preflight в
production отклоняет заглушки секретов; заголовки безопасности присутствуют.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from app.core.config import Settings
from app.core.middleware import RateLimitMiddleware
from app.core.preflight import SecretValidationError, check_required_secrets
from app.models import Organization
from app.services import communications as comm


# ------------------------------ Rate limiter ----------------------------- #

def _mini_app(limit: int) -> TestClient:
    async def ok(request):
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/x", ok)])
    app.add_middleware(RateLimitMiddleware, limit_per_minute=limit)
    return TestClient(app)


def test_rate_limiter_blocks_over_limit() -> None:
    client = _mini_app(limit=3)
    codes = [client.get("/x").status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200]
    assert 429 in codes[3:]


def test_rate_limiter_disabled_when_zero() -> None:
    client = _mini_app(limit=0)
    assert all(client.get("/x").status_code == 200 for _ in range(10))


# ----------------------------- Readiness --------------------------------- #

def test_health_ready(client) -> None:
    r = client.get("/health/ready")
    assert r.status_code == 200 and r.json()["database"] is True


def test_security_headers_present(client) -> None:
    r = client.get("/health")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"


# --------------------------- Idempotent dispatch ------------------------- #

def test_dispatch_idempotent_no_duplicate(db_session) -> None:
    org = Organization(legal_name="ТЕСТ")
    db_session.add(org)
    db_session.flush()
    approver = uuid.uuid4()
    m = comm.create_draft(db_session, org.id, channel="email", author_user_id=uuid.uuid4())
    comm.add_recipient(db_session, m, address="c@ex.com")
    comm.submit_for_approval(db_session, m, actor_user_id=uuid.uuid4())
    comm.approve(db_session, m, approver_user_id=approver)
    comm.dispatch_idempotent(db_session, m, actor_user_id=approver)
    assert m.status == "sent"
    events_before = len(comm.delivery_log(db_session, m))
    ext_before = m.external_id
    # повторная отправка — идемпотентна: без новых событий и без смены external_id
    comm.dispatch_idempotent(db_session, m, actor_user_id=approver)
    assert m.status == "sent" and m.external_id == ext_before
    assert len(comm.delivery_log(db_session, m)) == events_before


# ------------------------------- Preflight ------------------------------- #

def _prod_settings(**over) -> Settings:
    base = dict(
        app_env="production", jwt_secret="change-me", storage_backend="local",
        database_url="sqlite://", app_debug=True, cookie_secure=False,
    )
    base.update(over)
    return Settings(_env_file=None, **base)


def test_preflight_production_rejects_placeholders() -> None:
    with pytest.raises(SecretValidationError):
        check_required_secrets(_prod_settings())


def test_preflight_production_ok_with_secure_config() -> None:
    s = _prod_settings(
        jwt_secret="x" * 40, storage_backend="s3",
        minio_access_key="real-access", minio_secret_key="real-secret",
        database_url="postgresql+psycopg://u:p@db:5432/badrudin",
        app_debug=False, cookie_secure=True,
    )
    assert check_required_secrets(s) == []  # проблем нет


def test_preflight_development_allows_placeholders() -> None:
    s = Settings(_env_file=None, app_env="development", jwt_secret="change-me")
    # в development не блокирует (только предупреждение)
    problems = check_required_secrets(s)
    assert isinstance(problems, list)
