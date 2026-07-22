"""Руководительские панели и эскалации (этап H, PR-H).

Сводки процессного ядра для руководителей (PROCESS_CORE_PLAN.md §4, §8): процессы,
просрочки, ожидающие согласования, запросы исключений по доказательствам, проверки
качества, ожидающие итогового решения. Всё ограничено доступными пользователю
проектами (ABAC) и организацией. Эскалации создают только внутренние (in_app)
уведомления — реальная внешняя рассылка не выполняется.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    EvidenceExceptionRequest,
    Notification,
    QualityControlCheck,
    User,
    WorkflowProcess,
)
from app.models.workflow import TERMINAL_STATUSES
from app.services import notifications as notif_svc
from app.services import workflow as wf
from app.services.access import accessible_project_ids


def _visible_processes(session: Session, user: User, org: uuid.UUID) -> list[WorkflowProcess]:
    allowed = accessible_project_ids(session, user)  # None — без ограничения
    rows = list(
        session.execute(
            select(WorkflowProcess).where(
                WorkflowProcess.organization_id == org,
                WorkflowProcess.deleted_at.is_(None),
            )
        ).scalars()
    )
    if allowed is None:
        return rows
    return [p for p in rows if p.project_id is None or p.project_id in allowed]


def manager_overview(session: Session, user: User, org: uuid.UUID) -> dict:
    """Сводка по процессам, просрочкам, согласованиям, исключениям и качеству."""
    processes = _visible_processes(session, user, org)
    by_status: dict[str, int] = {}
    overdue = 0
    for p in processes:
        by_status[p.status] = by_status.get(p.status, 0) + 1
        if wf.is_overdue(p):
            overdue += 1
    visible_ids = {p.id for p in processes}

    exceptions_pending = 0
    if visible_ids:
        exceptions_pending = len([
            x for x in session.execute(
                select(EvidenceExceptionRequest).where(
                    EvidenceExceptionRequest.status == "pending"
                )
            ).scalars()
            if x.process_id in visible_ids
        ])

    quality_pending = len(
        session.execute(
            select(QualityControlCheck.id).where(
                QualityControlCheck.organization_id == org,
                QualityControlCheck.final_decision.is_(None),
                QualityControlCheck.result.in_(("fail", "conditional")),
            )
        ).all()
    )

    return {
        "processes_total": len(processes),
        "by_status": by_status,
        "overdue": overdue,
        "pending_approval": by_status.get("pending_approval", 0),
        "submitted_for_review": by_status.get("submitted_for_review", 0),
        "blocked": by_status.get("blocked", 0),
        "evidence_exceptions_pending": exceptions_pending,
        "quality_pending_finalization": quality_pending,
    }


def overdue_processes(session: Session, user: User, org: uuid.UUID) -> list[WorkflowProcess]:
    return [p for p in _visible_processes(session, user, org) if wf.is_overdue(p)]


def pending_exceptions(
    session: Session, user: User, org: uuid.UUID
) -> list[EvidenceExceptionRequest]:
    visible_ids = {p.id for p in _visible_processes(session, user, org)}
    return [
        x for x in session.execute(
            select(EvidenceExceptionRequest).where(
                EvidenceExceptionRequest.status == "pending"
            )
        ).scalars()
        if x.process_id in visible_ids
    ]


def _already_notified(session: Session, process_id: uuid.UUID) -> bool:
    existing = session.execute(
        select(Notification.id).where(
            Notification.entity_type == "workflow_process",
            Notification.entity_id == process_id,
            Notification.status == "unread",
        )
    ).first()
    return existing is not None


def escalate_overdue(session: Session, user: User, org: uuid.UUID) -> int:
    """Создаёт внутренние уведомления по просроченным процессам их руководителям.

    Идемпотентно в пределах непрочитанных: повторный запуск не плодит дубликаты для
    одного процесса. Внешняя рассылка не выполняется (только in_app).
    """
    created = 0
    for p in overdue_processes(session, user, org):
        recipient = p.responsible_manager_id or p.initiator_user_id
        if recipient is None or _already_notified(session, p.id):
            continue
        notif_svc.create_internal(
            session, organization_id=org, user=user,
            title="Просрочен процесс", message=f"«{p.title}» просрочен",
            recipient_user_id=recipient, priority="high",
            entity_type="workflow_process", entity_id=p.id,
        )
        created += 1
    return created
