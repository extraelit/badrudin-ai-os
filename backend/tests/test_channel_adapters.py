"""Тесты адаптеров каналов и реального режима отправки (PR-3).

Проверяют: по умолчанию отправка идёт в sandbox; реальная отправка заблокирована
без ключей; выбор адаптера (email→sandbox без ключей, email→EmailAdapter с
ключами); EmailAdapter строит письмо с вложениями и не делает сетевых вызовов
(транспорт внедряется); dispatch в реальном режиме использует адаптер и
прикладывает вложения сообщения. Реальный SMTP не подключается.
"""

from __future__ import annotations

import uuid

import pytest

from app.core.config import get_settings
from app.models import CommunicationContact, Organization
from app.services import attachments as att
from app.services import communications as svc
from app.services.channel_adapters import (
    EmailAdapter,
    SandboxAdapter,
    get_channel_adapter,
)


class FakeSMTP:
    """Поддельный SMTP-транспорт: захватывает письмо, без сети."""

    sent: list = []

    def __init__(self, host, port, timeout=None):
        self.host = host

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        pass

    def login(self, user, password):
        pass

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


@pytest.fixture
def smtp_configured(monkeypatch):
    """Включает реальный режим и настраивает SMTP на уровне настроек."""
    s = get_settings()
    monkeypatch.setattr(s, "comm_real_send", True)
    monkeypatch.setattr(s, "smtp_host", "smtp.example.test")
    monkeypatch.setattr(s, "smtp_from", "noreply@example.test")
    monkeypatch.setattr(s, "smtp_use_tls", False)
    FakeSMTP.sent = []
    yield


def _org(db, name="ТЕСТ") -> Organization:
    org = Organization(legal_name=name)
    db.add(org)
    db.flush()
    return org


def test_adapter_selection_sandbox_without_keys() -> None:
    a = get_channel_adapter("email")
    assert isinstance(a, SandboxAdapter)


def test_adapter_selection_email_with_keys(smtp_configured) -> None:
    a = get_channel_adapter("email")
    assert isinstance(a, EmailAdapter) and a.available()


def test_email_adapter_builds_message_with_attachment(smtp_configured) -> None:
    a = EmailAdapter(smtp_factory=FakeSMTP)
    res = a.send(subject="Тема", body="Текст", sender=None,
                 recipients=["c@example.test"],
                 attachments=[("акт.pdf", b"%PDF-1", "application/pdf")])
    assert res.ok and res.external_id
    assert len(FakeSMTP.sent) == 1
    msg = FakeSMTP.sent[0]
    assert msg["To"] == "c@example.test"
    names = [p.get_filename() for p in msg.iter_attachments()]
    assert "акт.pdf" in names


def test_dispatch_sandbox_by_default(db_session) -> None:
    org = _org(db_session)
    approver = uuid.uuid4()
    m = svc.create_draft(db_session, org.id, channel="email", author_user_id=uuid.uuid4())
    svc.add_recipient(db_session, m, address="c@example.test")
    svc.submit_for_approval(db_session, m, actor_user_id=uuid.uuid4())
    svc.approve(db_session, m, approver_user_id=approver)
    svc.dispatch(db_session, m, actor_user_id=approver)
    assert m.status == "sent" and m.external_id.startswith("sandbox:")


def test_dispatch_real_mode_uses_email_adapter(db_session, smtp_configured, monkeypatch) -> None:
    # Подменяем реальный адаптер email на EmailAdapter с поддельным транспортом.
    import app.services.channel_adapters as ca
    monkeypatch.setitem(ca._REAL_ADAPTERS, "email", lambda: EmailAdapter(smtp_factory=FakeSMTP))

    org = _org(db_session)
    approver = uuid.uuid4()
    m = svc.create_draft(db_session, org.id, channel="email", subject="Привет",
                         body_text="Тело", author_user_id=uuid.uuid4())
    contact = svc.create_contact(db_session, org.id, display_name="Получатель",
                                 email="c@example.test", consent=True)
    svc.add_recipient(db_session, m, address="c@example.test", contact_id=contact.id)
    # прикладываем файл к сообщению (universal attachments, entity_type=message)
    att.attach(db_session, organization_id=org.id, entity_type="message",
               entity_id=m.id, original_name="акт.pdf", content=b"%PDF-1",
               mime_type="application/pdf", attachment_type="pdf")
    svc.submit_for_approval(db_session, m, actor_user_id=uuid.uuid4())
    svc.approve(db_session, m, approver_user_id=approver)
    svc.dispatch(db_session, m, actor_user_id=approver)
    assert m.status == "sent"
    assert not m.external_id.startswith("sandbox:")  # реальный external_id
    assert len(FakeSMTP.sent) == 1
    names = [p.get_filename() for p in FakeSMTP.sent[0].iter_attachments()]
    assert "акт.pdf" in names  # вложение сообщения ушло


def test_real_send_flag_off_forces_sandbox(db_session, monkeypatch) -> None:
    # Ключи есть, но рубильник выключен → всё равно sandbox.
    s = get_settings()
    monkeypatch.setattr(s, "smtp_host", "smtp.example.test")
    monkeypatch.setattr(s, "smtp_from", "noreply@example.test")
    monkeypatch.setattr(s, "comm_real_send", False)
    org = _org(db_session)
    approver = uuid.uuid4()
    m = svc.create_draft(db_session, org.id, channel="email", author_user_id=uuid.uuid4())
    svc.add_recipient(db_session, m, address="c@example.test")
    svc.submit_for_approval(db_session, m, actor_user_id=uuid.uuid4())
    svc.approve(db_session, m, approver_user_id=approver)
    svc.dispatch(db_session, m, actor_user_id=approver)
    assert m.external_id.startswith("sandbox:")
