"""Сервис центра коммуникаций (PR-2).

Единый жизненный цикл сообщений (черновик → согласование → планирование →
отправка → доставка) с журналом доставки. Реальная отправка по умолчанию
выключена: до подключения ключей используется безопасный **sandbox**, который
не делает внешних вызовов, а лишь фиксирует состояния и события доставки.

Инварианты безопасности:
- внешние каналы требуют согласования (SoD: согласующий ≠ автор);
- стоп-лист и отсутствие согласия исключают получателя из отправки;
- каждое действие и событие доставки пишется в аудит/журнал;
- функции адаптеров каналов подключаются в PR-3…6; здесь — только sandbox.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    CommunicationContact,
    CommunicationMessage,
    MessageDeliveryEvent,
    MessageRecipient,
    MessageTemplate,
)
from app.models.communication import (
    COMM_CHANNELS,
    MESSAGE_DIRECTIONS,
)
from app.services.audit import record_event


class CommunicationError(Exception):
    """Нарушение правил центра коммуникаций (канал, статус, согласование)."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(session, message, action, actor, *, new=None, reason=None, risk="R1"):
    record_event(
        session, actor_type="user", action=action, actor_user_id=actor,
        organization_id=message.organization_id, entity_type="message",
        entity_id=message.id, new_values=new, reason=reason, risk_level=risk,
        commit=True,
    )


def _event(session, message, event, *, recipient=None, detail=None, external_id=None):
    session.add(MessageDeliveryEvent(
        message_id=message.id,
        recipient_id=recipient.id if recipient else None,
        event=event, detail=detail, external_id=external_id, occurred_at=_now(),
    ))


# --------------------------- Контакты и шаблоны -------------------------- #

def create_contact(
    session: Session, organization_id: uuid.UUID, *, display_name: str,
    email: str | None = None, phone: str | None = None, telegram: str | None = None,
    whatsapp: str | None = None, instagram: str | None = None,
    counterparty_id: uuid.UUID | None = None, project_id: uuid.UUID | None = None,
    consent: bool = False, actor_user_id: uuid.UUID | None = None,
) -> CommunicationContact:
    c = CommunicationContact(
        organization_id=organization_id, display_name=display_name, email=email,
        phone=phone, telegram=telegram, whatsapp=whatsapp, instagram=instagram,
        counterparty_id=counterparty_id, project_id=project_id, consent=consent,
    )
    session.add(c)
    session.flush()
    record_event(session, actor_type="user", action="communication.contact.create",
                 actor_user_id=actor_user_id, organization_id=organization_id,
                 entity_type="communication_contact", entity_id=c.id,
                 new_values={"display_name": display_name}, risk_level="R1", commit=True)
    return c


def set_stop_list(session: Session, contact: CommunicationContact, *, stop_listed: bool,
                  actor_user_id: uuid.UUID | None = None) -> CommunicationContact:
    contact.stop_listed = stop_listed
    record_event(session, actor_type="user", action="communication.contact.stoplist",
                 actor_user_id=actor_user_id, organization_id=contact.organization_id,
                 entity_type="communication_contact", entity_id=contact.id,
                 new_values={"stop_listed": stop_listed}, risk_level="R1", commit=True)
    return contact


def set_unsubscribed(session: Session, contact: CommunicationContact, *,
                     unsubscribed: bool, actor_user_id: uuid.UUID | None = None
                     ) -> CommunicationContact:
    """Отписка/переподписка контакта (исключает из рассылок)."""
    contact.unsubscribed = unsubscribed
    record_event(session, actor_type="user", action="communication.contact.unsubscribe",
                 actor_user_id=actor_user_id, organization_id=contact.organization_id,
                 entity_type="communication_contact", entity_id=contact.id,
                 new_values={"unsubscribed": unsubscribed}, risk_level="R1", commit=True)
    return contact


def create_template(
    session: Session, organization_id: uuid.UUID, *, code: str, name: str,
    channel: str, body_text: str, subject: str | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> MessageTemplate:
    if channel not in COMM_CHANNELS:
        raise CommunicationError(f"Недопустимый канал: {channel}")
    t = MessageTemplate(organization_id=organization_id, code=code, name=name,
                        channel=channel, subject=subject, body_text=body_text)
    session.add(t)
    session.flush()
    record_event(session, actor_type="user", action="communication.template.create",
                 actor_user_id=actor_user_id, organization_id=organization_id,
                 entity_type="message_template", entity_id=t.id,
                 new_values={"code": code, "channel": channel}, risk_level="R1", commit=True)
    return t


def approve_template(session: Session, template: MessageTemplate, *,
                     actor_user_id: uuid.UUID) -> MessageTemplate:
    template.is_approved = True
    template.approved_by = actor_user_id
    record_event(session, actor_type="user", action="communication.template.approve",
                 actor_user_id=actor_user_id, organization_id=template.organization_id,
                 entity_type="message_template", entity_id=template.id,
                 new_values={"is_approved": True}, risk_level="R2", commit=True)
    return template


# ------------------------------ Сообщения -------------------------------- #

def _requires_approval(channel: str) -> bool:
    """Внешние каналы требуют согласования; внутренние — нет."""
    return channel != "internal"


def create_draft(
    session: Session, organization_id: uuid.UUID, *, channel: str,
    subject: str | None = None, body_text: str | None = None,
    author_user_id: uuid.UUID | None = None, responsible_user_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None, template_id: uuid.UUID | None = None,
    connector_id: uuid.UUID | None = None, scheduled_at: datetime | None = None,
    entity_type: str | None = None, entity_id: uuid.UUID | None = None,
    direction: str = "out",
) -> CommunicationMessage:
    if channel not in COMM_CHANNELS:
        raise CommunicationError(f"Недопустимый канал: {channel}")
    if direction not in MESSAGE_DIRECTIONS:
        raise CommunicationError(f"Недопустимое направление: {direction}")
    msg = CommunicationMessage(
        organization_id=organization_id, direction=direction, channel=channel,
        connector_id=connector_id, template_id=template_id, project_id=project_id,
        subject=subject, body_text=body_text, author_user_id=author_user_id,
        responsible_user_id=responsible_user_id, scheduled_at=scheduled_at,
        status="draft", entity_type=entity_type, entity_id=entity_id,
    )
    session.add(msg)
    session.flush()
    _audit(session, msg, "communication.message.create", author_user_id,
           new={"channel": channel, "direction": direction})
    return msg


def add_recipient(
    session: Session, message: CommunicationMessage, *, address: str,
    contact_id: uuid.UUID | None = None, kind: str = "to",
) -> MessageRecipient:
    if message.status not in ("draft", "pending_approval"):
        raise CommunicationError("Получателей можно менять только до согласования/отправки")
    r = MessageRecipient(message_id=message.id, contact_id=contact_id,
                         address=address, kind=kind, status="pending")
    session.add(r)
    session.flush()
    return r


def _recipients(session: Session, message: CommunicationMessage) -> list[MessageRecipient]:
    return list(session.execute(
        select(MessageRecipient).where(MessageRecipient.message_id == message.id)
    ).scalars())


def submit_for_approval(session: Session, message: CommunicationMessage, *,
                        actor_user_id: uuid.UUID) -> CommunicationMessage:
    if message.status != "draft":
        raise CommunicationError("Отправить на согласование можно только черновик")
    if not _recipients(session, message):
        raise CommunicationError("Нет получателей")
    message.status = "pending_approval"
    _audit(session, message, "communication.message.submit_approval", actor_user_id,
           new={"status": "pending_approval"}, risk="R2")
    return message


def approve(session: Session, message: CommunicationMessage, *,
            approver_user_id: uuid.UUID) -> CommunicationMessage:
    if message.status != "pending_approval":
        raise CommunicationError("Согласовать можно только сообщение на согласовании")
    # SoD: внешнюю коммуникацию согласует не автор (независимость, CLAUDE.md §14).
    if _requires_approval(message.channel) and approver_user_id == message.author_user_id:
        raise CommunicationError("Согласующий не может совпадать с автором для внешнего канала")
    message.status = "scheduled" if message.scheduled_at else "approved"
    message.approved_by_user_id = approver_user_id
    message.approved_at = _now()
    _audit(session, message, "communication.message.approve", approver_user_id,
           new={"status": message.status}, risk="R2")
    return message


def cancel(session: Session, message: CommunicationMessage, *, actor_user_id: uuid.UUID,
           reason: str | None = None) -> CommunicationMessage:
    if message.status in ("sent", "delivered", "read"):
        raise CommunicationError("Отправленное сообщение нельзя отменить")
    message.status = "cancelled"
    _audit(session, message, "communication.message.cancel", actor_user_id,
           new={"status": "cancelled"}, reason=reason, risk="R2")
    return message


def _message_attachments(session: Session, message: CommunicationMessage):
    """Вложения сообщения (name, bytes, mime) через универсальный сервис (PR-1)."""
    from app.services import attachments as att_svc

    out = []
    for a in att_svc.list_for(session, "message", message.id):
        data, _url, file = att_svc.download(session, a)
        if data is not None:
            out.append((file.original_name, data, file.mime_type))
    return out


def dispatch(
    session: Session, message: CommunicationMessage, *, actor_user_id: uuid.UUID,
    allow_real_send: bool = False,
) -> CommunicationMessage:
    """Отправляет сообщение через адаптер канала (PR-3).

    Режим определяется рубильником `settings.comm_real_send` и готовностью
    адаптера канала (наличием ключей). Если реальная отправка недоступна —
    работает безопасный sandbox (без внешних вызовов), `external_id`=`sandbox:*`.
    `allow_real_send=True` при недоступном реальном адаптере явно блокируется.
    """
    from app.core.config import get_settings
    from app.services.channel_adapters import SandboxAdapter, get_channel_adapter

    if _requires_approval(message.channel) and message.status not in ("approved", "scheduled"):
        raise CommunicationError("Внешнее сообщение требует согласования перед отправкой")
    if message.status in ("sent", "delivered", "read"):
        raise CommunicationError("Сообщение уже отправлено")

    adapter = get_channel_adapter(message.channel)
    real_mode = get_settings().comm_real_send and adapter.is_real and adapter.available()
    if allow_real_send and not real_mode:
        raise CommunicationError("Реальная отправка недоступна: нет адаптера/ключей канала")

    recipients = _recipients(session, message)
    if not recipients:
        raise CommunicationError("Нет получателей")

    message.status = "sending"
    message.attempts += 1
    mode = "real" if real_mode else "sandbox"
    _event(session, message, "sending", detail=mode)

    # Фильтрация по согласию/стоп-листу — до фактической отправки.
    targets = []
    for r in recipients:
        contact = session.get(CommunicationContact, r.contact_id) if r.contact_id else None
        if contact is not None and (contact.stop_listed or not contact.consent):
            r.status = "skipped"
            r.error_reason = "стоп-лист или нет согласия"
            _event(session, message, "skipped", recipient=r, detail=r.error_reason)
            continue
        targets.append(r)

    if not targets:
        message.status = "failed"
        message.error_reason = "все получатели исключены (стоп-лист/нет согласия)"
        _audit(session, message, "communication.message.failed", actor_user_id,
               new={"status": "failed"}, risk="R2")
        return message

    send_adapter = adapter if real_mode else SandboxAdapter()
    attachments = _message_attachments(session, message) if real_mode else []
    result = send_adapter.send(
        subject=message.subject, body=message.body_text, sender=None,
        recipients=[t.address for t in targets], attachments=attachments,
    )

    if not result.ok:
        for t in targets:
            t.status = "failed"
            t.error_reason = result.error
            _event(session, message, "failed", recipient=t, detail=result.error)
        message.status = "failed"
        message.error_reason = result.error
        _audit(session, message, "communication.message.failed", actor_user_id,
               new={"status": "failed", "mode": mode}, reason=result.error, risk="R2")
        return message

    for t in targets:
        ext = result.per_recipient.get(t.address, result.external_id)
        t.status = "sent"
        t.external_id = ext
        _event(session, message, "sent", recipient=t, external_id=ext, detail=mode)

    message.status = "sent"
    message.sent_at = _now()
    message.external_id = result.external_id
    _audit(session, message, "communication.message.sent", actor_user_id,
           new={"status": "sent", "recipients_sent": len(targets), "mode": mode}, risk="R2")
    return message


def dispatch_idempotent(session: Session, message: CommunicationMessage, *,
                        actor_user_id: uuid.UUID) -> CommunicationMessage:
    """Идемпотентная отправка (PR-9): повтор уже отправленного — без дублей.

    Пригодно для фоновой задачи/очереди: если сообщение уже sent/delivered/read,
    возвращает его без повторной отправки (защита от двойного проведения).
    """
    if message.status in ("sent", "delivered", "read"):
        return message
    return dispatch(session, message, actor_user_id=actor_user_id)


def retry_failed(session: Session, message: CommunicationMessage, *,
                 actor_user_id: uuid.UUID) -> CommunicationMessage:
    """Повторная отправка только неуспешным получателям (защита от дублей)."""
    if message.status not in ("failed", "sent"):
        raise CommunicationError("Повтор возможен для отправленного/неуспешного сообщения")
    failed = [r for r in _recipients(session, message) if r.status in ("failed", "pending")]
    if not failed:
        raise CommunicationError("Нет неуспешных получателей для повтора")
    message.attempts += 1
    for r in failed:
        ext = f"sandbox:{uuid.uuid4().hex[:16]}"
        r.status = "sent"
        r.external_id = ext
        r.error_reason = None
        _event(session, message, "sent", recipient=r, external_id=ext, detail="retry/sandbox")
    if message.status == "failed":
        message.status = "sent"
        message.sent_at = _now()
    _audit(session, message, "communication.message.retry", actor_user_id,
           new={"retried": len(failed)}, risk="R2")
    return message


def mark_delivery(session: Session, message: CommunicationMessage, *, event: str,
                  recipient_id: uuid.UUID | None = None, external_id: str | None = None,
                  detail: str | None = None) -> None:
    """Регистрирует событие доставки (delivered/read/failed) — напр. из webhook."""
    recipient = session.get(MessageRecipient, recipient_id) if recipient_id else None
    if recipient is not None:
        if event == "delivered":
            recipient.status = "delivered"
            recipient.delivered_at = _now()
        elif event == "read":
            recipient.status = "read"
            recipient.read_at = _now()
        elif event == "failed":
            recipient.status = "failed"
            recipient.error_reason = detail
    _event(session, message, event, recipient=recipient, detail=detail, external_id=external_id)
    # Итоговый статус сообщения подтягиваем по «максимальному» прогрессу.
    order = {"sent": 1, "delivered": 2, "read": 3}
    if event in order and order[event] > order.get(message.status, 0):
        message.status = event
    session.flush()


def record_incoming(
    session: Session, organization_id: uuid.UUID, *, channel: str, address_from: str,
    subject: str | None = None, body_text: str | None = None,
    external_id: str | None = None, project_id: uuid.UUID | None = None,
) -> CommunicationMessage:
    """Регистрирует входящее сообщение (для webhooks каналов, PR-4…6)."""
    if channel not in COMM_CHANNELS:
        raise CommunicationError(f"Недопустимый канал: {channel}")
    msg = CommunicationMessage(
        organization_id=organization_id, direction="in", channel=channel,
        subject=subject, body_text=body_text, status="delivered",
        external_id=external_id, project_id=project_id,
    )
    session.add(msg)
    session.flush()
    session.add(MessageRecipient(message_id=msg.id, address=address_from, kind="to",
                                 status="delivered"))
    _event(session, msg, "delivered", detail=f"incoming/{channel}", external_id=external_id)
    record_event(session, actor_type="system", action="communication.message.incoming",
                 organization_id=organization_id, entity_type="message", entity_id=msg.id,
                 new_values={"channel": channel, "external_id": external_id},
                 risk_level="R1", commit=True)
    return msg


# ------------------------------- Выборки --------------------------------- #

def list_messages(
    session: Session, organization_id: uuid.UUID, *, direction: str | None = None,
    statuses: Iterable[str] | None = None, drafts: bool = False,
) -> list[CommunicationMessage]:
    stmt = select(CommunicationMessage).where(
        CommunicationMessage.organization_id == organization_id,
        CommunicationMessage.deleted_at.is_(None),
    )
    if direction:
        stmt = stmt.where(CommunicationMessage.direction == direction)
    if drafts:
        stmt = stmt.where(CommunicationMessage.status.in_(("draft", "pending_approval")))
    if statuses:
        stmt = stmt.where(CommunicationMessage.status.in_(tuple(statuses)))
    return list(session.execute(
        stmt.order_by(CommunicationMessage.created_at.desc())
    ).scalars())


def delivery_log(session: Session, message: CommunicationMessage) -> list[MessageDeliveryEvent]:
    return list(session.execute(
        select(MessageDeliveryEvent)
        .where(MessageDeliveryEvent.message_id == message.id)
        .order_by(MessageDeliveryEvent.occurred_at)
    ).scalars())


def list_contacts(session: Session, organization_id: uuid.UUID) -> list[CommunicationContact]:
    return list(session.execute(
        select(CommunicationContact).where(
            CommunicationContact.organization_id == organization_id,
            CommunicationContact.deleted_at.is_(None),
        ).order_by(CommunicationContact.display_name)
    ).scalars())


def list_templates(session: Session, organization_id: uuid.UUID) -> list[MessageTemplate]:
    return list(session.execute(
        select(MessageTemplate).where(
            MessageTemplate.organization_id == organization_id,
            MessageTemplate.deleted_at.is_(None),
        ).order_by(MessageTemplate.name)
    ).scalars())
