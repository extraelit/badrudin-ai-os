"""API строительного контроля и качества (этап F, PR-F).

Backend — единственная точка доступа. RBAC переиспользует права контроля/замечаний:
`audit.finding.view` (просмотр карт/проверок), `audit.finding.manage` (карты,
проверки, повторные проверки), `audit.finding.resolve` (итоговое решение —
дополнительно ограничено ролью уполномоченного специалиста в сервисе). ABAC:
карты/проверки с проектом ограничены доступом к проекту. Все действия — в аудит.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.api.pagination import PageParams, page_params, paginate
from app.db.session import get_db
from app.models import Employee, QualityControlCard, QualityControlCheck, User
from app.schemas.quality import (
    CardIn,
    CardOut,
    CheckIn,
    CheckOut,
    FinalizeIn,
    RecheckIn,
)
from app.services import quality as svc
from app.services.access import can_access_project

router = APIRouter(prefix="/quality", tags=["quality"])


def _org(db: Session, user: User) -> uuid.UUID:
    if user.employee_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пользователь не связан с сотрудником")
    return db.get(Employee, user.employee_id).organization_id


def _check_project(db: Session, user: User, project_id: uuid.UUID | None) -> None:
    if project_id is not None and not can_access_project(db, user, project_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к проекту")


def _card(db: Session, user: User, cid: uuid.UUID) -> QualityControlCard:
    c = db.get(QualityControlCard, cid)
    if c is None or c.deleted_at is not None or c.organization_id != _org(db, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Контрольная карта не найдена")
    _check_project(db, user, c.project_id)
    return c


def _check(db: Session, user: User, chid: uuid.UUID) -> QualityControlCheck:
    ch = db.get(QualityControlCheck, chid)
    if ch is None or ch.organization_id != _org(db, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Проверка не найдена")
    _check_project(db, user, ch.project_id)
    return ch


def _card_out(c: QualityControlCard) -> CardOut:
    return CardOut(
        id=c.id, work_type=c.work_type, name=c.name, control_kind=c.control_kind,
        controlled_parameter=c.controlled_parameter, allowed_value=c.allowed_value,
        check_method=c.check_method, normative_item_id=c.normative_item_id,
        requires_document=c.requires_document, requires_photo=c.requires_photo,
        requires_measurement=c.requires_measurement, status=c.status,
    )


def _check_out(c: QualityControlCheck) -> CheckOut:
    return CheckOut(
        id=c.id, card_id=c.card_id, result=c.result, measured_value=c.measured_value,
        instrument=c.instrument, instrument_verification=c.instrument_verification,
        remark=c.remark, defect_deadline=c.defect_deadline,
        recheck_required=c.recheck_required, recheck_of_check_id=c.recheck_of_check_id,
        ai_suggestion=c.ai_suggestion, final_decision=c.final_decision,
        final_decision_by=c.final_decision_by, checked_by=c.checked_by,
        checked_at=c.checked_at,
    )


def _guard(exc: svc.QualityError) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


# --- Контрольные карты ------------------------------------------------------


@router.get("/cards", response_model=list[CardOut])
def list_cards(
    control_kind: str | None = Query(default=None),
    current: User = Depends(require_permission("audit.finding.view")),
    db: Session = Depends(get_db),
    page: PageParams = Depends(page_params),
) -> list[CardOut]:
    rows = svc.list_cards(db, _org(db, current), control_kind=control_kind)
    return [_card_out(c) for c in paginate(rows, page)]


@router.post("/cards", response_model=CardOut, status_code=201)
def create_card(
    payload: CardIn,
    current: User = Depends(require_permission("audit.finding.manage")),
    db: Session = Depends(get_db),
) -> CardOut:
    _check_project(db, current, payload.project_id)
    try:
        c = svc.create_card(
            db, _org(db, current), work_type=payload.work_type, name=payload.name,
            controlled_parameter=payload.controlled_parameter,
            control_kind=payload.control_kind, project_id=payload.project_id,
            normative_item_id=payload.normative_item_id,
            allowed_value=payload.allowed_value, check_method=payload.check_method,
            responsible_position=payload.responsible_position,
            requires_document=payload.requires_document,
            requires_photo=payload.requires_photo,
            requires_measurement=payload.requires_measurement,
            actor_user_id=current.id,
        )
    except svc.QualityError as exc:
        raise _guard(exc) from exc
    return _card_out(c)


# --- Проверки ---------------------------------------------------------------


@router.post("/cards/{cid}/checks", response_model=CheckOut, status_code=201)
def record_check(
    cid: uuid.UUID, payload: CheckIn,
    current: User = Depends(require_permission("audit.finding.manage")),
    db: Session = Depends(get_db),
) -> CheckOut:
    card = _card(db, current, cid)
    _check_project(db, current, payload.project_id)
    try:
        ch = svc.record_check(
            db, card, result=payload.result, checked_by=current.id,
            measured_value=payload.measured_value, instrument=payload.instrument,
            instrument_verification=payload.instrument_verification,
            remark=payload.remark, defect_deadline=payload.defect_deadline,
            process_id=payload.process_id, project_id=payload.project_id,
            ai_suggestion=payload.ai_suggestion,
        )
    except svc.QualityError as exc:
        raise _guard(exc) from exc
    return _check_out(ch)


@router.get("/checks", response_model=list[CheckOut])
def list_checks(
    card_id: uuid.UUID | None = Query(default=None),
    current: User = Depends(require_permission("audit.finding.view")),
    db: Session = Depends(get_db),
    page: PageParams = Depends(page_params),
) -> list[CheckOut]:
    rows = svc.list_checks(db, _org(db, current), card_id=card_id)
    return [_check_out(c) for c in paginate(rows, page)]


@router.post("/checks/{chid}/recheck", response_model=CheckOut, status_code=201)
def create_recheck(
    chid: uuid.UUID, payload: RecheckIn,
    current: User = Depends(require_permission("audit.finding.manage")),
    db: Session = Depends(get_db),
) -> CheckOut:
    original = _check(db, current, chid)
    try:
        ch = svc.create_recheck(
            db, original, result=payload.result, checked_by=current.id,
            measured_value=payload.measured_value, instrument=payload.instrument,
            remark=payload.remark,
        )
    except svc.QualityError as exc:
        raise _guard(exc) from exc
    return _check_out(ch)


@router.post("/checks/{chid}/finalize", response_model=CheckOut)
def finalize_check(
    chid: uuid.UUID, payload: FinalizeIn,
    current: User = Depends(require_permission("audit.finding.resolve")),
    db: Session = Depends(get_db),
) -> CheckOut:
    check = _check(db, current, chid)
    try:
        svc.finalize_check(
            db, check, decider_user_id=current.id, decision=payload.decision,
            comment=payload.comment,
        )
    except svc.QualityError as exc:
        # роль/SoD не позволяет — 403; прочее — 409
        msg = str(exc)
        if "специалист" in msg or "SoD" in msg:
            raise HTTPException(status.HTTP_403_FORBIDDEN, msg) from exc
        raise _guard(exc) from exc
    return _check_out(check)
