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


def _httpx_telegram_call(method: str, token: str, base: str, *, data: dict,
                         files: dict | None = None) -> dict:
    """Реальный вызов Telegram Bot API через httpx (используется по умолчанию)."""
    import httpx

    url = f"{base}/bot{token}/{method}"
    with httpx.Client(timeout=20) as client:
        resp = client.post(url, data=data, files=files)
    try:
        return resp.json()
    except Exception:  # noqa: BLE001
        return {"ok": False, "description": f"HTTP {resp.status_code}"}


class TelegramAdapter:
    """Отправка через официальный Telegram Bot API (sendMessage/sendDocument).

    HTTP-транспорт (`call`) внедряется для тестируемости; по умолчанию — httpx.
    Без токена `available()` = False, сетевые вызовы не выполняются. Адрес
    получателя — chat_id. Неофициальные способы не используются (CLAUDE.md §13).
    """

    channel = "telegram"
    is_real = True

    def __init__(self, call: Callable[..., dict] | None = None) -> None:
        self._call = call or _httpx_telegram_call

    def available(self) -> bool:
        return bool(get_settings().telegram_bot_token)

    def _api(self, method: str, *, data: dict, files: dict | None = None) -> dict:
        s = get_settings()
        return self._call(method, s.telegram_bot_token, s.telegram_api_base,
                          data=data, files=files)

    def send(self, *, subject, body, sender, recipients, attachments) -> SendResult:
        if not self.available():
            return SendResult(ok=False, error="Telegram-бот не настроен")
        text = "\n".join(p for p in (subject, body) if p) or "(без текста)"
        per: dict[str, str] = {}
        last_id: str | None = None
        for chat_id in recipients:
            r = self._api("sendMessage", data={"chat_id": chat_id, "text": text})
            if not r.get("ok"):
                return SendResult(ok=False, error=f"Telegram: {r.get('description')}")
            mid = str(r.get("result", {}).get("message_id", ""))
            for name, content, _mime in attachments:
                rd = self._api("sendDocument", data={"chat_id": chat_id},
                               files={"document": (name, content)})
                if not rd.get("ok"):
                    return SendResult(ok=False, error=f"Telegram(doc): {rd.get('description')}")
            per[chat_id] = f"tg:{mid}"
            last_id = f"tg:{mid}"
        return SendResult(ok=True, external_id=last_id, per_recipient=per)


def _httpx_whatsapp_call(url: str, token: str, *, json: dict | None = None,
                         data: dict | None = None, files: dict | None = None) -> dict:
    """Реальный вызов WhatsApp Graph API через httpx (по умолчанию)."""
    import httpx

    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=20) as client:
        resp = client.post(url, headers=headers, json=json, data=data, files=files)
    try:
        return resp.json()
    except Exception:  # noqa: BLE001
        return {"error": {"message": f"HTTP {resp.status_code}"}}


class WhatsAppAdapter:
    """Отправка через официальный WhatsApp Business Cloud API (Graph API).

    Поддерживает text и document (медиа загружается, затем отправляется по id) и
    шаблоны (`send_template`). HTTP-транспорт внедряется; без токена и
    phone_number_id `available()` = False (сетевые вызовы не выполняются).
    Требования канала (согласие получателя, шаблоны вне 24-часового окна) —
    учитываются согласием/стоп-листом в сервисе и утверждением шаблонов.
    """

    channel = "whatsapp"
    is_real = True
    api_version = "v20.0"

    def __init__(self, call: Callable[..., dict] | None = None) -> None:
        self._call = call or _httpx_whatsapp_call

    def available(self) -> bool:
        s = get_settings()
        return bool(s.whatsapp_token and s.whatsapp_phone_number_id)

    def _base(self) -> str:
        s = get_settings()
        return f"{s.whatsapp_api_base}/{self.api_version}/{s.whatsapp_phone_number_id}"

    def _token(self) -> str:
        return get_settings().whatsapp_token

    def _upload_media(self, name: str, content: bytes, mime: str | None) -> str | None:
        r = self._call(f"{self._base()}/media", self._token(),
                       data={"messaging_product": "whatsapp"},
                       files={"file": (name, content, mime or "application/octet-stream")})
        return r.get("id")

    def send(self, *, subject, body, sender, recipients, attachments) -> SendResult:
        if not self.available():
            return SendResult(ok=False, error="WhatsApp не настроен")
        text = "\n".join(p for p in (subject, body) if p) or "(без текста)"
        url = f"{self._base()}/messages"
        per: dict[str, str] = {}
        last: str | None = None
        for to in recipients:
            r = self._call(url, self._token(), json={
                "messaging_product": "whatsapp", "to": to, "type": "text",
                "text": {"body": text},
            })
            if "error" in r:
                return SendResult(ok=False, error=f"WhatsApp: {r['error'].get('message')}")
            mid = (r.get("messages") or [{}])[0].get("id", "")
            for name, content, mime in attachments:
                media_id = self._upload_media(name, content, mime)
                if media_id is None:
                    return SendResult(ok=False, error="WhatsApp: загрузка медиа не удалась")
                rd = self._call(url, self._token(), json={
                    "messaging_product": "whatsapp", "to": to, "type": "document",
                    "document": {"id": media_id, "filename": name},
                })
                if "error" in rd:
                    return SendResult(ok=False, error=f"WhatsApp(doc): {rd['error'].get('message')}")
            per[to] = f"wa:{mid}"
            last = f"wa:{mid}"
        return SendResult(ok=True, external_id=last, per_recipient=per)

    def send_template(self, *, to: str, name: str, language: str = "ru",
                      components: list | None = None) -> SendResult:
        """Отправка утверждённого шаблона (вне 24-часового окна — требование канала)."""
        if not self.available():
            return SendResult(ok=False, error="WhatsApp не настроен")
        payload = {
            "messaging_product": "whatsapp", "to": to, "type": "template",
            "template": {"name": name, "language": {"code": language}},
        }
        if components:
            payload["template"]["components"] = components
        r = self._call(f"{self._base()}/messages", self._token(), json=payload)
        if "error" in r:
            return SendResult(ok=False, error=f"WhatsApp(tpl): {r['error'].get('message')}")
        mid = (r.get("messages") or [{}])[0].get("id", "")
        return SendResult(ok=True, external_id=f"wa:{mid}", per_recipient={to: f"wa:{mid}"})


# Реестр реальных адаптеров по каналам (расширяется в PR-6).
_REAL_ADAPTERS: dict[str, Callable[[], ChannelAdapter]] = {
    "email": EmailAdapter,
    "telegram": TelegramAdapter,
    "whatsapp": WhatsAppAdapter,
}


def get_channel_adapter(channel: str) -> ChannelAdapter:
    """Возвращает реальный адаптер канала, если он доступен, иначе sandbox."""
    factory = _REAL_ADAPTERS.get(channel)
    if factory is not None:
        adapter = factory()
        if adapter.available():
            return adapter
    return SandboxAdapter()
