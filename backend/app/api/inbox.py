"""API модуля «Единый входящий поток».

Backend — единственная точка доступа. RBAC: `inbox.view` (очередь, сводка),
`inbox.manage` (приём, классификация, назначение, конверсия, отклонение). ABAC:
обращения с проектом доступны при доступе к проекту; без проекта — общий контур
сортировки. Конверсия в задачу переиспользует общий сервис. Всё — в `audit_events`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.api.pagination import PageParams, page_params, paginate
from app.db.session import get_db
from app.models import Employee, InboxItem, User
from app.schemas.inbox import (
    AssignIn,
    CaptureIn,
    ClassifyIn,
    ConvertTaskIn,
    DismissIn,
    ItemOut,
    MarkConvertedIn,
    SummaryOut,
    TaskRefOut,
)
from app.services import inbox as svc

router = APIRouter(prefix="/inbox", tags=["inbox"])


def _org(db: Session, user: User) -> uuid.UUID:
    if user.employee_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пользователь не связан с сотрудником")
    emp = db.get(Employee, user.employee_id)
    return emp.organization_id


def _item(db: Session, user: User, item_id: uuid.UUID) -> InboxItem:
    item = db.get(InboxItem, item_id)
    if item is None or item.deleted_at is not None or item.organization_id != _org(db, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Обращение не найдено")
    if not svc.can_access_item(db, user, item):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к обращению")
    return item


def _out(i: InboxItem) -> ItemOut:
    return ItemOut(
        id=i.id, source_type=i.source_type, channel=i.channel, subject=i.subject,
        body_text=i.body_text, status=i.status, category=i.category, priority=i.priority,
        project_id=i.project_id, counterparty_id=i.counterparty_id,
        assigned_to_employee_id=i.assigned_to_employee_id,
        converted_entity_type=i.converted_entity_type,
        converted_entity_id=i.converted_entity_id, received_at=i.received_at,
    )


def _guard(exc: svc.InboxError) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


@router.get("/summary", response_model=SummaryOut)
def summary(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inbox.view")),
) -> SummaryOut:
    return SummaryOut(**svc.summary(db, user, _org(db, user)))


@router.get("", response_model=list[ItemOut])
def list_items(
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    page: PageParams = Depends(page_params),
    user: User = Depends(require_permission("inbox.view")),
) -> list[ItemOut]:
    rows = svc.list_items(db, user, _org(db, user), status=status_filter)
    return [_out(i) for i in paginate(rows, page)]


@router.post("", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
def capture(
    payload: CaptureIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inbox.manage")),
) -> ItemOut:
    try:
        item = svc.capture_item(db, organization_id=_org(db, user), user=user, **payload.model_dump())
    except svc.InboxError as exc:
        raise _guard(exc) from exc
    return _out(item)


@router.get("/{item_id}", response_model=ItemOut)
def get_item(
    item_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inbox.view")),
) -> ItemOut:
    return _out(_item(db, user, item_id))


@router.post("/{item_id}/classify", response_model=ItemOut)
def classify(
    item_id: uuid.UUID, payload: ClassifyIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inbox.manage")),
) -> ItemOut:
    item = _item(db, user, item_id)
    try:
        svc.classify_item(db, item, user=user, **payload.model_dump(exclude_none=True))
    except svc.InboxError as exc:
        raise _guard(exc) from exc
    return _out(item)


@router.post("/{item_id}/assign", response_model=ItemOut)
def assign(
    item_id: uuid.UUID, payload: AssignIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inbox.manage")),
) -> ItemOut:
    item = _item(db, user, item_id)
    try:
        svc.assign_item(db, item, user=user, employee_id=payload.employee_id)
    except svc.InboxError as exc:
        raise _guard(exc) from exc
    return _out(item)


@router.post("/{item_id}/convert-to-task", response_model=TaskRefOut, status_code=status.HTTP_201_CREATED)
def convert_to_task(
    item_id: uuid.UUID, payload: ConvertTaskIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inbox.manage")),
) -> TaskRefOut:
    item = _item(db, user, item_id)
    try:
        task = svc.convert_to_task(db, item, user=user, title=payload.title,
                                   description=payload.description, priority=payload.priority)
    except svc.InboxError as exc:
        raise _guard(exc) from exc
    return TaskRefOut(id=task.id, title=task.title, status=task.status)


@router.post("/{item_id}/mark-converted", response_model=ItemOut)
def mark_converted(
    item_id: uuid.UUID, payload: MarkConvertedIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inbox.manage")),
) -> ItemOut:
    item = _item(db, user, item_id)
    try:
        svc.mark_converted(db, item, user=user, entity_type=payload.entity_type,
                           entity_id=payload.entity_id, note=payload.note)
    except svc.InboxError as exc:
        raise _guard(exc) from exc
    return _out(item)


@router.post("/{item_id}/dismiss", response_model=ItemOut)
def dismiss(
    item_id: uuid.UUID, payload: DismissIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inbox.manage")),
) -> ItemOut:
    item = _item(db, user, item_id)
    try:
        svc.dismiss_item(db, item, user=user, reason=payload.reason)
    except svc.InboxError as exc:
        raise _guard(exc) from exc
    return _out(item)
