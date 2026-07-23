"""API центра коммуникаций `/communications` (PR-2).

Вкладки раздела «Коммуникации»: Входящие, Исходящие, Черновики, Шаблоны,
Контакты, Каналы, Журнал доставки. Backend — единственная точка доступа; RBAC:
`communication.view` (чтение), `communication.manage` (черновики/контакты/шаблоны),
`communication.approve` (согласование), `communication.send` (отправка/повтор).
ABAC — по проекту сообщения/контакта; tenant isolation — по организации.
Реальная отправка выключена: отправка идёт в безопасный sandbox.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.session import get_db
from app.models import (
    CommunicationContact,
    CommunicationMessage,
    Employee,
    IntegrationConnector,
    MessageTemplate,
    User,
)
from app.models.communication import COMM_CHANNELS
from app.schemas.communication import (
    CancelIn,
    ChannelOut,
    ContactIn,
    ContactOut,
    DeliveryEventOut,
    MessageDetailOut,
    MessageIn,
    MessageOut,
    RecipientIn,
    RecipientOut,
    StopListIn,
    TemplateIn,
    TemplateOut,
)
from app.services import communications as svc
from app.services.access import can_access_project

router = APIRouter(prefix="/communications", tags=["communications"])


def _org(db: Session, user: User) -> uuid.UUID:
    if user.employee_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пользователь не связан с сотрудником")
    emp = db.get(Employee, user.employee_id)
    return emp.organization_id


def _check_project(db: Session, user: User, project_id: uuid.UUID | None) -> None:
    if project_id is not None and not can_access_project(db, user, project_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к проекту")


def _guard(exc: svc.CommunicationError) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


def _msg_out(m: CommunicationMessage) -> MessageOut:
    return MessageOut(
        id=m.id, direction=m.direction, channel=m.channel, subject=m.subject,
        body_text=m.body_text, project_id=m.project_id, status=m.status,
        external_id=m.external_id, error_reason=m.error_reason, attempts=m.attempts,
        scheduled_at=m.scheduled_at, sent_at=m.sent_at,
        responsible_user_id=m.responsible_user_id, author_user_id=m.author_user_id,
        created_at=m.created_at,
    )


def _rcpt_out(r) -> RecipientOut:
    return RecipientOut(id=r.id, address=r.address, kind=r.kind, status=r.status,
                        external_id=r.external_id, error_reason=r.error_reason)


def _message(db: Session, user: User, mid: uuid.UUID) -> CommunicationMessage:
    m = db.get(CommunicationMessage, mid)
    if m is None or m.deleted_at is not None or m.organization_id != _org(db, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сообщение не найдено")
    _check_project(db, user, m.project_id)
    return m


def _visible(db: Session, user: User, rows: list[CommunicationMessage]) -> list[MessageOut]:
    out: list[MessageOut] = []
    for m in rows:
        if m.project_id is not None and not can_access_project(db, user, m.project_id):
            continue
        out.append(_msg_out(m))
    return out


# ------------------------------- Вкладки --------------------------------- #

@router.get("/inbox", response_model=list[MessageOut])
def inbox(current: User = Depends(require_permission("communication.view")),
          db: Session = Depends(get_db)) -> list[MessageOut]:
    return _visible(db, current, svc.list_messages(db, _org(db, current), direction="in"))


@router.get("/outbox", response_model=list[MessageOut])
def outbox(current: User = Depends(require_permission("communication.view")),
           db: Session = Depends(get_db)) -> list[MessageOut]:
    rows = [m for m in svc.list_messages(db, _org(db, current), direction="out")
            if m.status not in ("draft", "pending_approval")]
    return _visible(db, current, rows)


@router.get("/drafts", response_model=list[MessageOut])
def drafts(current: User = Depends(require_permission("communication.view")),
           db: Session = Depends(get_db)) -> list[MessageOut]:
    return _visible(db, current, svc.list_messages(db, _org(db, current), drafts=True))


@router.get("/channels", response_model=list[ChannelOut])
def channels(current: User = Depends(require_permission("communication.view")),
             db: Session = Depends(get_db)) -> list[ChannelOut]:
    org = _org(db, current)
    rows = db.execute(
        select(IntegrationConnector).where(
            IntegrationConnector.organization_id == org,
            IntegrationConnector.deleted_at.is_(None),
            IntegrationConnector.channel.in_(COMM_CHANNELS),
        )
    ).scalars()
    return [ChannelOut(id=c.id, code=c.code, name=c.name, channel=c.channel,
                       provider=c.provider, status=c.status,
                       credentials_configured_externally=c.credentials_configured_externally)
            for c in rows]


@router.get("/templates", response_model=list[TemplateOut])
def templates(current: User = Depends(require_permission("communication.view")),
              db: Session = Depends(get_db)) -> list[TemplateOut]:
    return [TemplateOut(id=t.id, code=t.code, name=t.name, channel=t.channel,
                        subject=t.subject, body_text=t.body_text, is_approved=t.is_approved)
            for t in svc.list_templates(db, _org(db, current))]


@router.get("/contacts", response_model=list[ContactOut])
def contacts(current: User = Depends(require_permission("communication.view")),
             db: Session = Depends(get_db)) -> list[ContactOut]:
    org = _org(db, current)
    out: list[ContactOut] = []
    for c in svc.list_contacts(db, org):
        if c.project_id is not None and not can_access_project(db, current, c.project_id):
            continue
        out.append(ContactOut(id=c.id, display_name=c.display_name, email=c.email,
                              phone=c.phone, telegram=c.telegram, whatsapp=c.whatsapp,
                              instagram=c.instagram, project_id=c.project_id,
                              consent=c.consent, stop_listed=c.stop_listed))
    return out


# --------------------------- Сообщение: детали --------------------------- #

@router.get("/messages/{message_id}", response_model=MessageDetailOut)
def get_message(message_id: uuid.UUID,
                current: User = Depends(require_permission("communication.view")),
                db: Session = Depends(get_db)) -> MessageDetailOut:
    m = _message(db, current, message_id)
    base = _msg_out(m).model_dump()
    return MessageDetailOut(**base,
                            recipients=[_rcpt_out(r) for r in svc._recipients(db, m)])


@router.get("/messages/{message_id}/delivery-log", response_model=list[DeliveryEventOut])
def get_delivery_log(message_id: uuid.UUID,
                     current: User = Depends(require_permission("communication.view")),
                     db: Session = Depends(get_db)) -> list[DeliveryEventOut]:
    m = _message(db, current, message_id)
    return [DeliveryEventOut(id=e.id, event=e.event, detail=e.detail,
                             external_id=e.external_id, recipient_id=e.recipient_id,
                             occurred_at=e.occurred_at) for e in svc.delivery_log(db, m)]


# --------------------------- Жизненный цикл ------------------------------ #

@router.post("/messages", response_model=MessageDetailOut, status_code=status.HTTP_201_CREATED)
def create_message(payload: MessageIn,
                   current: User = Depends(require_permission("communication.manage")),
                   db: Session = Depends(get_db)) -> MessageDetailOut:
    _check_project(db, current, payload.project_id)
    try:
        m = svc.create_draft(
            db, _org(db, current), channel=payload.channel, subject=payload.subject,
            body_text=payload.body_text, author_user_id=current.id,
            responsible_user_id=payload.responsible_user_id, project_id=payload.project_id,
            template_id=payload.template_id, connector_id=payload.connector_id,
            scheduled_at=payload.scheduled_at, entity_type=payload.entity_type,
            entity_id=payload.entity_id,
        )
        for r in payload.recipients:
            svc.add_recipient(db, m, address=r.address, contact_id=r.contact_id, kind=r.kind)
        db.commit()
    except svc.CommunicationError as exc:
        raise _guard(exc) from exc
    base = _msg_out(m).model_dump()
    return MessageDetailOut(**base, recipients=[_rcpt_out(r) for r in svc._recipients(db, m)])


@router.post("/messages/{message_id}/recipients", response_model=RecipientOut,
             status_code=status.HTTP_201_CREATED)
def add_recipient(message_id: uuid.UUID, payload: RecipientIn,
                  current: User = Depends(require_permission("communication.manage")),
                  db: Session = Depends(get_db)) -> RecipientOut:
    m = _message(db, current, message_id)
    try:
        r = svc.add_recipient(db, m, address=payload.address, contact_id=payload.contact_id,
                              kind=payload.kind)
        db.commit()
    except svc.CommunicationError as exc:
        raise _guard(exc) from exc
    return _rcpt_out(r)


@router.post("/messages/{message_id}/submit-approval", response_model=MessageOut)
def submit_approval(message_id: uuid.UUID,
                    current: User = Depends(require_permission("communication.manage")),
                    db: Session = Depends(get_db)) -> MessageOut:
    m = _message(db, current, message_id)
    try:
        svc.submit_for_approval(db, m, actor_user_id=current.id)
    except svc.CommunicationError as exc:
        raise _guard(exc) from exc
    return _msg_out(m)


@router.post("/messages/{message_id}/approve", response_model=MessageOut)
def approve_message(message_id: uuid.UUID,
                    current: User = Depends(require_permission("communication.approve")),
                    db: Session = Depends(get_db)) -> MessageOut:
    m = _message(db, current, message_id)
    try:
        svc.approve(db, m, approver_user_id=current.id)
    except svc.CommunicationError as exc:
        raise _guard(exc) from exc
    return _msg_out(m)


@router.post("/messages/{message_id}/cancel", response_model=MessageOut)
def cancel_message(message_id: uuid.UUID, payload: CancelIn,
                   current: User = Depends(require_permission("communication.manage")),
                   db: Session = Depends(get_db)) -> MessageOut:
    m = _message(db, current, message_id)
    try:
        svc.cancel(db, m, actor_user_id=current.id, reason=payload.reason)
    except svc.CommunicationError as exc:
        raise _guard(exc) from exc
    return _msg_out(m)


@router.post("/messages/{message_id}/send", response_model=MessageOut)
def send_message(message_id: uuid.UUID,
                 current: User = Depends(require_permission("communication.send")),
                 db: Session = Depends(get_db)) -> MessageOut:
    m = _message(db, current, message_id)
    try:
        svc.dispatch(db, m, actor_user_id=current.id)  # sandbox по умолчанию
    except svc.CommunicationError as exc:
        raise _guard(exc) from exc
    return _msg_out(m)


@router.post("/messages/{message_id}/retry", response_model=MessageOut)
def retry_message(message_id: uuid.UUID,
                  current: User = Depends(require_permission("communication.send")),
                  db: Session = Depends(get_db)) -> MessageOut:
    m = _message(db, current, message_id)
    try:
        svc.retry_failed(db, m, actor_user_id=current.id)
    except svc.CommunicationError as exc:
        raise _guard(exc) from exc
    return _msg_out(m)


# ------------------------- Контакты и шаблоны ---------------------------- #

@router.post("/contacts", response_model=ContactOut, status_code=status.HTTP_201_CREATED)
def create_contact(payload: ContactIn,
                   current: User = Depends(require_permission("communication.manage")),
                   db: Session = Depends(get_db)) -> ContactOut:
    _check_project(db, current, payload.project_id)
    c = svc.create_contact(db, _org(db, current), display_name=payload.display_name,
                           email=payload.email, phone=payload.phone, telegram=payload.telegram,
                           whatsapp=payload.whatsapp, instagram=payload.instagram,
                           counterparty_id=payload.counterparty_id, project_id=payload.project_id,
                           consent=payload.consent, actor_user_id=current.id)
    return ContactOut(id=c.id, display_name=c.display_name, email=c.email, phone=c.phone,
                      telegram=c.telegram, whatsapp=c.whatsapp, instagram=c.instagram,
                      project_id=c.project_id, consent=c.consent, stop_listed=c.stop_listed)


@router.post("/contacts/{contact_id}/stop-list", response_model=ContactOut)
def stop_list(contact_id: uuid.UUID, payload: StopListIn,
              current: User = Depends(require_permission("communication.manage")),
              db: Session = Depends(get_db)) -> ContactOut:
    c = db.get(CommunicationContact, contact_id)
    if c is None or c.deleted_at is not None or c.organization_id != _org(db, current):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Контакт не найден")
    svc.set_stop_list(db, c, stop_listed=payload.stop_listed, actor_user_id=current.id)
    return ContactOut(id=c.id, display_name=c.display_name, email=c.email, phone=c.phone,
                      telegram=c.telegram, whatsapp=c.whatsapp, instagram=c.instagram,
                      project_id=c.project_id, consent=c.consent, stop_listed=c.stop_listed)


@router.post("/templates", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
def create_template(payload: TemplateIn,
                    current: User = Depends(require_permission("communication.manage")),
                    db: Session = Depends(get_db)) -> TemplateOut:
    try:
        t = svc.create_template(db, _org(db, current), code=payload.code, name=payload.name,
                                channel=payload.channel, body_text=payload.body_text,
                                subject=payload.subject, actor_user_id=current.id)
    except svc.CommunicationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return TemplateOut(id=t.id, code=t.code, name=t.name, channel=t.channel,
                       subject=t.subject, body_text=t.body_text, is_approved=t.is_approved)


@router.post("/templates/{template_id}/approve", response_model=TemplateOut)
def approve_template(template_id: uuid.UUID,
                     current: User = Depends(require_permission("communication.approve")),
                     db: Session = Depends(get_db)) -> TemplateOut:
    t = db.get(MessageTemplate, template_id)
    if t is None or t.deleted_at is not None or t.organization_id != _org(db, current):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Шаблон не найден")
    svc.approve_template(db, t, actor_user_id=current.id)
    return TemplateOut(id=t.id, code=t.code, name=t.name, channel=t.channel,
                       subject=t.subject, body_text=t.body_text, is_approved=t.is_approved)
