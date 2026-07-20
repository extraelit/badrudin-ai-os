"""API центра уведомлений (in-app) — ROADMAP MVP §18/§24.

Backend — единственная точка доступа. Персональные операции (список, счётчик,
отметка прочитанным) доступны любому аутентифицированному пользователю, но ТОЛЬКО по
его собственным уведомлениям. Создание внутренних уведомлений другим адресатам —
право `notification.manage`. Канал только `in_app`: внешняя рассылка здесь не
выполняется (§14). Создание — в `audit_events`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.db.session import get_db
from app.models import Notification, User
from app.schemas.notifications import (
    InternalNotificationIn,
    MarkAllOut,
    NotificationOut,
    UnreadCountOut,
)
from app.services import notifications as svc

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _out(n: Notification) -> NotificationOut:
    return NotificationOut(
        id=n.id, title=n.title, message=n.message, priority=n.priority, status=n.status,
        entity_type=n.entity_type, entity_id=n.entity_id, read_at=n.read_at,
        created_at=n.created_at,
    )


def _guard(exc: svc.NotificationError) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.get("", response_model=list[NotificationOut])
def list_my(
    only_unread: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[NotificationOut]:
    return [_out(n) for n in svc.list_my(db, user, only_unread=only_unread)]


@router.get("/unread-count", response_model=UnreadCountOut)
def unread_count(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UnreadCountOut:
    return UnreadCountOut(unread=svc.unread_count(db, user))


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(
    notification_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NotificationOut:
    try:
        n = svc.mark_read(db, user, notification_id)
    except svc.NotificationError as exc:
        raise _guard(exc) from exc
    return _out(n)


@router.post("/read-all", response_model=MarkAllOut)
def mark_all_read(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MarkAllOut:
    return MarkAllOut(marked=svc.mark_all_read(db, user))


@router.post("", response_model=NotificationOut, status_code=status.HTTP_201_CREATED)
def create_internal(
    payload: InternalNotificationIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("notification.manage")),
) -> NotificationOut:
    org = svc.org_of(db, user)
    if org is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пользователь не связан с сотрудником")
    try:
        n = svc.create_internal(db, organization_id=org, user=user, **payload.model_dump())
    except svc.NotificationError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _out(n)
