"""API модуля «Реестр рисков».

Backend — единственная точка доступа. RBAC: `risk.view` (реестр/сводка),
`risk.manage` (регистрация, оценка, план снижения), `risk.approve` (принятие/
закрытие/фиксация реализации — решение человека). ABAC: риски с проектом
ограничены доступом к проекту. Все значимые действия — в `audit_events`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.api.pagination import PageParams, page_params, paginate
from app.db.session import get_db
from app.models import Employee, Risk, User
from app.schemas.risk import (
    AssessIn,
    DecisionIn,
    MitigationIn,
    RiskIn,
    RiskOut,
    SummaryOut,
)
from app.services import risk as svc

router = APIRouter(prefix="/risks", tags=["risks"])


def _org(db: Session, user: User) -> uuid.UUID:
    if user.employee_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пользователь не связан с сотрудником")
    emp = db.get(Employee, user.employee_id)
    return emp.organization_id


def _risk(db: Session, user: User, risk_id: uuid.UUID) -> Risk:
    r = db.get(Risk, risk_id)
    if r is None or r.deleted_at is not None or r.organization_id != _org(db, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Риск не найден")
    if not svc.can_access_risk(db, user, r):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к риску")
    return r


def _project_access(db: Session, user: User, project_id: uuid.UUID | None) -> None:
    if project_id is None:
        return
    from app.services.access import can_access_project

    if not can_access_project(db, user, project_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к проекту")


def _out(r: Risk) -> RiskOut:
    return RiskOut(
        id=r.id, number=r.number, title=r.title, description=r.description,
        category=r.category, probability=r.probability, impact=r.impact,
        severity=r.severity, status=r.status, project_id=r.project_id,
        owner_employee_id=r.owner_employee_id, mitigation_plan=r.mitigation_plan,
        due_at=r.due_at, source_type=r.source_type,
    )


def _guard(exc: svc.RiskError) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


@router.get("/summary", response_model=SummaryOut)
def summary(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("risk.view")),
) -> SummaryOut:
    return SummaryOut(**svc.summary(db, user, _org(db, user)))


@router.get("", response_model=list[RiskOut])
def list_risks(
    status_filter: str | None = Query(None, alias="status"),
    severity: str | None = None,
    db: Session = Depends(get_db),
    page: PageParams = Depends(page_params),
    user: User = Depends(require_permission("risk.view")),
) -> list[RiskOut]:
    rows = svc.list_risks(db, user, _org(db, user), status=status_filter, severity=severity)
    return [_out(r) for r in paginate(rows, page)]


@router.post("", response_model=RiskOut, status_code=status.HTTP_201_CREATED)
def register_risk(
    payload: RiskIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("risk.manage")),
) -> RiskOut:
    _project_access(db, user, payload.project_id)
    try:
        r = svc.register_risk(db, organization_id=_org(db, user), user=user, **payload.model_dump())
    except svc.RiskError as exc:
        raise _guard(exc) from exc
    return _out(r)


@router.get("/{risk_id}", response_model=RiskOut)
def get_risk(
    risk_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("risk.view")),
) -> RiskOut:
    return _out(_risk(db, user, risk_id))


@router.post("/{risk_id}/assess", response_model=RiskOut)
def assess_risk(
    risk_id: uuid.UUID, payload: AssessIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("risk.manage")),
) -> RiskOut:
    r = _risk(db, user, risk_id)
    try:
        svc.assess_risk(db, r, user=user, **payload.model_dump(exclude_none=True))
    except svc.RiskError as exc:
        raise _guard(exc) from exc
    return _out(r)


@router.post("/{risk_id}/mitigation", response_model=RiskOut)
def plan_mitigation(
    risk_id: uuid.UUID, payload: MitigationIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("risk.manage")),
) -> RiskOut:
    r = _risk(db, user, risk_id)
    try:
        svc.plan_mitigation(db, r, user=user, **payload.model_dump(exclude_none=True))
    except svc.RiskError as exc:
        raise _guard(exc) from exc
    return _out(r)


@router.post("/{risk_id}/decision", response_model=RiskOut)
def decide_risk(
    risk_id: uuid.UUID, payload: DecisionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("risk.approve")),
) -> RiskOut:
    r = _risk(db, user, risk_id)
    try:
        svc.decide_risk(db, r, user=user, decision=payload.decision, comment=payload.comment)
    except svc.RiskError as exc:
        raise _guard(exc) from exc
    return _out(r)
