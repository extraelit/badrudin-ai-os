"""API руководительских панелей и эскалаций (этап H, PR-H).

Backend — единственная точка доступа. RBAC: `management.view` (сводка и эскалация —
руководители), `task.view` (списки просрочек/исключений). ABAC: всё ограничено
доступными пользователю проектами. Эскалации создают только внутренние (in_app)
уведомления — реальная внешняя рассылка не выполняется.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.api.pagination import PageParams, page_params, paginate
from app.db.session import get_db
from app.models import Employee, User
from app.schemas.dashboards import (
    EscalateOut,
    ExceptionItemOut,
    ManagerOverviewOut,
    OverdueItemOut,
)
from app.services import dashboards as svc

router = APIRouter(prefix="/manager", tags=["manager-dashboard"])


def _org(db: Session, user: User) -> uuid.UUID:
    if user.employee_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пользователь не связан с сотрудником")
    return db.get(Employee, user.employee_id).organization_id


@router.get("/overview", response_model=ManagerOverviewOut)
def overview(
    current: User = Depends(require_permission("management.view")),
    db: Session = Depends(get_db),
) -> ManagerOverviewOut:
    return ManagerOverviewOut(**svc.manager_overview(db, current, _org(db, current)))


@router.get("/overdue", response_model=list[OverdueItemOut])
def overdue(
    current: User = Depends(require_permission("task.view")),
    db: Session = Depends(get_db),
    page: PageParams = Depends(page_params),
) -> list[OverdueItemOut]:
    rows = svc.overdue_processes(db, current, _org(db, current))
    return [
        OverdueItemOut(
            id=p.id, title=p.title, process_kind=p.process_kind,
            risk_level=p.risk_level, status=p.status, due_at=p.due_at,
            primary_executor_id=p.primary_executor_id,
            responsible_manager_id=p.responsible_manager_id,
        )
        for p in paginate(rows, page)
    ]


@router.get("/exceptions", response_model=list[ExceptionItemOut])
def exceptions(
    current: User = Depends(require_permission("task.view")),
    db: Session = Depends(get_db),
    page: PageParams = Depends(page_params),
) -> list[ExceptionItemOut]:
    rows = svc.pending_exceptions(db, current, _org(db, current))
    return [
        ExceptionItemOut(
            id=x.id, process_id=x.process_id, evidence_type=x.evidence_type,
            reason=x.reason, status=x.status,
        )
        for x in paginate(rows, page)
    ]


@router.post("/escalate-overdue", response_model=EscalateOut)
def escalate_overdue(
    current: User = Depends(require_permission("management.view")),
    db: Session = Depends(get_db),
) -> EscalateOut:
    count = svc.escalate_overdue(db, current, _org(db, current))
    return EscalateOut(notifications_created=count)
