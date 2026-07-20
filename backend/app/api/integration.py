"""API модуля «Масштабирование интеграций» — внутренний контур (§14).

Backend — единственная точка доступа. RBAC: `integration.view` (реестр/очередь/
сводка), `integration.manage` (реестр коннекторов, черновики исходящих),
`integration.approve` (утверждение исходящих сообщений — человек в контуре). ABAC:
исходящие с проектом ограничены доступом к проекту. Модуль НЕ отправляет сообщения
и НЕ хранит секретов; утверждённое сообщение готово к отправке вне модуля. Всё —
в `audit_events`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.api.pagination import PageParams, page_params, paginate
from app.db.session import get_db
from app.models import Employee, IntegrationConnector, OutboundMessage, User
from app.schemas.integration import (
    CancelIn,
    ConnectorIn,
    ConnectorOut,
    ConnectorStatusIn,
    DecisionIn,
    OutboundIn,
    OutboundOut,
    SummaryOut,
)
from app.services import integration as svc

router = APIRouter(prefix="/integrations", tags=["integrations"])


def _org(db: Session, user: User) -> uuid.UUID:
    if user.employee_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пользователь не связан с сотрудником")
    emp = db.get(Employee, user.employee_id)
    return emp.organization_id


def _connector(db: Session, user: User, cid: uuid.UUID) -> IntegrationConnector:
    c = db.get(IntegrationConnector, cid)
    if c is None or c.deleted_at is not None or c.organization_id != _org(db, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Коннектор не найден")
    return c


def _outbound(db: Session, user: User, mid: uuid.UUID) -> OutboundMessage:
    m = db.get(OutboundMessage, mid)
    if m is None or m.deleted_at is not None or m.organization_id != _org(db, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сообщение не найдено")
    if not svc.can_access_outbound(db, user, m):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к сообщению")
    return m


def _c_out(c: IntegrationConnector) -> ConnectorOut:
    return ConnectorOut(id=c.id, code=c.code, name=c.name, channel=c.channel,
                        provider=c.provider, config_summary=c.config_summary, status=c.status,
                        credentials_configured_externally=c.credentials_configured_externally)


def _m_out(m: OutboundMessage) -> OutboundOut:
    return OutboundOut(id=m.id, channel=m.channel, subject=m.subject, body_text=m.body_text,
                       recipient=m.recipient, status=m.status, risk_level=m.risk_level,
                       project_id=m.project_id, connector_id=m.connector_id,
                       approval_id=m.approval_id, approved_at=m.approved_at)


def _guard(exc: svc.IntegrationError) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


@router.get("/summary", response_model=SummaryOut)
def summary(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("integration.view")),
) -> SummaryOut:
    return SummaryOut(**svc.summary(db, user, _org(db, user)))


# ------------------------------ Коннекторы ------------------------------- #


@router.get("/connectors", response_model=list[ConnectorOut])
def list_connectors(
    db: Session = Depends(get_db),
    page: PageParams = Depends(page_params),
    user: User = Depends(require_permission("integration.view")),
) -> list[ConnectorOut]:
    return [_c_out(c) for c in paginate(svc.list_connectors(db, _org(db, user)), page)]


@router.post("/connectors", response_model=ConnectorOut, status_code=status.HTTP_201_CREATED)
def register_connector(
    payload: ConnectorIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("integration.manage")),
) -> ConnectorOut:
    try:
        c = svc.register_connector(db, organization_id=_org(db, user), user=user, **payload.model_dump())
    except svc.IntegrationError as exc:
        raise _guard(exc) from exc
    return _c_out(c)


@router.post("/connectors/{connector_id}/status", response_model=ConnectorOut)
def set_connector_status(
    connector_id: uuid.UUID, payload: ConnectorStatusIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("integration.manage")),
) -> ConnectorOut:
    c = _connector(db, user, connector_id)
    try:
        svc.set_connector_status(db, c, user=user, **payload.model_dump(exclude_none=True))
    except svc.IntegrationError as exc:
        raise _guard(exc) from exc
    return _c_out(c)


# ------------------------- Исходящие сообщения --------------------------- #


@router.get("/outbound", response_model=list[OutboundOut])
def list_outbound(
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    page: PageParams = Depends(page_params),
    user: User = Depends(require_permission("integration.view")),
) -> list[OutboundOut]:
    rows = svc.list_outbound(db, user, _org(db, user), status=status_filter)
    return [_m_out(m) for m in paginate(rows, page)]


@router.post("/outbound", response_model=OutboundOut, status_code=status.HTTP_201_CREATED)
def create_outbound(
    payload: OutboundIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("integration.manage")),
) -> OutboundOut:
    if payload.project_id is not None:
        from app.services.access import can_access_project

        if not can_access_project(db, user, payload.project_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к проекту")
    try:
        m = svc.create_outbound_draft(db, organization_id=_org(db, user), user=user, **payload.model_dump())
    except svc.IntegrationError as exc:
        raise _guard(exc) from exc
    return _m_out(m)


@router.post("/outbound/{message_id}/submit", response_model=OutboundOut)
def submit_outbound(
    message_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("integration.manage")),
) -> OutboundOut:
    m = _outbound(db, user, message_id)
    try:
        svc.submit_outbound(db, m, user=user)
    except svc.IntegrationError as exc:
        raise _guard(exc) from exc
    return _m_out(m)


@router.post("/outbound/{message_id}/decision", response_model=OutboundOut)
def decide_outbound(
    message_id: uuid.UUID, payload: DecisionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("integration.approve")),
) -> OutboundOut:
    m = _outbound(db, user, message_id)
    try:
        svc.decide_outbound(db, m, user=user, decision=payload.decision, comment=payload.comment)
    except svc.IntegrationError as exc:
        raise _guard(exc) from exc
    return _m_out(m)


@router.post("/outbound/{message_id}/cancel", response_model=OutboundOut)
def cancel_outbound(
    message_id: uuid.UUID, payload: CancelIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("integration.manage")),
) -> OutboundOut:
    m = _outbound(db, user, message_id)
    try:
        svc.cancel_outbound(db, m, user=user, reason=payload.reason)
    except svc.IntegrationError as exc:
        raise _guard(exc) from exc
    return _m_out(m)
