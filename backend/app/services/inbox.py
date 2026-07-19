"""Бизнес-логика модуля «Единый входящий поток» (§18, ROADMAP этап 5).

Сортировка входящих обращений: приём → классификация → назначение → конверсия в
задачу (или отметка иной цели) → закрытие/отклонение. Конверсия в задачу
переиспускает общий сервис `services.core.create_task` — новые задачи не
дублируются, связь ведётся идентификаторами. Все значимые действия — в
`audit_events`; изоляция по проекту (ABAC), обращения без проекта — общий контур.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Communication, InboxItem, Project, Task, User
from app.services import core as core_svc
from app.services.access import accessible_project_ids, can_access_project
from app.services.audit import record_event


class InboxError(RuntimeError):
    """Недопустимый переход состояния обращения."""


VALID_CATEGORY = (
    "request", "complaint", "inquiry", "document", "risk", "lead", "invoice", "other",
)


def can_access_item(session: Session, user: User, item: InboxItem) -> bool:
    if item.project_id is None:
        return True
    return can_access_project(session, user, item.project_id)


# ------------------------------ Приём ------------------------------------ #


def capture_item(
    session: Session, *, organization_id: uuid.UUID, user: User, subject: str | None,
    body_text: str | None, source_type: str = "manual", channel: str = "manual",
    communication_id: uuid.UUID | None = None, sender_name: str | None = None,
    sender_contact: str | None = None, counterparty_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None, external_ref: str | None = None,
) -> InboxItem:
    source_id = None
    if communication_id is not None:
        comm = session.get(Communication, communication_id)
        if comm is None or comm.organization_id != organization_id:
            raise InboxError("исходная коммуникация не найдена")
        source_id = comm.id
        source_type = "communication"
    item = InboxItem(
        organization_id=organization_id, source_type=source_type, source_id=source_id,
        communication_id=communication_id, channel=channel, external_ref=external_ref,
        subject=subject, body_text=body_text, received_at=datetime.now(UTC),
        sender_name=sender_name, sender_contact=sender_contact,
        counterparty_id=counterparty_id, project_id=project_id, status="new",
        created_by=user.id,
    )
    session.add(item)
    session.flush()
    _audit(session, user, "inbox.captured", organization_id, item.id,
           {"channel": channel, "source_type": source_type})
    session.commit()
    return item


# --------------------------- Классификация ------------------------------- #


def classify_item(
    session: Session, item: InboxItem, *, user: User, category: str,
    priority: str | None = None, project_id: uuid.UUID | None = None,
    site_id: uuid.UUID | None = None, counterparty_id: uuid.UUID | None = None,
    assigned_to_employee_id: uuid.UUID | None = None,
) -> InboxItem:
    if item.status in ("converted", "dismissed"):
        raise InboxError("обращение уже обработано")
    if category not in VALID_CATEGORY:
        raise InboxError(f"недопустимая категория '{category}'")
    item.category = category
    if priority is not None:
        item.priority = priority
    if project_id is not None:
        item.project_id = project_id
    if site_id is not None:
        item.site_id = site_id
    if counterparty_id is not None:
        item.counterparty_id = counterparty_id
    if assigned_to_employee_id is not None:
        item.assigned_to_employee_id = assigned_to_employee_id
    item.status = "classified"
    item.triaged_by_user_id = user.id
    item.triaged_at = datetime.now(UTC)
    _audit(session, user, "inbox.classified", item.organization_id, item.id,
           {"category": category, "priority": item.priority})
    session.commit()
    return item


def assign_item(
    session: Session, item: InboxItem, *, user: User, employee_id: uuid.UUID,
) -> InboxItem:
    if item.status in ("converted", "dismissed"):
        raise InboxError("обращение уже обработано")
    item.assigned_to_employee_id = employee_id
    if item.status == "new":
        item.status = "classified"
    _audit(session, user, "inbox.assigned", item.organization_id, item.id,
           {"employee_id": str(employee_id)})
    session.commit()
    return item


# ----------------------------- Конверсия --------------------------------- #


def convert_to_task(
    session: Session, item: InboxItem, *, user: User, title: str | None = None,
    description: str | None = None, priority: str | None = None,
) -> Task:
    """Создаёт поручение из обращения (переиспользует core.create_task)."""
    if item.status in ("converted", "dismissed"):
        raise InboxError("обращение уже обработано")
    if item.project_id is None:
        raise InboxError("для создания поручения укажите проект при классификации")
    project = session.get(Project, item.project_id)
    if project is None or project.deleted_at is not None:
        raise InboxError("проект не найден")
    task = core_svc.create_task(
        session, project, user=user, title=title or (item.subject or "Обращение"),
        description=description or item.body_text,
        owner_employee_id=item.assigned_to_employee_id,
        priority=priority or item.priority,
    )
    item.status = "converted"
    item.converted_entity_type = "task"
    item.converted_entity_id = task.id
    item.triaged_by_user_id = user.id
    item.triaged_at = datetime.now(UTC)
    _audit(session, user, "inbox.converted_to_task", item.organization_id, item.id,
           {"task_id": str(task.id)})
    session.commit()
    return task


def mark_converted(
    session: Session, item: InboxItem, *, user: User, entity_type: str,
    entity_id: uuid.UUID | None = None, note: str | None = None,
) -> InboxItem:
    """Отмечает обращение обработанным с иной целью (документ/заявка/риск/лид)."""
    if item.status in ("converted", "dismissed"):
        raise InboxError("обращение уже обработано")
    if entity_type not in ("document", "material_request", "risk", "lead"):
        raise InboxError("недопустимая цель конверсии")
    item.status = "converted"
    item.converted_entity_type = entity_type
    item.converted_entity_id = entity_id
    item.resolution_note = note
    item.triaged_by_user_id = user.id
    item.triaged_at = datetime.now(UTC)
    _audit(session, user, "inbox.marked_converted", item.organization_id, item.id,
           {"entity_type": entity_type})
    session.commit()
    return item


def dismiss_item(session: Session, item: InboxItem, *, user: User, reason: str) -> InboxItem:
    if item.status in ("converted", "dismissed"):
        raise InboxError("обращение уже обработано")
    item.status = "dismissed"
    item.dismissed_reason = reason
    item.triaged_by_user_id = user.id
    item.triaged_at = datetime.now(UTC)
    _audit(session, user, "inbox.dismissed", item.organization_id, item.id, {"reason": reason})
    session.commit()
    return item


# ------------------------------ Чтение ----------------------------------- #


def list_items(
    session: Session, user: User, organization_id: uuid.UUID, *, status: str | None = None,
) -> list[InboxItem]:
    allowed = accessible_project_ids(session, user)
    stmt = select(InboxItem).where(
        InboxItem.organization_id == organization_id, InboxItem.deleted_at.is_(None)
    )
    if status is not None:
        stmt = stmt.where(InboxItem.status == status)
    rows = list(session.execute(stmt.order_by(InboxItem.received_at.desc())).scalars())
    if allowed is None:
        return rows
    return [i for i in rows if i.project_id is None or i.project_id in allowed]


def summary(session: Session, user: User, organization_id: uuid.UUID) -> dict:
    items = list_items(session, user, organization_id)
    return {
        "new": sum(1 for i in items if i.status == "new"),
        "classified": sum(1 for i in items if i.status == "classified"),
        "in_progress": sum(1 for i in items if i.status == "in_progress"),
        "converted": sum(1 for i in items if i.status == "converted"),
        "dismissed": sum(1 for i in items if i.status == "dismissed"),
        "unresolved": sum(1 for i in items if i.status in ("new", "classified", "in_progress")),
    }


# ------------------------------ Помощники -------------------------------- #


def _audit(session, user, action, org_id, item_id, new_values):
    record_event(
        session, actor_type="user", action=action, actor_user_id=user.id,
        organization_id=org_id, entity_type="inbox_item", entity_id=item_id,
        new_values=new_values, risk_level="R1", commit=False,
    )
