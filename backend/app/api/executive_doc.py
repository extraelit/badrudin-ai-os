"""API модуля «Исполнительная документация ПТО» — ROADMAP этап 12 (§12).

Backend — единственная точка доступа. RBAC: `pto.view` (реестр/комплектность/сводка),
`pto.manage` (создание, версии, отправка на согласование), `pto.approve` (инженерное
утверждение — уполномоченный специалист, человек в контуре). ABAC: документы
ограничены доступом к объекту. Утверждение выполняет человек; ИИ не подменяет
инженерную подпись. Всё — в `audit_events`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.db.session import get_db
from app.models import Employee, ExecutiveDocument, User
from app.schemas.executive_doc import (
    CompletenessOut,
    DecisionIn,
    DocumentIn,
    DocumentOut,
    SummaryOut,
)
from app.services import executive_doc as svc
from app.services.access import can_access_project

router = APIRouter(prefix="/pto", tags=["pto"])


def _org(db: Session, user: User) -> uuid.UUID:
    if user.employee_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пользователь не связан с сотрудником")
    emp = db.get(Employee, user.employee_id)
    return emp.organization_id


def _doc(db: Session, user: User, did: uuid.UUID) -> ExecutiveDocument:
    d = db.get(ExecutiveDocument, did)
    if d is None or d.deleted_at is not None or d.organization_id != _org(db, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Документ не найден")
    if not svc.can_access_document(db, user, d):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к документу")
    return d


def _out(d: ExecutiveDocument) -> DocumentOut:
    return DocumentOut(
        id=d.id, project_id=d.project_id, doc_type=d.doc_type, number=d.number,
        title=d.title, description=d.description, file_id=d.file_id,
        work_item_type=d.work_item_type, work_item_id=d.work_item_id,
        version_number=d.version_number, supersedes_id=d.supersedes_id, status=d.status,
        approval_id=d.approval_id, reviewed_by_user_id=d.reviewed_by_user_id,
        review_comment=d.review_comment, approved_at=d.approved_at,
    )


def _guard(exc: svc.ExecutiveDocError) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


@router.get("/summary", response_model=SummaryOut)
def summary(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("pto.view")),
) -> SummaryOut:
    return SummaryOut(**svc.summary(db, user, _org(db, user)))


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(
    project_id: uuid.UUID | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("pto.view")),
) -> list[DocumentOut]:
    return [_out(d) for d in svc.list_documents(db, user, _org(db, user), project_id=project_id, status=status_filter)]


@router.post("/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def create_document(
    payload: DocumentIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("pto.manage")),
) -> DocumentOut:
    if not can_access_project(db, user, payload.project_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к объекту")
    try:
        d = svc.create_document(db, organization_id=_org(db, user), user=user, **payload.model_dump())
    except svc.ExecutiveDocError as exc:
        raise _guard(exc) from exc
    return _out(d)


@router.post("/documents/{document_id}/submit", response_model=DocumentOut)
def submit_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("pto.manage")),
) -> DocumentOut:
    d = _doc(db, user, document_id)
    try:
        svc.submit_document(db, d, user=user)
    except svc.ExecutiveDocError as exc:
        raise _guard(exc) from exc
    return _out(d)


@router.post("/documents/{document_id}/decision", response_model=DocumentOut)
def decide_document(
    document_id: uuid.UUID, payload: DecisionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("pto.approve")),
) -> DocumentOut:
    d = _doc(db, user, document_id)
    try:
        svc.decide_document(db, d, user=user, decision=payload.decision, comment=payload.comment)
    except svc.ExecutiveDocError as exc:
        raise _guard(exc) from exc
    return _out(d)


@router.get("/completeness", response_model=CompletenessOut)
def completeness(
    project_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("pto.view")),
) -> CompletenessOut:
    if not can_access_project(db, user, project_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к объекту")
    return CompletenessOut(**svc.completeness(db, user, _org(db, user), project_id))
