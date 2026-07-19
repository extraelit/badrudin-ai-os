"""API модуля «KPI и независимый аудит» — ROADMAP этап 15 (§20).

Backend — единственная точка доступа. RBAC: `kpi.view` (сводка KPI),
`audit.finding.view` (реестр находок), `audit.finding.manage` (создание находок,
запуск сканирования), `audit.finding.resolve` (человеческий разбор находки). ABAC:
находки с проектом ограничены доступом к проекту; KPI считаются по доступным
проектам. Аудит НЕ изменяет проверяемые данные — только регистрирует находки. Всё —
в `audit_events`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.db.session import get_db
from app.models import AuditFinding, Employee, User
from app.schemas.kpi import (
    FindingIn,
    FindingOut,
    FindingResolveIn,
    KpiSummaryOut,
    ScanResultOut,
)
from app.services import kpi as svc

router = APIRouter(prefix="/kpi", tags=["kpi"])


def _org(db: Session, user: User) -> uuid.UUID:
    if user.employee_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пользователь не связан с сотрудником")
    emp = db.get(Employee, user.employee_id)
    return emp.organization_id


def _finding(db: Session, user: User, fid: uuid.UUID) -> AuditFinding:
    f = db.get(AuditFinding, fid)
    if f is None or f.deleted_at is not None or f.organization_id != _org(db, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Находка не найдена")
    if not svc.can_access_finding(db, user, f):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к находке")
    return f


def _f_out(f: AuditFinding) -> FindingOut:
    return FindingOut(
        id=f.id, category=f.category, severity=f.severity, title=f.title, detail=f.detail,
        entity_type=f.entity_type, entity_id=f.entity_id, status=f.status,
        detected_by=f.detected_by, project_id=f.project_id, owner_user_id=f.owner_user_id,
        resolution_note=f.resolution_note, created_at=f.created_at,
    )


def _guard(exc: svc.KpiError) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


@router.get("/summary", response_model=KpiSummaryOut)
def summary(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("kpi.view")),
) -> KpiSummaryOut:
    return KpiSummaryOut(**svc.kpi_summary(db, user, _org(db, user)))


# --------------------------- Находки аудита ------------------------------ #


@router.get("/findings", response_model=list[FindingOut])
def list_findings(
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("audit.finding.view")),
) -> list[FindingOut]:
    return [_f_out(f) for f in svc.list_findings(db, user, _org(db, user), status=status_filter)]


@router.post("/findings", response_model=FindingOut, status_code=status.HTTP_201_CREATED)
def create_finding(
    payload: FindingIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("audit.finding.manage")),
) -> FindingOut:
    if payload.project_id is not None:
        from app.services.access import can_access_project

        if not can_access_project(db, user, payload.project_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к проекту")
    try:
        f = svc.create_finding(db, organization_id=_org(db, user), user=user, **payload.model_dump())
    except svc.KpiError as exc:
        raise _guard(exc) from exc
    return _f_out(f)


@router.post("/findings/{finding_id}/resolve", response_model=FindingOut)
def resolve_finding(
    finding_id: uuid.UUID, payload: FindingResolveIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("audit.finding.resolve")),
) -> FindingOut:
    f = _finding(db, user, finding_id)
    try:
        svc.resolve_finding(db, f, user=user, status=payload.status, note=payload.note)
    except svc.KpiError as exc:
        raise _guard(exc) from exc
    return _f_out(f)


@router.post("/scan", response_model=ScanResultOut)
def run_scan(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("audit.finding.manage")),
) -> ScanResultOut:
    return ScanResultOut(**svc.run_scan(db, organization_id=_org(db, user), user=user))
