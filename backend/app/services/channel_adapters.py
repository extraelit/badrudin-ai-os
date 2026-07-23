"""Адаптеры каналов коммуникаций (PR-3): единый контракт отправки + email/SMTP.

Абстракция позволяет подключать каналы (email, WhatsApp, Instagram, Telegram) без
изменения бизнес-логики центра коммуникаций. Реальная отправка выполняется ТОЛЬКО
при `settings.comm_real_send=True` и настроенных ключах канала; иначе используется
безопасный sandbox (без внешних вызовов).

Только официальные механизмы: email — стандартный SMTP. Неофициальные боты и
эмуляция веб-клиентов запрещены (CLAUDE.md §13–14).
"""

from __future__ import annotations

import smtplib
import uuid
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Callable, Protocol

from app.core.config import get_settings


@dataclass
class SendResult:
    """Итог отправки: успех/ошибка и внешний идентификатор у провайдера."""

    ok: bool
    external_id: str | None = None
    error: str | None = None
    per_recipient: dict[str, str] = field(default_factory=dict)


# Вложение для отправки: (имя файла, содержимое, MIME-тип).
Attachment = tuple[str, bytes, str | None]


class ChannelAdapter(Protocol):
    channel: str
    is_real: bool

    def available(self) -> bool:
        """Готов ли адаптер к реальной отправке (ключи настроены)."""

    def send(
        self, *, subject: str | None, body: str | None, sender: str | None,
        recipients: list[str], attachments: list[Attachment],
    ) -> SendResult:
        ...


class SandboxAdapter:
    """Безопасная имитация: не делает внешних вызовов, помечает `sandbox:*`."""

    channel = "*"
    is_real = False

    def available(self) -> bool:
        return True

    def send(self, *, subject, body, sender, recipients, attachments) -> SendResult:
        per = {addr: f"sandbox:{uuid.uuid4().hex[:16]}" for addr in recipients}
        return SendResult(ok=True, external_id=f"sandbox:{uuid.uuid4().hex[:16]}",
                          per_recipient=per)


class EmailAdapter:
    """Отправка email по SMTP. Реально шлёт только при настроенных ключах.

    Транспорт (`smtp_factory`) внедряется для тестируемости — по умолчанию это
    стандартный `smtplib.SMTP`. Без хоста/отправителя `available()` = False, и
    адаптер никогда не выполняет сетевых вызовов.
    """

    channel = "email"
    is_real = True

    def __init__(self, smtp_factory: Callable[..., smtplib.SMTP] | None = None) -> None:
        self._smtp_factory = smtp_factory or smtplib.SMTP

    def available(self) -> bool:
        s = get_settings()
        return bool(s.smtp_host and s.smtp_from)

    def _build(self, *, subject, body, sender, recipients, attachments) -> EmailMessage:
        msg = EmailMessage()
        msg["Subject"] = subject or ""
        msg["From"] = sender or get_settings().smtp_from
        msg["To"] = ", ".join(recipients)
        msg.set_content(body or "")
        for name, content, mime in attachments:
            maintype, _, subtype = (mime or "application/octet-stream").partition("/")
            msg.add_attachment(content, maintype=maintype or "application",
                               subtype=subtype or "octet-stream", filename=name)
        return msg

    def send(self, *, subject, body, sender, recipients, attachments) -> SendResult:
        if not self.available():
            return SendResult(ok=False, error="SMTP не настроен")
        s = get_settings()
        message = self._build(subject=subject, body=body, sender=sender,
                              recipients=recipients, attachments=attachments)
        external_id = message.get("Message-ID") or f"smtp:{uuid.uuid4().hex[:16]}"
        try:
            with self._smtp_factory(s.smtp_host, s.smtp_port,
                                    timeout=s.smtp_timeout_seconds) as client:
                if s.smtp_use_tls:
                    client.starttls()
                if s.smtp_user:
                    client.login(s.smtp_user, s.smtp_password)
                client.send_message(message)
        except Exception as exc:  # noqa: BLE001 — доменная ошибка отправки
            return SendResult(ok=False, error=f"SMTP: {exc}")
        per = {addr: external_id for addr in recipients}
        return SendResult(ok=True, external_id=external_id, per_recipient=per)


# Реестр реальных адаптеров по каналам (расширяется в PR-4…6).
_REAL_ADAPTERS: dict[str, Callable[[], ChannelAdapter]] = {
    "email": EmailAdapter,
}


def get_channel_adapter(channel: str) -> ChannelAdapter:
    """Возвращает реальный адаптер канала, если он доступен, иначе sandbox."""
    factory = _REAL_ADAPTERS.get(channel)
    if factory is not None:
        adapter = factory()
        if adapter.available():
            return adapter
    return SandboxAdapter()
