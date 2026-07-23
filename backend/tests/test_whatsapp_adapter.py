"""Тесты WhatsApp-адаптера и вебхуков (PR-5).

Проверяют: выбор адаптера (whatsapp→sandbox без ключей, →WhatsAppAdapter с
токеном+phone_number_id); sandbox по умолчанию; реальный режим через поддельный
транспорт (text + document с вложением); отправка шаблона; webhook verify
(challenge при верном verify_token, 403 при неверном, 503 без токена); webhook
incoming создаёт входящее сообщение. Реальный аккаунт не подключается.
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
from app.services import attachments as att
from app.services import communications as svc
from app.services.channel_adapters import (
    SandboxAdapter,
    WhatsAppAdapter,
    get_channel_adapter,
)


def _org(db, name="ТЕСТ") -> Organization:
    org = Organization(legal_name=name)
    db.add(org)
    db.flush()
    return org


class FakeWA:
    """Поддельный транспорт WhatsApp Graph API: фиксирует вызовы, без сети."""

    def __init__(self):
        self.calls = []

    def __call__(self, url, token, *, json=None, data=None, files=None):
        self.calls.append({"url": url, "json": json, "data": data, "files": files})
        if url.endswith("/media"):
            return {"id": "media-123"}
        return {"messages": [{"id": "wamid.ABC"}]}


@pytest.fixture
def wa_configured(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "comm_real_send", True)
    monkeypatch.setattr(s, "whatsapp_token", "wa-token")
    monkeypatch.setattr(s, "whatsapp_phone_number_id", "100200")
    yield


def test_adapter_selection_sandbox_without_keys(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "whatsapp_token", "")
    assert isinstance(get_channel_adapter("whatsapp"), SandboxAdapter)


def test_adapter_selection_whatsapp_with_keys(wa_configured) -> None:
    a = get_channel_adapter("whatsapp")
    assert isinstance(a, WhatsAppAdapter) and a.available()


def test_whatsapp_send_text_and_document(wa_configured) -> None:
    fake = FakeWA()
    a = WhatsAppAdapter(call=fake)
    res = a.send(subject="Тема", body="Текст", sender=None, recipients=["79990000000"],
                 attachments=[("акт.pdf", b"%PDF-1", "application/pdf")])
    assert res.ok and res.external_id == "wa:wamid.ABC"
    urls = [c["url"] for c in fake.calls]
    assert any(u.endswith("/media") for u in urls)  # медиа загружено
    types = [c["json"]["type"] for c in fake.calls if c["json"]]
    assert "text" in types and "document" in types


def test_whatsapp_send_template(wa_configured) -> None:
    fake = FakeWA()
    a = WhatsAppAdapter(call=fake)
    res = a.send_template(to="79990000000", name="welcome", language="ru")
    assert res.ok and res.external_id.startswith("wa:")
    assert fake.calls[0]["json"]["type"] == "template"


def test_dispatch_sandbox_by_default(db_session, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "comm_real_send", False)
    org = _org(db_session)
    approver = uuid.uuid4()
    m = svc.create_draft(db_session, org.id, channel="whatsapp", author_user_id=uuid.uuid4())
    svc.add_recipient(db_session, m, address="79990000000")
    svc.submit_for_approval(db_session, m, actor_user_id=uuid.uuid4())
    svc.approve(db_session, m, approver_user_id=approver)
    svc.dispatch(db_session, m, actor_user_id=approver)
    assert m.status == "sent" and m.external_id.startswith("sandbox:")


def test_dispatch_real_mode_uses_whatsapp(db_session, wa_configured, monkeypatch) -> None:
    import app.services.channel_adapters as ca
    fake = FakeWA()
    monkeypatch.setitem(ca._REAL_ADAPTERS, "whatsapp", lambda: WhatsAppAdapter(call=fake))

    org = _org(db_session)
    approver = uuid.uuid4()
    m = svc.create_draft(db_session, org.id, channel="whatsapp", subject="Привет",
                         body_text="Тело", author_user_id=uuid.uuid4())
    contact = svc.create_contact(db_session, org.id, display_name="Клиент",
                                 whatsapp="79990000000", consent=True)
    svc.add_recipient(db_session, m, address="79990000000", contact_id=contact.id)
    att.attach(db_session, organization_id=org.id, entity_type="message",
               entity_id=m.id, original_name="акт.pdf", content=b"%PDF-1",
               mime_type="application/pdf", attachment_type="pdf")
    svc.submit_for_approval(db_session, m, actor_user_id=uuid.uuid4())
    svc.approve(db_session, m, approver_user_id=approver)
    svc.dispatch(db_session, m, actor_user_id=approver)
    assert m.status == "sent" and m.external_id == "wa:wamid.ABC"
    assert any(c["url"].endswith("/media") for c in fake.calls)


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
    monkeypatch.setattr(get_settings(), "whatsapp_verify_token", "verify-me")
    client = _client(db_engine)
    r = client.get("/communications/webhooks/whatsapp", params={
        "hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "42",
    })
    assert r.status_code == 200 and r.text == "42"


def test_webhook_verify_wrong_token(db_engine, db_session, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "whatsapp_verify_token", "verify-me")
    client = _client(db_engine)
    r = client.get("/communications/webhooks/whatsapp", params={
        "hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "42",
    })
    assert r.status_code == 403


def test_webhook_verify_disabled_without_token(db_engine, db_session, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "whatsapp_verify_token", "")
    client = _client(db_engine)
    r = client.get("/communications/webhooks/whatsapp", params={"hub.mode": "subscribe"})
    assert r.status_code == 503


def test_webhook_incoming_creates_message(db_engine, db_session, monkeypatch) -> None:
    _org(db_session)
    db_session.commit()
    # без app secret приём разрешён по контуру verify-токена
    monkeypatch.setattr(get_settings(), "whatsapp_app_secret", "")
    monkeypatch.setattr(get_settings(), "whatsapp_verify_token", "verify-me")
    client = _client(db_engine)
    body = {"entry": [{"changes": [{"value": {"messages": [
        {"from": "79990000000", "id": "wamid.IN", "text": {"body": "Привет"}}
    ]}}]}]}
    r = client.post("/communications/webhooks/whatsapp", json=body)
    assert r.status_code == 200 and r.json()["received"] == 1
