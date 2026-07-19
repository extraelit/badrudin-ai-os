"""Бизнес-логика модуля «Масштабирование интеграций» — внутренний контур (§14).

Реестр коннекторов и очередь исходящих сообщений как черновиков на утверждение.
Модуль НИЧЕГО не отправляет и не хранит секретов: статусы отражают внутреннюю
подготовку и человеческое утверждение. Утверждённое сообщение переходит в статус
`approved` (готово к отправке уполномоченным человеком/коннектором вне модуля) —
фактическая отправка здесь не выполняется. Все действия — в `audit_events`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Approval,
    ApprovalStep,
    IntegrationConnector,
    OutboundMessage,
    User,
)
from app.services.access import accessible_project_ids, can_access_project
from app.services.audit import record_event

CHANNELS = ("email", "telegram", "whatsapp_business", "instagram", "webhook", "internal")


class IntegrationError(RuntimeError):
    """Нарушение правил внутреннего контура интеграций."""


# ------------------------------ Коннекторы ------------------------------- #


def register_connector(
    session: Session, *, organization_id: uuid.UUID, user: User, code: str, name: str,
    channel: str = "internal", provider: str | None = None,
    config_summary: str | None = None,
) -> IntegrationConnector:
    if channel not in CHANNELS:
        raise IntegrationError(f"недопустимый канал '{channel}'")
    existing = session.execute(
        select(IntegrationConnector).where(
            IntegrationConnector.organization_id == organization_id,
            IntegrationConnector.code == code,
            IntegrationConnector.deleted_at.is_(None),
        )
    ).scalars().first()
    if existing is not None:
        raise IntegrationError(f"коннектор с кодом '{code}' уже существует")
    connector = IntegrationConnector(
        organization_id=organization_id, code=code, name=name, channel=channel,
        provider=provider, config_summary=config_summary, status="draft",
        created_by=user.id,
    )
    session.add(connector)
    session.flush()
    _audit(session, user, "integration.connector_registered", organization_id,
           "integration_connector", connector.id, {"code": code, "channel": channel})
    session.commit()
    return connector


def set_connector_status(
    session: Session, connector: IntegrationConnector, *, user: User, status: str,
    credentials_configured_externally: bool | None = None,
) -> IntegrationConnector:
    if status not in ("draft", "configured", "disabled"):
        raise IntegrationError(f"недопустимый статус '{status}'")
    connector.status = status
    if credentials_configured_externally is not None:
        connector.credentials_configured_externally = credentials_configured_externally
    _audit(session, user, "integration.connector_status", connector.organization_id,
           "integration_connector", connector.id, {"status": status})
    session.commit()
    return connector


# ------------------------- Исходящие сообщения --------------------------- #


def create_outbound_draft(
    session: Session, *, organization_id: uuid.UUID, user: User, channel: str,
    subject: str | None = None, body_text: str | None = None,
    connector_id: uuid.UUID | None = None, recipient: str | None = None,
    project_id: uuid.UUID | None = None, counterparty_id: uuid.UUID | None = None,
    entity_type: str | None = None, entity_id: uuid.UUID | None = None,
) -> OutboundMessage:
    """Создаёт исходящее сообщение в статусе черновика (никогда не отправляется)."""
    if channel not in CHANNELS:
        raise IntegrationError(f"недопустимый канал '{channel}'")
    msg = OutboundMessage(
        organization_id=organization_id, connector_id=connector_id, channel=channel,
        project_id=project_id, counterparty_id=counterparty_id, recipient=recipient,
        subject=subject, body_text=body_text, entity_type=entity_type, entity_id=entity_id,
        status="draft", created_by=user.id,
    )
    session.add(msg)
    session.flush()
    _audit(session, user, "integration.outbound_drafted", organization_id,
           "outbound_message", msg.id, {"channel": channel})
    session.commit()
    return msg


def submit_outbound(session: Session, msg: OutboundMessage, *, user: User) -> Approval:
    """Отправляет черновик на утверждение (важная внешняя коммуникация, §14)."""
    if msg.status != "draft":
        raise IntegrationError(f"нельзя отправить на утверждение из '{msg.status}'")
    if not (msg.body_text or msg.subject):
        raise IntegrationError("пустое сообщение")
    approval = Approval(
        organization_id=msg.organization_id, entity_type="outbound_message",
        entity_id=msg.id, approval_type="outbound_message_approval",
        requested_by_user_id=user.id, status="pending", current_step=1,
    )
    session.add(approval)
    session.flush()
    msg.status = "pending_approval"
    msg.approval_id = approval.id
    _audit(session, user, "integration.outbound_submitted", msg.organization_id,
           "outbound_message", msg.id, {}, approval_id=approval.id)
    session.commit()
    return approval


def decide_outbound(
    session: Session, msg: OutboundMessage, *, user: User, decision: str,
    comment: str | None = None,
) -> OutboundMessage:
    """Утверждение/отклонение исходящего сообщения человеком.

    `approved` означает «готово к отправке уполномоченным человеком/коннектором» —
    фактическая отправка выполняется вне модуля. Отправку здесь не производим.
    """
    if decision not in ("approved", "rejected"):
        raise IntegrationError("решение — approved | rejected")
    if msg.status != "pending_approval":
        raise IntegrationError("сообщение не на утверждении")
    if msg.approval_id is not None:
        approval = session.get(Approval, msg.approval_id)
        approval.status = decision
        approval.completed_at = datetime.now(UTC)
        session.add(ApprovalStep(
            approval_id=approval.id, step_number=approval.current_step,
            approver_user_id=user.id, decision=decision, comment=comment,
            decided_at=datetime.now(UTC),
        ))
    if decision == "approved":
        msg.status = "approved"
        msg.approved_by_user_id = user.id
        msg.approved_at = datetime.now(UTC)
    else:
        msg.status = "cancelled"
        msg.rejection_reason = comment
    _audit(session, user, f"integration.outbound_{decision}", msg.organization_id,
           "outbound_message", msg.id, {"decision": decision},
           approval_id=msg.approval_id)
    session.commit()
    return msg


def cancel_outbound(session: Session, msg: OutboundMessage, *, user: User, reason: str) -> OutboundMessage:
    if msg.status in ("approved", "cancelled"):
        raise IntegrationError("сообщение уже обработано")
    msg.status = "cancelled"
    msg.rejection_reason = reason
    _audit(session, user, "integration.outbound_cancelled", msg.organization_id,
           "outbound_message", msg.id, {"reason": reason})
    session.commit()
    return msg


# ------------------------------ Чтение ----------------------------------- #


def list_connectors(session: Session, organization_id: uuid.UUID) -> list[IntegrationConnector]:
    return list(session.execute(
        select(IntegrationConnector).where(
            IntegrationConnector.organization_id == organization_id,
            IntegrationConnector.deleted_at.is_(None),
        ).order_by(IntegrationConnector.created_at.desc())
    ).scalars())


def list_outbound(
    session: Session, user: User, organization_id: uuid.UUID, *, status: str | None = None,
) -> list[OutboundMessage]:
    allowed = accessible_project_ids(session, user)
    stmt = select(OutboundMessage).where(
        OutboundMessage.organization_id == organization_id,
        OutboundMessage.deleted_at.is_(None),
    )
    if status is not None:
        stmt = stmt.where(OutboundMessage.status == status)
    rows = list(session.execute(stmt.order_by(OutboundMessage.created_at.desc())).scalars())
    if allowed is None:
        return rows
    return [m for m in rows if m.project_id is None or m.project_id in allowed]


def can_access_outbound(session: Session, user: User, msg: OutboundMessage) -> bool:
    if msg.project_id is None:
        return True
    return can_access_project(session, user, msg.project_id)


def summary(session: Session, user: User, organization_id: uuid.UUID) -> dict:
    connectors = list_connectors(session, organization_id)
    msgs = list_outbound(session, user, organization_id)
    return {
        "connectors_total": len(connectors),
        "connectors_configured": sum(1 for c in connectors if c.status == "configured"),
        "outbound_draft": sum(1 for m in msgs if m.status == "draft"),
        "outbound_pending": sum(1 for m in msgs if m.status == "pending_approval"),
        "outbound_approved": sum(1 for m in msgs if m.status == "approved"),
    }


def _audit(session, user, action, org_id, entity_type, entity_id, new_values, *, approval_id=None):
    record_event(
        session, actor_type="user", action=action, actor_user_id=user.id,
        organization_id=org_id, entity_type=entity_type, entity_id=entity_id,
        new_values=new_values, approval_id=approval_id, risk_level="R2", commit=False,
    )
