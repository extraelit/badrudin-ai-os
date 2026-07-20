"""Бизнес-логика модуля «Исполнительная документация ПТО» (ROADMAP этап 12).

Реестр исполнительной документации с версионированием и инженерным согласованием.
Утверждение выполняет уполномоченный специалист (человек) — ИИ не подменяет
инженерную подпись. Новая версия помечает предыдущую как `superseded`. Обязательный
комплект контролируется автоматически. Все действия — в `audit_events`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Approval, ApprovalStep, ExecutiveDocument, User
from app.services.access import accessible_project_ids, can_access_project
from app.services.audit import record_event

DOC_TYPES = (
    "hidden_work_act", "as_built_scheme", "work_log", "material_certificate",
    "lab_report", "cumulative_statement", "other",
)
# обязательный комплект исполнительной документации по умолчанию
REQUIRED_SET = (
    "hidden_work_act", "as_built_scheme", "work_log", "material_certificate",
)


class ExecutiveDocError(RuntimeError):
    """Нарушение правил модуля исполнительной документации."""


def create_document(
    session: Session, *, organization_id: uuid.UUID, user: User, project_id: uuid.UUID,
    doc_type: str, title: str, number: str | None = None, description: str | None = None,
    file_id: uuid.UUID | None = None, work_item_type: str | None = None,
    work_item_id: uuid.UUID | None = None, supersedes_id: uuid.UUID | None = None,
) -> ExecutiveDocument:
    if doc_type not in DOC_TYPES:
        raise ExecutiveDocError(f"недопустимый тип документа '{doc_type}'")
    version = 1
    if supersedes_id is not None:
        prev = session.get(ExecutiveDocument, supersedes_id)
        if prev is None or prev.deleted_at is not None or prev.organization_id != organization_id:
            raise ExecutiveDocError("предыдущая версия не найдена")
        if prev.project_id != project_id:
            raise ExecutiveDocError("новая версия должна относиться к тому же объекту")
        version = prev.version_number + 1
    doc = ExecutiveDocument(
        organization_id=organization_id, project_id=project_id, doc_type=doc_type,
        number=number, title=title, description=description, file_id=file_id,
        work_item_type=work_item_type, work_item_id=work_item_id,
        version_number=version, supersedes_id=supersedes_id, status="draft",
        created_by=user.id,
    )
    session.add(doc)
    session.flush()
    _audit(session, user, "pto.document_created", organization_id, doc.id,
           {"doc_type": doc_type, "version": version})
    session.commit()
    return doc


def submit_document(session: Session, doc: ExecutiveDocument, *, user: User) -> Approval:
    """Направляет документ на инженерное согласование (§12)."""
    if doc.status not in ("draft", "rejected"):
        raise ExecutiveDocError(f"нельзя отправить на согласование из '{doc.status}'")
    if doc.file_id is None:
        raise ExecutiveDocError("к документу не приложен файл")
    approval = Approval(
        organization_id=doc.organization_id, entity_type="executive_document",
        entity_id=doc.id, approval_type="executive_document_approval",
        requested_by_user_id=user.id, status="pending", current_step=1,
    )
    session.add(approval)
    session.flush()
    doc.status = "under_review"
    doc.approval_id = approval.id
    _audit(session, user, "pto.document_submitted", doc.organization_id, doc.id, {},
           approval_id=approval.id)
    session.commit()
    return approval


def decide_document(
    session: Session, doc: ExecutiveDocument, *, user: User, decision: str,
    comment: str | None = None,
) -> ExecutiveDocument:
    """Инженерное утверждение/отклонение документа человеком.

    При утверждении предыдущая версия (supersedes) помечается `superseded`.
    """
    if decision not in ("approved", "rejected"):
        raise ExecutiveDocError("решение — approved | rejected")
    if doc.status != "under_review":
        raise ExecutiveDocError("документ не на согласовании")
    if doc.approval_id is not None:
        approval = session.get(Approval, doc.approval_id)
        approval.status = decision
        approval.completed_at = datetime.now(UTC)
        session.add(ApprovalStep(
            approval_id=approval.id, step_number=approval.current_step,
            approver_user_id=user.id, decision=decision, comment=comment,
            decided_at=datetime.now(UTC),
        ))
    doc.reviewed_by_user_id = user.id
    doc.review_comment = comment
    if decision == "approved":
        doc.status = "approved"
        doc.approved_at = datetime.now(UTC)
        if doc.supersedes_id is not None:
            prev = session.get(ExecutiveDocument, doc.supersedes_id)
            if prev is not None and prev.status != "superseded":
                prev.status = "superseded"
    else:
        doc.status = "rejected"
    _audit(session, user, f"pto.document_{decision}", doc.organization_id, doc.id,
           {"decision": decision}, approval_id=doc.approval_id)
    session.commit()
    return doc


# ------------------------------ Чтение ----------------------------------- #


def list_documents(
    session: Session, user: User, organization_id: uuid.UUID, *,
    project_id: uuid.UUID | None = None, status: str | None = None,
) -> list[ExecutiveDocument]:
    allowed = accessible_project_ids(session, user)
    stmt = select(ExecutiveDocument).where(
        ExecutiveDocument.organization_id == organization_id,
        ExecutiveDocument.deleted_at.is_(None),
    )
    if project_id is not None:
        stmt = stmt.where(ExecutiveDocument.project_id == project_id)
    if status is not None:
        stmt = stmt.where(ExecutiveDocument.status == status)
    rows = list(session.execute(
        stmt.order_by(ExecutiveDocument.created_at.desc())
    ).scalars())
    if allowed is None:
        return rows
    return [d for d in rows if d.project_id in allowed]


def can_access_document(session: Session, user: User, doc: ExecutiveDocument) -> bool:
    return can_access_project(session, user, doc.project_id)


def completeness(
    session: Session, user: User, organization_id: uuid.UUID, project_id: uuid.UUID,
) -> dict:
    """Контроль обязательного комплекта: какие типы утверждены, каких не хватает."""
    docs = list_documents(session, user, organization_id, project_id=project_id)
    approved_types = {d.doc_type for d in docs if d.status == "approved"}
    present = [t for t in REQUIRED_SET if t in approved_types]
    missing = [t for t in REQUIRED_SET if t not in approved_types]
    return {
        "required": list(REQUIRED_SET),
        "present": present,
        "missing": missing,
        "complete": len(missing) == 0,
    }


def summary(session: Session, user: User, organization_id: uuid.UUID) -> dict:
    docs = list_documents(session, user, organization_id)
    return {
        "documents_total": len(docs),
        "documents_draft": sum(1 for d in docs if d.status in ("draft", "rejected")),
        "documents_under_review": sum(1 for d in docs if d.status == "under_review"),
        "documents_approved": sum(1 for d in docs if d.status == "approved"),
        "documents_superseded": sum(1 for d in docs if d.status == "superseded"),
    }


def _audit(session, user, action, org_id, entity_id, new_values, *, approval_id=None):
    record_event(
        session, actor_type="user", action=action, actor_user_id=user.id,
        organization_id=org_id, entity_type="executive_document", entity_id=entity_id,
        new_values=new_values, approval_id=approval_id, risk_level="R2", commit=False,
    )
