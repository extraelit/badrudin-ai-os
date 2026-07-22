"""API настраиваемых порогов согласований (этап G, PR-G).

Backend — единственная точка доступа. RBAC переиспользует права рисков:
`risk.view` (просмотр/расчёт), `risk.manage` (настройка порогов). Пороги задаются
по организации/проекту/виду процесса; уровень риска процесса определяется
наиболее специфичным правилом. Действия — в аудит.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.api.pagination import PageParams, page_params, paginate
from app.db.session import get_db
from app.models import Employee, RiskThreshold, User
from app.schemas.risk_threshold import ResolveOut, ThresholdIn, ThresholdOut
from app.services import risk_threshold as svc

router = APIRouter(prefix="/risk-thresholds", tags=["risk-thresholds"])


def _org(db: Session, user: User) -> uuid.UUID:
    if user.employee_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пользователь не связан с сотрудником")
    return db.get(Employee, user.employee_id).organization_id


def _out(t: RiskThreshold) -> ThresholdOut:
    return ThresholdOut(
        id=t.id, metric=t.metric, risk_level=t.risk_level, min_value=t.min_value,
        max_value=t.max_value, process_kind=t.process_kind, project_id=t.project_id,
        required_approvals=t.required_approvals, requires_mfa=t.requires_mfa,
        description=t.description,
    )


@router.get("", response_model=list[ThresholdOut])
def list_thresholds(
    process_kind: str | None = Query(default=None),
    current: User = Depends(require_permission("risk.view")),
    db: Session = Depends(get_db),
    page: PageParams = Depends(page_params),
) -> list[ThresholdOut]:
    rows = svc.list_thresholds(db, _org(db, current), process_kind=process_kind)
    return [_out(t) for t in paginate(rows, page)]


@router.post("", response_model=ThresholdOut, status_code=201)
def set_threshold(
    payload: ThresholdIn,
    current: User = Depends(require_permission("risk.manage")),
    db: Session = Depends(get_db),
) -> ThresholdOut:
    try:
        t = svc.set_threshold(
            db, _org(db, current), metric=payload.metric,
            risk_level=payload.risk_level, min_value=payload.min_value,
            max_value=payload.max_value, process_kind=payload.process_kind,
            project_id=payload.project_id,
            required_approvals=payload.required_approvals,
            requires_mfa=payload.requires_mfa, description=payload.description,
            actor_user_id=current.id,
        )
    except svc.RiskThresholdError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _out(t)


@router.get("/resolve", response_model=ResolveOut)
def resolve(
    process_kind: str | None = Query(default=None),
    amount: Decimal | None = Query(default=None),
    duration_days: int | None = Query(default=None),
    current: User = Depends(require_permission("risk.view")),
    db: Session = Depends(get_db),
) -> ResolveOut:
    result = svc.resolve(
        db, _org(db, current), process_kind=process_kind, amount=amount,
        duration_days=duration_days,
    )
    return ResolveOut(**result)
