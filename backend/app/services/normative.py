"""Сервис нормативного реестра и нормативного профиля проекта (этап 1).

Инварианты (NORMATIVE_ACCESS_AND_INTEGRITY_PLAN.md §1–2):
- новая запись реестра создаётся со статусом `needs_review` — система не
  подтверждает актуальность редакции сама, даже если вызывающая сторона просит
  иной статус;
- перевод в `in_force` (и иные статусы) — действие уполномоченного лица, всегда
  фиксируется в аудите с указанием проверяющего и комментария;
- при изменении нормы прежние записи не переписываются и не удаляются (архивация,
  а не удаление) — сохраняется историческая привязка отчётов к редакции;
- применимость норматива к проекту (профиль) подтверждает человек, не система.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import (
    NormativeDocument,
    ProjectNormativeItem,
    ProjectNormativeProfile,
)
from app.models.normative import DOC_KINDS, DOC_STATUSES
from app.services.audit import record_event

# Статусы, устанавливаемые уполномоченным лицом (кроме служебного needs_review).
_CONFIRMABLE_STATUSES = ("in_force", "amended", "superseded", "repealed")


class NormativeError(Exception):
    """Нарушение правил работы с нормативным реестром/профилем."""


def _now() -> datetime:
    return datetime.now(UTC)


def create_document(
    session: Session,
    organization_id: uuid.UUID,
    *,
    full_title: str,
    doc_kind: str,
    number: str | None = None,
    edition: str | None = None,
    amendment_no: str | None = None,
    official_source_url: str | None = None,
    scope: str | None = None,
    work_types: list | None = None,
    object_types: list | None = None,
    related_control_ops: list | None = None,
    responsible_user_id: uuid.UUID | None = None,
    created_by: uuid.UUID | None = None,
) -> NormativeDocument:
    """Вносит документ в реестр строго со статусом `needs_review`.

    Актуальность редакции система не подтверждает — это делает уполномоченное лицо
    отдельным действием (`confirm_status`).
    """
    if doc_kind not in DOC_KINDS:
        raise NormativeError(f"Недопустимый вид документа: {doc_kind}")
    doc = NormativeDocument(
        organization_id=organization_id,
        full_title=full_title,
        doc_kind=doc_kind,
        number=number,
        edition=edition,
        amendment_no=amendment_no,
        official_source_url=official_source_url,
        scope=scope,
        work_types=work_types,
        object_types=object_types,
        related_control_ops=related_control_ops,
        responsible_user_id=responsible_user_id,
        status="needs_review",  # инвариант: система не считает редакцию актуальной
    )
    session.add(doc)
    session.flush()
    record_event(
        session,
        actor_type="user",
        action="normative.document.create",
        actor_user_id=created_by,
        organization_id=organization_id,
        entity_type="normative_document",
        entity_id=doc.id,
        new_values={"status": "needs_review", "doc_kind": doc_kind},
        risk_level="R1",
        commit=True,
    )
    return doc


def confirm_status(
    session: Session,
    document_id: uuid.UUID,
    new_status: str,
    *,
    reviewer_user_id: uuid.UUID,
    comment: str | None = None,
) -> NormativeDocument:
    """Устанавливает статус актуальности документа уполномоченным лицом.

    Допустимые целевые статусы: in_force | amended | superseded | repealed.
    Фиксирует проверяющего, время проверки и комментарий; пишет аудит. Прежние
    записи и отчёты не переписываются (историческая привязка сохраняется).
    """
    if new_status not in _CONFIRMABLE_STATUSES:
        raise NormativeError(
            f"Статус '{new_status}' не устанавливается вручную "
            f"(допустимо: {', '.join(_CONFIRMABLE_STATUSES)})"
        )
    doc = session.get(NormativeDocument, document_id)
    if doc is None or doc.deleted_at is not None:
        raise NormativeError("Нормативный документ не найден")
    old_status = doc.status
    doc.status = new_status
    doc.responsible_user_id = reviewer_user_id
    doc.last_checked_at = _now()
    if comment is not None:
        doc.reviewer_comment = comment
    record_event(
        session,
        actor_type="user",
        action="normative.document.confirm_status",
        actor_user_id=reviewer_user_id,
        organization_id=doc.organization_id,
        entity_type="normative_document",
        entity_id=doc.id,
        old_values={"status": old_status},
        new_values={"status": new_status},
        reason=comment,
        risk_level="R2",
        commit=True,
    )
    return doc


def archive_document(
    session: Session,
    document_id: uuid.UUID,
    *,
    actor_user_id: uuid.UUID | None = None,
) -> NormativeDocument:
    """Архивирует документ (не удаляет) — сохранение истории применения."""
    doc = session.get(NormativeDocument, document_id)
    if doc is None:
        raise NormativeError("Нормативный документ не найден")
    doc.is_archived = True
    record_event(
        session,
        actor_type="user",
        action="normative.document.archive",
        actor_user_id=actor_user_id,
        organization_id=doc.organization_id,
        entity_type="normative_document",
        entity_id=doc.id,
        new_values={"is_archived": True},
        risk_level="R1",
        commit=True,
    )
    return doc


# --- Нормативный профиль проекта -------------------------------------------


def get_or_create_profile(
    session: Session,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
) -> ProjectNormativeProfile:
    """Возвращает профиль проекта, создавая его при отсутствии (один на проект)."""
    profile = (
        session.query(ProjectNormativeProfile)
        .filter(ProjectNormativeProfile.project_id == project_id)
        .first()
    )
    if profile is None:
        profile = ProjectNormativeProfile(
            organization_id=organization_id, project_id=project_id, status="draft"
        )
        session.add(profile)
        session.flush()
    return profile


def add_profile_item(
    session: Session,
    profile_id: uuid.UUID,
    normative_document_id: uuid.UUID,
    *,
    applicable_edition: str | None = None,
    mandatory: bool = True,
    work_types: list | None = None,
    special_requirements: str | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> ProjectNormativeItem:
    """Добавляет норматив в профиль проекта (применимость подтверждает человек)."""
    profile = session.get(ProjectNormativeProfile, profile_id)
    if profile is None:
        raise NormativeError("Профиль проекта не найден")
    doc = session.get(NormativeDocument, normative_document_id)
    if doc is None or doc.organization_id != profile.organization_id:
        raise NormativeError("Нормативный документ не найден в организации")
    exists = (
        session.query(ProjectNormativeItem)
        .filter(
            ProjectNormativeItem.profile_id == profile_id,
            ProjectNormativeItem.normative_document_id == normative_document_id,
        )
        .first()
    )
    if exists is not None:
        raise NormativeError("Норматив уже включён в профиль проекта")
    item = ProjectNormativeItem(
        profile_id=profile_id,
        normative_document_id=normative_document_id,
        applicable_edition=applicable_edition,
        mandatory=mandatory,
        work_types=work_types,
        special_requirements=special_requirements,
    )
    session.add(item)
    session.flush()
    record_event(
        session,
        actor_type="user",
        action="normative.profile.item_add",
        actor_user_id=actor_user_id,
        organization_id=profile.organization_id,
        entity_type="project_normative_profile",
        entity_id=profile_id,
        new_values={"normative_document_id": str(normative_document_id)},
        risk_level="R1",
        commit=True,
    )
    return item


def activate_profile(
    session: Session,
    profile_id: uuid.UUID,
    *,
    approved_by: uuid.UUID,
) -> ProjectNormativeProfile:
    """Активирует нормативный профиль проекта (подтверждение уполномоченным лицом)."""
    profile = session.get(ProjectNormativeProfile, profile_id)
    if profile is None:
        raise NormativeError("Профиль проекта не найден")
    profile.status = "active"
    profile.approved_by = approved_by
    profile.approved_at = _now()
    record_event(
        session,
        actor_type="user",
        action="normative.profile.activate",
        actor_user_id=approved_by,
        organization_id=profile.organization_id,
        entity_type="project_normative_profile",
        entity_id=profile.id,
        new_values={"status": "active"},
        risk_level="R2",
        commit=True,
    )
    return profile
