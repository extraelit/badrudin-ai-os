"""API модуля «Сметы и ценообразование».

Backend — единственная точка доступа к данным (ARCHITECTURE.md раздел 5.2).
Все действия проходят серверную проверку прав (RBAC) и изоляцию по организации/
проекту/объекту (ABAC). Утверждение сметы — R2; коммерческое предложение — R3/R4
(порог настраивается для организации, R4 требует MFA). Все действия — в
`audit_events`. Денежные значения — Decimal, в ответах сериализуются строкой.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.session import get_db
from app.models import (
    Approval,
    CommercialOffer,
    Estimate,
    EstimatePosition,
    Project,
    RateItem,
    UnitOfMeasure,
    User,
)
from app.schemas.estimates import (
    ChangeIn,
    EstimateIn,
    EstimateOut,
    EstimateSummaryRow,
    NewVersionIn,
    OfferDecisionIn,
    OfferIn,
    OfferOut,
    PlanFactOut,
    PlanFactRowOut,
    PositionIn,
    PositionOut,
    ProjectEstimateSummary,
    RateItemIn,
    RateItemOut,
    UnitOut,
)
from app.services import estimates as svc
from app.services.auth import verify_totp

router = APIRouter(prefix="/estimates", tags=["estimates"])


def _project(db: Session, user: User, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Проект не найден")
    if not svc.can_access_estimate_project(db, user, project_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к проекту")
    return project


def _load_estimate(db: Session, user: User, estimate_id: uuid.UUID) -> Estimate:
    est = db.get(Estimate, estimate_id)
    if est is None or est.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Смета не найдена")
    _project(db, user, est.project_id)
    return est


def _pos_out(p: EstimatePosition) -> PositionOut:
    return PositionOut(
        id=p.id, code=p.code, name=p.name, unit_id=p.unit_id,
        quantity=str(p.quantity), material_unit_cost=str(p.material_unit_cost),
        labor_unit_cost=str(p.labor_unit_cost), machine_unit_cost=str(p.machine_unit_cost),
        coefficient=str(p.coefficient), overhead_percent=str(p.overhead_percent),
        profit_percent=str(p.profit_percent), position_direct=str(p.position_direct),
        position_overhead=str(p.position_overhead), position_profit=str(p.position_profit),
        position_total=str(p.position_total),
    )


def _est_out(db: Session, est: Estimate) -> EstimateOut:
    positions = list(
        db.execute(
            select(EstimatePosition)
            .where(EstimatePosition.estimate_id == est.id)
            .order_by(EstimatePosition.position_no)
        ).scalars()
    )
    return EstimateOut(
        id=est.id, project_id=est.project_id, name=est.name, number=est.number,
        estimate_type=est.estimate_type, version=est.version, status=est.status,
        currency=est.currency, base_index=str(est.base_index), vat_rate=str(est.vat_rate),
        material_total=str(est.material_total), labor_total=str(est.labor_total),
        machine_total=str(est.machine_total), direct_total=str(est.direct_total),
        overhead_total=str(est.overhead_total), profit_total=str(est.profit_total),
        subtotal=str(est.subtotal), vat_total=str(est.vat_total),
        grand_total=str(est.grand_total), positions=[_pos_out(p) for p in positions],
    )


# ------------------------------ Справочники ------------------------------ #


@router.get("/units", response_model=list[UnitOut])
def list_units(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("estimate.view")),
) -> list[UnitOut]:
    rows = db.execute(select(UnitOfMeasure).where(UnitOfMeasure.status == "active")).scalars()
    return [UnitOut(id=u.id, code=u.code, name=u.name, category=u.category) for u in rows]


@router.get("/rate-items", response_model=list[RateItemOut])
def list_rate_items(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("estimate.view")),
) -> list[RateItemOut]:
    rows = db.execute(select(RateItem).where(RateItem.deleted_at.is_(None))).scalars()
    return [
        RateItemOut(
            id=r.id, code=r.code, name=r.name, unit_id=r.unit_id,
            material_cost=str(r.material_cost), labor_cost=str(r.labor_cost),
            machine_cost=str(r.machine_cost), source=r.source, status=r.status,
        )
        for r in rows
    ]


@router.post("/rate-items", response_model=RateItemOut, status_code=status.HTTP_201_CREATED)
def create_rate_item(
    payload: RateItemIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("estimate.manage")),
) -> RateItemOut:
    if user.employee_id is None:
        # организация берётся из проекта при работе со сметами; справочник — по
        # организации пользователя недоступен без сотрудника → 400
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пользователь не связан с сотрудником")
    from app.models import Employee

    emp = db.get(Employee, user.employee_id)
    r = RateItem(
        organization_id=emp.organization_id, code=payload.code, name=payload.name,
        unit_id=payload.unit_id, material_cost=payload.material_cost,
        labor_cost=payload.labor_cost, machine_cost=payload.machine_cost,
        source=payload.source, created_by=user.id,
    )
    db.add(r)
    db.commit()
    return RateItemOut(
        id=r.id, code=r.code, name=r.name, unit_id=r.unit_id,
        material_cost=str(r.material_cost), labor_cost=str(r.labor_cost),
        machine_cost=str(r.machine_cost), source=r.source, status=r.status,
    )


# -------------------------------- Сметы ---------------------------------- #


@router.get("/projects/{project_id}/estimates", response_model=list[EstimateOut])
def list_estimates(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("estimate.view")),
) -> list[EstimateOut]:
    _project(db, user, project_id)
    rows = db.execute(
        select(Estimate).where(
            Estimate.project_id == project_id, Estimate.deleted_at.is_(None)
        )
    ).scalars()
    return [_est_out(db, e) for e in rows]


@router.post(
    "/projects/{project_id}/estimates",
    response_model=EstimateOut,
    status_code=status.HTTP_201_CREATED,
)
def create_estimate(
    project_id: uuid.UUID,
    payload: EstimateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("estimate.manage")),
) -> EstimateOut:
    project = _project(db, user, project_id)
    est = Estimate(
        organization_id=project.organization_id, project_id=project_id,
        site_id=payload.site_id, contract_id=payload.contract_id,
        discipline_id=payload.discipline_id, design_brief_id=payload.design_brief_id,
        parent_estimate_id=payload.parent_estimate_id, estimate_type=payload.estimate_type,
        number=payload.number, name=payload.name, currency=payload.currency,
        base_index=payload.base_index, vat_rate=payload.vat_rate,
        overhead_percent=payload.overhead_percent, profit_percent=payload.profit_percent,
        rounding=payload.rounding, created_by=user.id,
    )
    db.add(est)
    db.commit()
    return _est_out(db, est)


@router.get("/{estimate_id}", response_model=EstimateOut)
def get_estimate(
    estimate_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("estimate.view")),
) -> EstimateOut:
    est = _load_estimate(db, user, estimate_id)
    return _est_out(db, est)


@router.post("/{estimate_id}/positions", response_model=EstimateOut, status_code=status.HTTP_201_CREATED)
def add_position(
    estimate_id: uuid.UUID,
    payload: PositionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("estimate.manage")),
) -> EstimateOut:
    est = _load_estimate(db, user, estimate_id)
    try:
        svc.assert_editable(est)  # запрет прямого изменения утверждённой сметы
    except svc.EstimateStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    count = len(
        list(db.execute(select(EstimatePosition.id).where(EstimatePosition.estimate_id == est.id)).scalars())
    )
    pos = EstimatePosition(
        estimate_id=est.id, rate_item_id=payload.rate_item_id, material_id=payload.material_id,
        design_specification_id=payload.design_specification_id, discipline_id=payload.discipline_id,
        location_id=payload.location_id, unit_id=payload.unit_id, code=payload.code,
        name=payload.name, work_type=payload.work_type, position_no=count + 1,
        quantity=payload.quantity, material_unit_cost=payload.material_unit_cost,
        labor_unit_cost=payload.labor_unit_cost, machine_unit_cost=payload.machine_unit_cost,
        coefficient=payload.coefficient, overhead_percent=payload.overhead_percent,
        profit_percent=payload.profit_percent,
    )
    db.add(pos)
    db.flush()
    svc.recalc_estimate(db, est)
    db.commit()
    return _est_out(db, est)


@router.post("/{estimate_id}/recalc", response_model=EstimateOut)
def recalc(
    estimate_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("estimate.manage")),
) -> EstimateOut:
    est = _load_estimate(db, user, estimate_id)
    svc.recalc_estimate(db, est)
    db.commit()
    return _est_out(db, est)


@router.post("/{estimate_id}/approve", response_model=EstimateOut)
def approve(
    estimate_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("estimate.approve")),
) -> EstimateOut:
    est = _load_estimate(db, user, estimate_id)
    try:
        svc.approve_estimate(db, est, user=user)
    except svc.EstimateValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except svc.EstimateStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _est_out(db, est)


@router.post("/{estimate_id}/new-version", response_model=EstimateOut, status_code=status.HTTP_201_CREATED)
def new_version(
    estimate_id: uuid.UUID,
    payload: NewVersionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("estimate.manage")),
) -> EstimateOut:
    est = _load_estimate(db, user, estimate_id)
    new = svc.create_new_version(db, est, user=user, reason=payload.reason)
    return _est_out(db, new)


@router.post("/{estimate_id}/changes", response_model=dict, status_code=status.HTTP_201_CREATED)
def record_change(
    estimate_id: uuid.UUID,
    payload: ChangeIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("estimate.manage")),
) -> dict:
    est = _load_estimate(db, user, estimate_id)
    try:
        ch = svc.record_change(
            db, est, user=user, change_type=payload.change_type, reason=payload.reason,
            amount_delta=Decimal(str(payload.amount_delta)), position_id=payload.position_id,
        )
    except svc.EstimateStateError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return {"change_id": str(ch.id), "status": ch.status}


@router.get("/{estimate_id}/plan-fact", response_model=PlanFactOut)
def get_plan_fact(
    estimate_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("estimate.view")),
) -> PlanFactOut:
    est = _load_estimate(db, user, estimate_id)
    rows = svc.plan_fact(db, est)
    planned = sum((r.planned_total for r in rows), Decimal("0"))
    actual = sum((r.actual_total for r in rows), Decimal("0"))
    return PlanFactOut(
        estimate_id=est.id, planned_total=str(planned), actual_total=str(actual),
        deviation=str(actual - planned),
        rows=[
            PlanFactRowOut(
                position_id=r.position_id, name=r.name,
                planned_quantity=str(r.planned_quantity), actual_quantity=str(r.actual_quantity),
                planned_total=str(r.planned_total), actual_total=str(r.actual_total),
                deviation=str(r.deviation),
            )
            for r in rows
        ],
    )


# ------------------------- Коммерческое предложение ---------------------- #


def _offer_out(o: CommercialOffer) -> OfferOut:
    return OfferOut(
        id=o.id, estimate_id=o.estimate_id, markup_percent=str(o.markup_percent),
        base_amount=str(o.base_amount), offer_amount=str(o.offer_amount),
        currency=o.currency, status=o.status, risk_level=o.risk_level,
        approval_id=o.approval_id,
    )


@router.post("/{estimate_id}/offers", response_model=OfferOut, status_code=status.HTTP_201_CREATED)
def create_offer(
    estimate_id: uuid.UUID,
    payload: OfferIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("estimate.manage")),
) -> OfferOut:
    est = _load_estimate(db, user, estimate_id)
    try:
        offer = svc.create_offer(db, est, user=user, markup_percent=Decimal(str(payload.markup_percent)))
    except svc.EstimateStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    if payload.valid_until is not None:
        offer.valid_until = payload.valid_until
        db.commit()
    return _offer_out(offer)


@router.post("/offers/{offer_id}/request-approval", response_model=OfferOut)
def request_offer_approval(
    offer_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("estimate.manage")),
) -> OfferOut:
    offer = db.get(CommercialOffer, offer_id)
    if offer is None or offer.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "КП не найдено")
    _project(db, user, offer.project_id)
    try:
        svc.request_offer_approval(db, offer, user=user)
    except svc.EstimateStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _offer_out(offer)


@router.post("/offers/{offer_id}/decision", response_model=OfferOut)
def decide_offer(
    offer_id: uuid.UUID,
    payload: OfferDecisionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("offer.approve")),
) -> OfferOut:
    offer = db.get(CommercialOffer, offer_id)
    if offer is None or offer.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "КП не найдено")
    _project(db, user, offer.project_id)
    mfa_verified = False
    if offer.risk_level == "R4" and payload.decision == "approved":
        if not user.mfa_enabled or not user.mfa_secret or not payload.mfa_code:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Для КП уровня R4 требуется код MFA")
        if not verify_totp(user.mfa_secret, payload.mfa_code):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный код MFA")
        mfa_verified = True
    try:
        svc.decide_offer(
            db, offer, user=user, decision=payload.decision, comment=payload.comment,
            mfa_verified=mfa_verified,
        )
    except (svc.EstimateStateError, svc.OfferAuthorizationError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _offer_out(offer)


# ------------------------------- Сводка ---------------------------------- #


@router.get("/projects/{project_id}/summary", response_model=ProjectEstimateSummary)
def project_summary(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("estimate.view")),
) -> ProjectEstimateSummary:
    _project(db, user, project_id)
    estimates = list(
        db.execute(
            select(Estimate).where(
                Estimate.project_id == project_id, Estimate.deleted_at.is_(None)
            )
        ).scalars()
    )
    approved = [e for e in estimates if e.status == "approved"]
    offers_pending = len(
        list(
            db.execute(
                select(CommercialOffer.id).where(
                    CommercialOffer.project_id == project_id,
                    CommercialOffer.status == "pending_approval",
                )
            ).scalars()
        )
    )
    grand = sum((Decimal(e.grand_total or 0) for e in approved), Decimal("0"))
    return ProjectEstimateSummary(
        project_id=project_id, estimates_total=len(estimates),
        approved_total=len(approved), grand_total_approved=str(grand),
        offers_pending=offers_pending,
        estimates=[
            EstimateSummaryRow(
                estimate_id=e.id, name=e.name, version=e.version, status=e.status,
                grand_total=str(e.grand_total),
            )
            for e in estimates
        ],
    )
