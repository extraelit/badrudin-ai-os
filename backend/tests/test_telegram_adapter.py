"""Тесты Telegram-адаптера и входящего вебхука (PR-4).

Проверяют: выбор адаптера (telegram→sandbox без токена, →TelegramAdapter с
токеном); sandbox по умолчанию; реальный режим через поддельный http-транспорт
(sendMessage + sendDocument с вложением, без сети); вебхук создаёт входящее
сообщение при верном секрете; вебхук отклоняет неверный секрет и отключён без
секрета. Реальный бот не подключается.
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
    TelegramAdapter,
    get_channel_adapter,
)


def _org(db, name="ТЕСТ") -> Organization:
    org = Organization(legal_name=name)
    db.add(org)
    db.flush()
    return org


class FakeTelegram:
    """Поддельный транспорт Telegram: фиксирует вызовы, без сети."""

    def __init__(self):
        self.calls = []

    def __call__(self, method, token, base, *, data, files=None):
        self.calls.append({"method": method, "data": data, "files": files})
        return {"ok": True, "result": {"message_id": 4242}}


@pytest.fixture
def tg_configured(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "comm_real_send", True)
    monkeypatch.setattr(s, "telegram_bot_token", "test-token")
    yield


def test_adapter_selection_sandbox_without_token(monkeypatch) -> None:
    # Явно очищаем токен (локальный .env может содержать placeholder).
    monkeypatch.setattr(get_settings(), "telegram_bot_token", "")
    assert isinstance(get_channel_adapter("telegram"), SandboxAdapter)


def test_adapter_selection_telegram_with_token(tg_configured) -> None:
    a = get_channel_adapter("telegram")
    assert isinstance(a, TelegramAdapter) and a.available()


def test_telegram_send_message_and_document(tg_configured) -> None:
    fake = FakeTelegram()
    a = TelegramAdapter(call=fake)
    res = a.send(subject="Тема", body="Текст", sender=None, recipients=["123456"],
                 attachments=[("акт.pdf", b"%PDF-1", "application/pdf")])
    assert res.ok and res.external_id == "tg:4242"
    methods = [c["method"] for c in fake.calls]
    assert "sendMessage" in methods and "sendDocument" in methods
    doc_call = next(c for c in fake.calls if c["method"] == "sendDocument")
    assert doc_call["files"]["document"][0] == "акт.pdf"


def test_dispatch_sandbox_by_default(db_session, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "comm_real_send", False)  # рубильник off
    org = _org(db_session)
    approver = uuid.uuid4()
    m = svc.create_draft(db_session, org.id, channel="telegram", author_user_id=uuid.uuid4())
    svc.add_recipient(db_session, m, address="123456")
    svc.submit_for_approval(db_session, m, actor_user_id=uuid.uuid4())
    svc.approve(db_session, m, approver_user_id=approver)
    svc.dispatch(db_session, m, actor_user_id=approver)
    assert m.status == "sent" and m.external_id.startswith("sandbox:")


def test_dispatch_real_mode_uses_telegram(db_session, tg_configured, monkeypatch) -> None:
    import app.services.channel_adapters as ca
    fake = FakeTelegram()
    monkeypatch.setitem(ca._REAL_ADAPTERS, "telegram", lambda: TelegramAdapter(call=fake))

    org = _org(db_session)
    approver = uuid.uuid4()
    m = svc.create_draft(db_session, org.id, channel="telegram", subject="Привет",
                         body_text="Тело", author_user_id=uuid.uuid4())
    contact = svc.create_contact(db_session, org.id, display_name="Чат",
                                 telegram="123456", consent=True)
    svc.add_recipient(db_session, m, address="123456", contact_id=contact.id)
    att.attach(db_session, organization_id=org.id, entity_type="message",
               entity_id=m.id, original_name="акт.pdf", content=b"%PDF-1",
               mime_type="application/pdf", attachment_type="pdf")
    svc.submit_for_approval(db_session, m, actor_user_id=uuid.uuid4())
    svc.approve(db_session, m, approver_user_id=approver)
    svc.dispatch(db_session, m, actor_user_id=approver)
    assert m.status == "sent" and m.external_id == "tg:4242"
    assert any(c["method"] == "sendDocument" for c in fake.calls)


# ------------------------------- Webhook --------------------------------- #

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


def test_webhook_creates_incoming(db_engine, db_session, monkeypatch) -> None:
    _org(db_session)
    db_session.commit()
    monkeypatch.setattr(get_settings(), "telegram_webhook_secret", "hook-secret")
    client = _client(db_engine)
    r = client.post("/communications/webhooks/telegram",
                    headers={"X-Telegram-Bot-Api-Secret-Token": "hook-secret"},
                    json={"message": {"message_id": 7, "chat": {"id": 555}, "text": "Привет"}})
    assert r.status_code == 200 and r.json()["ok"] is True


def test_webhook_wrong_secret_rejected(db_engine, db_session, monkeypatch) -> None:
    _org(db_session)
    db_session.commit()
    monkeypatch.setattr(get_settings(), "telegram_webhook_secret", "hook-secret")
    client = _client(db_engine)
    r = client.post("/communications/webhooks/telegram",
                    headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
                    json={"message": {"message_id": 7, "chat": {"id": 555}}})
    assert r.status_code == 403


def test_webhook_disabled_without_secret(db_engine, db_session, monkeypatch) -> None:
    _org(db_session)
    db_session.commit()
    monkeypatch.setattr(get_settings(), "telegram_webhook_secret", "")
    client = _client(db_engine)
    r = client.post("/communications/webhooks/telegram", json={"message": {}})
    assert r.status_code == 503
