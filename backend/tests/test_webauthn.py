"""Тесты WebAuthn / passkey (этап 1, отдельный безопасный контур).

Криптографическая проверка библиотеки `webauthn` подменяется в тестах (реального
устройства нет), а проверяется логика контура: генерация опций с челленджем,
сохранение **только публичного ключа**, жизненный цикл ключа и — обязательно —
что отозванный/приостановленный ключ вход не допускает, а регресс счётчика
подписей отклоняется.
"""

from __future__ import annotations

import base64
import types
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_current_user
from app.core import token_store, webauthn_challenge
from app.core.security import hash_password
from app.db.session import get_db
from app.main import app
from app.models import User, WebAuthnCredential
from app.services import webauthn as svc


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _make_user(db, *, email="k@example.com", status="active"):
    user = User(
        id=uuid.uuid4(), email=email,
        password_hash=hash_password("Secret123!"), status=status,
    )
    db.add(user)
    db.commit()
    return user


def _add_credential(db, user, *, status="active", sign_count=5, cred_id=None):
    cred = WebAuthnCredential(
        user_id=user.id,
        credential_id=cred_id or _b64url(uuid.uuid4().bytes),
        public_key=_b64url(b"public-key-bytes"),
        sign_count=sign_count,
        status=status,
        label="Ключ",
    )
    db.add(cred)
    db.commit()
    return cred


def _client(db_engine, user=None) -> TestClient:
    factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)

    def override_db() -> Iterator[Session]:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    token_store.clear()
    webauthn_challenge.clear()
    app.dependency_overrides[get_db] = override_db
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.clear()
    webauthn_challenge.clear()


# ---------------------------------------------------------------------------
# Опции и хранение только публичного ключа
# ---------------------------------------------------------------------------

def test_register_begin_returns_options_with_challenge(db_engine, db_session) -> None:
    user = _make_user(db_session)
    client = _client(db_engine, user)
    resp = client.post("/auth/webauthn/register/begin")
    assert resp.status_code == 200
    body = resp.json()
    assert body["challenge"] and body["rp"]["id"] == "localhost"
    assert "pubKeyCredParams" in body


def test_model_stores_no_private_key(db_session) -> None:
    # у модели ключа нет поля закрытого ключа — хранится только публичный
    cols = set(WebAuthnCredential.__table__.columns.keys())
    assert "public_key" in cols
    assert not any("private" in c for c in cols)


def test_complete_registration_stores_public_key_only(
    db_engine, db_session, monkeypatch
) -> None:
    user = _make_user(db_session)
    client = _client(db_engine, user)
    client.post("/auth/webauthn/register/begin")  # кладёт челлендж

    fake = types.SimpleNamespace(
        credential_id=b"cred-1", credential_public_key=b"cose-public-key",
        sign_count=0, aaguid="aa-guid",
    )
    monkeypatch.setattr(svc, "verify_registration_response", lambda **kw: fake)

    resp = client.post(
        "/auth/webauthn/register/complete",
        json={"credential": {"id": "x"}, "label": "Мой ключ"},
    )
    assert resp.status_code == 201, resp.text
    cred = db_session.query(WebAuthnCredential).filter_by(user_id=user.id).one()
    assert cred.public_key == _b64url(b"cose-public-key")
    assert cred.credential_id == _b64url(b"cred-1")
    assert cred.status == "active"


# ---------------------------------------------------------------------------
# Обязательное: отозванный/приостановленный ключ вход не допускает
# ---------------------------------------------------------------------------

def test_revoked_credential_cannot_authenticate(db_session, monkeypatch) -> None:
    user = _make_user(db_session)
    cred = _add_credential(db_session, user, status="revoked")
    webauthn_challenge.put(f"auth:{user.id}", b"chal")
    # даже если крипто-проверка прошла бы — статус отклоняет вход
    monkeypatch.setattr(
        svc, "verify_authentication_response",
        lambda **kw: types.SimpleNamespace(new_sign_count=6),
    )
    with pytest.raises(svc.WebAuthnError, match="отозван|приостановлен"):
        svc.complete_authentication(
            db_session, user, {"rawId": cred.credential_id}
        )


def test_suspended_credential_cannot_authenticate(db_session, monkeypatch) -> None:
    user = _make_user(db_session)
    cred = _add_credential(db_session, user, status="suspended")
    webauthn_challenge.put(f"auth:{user.id}", b"chal")
    monkeypatch.setattr(
        svc, "verify_authentication_response",
        lambda **kw: types.SimpleNamespace(new_sign_count=6),
    )
    with pytest.raises(svc.WebAuthnError):
        svc.complete_authentication(db_session, user, {"rawId": cred.credential_id})


def test_active_credential_authenticates_and_updates_sign_count(
    db_session, monkeypatch
) -> None:
    user = _make_user(db_session)
    cred = _add_credential(db_session, user, status="active", sign_count=5)
    webauthn_challenge.put(f"auth:{user.id}", b"chal")
    monkeypatch.setattr(
        svc, "verify_authentication_response",
        lambda **kw: types.SimpleNamespace(new_sign_count=6),
    )
    result = svc.complete_authentication(db_session, user, {"rawId": cred.credential_id})
    assert result.sign_count == 6
    assert result.last_used_at is not None


def test_sign_count_regression_rejected(db_session, monkeypatch) -> None:
    user = _make_user(db_session)
    cred = _add_credential(db_session, user, status="active", sign_count=10)
    webauthn_challenge.put(f"auth:{user.id}", b"chal")
    # устройство сообщило счётчик не больше сохранённого — признак клонирования
    monkeypatch.setattr(
        svc, "verify_authentication_response",
        lambda **kw: types.SimpleNamespace(new_sign_count=9),
    )
    with pytest.raises(svc.WebAuthnError, match="регресс"):
        svc.complete_authentication(db_session, user, {"rawId": cred.credential_id})


# ---------------------------------------------------------------------------
# Жизненный цикл ключа
# ---------------------------------------------------------------------------

def test_revoke_via_api_then_login_blocked(db_engine, db_session, monkeypatch) -> None:
    user = _make_user(db_session)
    cred = _add_credential(db_session, user, status="active")
    client = _client(db_engine, user)
    # отзыв ключа владельцем
    r = client.post(f"/auth/webauthn/credentials/{cred.id}/revoke")
    assert r.status_code == 200 and r.json()["status"] == "revoked"

    # вход по отозванному ключу невозможен (через публичную церемонию)
    app.dependency_overrides.pop(get_current_user, None)
    webauthn_challenge.put(f"auth:{user.id}", b"chal")
    monkeypatch.setattr(
        svc, "verify_authentication_response",
        lambda **kw: types.SimpleNamespace(new_sign_count=99),
    )
    resp = client.post(
        "/auth/webauthn/authenticate/complete",
        json={"email": user.email, "credential": {"rawId": cred.credential_id}},
    )
    assert resp.status_code == 401


def test_revoked_key_cannot_be_reactivated(db_session) -> None:
    user = _make_user(db_session)
    cred = _add_credential(db_session, user, status="revoked")
    with pytest.raises(svc.WebAuthnError):
        svc.set_status(db_session, user.id, cred.id, "active")


def test_credentials_isolated_by_owner(db_session) -> None:
    owner = _make_user(db_session, email="owner@example.com")
    other = _make_user(db_session, email="other@example.com")
    cred = _add_credential(db_session, owner)
    # чужой пользователь не может отозвать не свой ключ
    with pytest.raises(svc.WebAuthnError):
        svc.set_status(db_session, other.id, cred.id, "revoked")


def test_successful_passkey_login_issues_token(db_engine, db_session, monkeypatch) -> None:
    user = _make_user(db_session, email="login@example.com")
    cred = _add_credential(db_session, user, status="active", sign_count=1)
    client = _client(db_engine)  # публичная церемония, без current_user
    webauthn_challenge.put(f"auth:{user.id}", b"chal")
    monkeypatch.setattr(
        svc, "verify_authentication_response",
        lambda **kw: types.SimpleNamespace(new_sign_count=2),
    )
    resp = client.post(
        "/auth/webauthn/authenticate/complete",
        json={"email": user.email, "credential": {"rawId": cred.credential_id}},
    )
    assert resp.status_code == 200, resp.text
    assert "access_token" in resp.json()
