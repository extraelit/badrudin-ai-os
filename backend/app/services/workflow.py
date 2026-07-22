"""Сервис процессного ядра: жизненный цикл и инварианты (этап D, PR-D1).

Единый жизненный цикл (PROCESS_CORE_PLAN.md §1.2):

    draft → pending_approval → approved → assigned → accepted → in_progress
         → submitted_for_review → (revision_required → in_progress) | completed → archived

Инварианты (проверяются на backend, §1.3):
- назначение делает постановщик/руководитель, а не сам исполнитель;
- переход в `accepted` — только назначенный исполнитель (фиксируются дата/пользователь);
- закрытие R2–R4 — независимая проверка (SoD): исполнитель не закрывает сам;
- перенос срока требует причины; для R3–R4 — согласование руководителя;
- терминальные состояния далее допускают только архивирование (не удаление);
- `overdue` — вычисляемый признак, не хранится.

Все значимые переходы фиксируются в `AuditEvent`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import WorkflowProcess
from app.models.workflow import (
    DEFAULT_RISK_BY_KIND,
    PROCESS_KINDS,
    RISK_LEVELS,
    TERMINAL_STATUSES,
)
from app.services.audit import record_event


class WorkflowError(Exception):
    """Нарушение правил процессного ядра (недопустимый переход, права, SoD)."""


def _now() -> datetime:
    return datetime.now(UTC)


def _as_aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def is_overdue(process: WorkflowProcess, *, now: datetime | None = None) -> bool:
    """Вычисляемый признак просрочки (не хранится в модели)."""
    if process.status in TERMINAL_STATUSES:
        return False
    due = _as_aware(process.due_at)
    if due is None:
        return False
    return due < (now or _now())


def _needs_manager_approval_for_reschedule(process: WorkflowProcess) -> bool:
    # R3–R4 либо повторный перенос требуют согласования руководителя (§1.3)
    return process.risk_level in ("R3", "R4") or process.reschedule_count >= 1


def _audit(session, process, action, actor, *, old=None, new=None, reason=None,
           risk="R1"):
    record_event(
        session, actor_type="user", action=action, actor_user_id=actor,
        organization_id=process.organization_id, entity_type="workflow_process",
        entity_id=process.id, old_values=old, new_values=new, reason=reason,
        risk_level=risk, commit=True,
    )


def create_process(
    session: Session,
    organization_id: uuid.UUID,
    *,
    process_kind: str,
    title: str,
    author_user_id: uuid.UUID | None = None,
    initiator_user_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    risk_level: str | None = None,
    description: str | None = None,
    due_at: datetime | None = None,
) -> WorkflowProcess:
    """Создаёт процесс в статусе `draft`. Уровень риска — по виду, если не задан."""
    if process_kind not in PROCESS_KINDS:
        raise WorkflowError(f"Недопустимый вид процесса: {process_kind}")
    level = risk_level or DEFAULT_RISK_BY_KIND.get(process_kind, "R1")
    if level not in RISK_LEVELS:
        raise WorkflowError(f"Недопустимый уровень риска: {level}")
    proc = WorkflowProcess(
        organization_id=organization_id, project_id=project_id,
        process_kind=process_kind, title=title, description=description,
        risk_level=level, status="draft",
        author_user_id=author_user_id,
        initiator_user_id=initiator_user_id or author_user_id,
        due_at=due_at,
    )
    session.add(proc)
    session.flush()
    _audit(session, proc, "process.create", author_user_id,
           new={"kind": process_kind, "risk": level})
    return proc


def _require_status(process: WorkflowProcess, allowed: tuple[str, ...]) -> None:
    if process.status not in allowed:
        raise WorkflowError(
            f"Недопустимый переход из статуса '{process.status}'"
        )


def submit_for_approval(session, process, *, actor_user_id):
    _require_status(process, ("draft",))
    process.status = "pending_approval"
    _audit(session, process, "process.submit_approval", actor_user_id,
           new={"status": "pending_approval"})
    return process


def approve(session, process, *, approver_user_id):
    """Согласование. Для R3–R4 согласующий не может быть автором (независимость)."""
    _require_status(process, ("pending_approval",))
    if process.risk_level in ("R3", "R4") and approver_user_id == process.author_user_id:
        raise WorkflowError("Согласующий не может совпадать с автором для R3–R4")
    process.status = "approved"
    _audit(session, process, "process.approve", approver_user_id,
           new={"status": "approved"}, risk="R2")
    return process


def reject(session, process, *, approver_user_id, reason: str | None = None):
    _require_status(process, ("pending_approval",))
    process.status = "rejected"
    _audit(session, process, "process.reject", approver_user_id,
           new={"status": "rejected"}, reason=reason, risk="R2")
    return process


def assign(session, process, *, initiator_user_id, executor_id,
           responsible_manager_id=None, due_at=None):
    """Назначение исполнителя постановщиком/руководителем (не самим исполнителем)."""
    _require_status(process, ("draft", "approved"))
    # R1 можно назначать напрямую из draft; R2+ — только после approved
    if process.status == "draft" and process.risk_level != "R1":
        raise WorkflowError("Процесс уровня R2+ требует согласования до назначения")
    if executor_id == initiator_user_id:
        raise WorkflowError("Постановщик не может назначить исполнителем себя")
    process.status = "assigned"
    process.primary_executor_id = executor_id
    if responsible_manager_id is not None:
        process.responsible_manager_id = responsible_manager_id
    if due_at is not None:
        process.due_at = due_at
    _audit(session, process, "process.assign", initiator_user_id,
           new={"status": "assigned", "executor": str(executor_id)})
    return process


def accept(session, process, *, actor_user_id):
    """Принятие в работу — только назначенным исполнителем (фиксация даты/пользователя)."""
    _require_status(process, ("assigned",))
    if actor_user_id != process.primary_executor_id:
        raise WorkflowError("Принять процесс в работу может только назначенный исполнитель")
    process.status = "accepted"
    process.accepted_at = _now()
    _audit(session, process, "process.accept", actor_user_id,
           new={"status": "accepted", "accepted_at": process.accepted_at.isoformat()})
    return process


def start(session, process, *, actor_user_id):
    _require_status(process, ("accepted", "revision_required"))
    if actor_user_id != process.primary_executor_id:
        raise WorkflowError("Начать работу может только исполнитель")
    process.status = "in_progress"
    _audit(session, process, "process.start", actor_user_id,
           new={"status": "in_progress"})
    return process


def submit_for_review(session, process, *, actor_user_id, executor_comment=None):
    _require_status(process, ("in_progress",))
    if actor_user_id != process.primary_executor_id:
        raise WorkflowError("Отправить на проверку может только исполнитель")
    process.status = "submitted_for_review"
    process.submitted_at = _now()
    if executor_comment is not None:
        process.executor_comment = executor_comment
    _audit(session, process, "process.submit_review", actor_user_id,
           new={"status": "submitted_for_review"})
    return process


def review(session, process, *, reviewer_user_id, decision: str,
           comment: str | None = None):
    """Проверка результата. Для R2–R4 — независимая (SoD): проверяющий ≠ исполнитель."""
    _require_status(process, ("submitted_for_review",))
    if decision not in ("completed", "revision_required"):
        raise WorkflowError("Решение проверки: completed | revision_required")
    if process.risk_level != "R1" and reviewer_user_id == process.primary_executor_id:
        raise WorkflowError(
            "Проверять результат R2–R4 должен независимый сотрудник (не исполнитель)"
        )
    process.reviewer_comment = comment
    if decision == "completed":
        process.status = "completed"
        process.completed_at = _now()
    else:
        process.status = "revision_required"
    _audit(session, process, "process.review", reviewer_user_id,
           new={"status": process.status}, reason=comment, risk="R2")
    return process


def reschedule(session, process, *, actor_user_id, new_due_at, reason: str,
               approved_by_manager: bool = False):
    """Перенос срока: причина обязательна; для R3–R4/повтора — согласование руководителя."""
    if process.status in TERMINAL_STATUSES:
        raise WorkflowError("Нельзя перенести срок терминального процесса")
    if not reason or not reason.strip():
        raise WorkflowError("Перенос срока требует указания причины")
    if _needs_manager_approval_for_reschedule(process) and not approved_by_manager:
        raise WorkflowError("Перенос требует согласования руководителя (R3–R4/повтор)")
    old_due = process.due_at.isoformat() if process.due_at else None
    process.due_at = new_due_at
    process.reschedule_count += 1
    _audit(session, process, "process.reschedule", actor_user_id,
           old={"due_at": old_due},
           new={"due_at": new_due_at.isoformat(), "count": process.reschedule_count},
           reason=reason, risk="R2")
    return process


def change_executor(session, process, *, actor_user_id, new_executor_id, reason: str):
    """Смена исполнителя (в аудит)."""
    if process.status in TERMINAL_STATUSES:
        raise WorkflowError("Нельзя сменить исполнителя терминального процесса")
    if not reason or not reason.strip():
        raise WorkflowError("Смена исполнителя требует указания причины")
    old = str(process.primary_executor_id) if process.primary_executor_id else None
    process.primary_executor_id = new_executor_id
    # смена исполнителя возвращает процесс к назначению (требуется принятие заново)
    if process.status in ("accepted", "in_progress"):
        process.status = "assigned"
    _audit(session, process, "process.change_executor", actor_user_id,
           old={"executor": old}, new={"executor": str(new_executor_id)},
           reason=reason, risk="R2")
    return process


def block(session, process, *, actor_user_id, reason: str):
    if process.status in TERMINAL_STATUSES:
        raise WorkflowError("Нельзя заблокировать терминальный процесс")
    process.blocked_reason = reason
    process.status = "blocked"
    _audit(session, process, "process.block", actor_user_id,
           new={"status": "blocked"}, reason=reason)
    return process


def cancel(session, process, *, actor_user_id, reason: str | None = None):
    if process.status in TERMINAL_STATUSES:
        raise WorkflowError("Процесс уже в терминальном состоянии")
    process.status = "cancelled"
    _audit(session, process, "process.cancel", actor_user_id,
           new={"status": "cancelled"}, reason=reason, risk="R2")
    return process


def archive(session, process, *, actor_user_id):
    """Архивирование (вместо удаления). Допустимо из терминальных состояний."""
    if process.status not in ("completed", "cancelled", "rejected"):
        raise WorkflowError("Архивировать можно только завершённый/отменённый/отклонённый процесс")
    process.status = "archived"
    process.archived_at = _now()
    process.is_archived = True
    _audit(session, process, "process.archive", actor_user_id,
           new={"status": "archived"})
    return process
