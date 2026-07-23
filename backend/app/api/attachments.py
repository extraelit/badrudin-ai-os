"""API универсальных вложений `/attachments` (PR-1).

Единая точка прикрепления файлов к любой основной сущности. Backend — единственная
точка доступа; проверки прав (RBAC) и доступа к проекту (ABAC) выполняются на
сервере. RBAC: `attachment.view` — просмотр/скачивание, `attachment.manage` —
прикрепление/архивирование. Действия фиксируются в неизменяемом аудите.
"""

from __future__ import annotations

import base64
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse, StreamingResponse

from app.api.deps import require_permission
from app.db.session import get_db
from app.models import Attachment, Employee, File, User
from app.schemas.attachment import ArchiveIn, AttachmentIn, AttachmentOut
from app.services import attachments as svc
from app.services.access import can_access_project
from sqlalchemy.orm import Session

router = APIRouter(prefix="/attachments", tags=["attachments"])


def _org(db: Session, user: User) -> uuid.UUID:
    if user.employee_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пользователь не связан с сотрудником")
    emp = db.get(Employee, user.employee_id)
    return emp.organization_id


def _check_project(db: Session, user: User, project_id: uuid.UUID | None) -> None:
    if project_id is not None and not can_access_project(db, user, project_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к проекту")


def _out(att: Attachment, file: File) -> AttachmentOut:
    return AttachmentOut(
        id=att.id, file_id=att.file_id, entity_type=att.entity_type,
        entity_id=att.entity_id, project_id=att.project_id,
        attachment_type=att.attachment_type, description=att.description,
        original_name=file.original_name, mime_type=file.mime_type,
        size_bytes=file.size_bytes, checksum_sha256=file.checksum_sha256,
        version=att.version, is_current=att.is_current, is_archived=att.is_archived,
        uploaded_by=att.uploaded_by, created_at=att.created_at,
    )


def _load(db: Session, user: User, attachment_id: uuid.UUID) -> Attachment:
    att = svc.get(db, attachment_id)
    if att is None or att.organization_id != _org(db, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Вложение не найдено")
    _check_project(db, user, att.project_id)
    return att


@router.post("/", response_model=AttachmentOut, status_code=status.HTTP_201_CREATED)
def create_attachment(
    payload: AttachmentIn,
    current: User = Depends(require_permission("attachment.manage")),
    db: Session = Depends(get_db),
) -> AttachmentOut:
    _check_project(db, current, payload.project_id)
    try:
        content = base64.b64decode(payload.content_base64, validate=True)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Некорректное содержимое (base64)") from exc
    try:
        att = svc.attach(
            db, organization_id=_org(db, current),
            entity_type=payload.entity_type, entity_id=payload.entity_id,
            original_name=payload.original_name, content=content,
            mime_type=payload.mime_type, attachment_type=payload.attachment_type,
            description=payload.description, project_id=payload.project_id,
            uploaded_by=current.id, replaces_id=payload.replaces_id,
        )
    except svc.UploadValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except svc.AttachmentError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    file = db.get(File, att.file_id)
    return _out(att, file)


@router.get("/", response_model=list[AttachmentOut])
def list_attachments(
    entity_type: str = Query(max_length=48),
    entity_id: uuid.UUID = Query(),
    include_archived: bool = Query(default=False),
    current: User = Depends(require_permission("attachment.view")),
    db: Session = Depends(get_db),
) -> list[AttachmentOut]:
    org = _org(db, current)
    rows = svc.list_for(db, entity_type, entity_id, include_archived=include_archived)
    out: list[AttachmentOut] = []
    for att in rows:
        if att.organization_id != org:
            continue
        if att.project_id is not None and not can_access_project(db, current, att.project_id):
            continue
        file = db.get(File, att.file_id)
        if file is not None:
            out.append(_out(att, file))
    return out


@router.get("/{attachment_id}/download")
def download_attachment(
    attachment_id: uuid.UUID,
    current: User = Depends(require_permission("attachment.view")),
    db: Session = Depends(get_db),
):
    att = _load(db, current, attachment_id)
    try:
        data, url, file = svc.download(db, att)
    except svc.AttachmentError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    if url is not None:
        return RedirectResponse(url)
    import io
    from urllib.parse import quote

    # Имя файла может содержать кириллицу — кодируем по RFC 5987 (filename*),
    # с ASCII-фолбэком, чтобы заголовок оставался latin-1-совместимым.
    ascii_name = file.original_name.encode("ascii", "ignore").decode() or "file"
    disposition = (
        f"attachment; filename=\"{ascii_name}\"; "
        f"filename*=UTF-8''{quote(file.original_name)}"
    )
    return StreamingResponse(
        io.BytesIO(data or b""),
        media_type=file.mime_type or "application/octet-stream",
        headers={"Content-Disposition": disposition},
    )


@router.post("/{attachment_id}/archive", response_model=AttachmentOut)
def archive_attachment(
    attachment_id: uuid.UUID, payload: ArchiveIn,
    current: User = Depends(require_permission("attachment.manage")),
    db: Session = Depends(get_db),
) -> AttachmentOut:
    att = _load(db, current, attachment_id)
    try:
        svc.archive(db, att, actor_user_id=current.id, reason=payload.reason)
    except svc.AttachmentError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    file = db.get(File, att.file_id)
    return _out(att, file)
