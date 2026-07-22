"""API нормативного реестра и нормативного профиля проекта (этап 1).

Backend — единственная точка доступа. RBAC: `normative.view` (просмотр),
`normative.manage` (внесение документов и позиций профиля), `normative.confirm`
(подтверждение статуса актуальности и активация профиля — решение уполномоченного
лица: главный инженер / ПТО / юрист). ABAC: профиль проекта ограничен доступом к
проекту. Все значимые действия фиксируются в `audit_events`.

Важно: система не подтверждает актуальность редакции сама — новый документ вносится
со статусом `needs_review`; перевод в `in_force` выполняет человек.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.api.pagination import PageParams, page_params, paginate
from app.db.session import get_db
from app.models import (
    Employee,
    NormativeDocument,
    ProjectNormativeItem,
    ProjectNormativeProfile,
    User,
)
from app.schemas.normative import (
    ConfirmStatusIn,
    NormativeDocumentIn,
    NormativeDocumentOut,
    ProfileItemIn,
    ProfileItemOut,
    ProfileOut,
)
from app.services import normative as svc
from app.services.access import can_access_project

router = APIRouter(prefix="/normative", tags=["normative"])


def _org(db: Session, user: User) -> uuid.UUID:
    if user.employee_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Пользователь не связан с сотрудником"
        )
    emp = db.get(Employee, user.employee_id)
    return emp.organization_id


def _doc_out(d: NormativeDocument) -> NormativeDocumentOut:
    return NormativeDocumentOut(
        id=d.id, full_title=d.full_title, number=d.number, doc_kind=d.doc_kind,
        edition=d.edition, amendment_no=d.amendment_no, status=d.status,
        effective_from=d.effective_from, effective_until=d.effective_until,
        official_source_url=d.official_source_url, last_checked_at=d.last_checked_at,
        reviewer_comment=d.reviewer_comment, is_archived=d.is_archived,
    )


def _guard(exc: svc.NormativeError) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


# --- Реестр нормативных документов ------------------------------------------


@router.get("/documents", response_model=list[NormativeDocumentOut])
def list_documents(
    current: User = Depends(require_permission("normative.view")),
    db: Session = Depends(get_db),
    page: PageParams = Depends(page_params),
) -> list[NormativeDocumentOut]:
    org = _org(db, current)
    rows = (
        db.query(NormativeDocument)
        .filter(
            NormativeDocument.organization_id == org,
            NormativeDocument.deleted_at.is_(None),
        )
        .order_by(NormativeDocument.created_at.desc())
        .all()
    )
    return [_doc_out(d) for d in paginate(rows, page)]


@router.post("/documents", response_model=NormativeDocumentOut, status_code=201)
def create_document(
    payload: NormativeDocumentIn,
    current: User = Depends(require_permission("normative.manage")),
    db: Session = Depends(get_db),
) -> NormativeDocumentOut:
    org = _org(db, current)
    try:
        doc = svc.create_document(
            db, org,
            full_title=payload.full_title, doc_kind=payload.doc_kind,
            number=payload.number, edition=payload.edition,
            amendment_no=payload.amendment_no,
            official_source_url=payload.official_source_url, scope=payload.scope,
            work_types=payload.work_types, object_types=payload.object_types,
            related_control_ops=payload.related_control_ops,
            created_by=current.id,
        )
    except svc.NormativeError as exc:
        raise _guard(exc) from exc
    return _doc_out(doc)


def _owned_document(db: Session, user: User, document_id: uuid.UUID) -> NormativeDocument:
    doc = db.get(NormativeDocument, document_id)
    if doc is None or doc.deleted_at is not None or doc.organization_id != _org(db, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Нормативный документ не найден")
    return doc


@router.post("/documents/{document_id}/confirm", response_model=NormativeDocumentOut)
def confirm_document_status(
    document_id: uuid.UUID,
    payload: ConfirmStatusIn,
    current: User = Depends(require_permission("normative.confirm")),
    db: Session = Depends(get_db),
) -> NormativeDocumentOut:
    _owned_document(db, current, document_id)  # проверка принадлежности организации
    try:
        doc = svc.confirm_status(
            db, document_id, payload.status,
            reviewer_user_id=current.id, comment=payload.comment,
        )
    except svc.NormativeError as exc:
        raise _guard(exc) from exc
    return _doc_out(doc)


# --- Нормативный профиль проекта --------------------------------------------


def _profile_out(db: Session, profile: ProjectNormativeProfile) -> ProfileOut:
    items = (
        db.query(ProjectNormativeItem)
        .filter(ProjectNormativeItem.profile_id == profile.id)
        .all()
    )
    return ProfileOut(
        id=profile.id, project_id=profile.project_id, status=profile.status,
        approved_by=profile.approved_by, approved_at=profile.approved_at,
        items=[
            ProfileItemOut(
                id=i.id, normative_document_id=i.normative_document_id,
                applicable_edition=i.applicable_edition, mandatory=i.mandatory,
                work_types=i.work_types, special_requirements=i.special_requirements,
            )
            for i in items
        ],
    )


def _check_project(db: Session, user: User, project_id: uuid.UUID) -> None:
    if not can_access_project(db, user, project_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к проекту")


@router.get("/projects/{project_id}/profile", response_model=ProfileOut)
def get_project_profile(
    project_id: uuid.UUID,
    current: User = Depends(require_permission("normative.view")),
    db: Session = Depends(get_db),
) -> ProfileOut:
    _check_project(db, current, project_id)
    profile = svc.get_or_create_profile(db, _org(db, current), project_id)
    db.commit()
    return _profile_out(db, profile)


@router.post(
    "/projects/{project_id}/profile/items",
    response_model=ProfileItemOut,
    status_code=201,
)
def add_project_profile_item(
    project_id: uuid.UUID,
    payload: ProfileItemIn,
    current: User = Depends(require_permission("normative.manage")),
    db: Session = Depends(get_db),
) -> ProfileItemOut:
    _check_project(db, current, project_id)
    profile = svc.get_or_create_profile(db, _org(db, current), project_id)
    try:
        item = svc.add_profile_item(
            db, profile.id, payload.normative_document_id,
            applicable_edition=payload.applicable_edition,
            mandatory=payload.mandatory, work_types=payload.work_types,
            special_requirements=payload.special_requirements,
            actor_user_id=current.id,
        )
    except svc.NormativeError as exc:
        raise _guard(exc) from exc
    return ProfileItemOut(
        id=item.id, normative_document_id=item.normative_document_id,
        applicable_edition=item.applicable_edition, mandatory=item.mandatory,
        work_types=item.work_types, special_requirements=item.special_requirements,
    )


@router.post("/projects/{project_id}/profile/activate", response_model=ProfileOut)
def activate_project_profile(
    project_id: uuid.UUID,
    current: User = Depends(require_permission("normative.confirm")),
    db: Session = Depends(get_db),
) -> ProfileOut:
    _check_project(db, current, project_id)
    profile = svc.get_or_create_profile(db, _org(db, current), project_id)
    try:
        profile = svc.activate_profile(db, profile.id, approved_by=current.id)
    except svc.NormativeError as exc:
        raise _guard(exc) from exc
    return _profile_out(db, profile)
