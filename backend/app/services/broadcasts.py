"""Рассылки (broadcasts) поверх центра коммуникаций (PR-7).

Рассылка формирует по одному `CommunicationMessage` на каждого контакта-получателя
(с `broadcast_id`) и управляет их жизненным циклом как группой: тестовая отправка,
предпросмотр, согласование, планирование, отправка, отчёт о доставке, повтор
только неуспешным.

Безопасность и требования каналов (CLAUDE.md §14):
- реальная отправка по умолчанию выключена (sandbox из центра коммуникаций);
- исключаются получатели без согласия, в стоп-листе и отписавшиеся;
- защита от спама: один контакт получает не более одного сообщения в рассылке;
- внешние каналы требуют согласования (SoD: согласующий ≠ автор);
- для внешнего канала с шаблоном требуется утверждённый шаблон (напр. WhatsApp).
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Broadcast,
    CommunicationContact,
    CommunicationMessage,
    MessageRecipient,
    MessageTemplate,
)
from app.models.communication import COMM_CHANNELS
from app.services import communications as comm
from app.services.audit import record_event


class BroadcastError(Exception):
    """Нарушение правил рассылки (канал, статус, согласование, получатели)."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _contact_address(contact: CommunicationContact, channel: str) -> str | None:
    return {
        "email": contact.email, "telegram": contact.telegram,
        "whatsapp": contact.whatsapp, "instagram": contact.instagram,
        "internal": f"user:{contact.id}",
    }.get(channel)


def _excluded(contact: CommunicationContact) -> str | None:
    if contact.unsubscribed:
        return "отписка"
    if contact.stop_listed:
        return "стоп-лист"
    if not contact.consent:
        return "нет согласия"
    return None


def create_broadcast(
    session: Session, organization_id: uuid.UUID, *, channel: str, title: str,
    subject: str | None = None, body_text: str | None = None,
    template_id: uuid.UUID | None = None, project_id: uuid.UUID | None = None,
    scheduled_at: datetime | None = None, author_user_id: uuid.UUID | None = None,
) -> Broadcast:
    if channel not in COMM_CHANNELS:
        raise BroadcastError(f"Недопустимый канал: {channel}")
    b = Broadcast(
        organization_id=organization_id, channel=channel, title=title,
        subject=subject, body_text=body_text, template_id=template_id,
        project_id=project_id, scheduled_at=scheduled_at, status="draft",
        author_user_id=author_user_id,
    )
    session.add(b)
    session.flush()
    record_event(session, actor_type="user", action="broadcast.create",
                 actor_user_id=author_user_id, organization_id=organization_id,
                 entity_type="broadcast", entity_id=b.id,
                 new_values={"channel": channel, "title": title}, risk_level="R1",
                 commit=True)
    return b


def add_targets(
    session: Session, broadcast: Broadcast, *, contact_ids: list[uuid.UUID],
) -> int:
    """Формирует по сообщению на контакт (без дублей). Возвращает число добавленных."""
    if broadcast.status not in ("draft", "pending_approval"):
        raise BroadcastError("Цели можно менять только до согласования/отправки")
    existing = {
        m.entity_id for m in session.execute(
            select(CommunicationMessage).where(
                CommunicationMessage.broadcast_id == broadcast.id
            )
        ).scalars()
    }
    added = 0
    for cid in contact_ids:
        contact = session.get(CommunicationContact, cid)
        if contact is None or contact.organization_id != broadcast.organization_id:
            continue
        if contact.id in existing:  # анти-спам: без дублей в рамках рассылки
            continue
        address = _contact_address(contact, broadcast.channel)
        if not address:
            continue
        msg = CommunicationMessage(
            organization_id=broadcast.organization_id, direction="out",
            channel=broadcast.channel, subject=broadcast.subject,
            body_text=broadcast.body_text, project_id=broadcast.project_id,
            author_user_id=broadcast.author_user_id, status="draft",
            broadcast_id=broadcast.id, entity_type="communication_contact",
            entity_id=contact.id,
        )
        session.add(msg)
        session.flush()
        session.add(MessageRecipient(message_id=msg.id, contact_id=contact.id,
                                     address=address, kind="to", status="pending"))
        existing.add(contact.id)
        added += 1
    broadcast.total_count = len(existing)
    session.flush()
    return added


def _messages(session: Session, broadcast: Broadcast) -> list[CommunicationMessage]:
    return list(session.execute(
        select(CommunicationMessage).where(
            CommunicationMessage.broadcast_id == broadcast.id
        )
    ).scalars())


def preview(session: Session, broadcast: Broadcast) -> dict:
    """Предпросмотр: тема/текст (из шаблона, если задан) и число получателей."""
    subject, body = broadcast.subject, broadcast.body_text
    if broadcast.template_id is not None:
        tpl = session.get(MessageTemplate, broadcast.template_id)
        if tpl is not None:
            subject = subject or tpl.subject
            body = body or tpl.body_text
    return {"subject": subject, "body": body, "recipients": broadcast.total_count}


def test_send(session: Session, broadcast: Broadcast, *, test_address: str,
              actor_user_id: uuid.UUID) -> CommunicationMessage:
    """Тестовая отправка одному адресу в sandbox (не затрагивает цели рассылки)."""
    pv = preview(session, broadcast)
    msg = comm.create_draft(session, broadcast.organization_id,
                            channel=broadcast.channel, subject=pv["subject"],
                            body_text=pv["body"], author_user_id=actor_user_id)
    comm.add_recipient(session, msg, address=test_address)
    broadcast.test_recipient = test_address
    # Тест всегда в sandbox: не требует согласования, external-канал — минуя гейт.
    if broadcast.channel != "internal":
        msg.status = "approved"
        msg.approved_by_user_id = actor_user_id
    comm.dispatch(session, msg, actor_user_id=actor_user_id)
    record_event(session, actor_type="user", action="broadcast.test_send",
                 actor_user_id=actor_user_id, organization_id=broadcast.organization_id,
                 entity_type="broadcast", entity_id=broadcast.id,
                 new_values={"test_recipient": test_address}, risk_level="R1", commit=True)
    return msg


def _requires_approval(channel: str) -> bool:
    return channel != "internal"


def submit_for_approval(session: Session, broadcast: Broadcast, *,
                        actor_user_id: uuid.UUID) -> Broadcast:
    if broadcast.status != "draft":
        raise BroadcastError("Отправить на согласование можно только черновик")
    if broadcast.total_count == 0:
        raise BroadcastError("Нет получателей")
    if _requires_approval(broadcast.channel) and broadcast.template_id is not None:
        tpl = session.get(MessageTemplate, broadcast.template_id)
        if tpl is None or not tpl.is_approved:
            raise BroadcastError("Шаблон внешнего канала должен быть утверждён")
    broadcast.status = "pending_approval"
    record_event(session, actor_type="user", action="broadcast.submit_approval",
                 actor_user_id=actor_user_id, organization_id=broadcast.organization_id,
                 entity_type="broadcast", entity_id=broadcast.id,
                 new_values={"status": "pending_approval"}, risk_level="R2", commit=True)
    return broadcast


def approve(session: Session, broadcast: Broadcast, *,
            approver_user_id: uuid.UUID) -> Broadcast:
    if broadcast.status != "pending_approval":
        raise BroadcastError("Согласовать можно только рассылку на согласовании")
    if _requires_approval(broadcast.channel) and approver_user_id == broadcast.author_user_id:
        raise BroadcastError("Согласующий не может совпадать с автором для внешнего канала")
    broadcast.status = "scheduled" if broadcast.scheduled_at else "approved"
    broadcast.approved_by_user_id = approver_user_id
    broadcast.approved_at = _now()
    record_event(session, actor_type="user", action="broadcast.approve",
                 actor_user_id=approver_user_id, organization_id=broadcast.organization_id,
                 entity_type="broadcast", entity_id=broadcast.id,
                 new_values={"status": broadcast.status}, risk_level="R2", commit=True)
    return broadcast


def cancel(session: Session, broadcast: Broadcast, *, actor_user_id: uuid.UUID,
           reason: str | None = None) -> Broadcast:
    if broadcast.status in ("sent", "sending"):
        raise BroadcastError("Нельзя отменить отправляемую/отправленную рассылку")
    broadcast.status = "cancelled"
    record_event(session, actor_type="user", action="broadcast.cancel",
                 actor_user_id=actor_user_id, organization_id=broadcast.organization_id,
                 entity_type="broadcast", entity_id=broadcast.id,
                 new_values={"status": "cancelled"}, reason=reason, risk_level="R2",
                 commit=True)
    return broadcast


def dispatch_broadcast(session: Session, broadcast: Broadcast, *,
                       actor_user_id: uuid.UUID) -> Broadcast:
    """Отправляет рассылку по всем получателям (sandbox по умолчанию)."""
    if _requires_approval(broadcast.channel) and broadcast.status not in ("approved", "scheduled"):
        raise BroadcastError("Внешняя рассылка требует согласования перед отправкой")
    if broadcast.status == "sent":
        raise BroadcastError("Рассылка уже отправлена")
    broadcast.status = "sending"
    sent = failed = 0
    for msg in _messages(session, broadcast):
        recipients = session.execute(
            select(MessageRecipient).where(MessageRecipient.message_id == msg.id)
        ).scalars().all()
        contact = session.get(CommunicationContact, msg.entity_id) if msg.entity_id else None
        reason = _excluded(contact) if contact else None
        if reason:
            for r in recipients:
                r.status = "skipped"
                r.error_reason = reason
            msg.status = "cancelled"
            msg.error_reason = reason
            failed += 1
            continue
        # Согласование группой: помечаем сообщение утверждённым перед отправкой.
        if _requires_approval(broadcast.channel):
            msg.status = "approved"
            msg.approved_by_user_id = broadcast.approved_by_user_id
        try:
            comm.dispatch(session, msg, actor_user_id=actor_user_id)
        except comm.CommunicationError:
            msg.status = "failed"
            failed += 1
            continue
        if msg.status == "sent":
            sent += 1
        else:
            failed += 1
    broadcast.sent_count = sent
    broadcast.failed_count = failed
    broadcast.status = "sent" if sent > 0 else "failed"
    record_event(session, actor_type="user", action="broadcast.sent",
                 actor_user_id=actor_user_id, organization_id=broadcast.organization_id,
                 entity_type="broadcast", entity_id=broadcast.id,
                 new_values={"status": broadcast.status, "sent": sent, "failed": failed},
                 risk_level="R2", commit=True)
    return broadcast


def retry_failed(session: Session, broadcast: Broadcast, *,
                 actor_user_id: uuid.UUID) -> Broadcast:
    """Повтор только неуспешным получателям рассылки (защита от дублей)."""
    failed_msgs = [m for m in _messages(session, broadcast) if m.status in ("failed", "cancelled")]
    if not failed_msgs:
        raise BroadcastError("Нет неуспешных получателей для повтора")
    retried = 0
    for msg in failed_msgs:
        contact = session.get(CommunicationContact, msg.entity_id) if msg.entity_id else None
        if contact and _excluded(contact):
            continue  # исключённых не повторяем
        # Сбрасываем получателей в pending и переотправляем.
        for r in session.execute(
            select(MessageRecipient).where(MessageRecipient.message_id == msg.id)
        ).scalars():
            r.status = "pending"
            r.error_reason = None
        msg.status = "approved" if _requires_approval(broadcast.channel) else "draft"
        msg.approved_by_user_id = broadcast.approved_by_user_id
        msg.error_reason = None
        try:
            comm.dispatch(session, msg, actor_user_id=actor_user_id)
            if msg.status == "sent":
                retried += 1
        except comm.CommunicationError:
            msg.status = "failed"
    report = delivery_report(session, broadcast)
    broadcast.sent_count = report["by_status"].get("sent", 0)
    broadcast.failed_count = broadcast.total_count - broadcast.sent_count
    if broadcast.sent_count > 0:
        broadcast.status = "sent"
    record_event(session, actor_type="user", action="broadcast.retry",
                 actor_user_id=actor_user_id, organization_id=broadcast.organization_id,
                 entity_type="broadcast", entity_id=broadcast.id,
                 new_values={"retried": retried}, risk_level="R2", commit=True)
    return broadcast


def delivery_report(session: Session, broadcast: Broadcast) -> dict:
    """Агрегированный отчёт о доставке по статусам сообщений рассылки."""
    msgs = _messages(session, broadcast)
    counts = Counter(m.status for m in msgs)
    return {
        "broadcast_id": str(broadcast.id),
        "total": broadcast.total_count,
        "sent": broadcast.sent_count,
        "failed": broadcast.failed_count,
        "by_status": dict(counts),
    }


def list_broadcasts(session: Session, organization_id: uuid.UUID) -> list[Broadcast]:
    return list(session.execute(
        select(Broadcast).where(
            Broadcast.organization_id == organization_id,
            Broadcast.deleted_at.is_(None),
        ).order_by(Broadcast.created_at.desc())
    ).scalars())
