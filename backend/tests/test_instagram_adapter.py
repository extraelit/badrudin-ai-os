"""Тесты Instagram-адаптера и вебхуков (PR-6).

Проверяют: выбор адаптера (instagram→sandbox без ключей, →InstagramAdapter с
токеном+account_id); sandbox по умолчанию; реальный режим через поддельный
транспорт (sendMessage text); webhook verify (challenge/403/503); webhook
incoming создаёт входящее сообщение. Реальный аккаунт Meta не подключается.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core import token_store
from app.core.config import get_settings
from app.db.session import get_db
from app.main import app
from app.models import Organization
from app.services import communications as svc
from app.services.channel_adapters import (
    InstagramAdapter,
    SandboxAdapter,
    get_channel_adapter,
)


def _org(db, name="ТЕСТ") -> Organization:
    org = Organization(legal_name=name)
    db.add(org)
    db.flush()
    return org


class FakeIG:
    def __init__(self):
        self.calls = []

    def __call__(self, url, token, *, json=None, data=None, files=None):
        self.calls.append({"url": url, "json": json})
        return {"message_id": "ig-msg-1"}


@pytest.fixture
def ig_configured(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "comm_real_send", True)
    monkeypatch.setattr(s, "instagram_token", "ig-token")
    monkeypatch.setattr(s, "instagram_account_id", "17841400000")
    yield


def test_adapter_selection_sandbox_without_keys(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "instagram_token", "")
    assert isinstance(get_channel_adapter("instagram"), SandboxAdapter)


def test_adapter_selection_instagram_with_keys(ig_configured) -> None:
    a = get_channel_adapter("instagram")
    assert isinstance(a, InstagramAdapter) and a.available()


def test_instagram_send_text(ig_configured) -> None:
    fake = FakeIG()
    a = InstagramAdapter(call=fake)
    res = a.send(subject=None, body="Привет", sender=None, recipients=["USER123"],
                 attachments=[])
    assert res.ok and res.external_id == "ig:ig-msg-1"
    assert fake.calls[0]["json"]["recipient"]["id"] == "USER123"


def test_dispatch_sandbox_by_default(db_session, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "comm_real_send", False)
    org = _org(db_session)
    approver = uuid.uuid4()
    m = svc.create_draft(db_session, org.id, channel="instagram", author_user_id=uuid.uuid4())
    svc.add_recipient(db_session, m, address="USER123")
    svc.submit_for_approval(db_session, m, actor_user_id=uuid.uuid4())
    svc.approve(db_session, m, approver_user_id=approver)
    svc.dispatch(db_session, m, actor_user_id=approver)
    assert m.status == "sent" and m.external_id.startswith("sandbox:")


def test_dispatch_real_mode_uses_instagram(db_session, ig_configured, monkeypatch) -> None:
    import app.services.channel_adapters as ca
    fake = FakeIG()
    monkeypatch.setitem(ca._REAL_ADAPTERS, "instagram", lambda: InstagramAdapter(call=fake))
    org = _org(db_session)
    approver = uuid.uuid4()
    m = svc.create_draft(db_session, org.id, channel="instagram", body_text="Привет",
                         author_user_id=uuid.uuid4())
    contact = svc.create_contact(db_session, org.id, display_name="IG", instagram="USER123",
                                 consent=True)
    svc.add_recipient(db_session, m, address="USER123", contact_id=contact.id)
    svc.submit_for_approval(db_session, m, actor_user_id=uuid.uuid4())
    svc.approve(db_session, m, approver_user_id=approver)
    svc.dispatch(db_session, m, actor_user_id=approver)
    assert m.status == "sent" and m.external_id == "ig:ig-msg-1"
    assert fake.calls and fake.calls[0]["json"]["recipient"]["id"] == "USER123"


# ------------------------------- Webhooks --------------------------------- #

def _client(db_engine) -> TestClient:
    factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)

    def override_db() -> Iterator[Session]:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    token_store.clear()
    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.clear()


def test_webhook_verify_challenge(db_engine, db_session, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "instagram_verify_token", "verify-me")
    client = _client(db_engine)
    r = client.get("/communications/webhooks/instagram", params={
        "hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "77",
    })
    assert r.status_code == 200 and r.text == "77"


def test_webhook_verify_wrong_token(db_engine, db_session, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "instagram_verify_token", "verify-me")
    client = _client(db_engine)
    r = client.get("/communications/webhooks/instagram", params={
        "hub.mode": "subscribe", "hub.verify_token": "wrong",
    })
    assert r.status_code == 403


def test_webhook_verify_disabled_without_token(db_engine, db_session, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "instagram_verify_token", "")
    client = _client(db_engine)
    r = client.get("/communications/webhooks/instagram", params={"hub.mode": "subscribe"})
    assert r.status_code == 503


def test_webhook_incoming_creates_message(db_engine, db_session, monkeypatch) -> None:
    _org(db_session)
    db_session.commit()
    monkeypatch.setattr(get_settings(), "instagram_app_secret", "")
    monkeypatch.setattr(get_settings(), "instagram_verify_token", "verify-me")
    client = _client(db_engine)
    body = {"entry": [{"messaging": [
        {"sender": {"id": "USER123"}, "message": {"mid": "m1", "text": "Привет"}}
    ]}]}
    r = client.post("/communications/webhooks/instagram", json=body)
    assert r.status_code == 200 and r.json()["received"] == 1
