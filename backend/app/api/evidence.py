"""API Evidence Gate (этап D, PR-D2).

Backend — единственная точка доступа. RBAC переиспользует права задач-поручений:
`task.view` (просмотр требований/доказательств/статуса гейта), `task.assign`
(настройка матрицы требований), `task.execute` (приложение доказательств, запрос
исключения), `task.approve` (решение по исключению — дополнительно ограничено
ролью уполномоченного руководителя в сервисе). ABAC: доступ к процессу с проектом
ограничен доступом к проекту. Значимые действия — в аудит.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.session import get_db
from app.models import Employee, EvidenceExceptionRequest, User, WorkflowProcess
from app.schemas.evidence import (
    EvidenceIn,
    EvidenceOut,
    ExceptionDecisionIn,
    ExceptionOut,
    ExceptionRequestIn,
    GateStatusOut,
    RequirementIn,
    RequirementOut,
)
from app.services import evidence as svc
from app.services.access import can_access_project

router = APIRouter(tags=["evidence"])


def _org(db: Session, user: User) -> uuid.UUID:
    if user.employee_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пользователь не связан с сотрудником")
    emp = db.get(Employee, user.employee_id)
    return emp.organization_id


def _process(db: Session, user: User, pid: uuid.UUID) -> WorkflowProcess:
    p = db.get(WorkflowProcess, pid)
    if p is None or p.deleted_at is not None or p.organization_id != _org(db, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Процесс не найден")
    if p.project_id is not None and not can_access_project(db, user, p.project_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к проекту")
    return p


def _guard(exc: svc.EvidenceError) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


# --- Матрица требований -----------------------------------------------------


@router.post("/evidence/requirements", response_model=RequirementOut, status_code=201)
def set_requirement(
    payload: RequirementIn,
    current: User = Depends(require_permission("task.assign")),
    db: Session = Depends(get_db),
) -> RequirementOut:
    try:
        r = svc.set_requirement(
            db, _org(db, current), process_kind=payload.process_kind,
            evidence_type=payload.evidence_type, required=payload.required,
            min_count=payload.min_count, phase=payload.phase,
            condition=payload.condition, actor_user_id=current.id,
        )
    except svc.EvidenceError as exc:
        raise _guard(exc) from exc
    return RequirementOut(
        id=r.id, process_kind=r.process_kind, evidence_type=r.evidence_type,
        required=r.required, min_count=r.min_count, phase=r.phase, condition=r.condition,
    )


@router.get("/evidence/requirements", response_model=list[RequirementOut])
def list_requirements(
    process_kind: str = Query(...),
    current: User = Depends(require_permission("task.view")),
    db: Session = Depends(get_db),
) -> list[RequirementOut]:
    rows = svc.list_requirements(db, _org(db, current), process_kind)
    return [
        RequirementOut(
            id=r.id, process_kind=r.process_kind, evidence_type=r.evidence_type,
            required=r.required, min_count=r.min_count, phase=r.phase,
            condition=r.condition,
        )
        for r in rows
    ]


# --- Доказательства процесса ------------------------------------------------


def _ev_out(e) -> EvidenceOut:
    return EvidenceOut(
        id=e.id, evidence_type=e.evidence_type, file_id=e.file_id, note=e.note,
        captured_phase=e.captured_phase, added_by=e.added_by, added_at=e.added_at,
    )


@router.post("/processes/{pid}/evidence", response_model=EvidenceOut, status_code=201)
def add_evidence(
    pid: uuid.UUID,
    payload: EvidenceIn,
    current: User = Depends(require_permission("task.execute")),
    db: Session = Depends(get_db),
) -> EvidenceOut:
    p = _process(db, current, pid)
    try:
        e = svc.add_evidence(
            db, p, evidence_type=payload.evidence_type, file_id=payload.file_id,
            note=payload.note, captured_phase=payload.captured_phase,
            actor_user_id=current.id,
        )
    except svc.EvidenceError as exc:
        raise _guard(exc) from exc
    return _ev_out(e)


@router.get("/processes/{pid}/evidence", response_model=list[EvidenceOut])
def list_evidence(
    pid: uuid.UUID,
    current: User = Depends(require_permission("task.view")),
    db: Session = Depends(get_db),
) -> list[EvidenceOut]:
    p = _process(db, current, pid)
    return [_ev_out(e) for e in svc.list_evidence(db, p.id)]


@router.get("/processes/{pid}/evidence/gate", response_model=GateStatusOut)
def gate_status(
    pid: uuid.UUID,
    current: User = Depends(require_permission("task.view")),
    db: Session = Depends(get_db),
) -> GateStatusOut:
    p = _process(db, current, pid)
    missing = svc.missing_required(db, p)
    return GateStatusOut(satisfied=not missing, missing=missing)


# --- Запросы на исключение --------------------------------------------------


def _exc_out(x: EvidenceExceptionRequest) -> ExceptionOut:
    return ExceptionOut(
        id=x.id, evidence_type=x.evidence_type, reason=x.reason, status=x.status,
        requested_by=x.requested_by, decided_by=x.decided_by,
        decided_at=x.decided_at, decision_comment=x.decision_comment,
    )


@router.post(
    "/processes/{pid}/evidence/exceptions", response_model=ExceptionOut, status_code=201
)
def request_exception(
    pid: uuid.UUID,
    payload: ExceptionRequestIn,
    current: User = Depends(require_permission("task.execute")),
    db: Session = Depends(get_db),
) -> ExceptionOut:
    p = _process(db, current, pid)
    try:
        x = svc.request_exception(
            db, p, evidence_type=payload.evidence_type, reason=payload.reason,
            requested_by=current.id,
        )
    except svc.EvidenceError as exc:
        raise _guard(exc) from exc
    return _exc_out(x)


@router.get("/processes/{pid}/evidence/exceptions", response_model=list[ExceptionOut])
def list_exceptions(
    pid: uuid.UUID,
    current: User = Depends(require_permission("task.view")),
    db: Session = Depends(get_db),
) -> list[ExceptionOut]:
    p = _process(db, current, pid)
    return [_exc_out(x) for x in svc.list_exceptions(db, p.id)]


@router.post(
    "/processes/{pid}/evidence/exceptions/{req_id}/decide", response_model=ExceptionOut
)
def decide_exception(
    pid: uuid.UUID,
    req_id: uuid.UUID,
    payload: ExceptionDecisionIn,
    current: User = Depends(require_permission("task.approve")),
    db: Session = Depends(get_db),
) -> ExceptionOut:
    p = _process(db, current, pid)
    req = db.get(EvidenceExceptionRequest, req_id)
    if req is None or req.process_id != p.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Запрос не найден")
    try:
        x = svc.decide_exception(
            db, req, approver_user_id=current.id, approve=payload.approve,
            comment=payload.comment,
        )
    except svc.EvidenceError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    return _exc_out(x)
