"""API модуля «SMM и внешние публикации» — внутренний контур (§14).

Backend — единственная точка доступа. RBAC: `smm.view` (план/публикации/сводка),
`smm.manage` (контент-план, черновики публикаций, проверки, материалы),
`smm.approve` (утверждение публикаций — человек в контуре). ABAC: план и публикации
с проектом ограничены доступом к проекту. Модуль НЕ публикует контент; утверждённая
публикация готова к публикации официальным инструментом вне модуля. Всё — в аудите.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.api.pagination import PageParams, page_params, paginate
from app.db.session import get_db
from app.models import ContentPlanItem, Employee, SocialPublication, User
from app.schemas.smm import (
    AssetIn,
    AssetOut,
    CancelIn,
    ChecksIn,
    DecisionIn,
    PlanItemIn,
    PlanItemOut,
    PlanStatusIn,
    PublicationIn,
    PublicationOut,
    SummaryOut,
)
from app.services import smm as svc

router = APIRouter(prefix="/smm", tags=["smm"])


def _org(db: Session, user: User) -> uuid.UUID:
    if user.employee_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пользователь не связан с сотрудником")
    emp = db.get(Employee, user.employee_id)
    return emp.organization_id


def _plan(db: Session, user: User, pid: uuid.UUID) -> ContentPlanItem:
    i = db.get(ContentPlanItem, pid)
    if i is None or i.deleted_at is not None or i.organization_id != _org(db, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Позиция плана не найдена")
    return i


def _pub(db: Session, user: User, pid: uuid.UUID) -> SocialPublication:
    p = db.get(SocialPublication, pid)
    if p is None or p.deleted_at is not None or p.organization_id != _org(db, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Публикация не найдена")
    if not svc.can_access_publication(db, user, p):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к публикации")
    return p


def _plan_out(i: ContentPlanItem) -> PlanItemOut:
    return PlanItemOut(id=i.id, title=i.title, theme=i.theme, channel=i.channel,
                       planned_date=i.planned_date, project_id=i.project_id,
                       status=i.status, notes=i.notes)


def _pub_out(p: SocialPublication) -> PublicationOut:
    return PublicationOut(
        id=p.id, channel=p.channel, title=p.title, body_text=p.body_text,
        hashtags=p.hashtags, status=p.status, rights_confirmed=p.rights_confirmed,
        pii_checked=p.pii_checked, legal_checked=p.legal_checked,
        scheduled_for=p.scheduled_for, risk_level=p.risk_level, project_id=p.project_id,
        connector_id=p.connector_id, plan_item_id=p.plan_item_id,
        approval_id=p.approval_id, approved_at=p.approved_at,
    )


def _asset_out(a) -> AssetOut:
    return AssetOut(id=a.id, publication_id=a.publication_id, file_id=a.file_id,
                    caption=a.caption, quality_ok=a.quality_ok, rights_ok=a.rights_ok)


def _guard(exc: svc.SmmError) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


def _check_project(db: Session, user: User, project_id: uuid.UUID | None) -> None:
    if project_id is not None:
        from app.services.access import can_access_project

        if not can_access_project(db, user, project_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к проекту")


@router.get("/summary", response_model=SummaryOut)
def summary(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("smm.view")),
) -> SummaryOut:
    return SummaryOut(**svc.summary(db, user, _org(db, user)))


# ------------------------------ Контент-план ----------------------------- #


@router.get("/plan", response_model=list[PlanItemOut])
def list_plan(
    db: Session = Depends(get_db),
    page: PageParams = Depends(page_params),
    user: User = Depends(require_permission("smm.view")),
) -> list[PlanItemOut]:
    return [_plan_out(i) for i in paginate(svc.list_plan(db, user, _org(db, user)), page)]


@router.post("/plan", response_model=PlanItemOut, status_code=status.HTTP_201_CREATED)
def create_plan_item(
    payload: PlanItemIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("smm.manage")),
) -> PlanItemOut:
    _check_project(db, user, payload.project_id)
    try:
        i = svc.create_plan_item(db, organization_id=_org(db, user), user=user, **payload.model_dump())
    except svc.SmmError as exc:
        raise _guard(exc) from exc
    return _plan_out(i)


@router.post("/plan/{item_id}/status", response_model=PlanItemOut)
def set_plan_status(
    item_id: uuid.UUID, payload: PlanStatusIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("smm.manage")),
) -> PlanItemOut:
    i = _plan(db, user, item_id)
    try:
        svc.set_plan_status(db, i, user=user, status=payload.status)
    except svc.SmmError as exc:
        raise _guard(exc) from exc
    return _plan_out(i)


# ------------------------------ Публикации ------------------------------- #


@router.get("/publications", response_model=list[PublicationOut])
def list_publications(
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    page: PageParams = Depends(page_params),
    user: User = Depends(require_permission("smm.view")),
) -> list[PublicationOut]:
    rows = svc.list_publications(db, user, _org(db, user), status=status_filter)
    return [_pub_out(p) for p in paginate(rows, page)]


@router.post("/publications", response_model=PublicationOut, status_code=status.HTTP_201_CREATED)
def create_publication(
    payload: PublicationIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("smm.manage")),
) -> PublicationOut:
    _check_project(db, user, payload.project_id)
    try:
        p = svc.create_publication(db, organization_id=_org(db, user), user=user, **payload.model_dump())
    except svc.SmmError as exc:
        raise _guard(exc) from exc
    return _pub_out(p)


@router.post("/publications/{publication_id}/checks", response_model=PublicationOut)
def set_checks(
    publication_id: uuid.UUID, payload: ChecksIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("smm.manage")),
) -> PublicationOut:
    p = _pub(db, user, publication_id)
    try:
        svc.set_checks(db, p, user=user, **payload.model_dump(exclude_none=True))
    except svc.SmmError as exc:
        raise _guard(exc) from exc
    return _pub_out(p)


@router.get("/publications/{publication_id}/assets", response_model=list[AssetOut])
def list_assets(
    publication_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("smm.view")),
) -> list[AssetOut]:
    p = _pub(db, user, publication_id)
    return [_asset_out(a) for a in svc.list_assets(db, p)]


@router.post("/publications/{publication_id}/assets", response_model=AssetOut, status_code=status.HTTP_201_CREATED)
def add_asset(
    publication_id: uuid.UUID, payload: AssetIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("smm.manage")),
) -> AssetOut:
    p = _pub(db, user, publication_id)
    try:
        a = svc.add_asset(db, p, user=user, **payload.model_dump())
    except svc.SmmError as exc:
        raise _guard(exc) from exc
    return _asset_out(a)


@router.post("/publications/{publication_id}/submit", response_model=PublicationOut)
def submit_publication(
    publication_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("smm.manage")),
) -> PublicationOut:
    p = _pub(db, user, publication_id)
    try:
        svc.submit_publication(db, p, user=user)
    except svc.SmmError as exc:
        raise _guard(exc) from exc
    return _pub_out(p)


@router.post("/publications/{publication_id}/decision", response_model=PublicationOut)
def decide_publication(
    publication_id: uuid.UUID, payload: DecisionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("smm.approve")),
) -> PublicationOut:
    p = _pub(db, user, publication_id)
    try:
        svc.decide_publication(db, p, user=user, decision=payload.decision, comment=payload.comment)
    except svc.SmmError as exc:
        raise _guard(exc) from exc
    return _pub_out(p)


@router.post("/publications/{publication_id}/cancel", response_model=PublicationOut)
def cancel_publication(
    publication_id: uuid.UUID, payload: CancelIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("smm.manage")),
) -> PublicationOut:
    p = _pub(db, user, publication_id)
    try:
        svc.cancel_publication(db, p, user=user, reason=payload.reason)
    except svc.SmmError as exc:
        raise _guard(exc) from exc
    return _pub_out(p)
