"""Сервис Evidence Gate: доказательства, матрица требований, исключения (PR-D2).

Правило гейта (PROCESS_CORE_PLAN.md §2.2): отправка на проверку и завершение
процесса запрещены, пока не приложены все обязательные доказательства по матрице
его вида — либо по недостающему типу утверждён запрос на исключение.

Исключение (§2.3) нельзя «просто отметить»: требуется причина и согласование
уполномоченного руководителя (ген./исп. директор; для технических вопросов —
дополнительно главный инженер). Решение и причина фиксируются в аудите; результат
помечается как «принят без стандартного доказательства».
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    EvidenceExceptionRequest,
    EvidenceRequirement,
    File,
    ProcessEvidence,
    WorkflowProcess,
)
from app.models.evidence import EVIDENCE_PHASES, EVIDENCE_TYPES
from app.services.access import get_role_codes
from app.services.audit import record_event

# Роли, уполномоченные согласовывать исключения по доказательствам.
EXCEPTION_APPROVER_ROLES = {
    "system_owner", "general_director", "executive_director", "chief_engineer",
}


class EvidenceError(Exception):
    """Ошибка работы с доказательствами (валидация, права)."""


class EvidenceGateError(Exception):
    """Гейт доказательств не пройден: не приложены обязательные доказательства."""

    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        super().__init__(
            "Нельзя завершить процесс без обязательных доказательств: "
            + ", ".join(missing)
        )


def _now() -> datetime:
    return datetime.now(UTC)


# --- Матрица требований -----------------------------------------------------


def set_requirement(
    session: Session,
    organization_id: uuid.UUID,
    *,
    process_kind: str,
    evidence_type: str,
    required: bool = True,
    min_count: int = 1,
    phase: str = "after",
    condition: str | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> EvidenceRequirement:
    """Задаёт/обновляет требование к доказательству для вида процесса."""
    if evidence_type not in EVIDENCE_TYPES:
        raise EvidenceError(f"Недопустимый тип доказательства: {evidence_type}")
    if phase not in EVIDENCE_PHASES:
        raise EvidenceError(f"Недопустимая фаза: {phase}")
    row = session.scalar(
        select(EvidenceRequirement).where(
            EvidenceRequirement.organization_id == organization_id,
            EvidenceRequirement.process_kind == process_kind,
            EvidenceRequirement.evidence_type == evidence_type,
        )
    )
    if row is None:
        row = EvidenceRequirement(
            organization_id=organization_id, process_kind=process_kind,
            evidence_type=evidence_type,
        )
        session.add(row)
    row.required = required
    row.min_count = min_count
    row.phase = phase
    row.condition = condition
    session.flush()
    record_event(
        session, actor_type="user", action="evidence.requirement.set",
        actor_user_id=actor_user_id, organization_id=organization_id,
        entity_type="evidence_requirement", entity_id=row.id,
        new_values={"process_kind": process_kind, "evidence_type": evidence_type,
                    "required": required, "min_count": min_count},
        risk_level="R1", commit=True,
    )
    return row


def list_requirements(
    session: Session, organization_id: uuid.UUID, process_kind: str
) -> list[EvidenceRequirement]:
    return list(
        session.execute(
            select(EvidenceRequirement).where(
                EvidenceRequirement.organization_id == organization_id,
                EvidenceRequirement.process_kind == process_kind,
            )
        ).scalars()
    )


# --- Доказательства процесса ------------------------------------------------


def add_evidence(
    session: Session,
    process: WorkflowProcess,
    *,
    evidence_type: str,
    file_id: uuid.UUID,
    note: str | None = None,
    captured_phase: str | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> ProcessEvidence:
    """Прикладывает доказательство (файл обязателен и принадлежит организации)."""
    if evidence_type not in EVIDENCE_TYPES:
        raise EvidenceError(f"Недопустимый тип доказательства: {evidence_type}")
    file = session.get(File, file_id)
    if file is None or file.deleted_at is not None:
        raise EvidenceError("Файл доказательства не найден")
    if file.organization_id != process.organization_id:
        raise EvidenceError("Файл принадлежит другой организации")
    ev = ProcessEvidence(
        process_id=process.id, evidence_type=evidence_type, file_id=file_id,
        note=note, captured_phase=captured_phase, added_by=actor_user_id,
        added_at=_now(),
    )
    session.add(ev)
    session.flush()
    record_event(
        session, actor_type="user", action="evidence.add",
        actor_user_id=actor_user_id, organization_id=process.organization_id,
        entity_type="workflow_process", entity_id=process.id,
        new_values={"evidence_type": evidence_type, "file_id": str(file_id)},
        risk_level="R1", commit=True,
    )
    return ev


# --- Гейт: недостающие обязательные доказательства --------------------------


def _approved_exception_types(session: Session, process_id: uuid.UUID) -> set[str]:
    rows = session.execute(
        select(EvidenceExceptionRequest.evidence_type).where(
            EvidenceExceptionRequest.process_id == process_id,
            EvidenceExceptionRequest.status == "approved",
        )
    ).all()
    return {r[0] for r in rows}


def missing_required(session: Session, process: WorkflowProcess) -> list[str]:
    """Список типов обязательных доказательств, которых не хватает.

    Тип считается закрытым, если приложено не менее `min_count` доказательств
    этого типа ИЛИ по нему утверждён запрос на исключение.
    """
    reqs = [
        r for r in list_requirements(session, process.organization_id, process.process_kind)
        if r.required
    ]
    if not reqs:
        return []
    approved = _approved_exception_types(session, process.id)
    missing: list[str] = []
    for r in reqs:
        if r.evidence_type in approved:
            continue
        count = session.scalar(
            select(func.count(ProcessEvidence.id)).where(
                ProcessEvidence.process_id == process.id,
                ProcessEvidence.evidence_type == r.evidence_type,
            )
        ) or 0
        # Универсальные вложения к процессу тоже засчитываются гейтом: реальный
        # приложенный файл нужного типа (актуальный, не архивный) закрывает
        # требование (PR-1: Evidence Gate учитывает реальные вложения).
        count += _attachment_count(session, process.id, r.evidence_type)
        if count < r.min_count:
            missing.append(r.evidence_type)
    return missing


def _attachment_count(
    session: Session, process_id: uuid.UUID, evidence_type: str
) -> int:
    """Число актуальных (не архивных) вложений процесса указанного типа."""
    from app.models import Attachment  # локальный импорт: избегаем цикла

    return session.scalar(
        select(func.count(Attachment.id)).where(
            Attachment.entity_type == "workflow_process",
            Attachment.entity_id == process_id,
            Attachment.attachment_type == evidence_type,
            Attachment.is_archived.is_(False),
            Attachment.is_current.is_(True),
            Attachment.deleted_at.is_(None),
        )
    ) or 0


def assert_gate_satisfied(session: Session, process: WorkflowProcess) -> None:
    """Бросает EvidenceGateError, если не приложены обязательные доказательства."""
    missing = missing_required(session, process)
    if missing:
        raise EvidenceGateError(missing)


# --- Запросы на исключение --------------------------------------------------


def request_exception(
    session: Session,
    process: WorkflowProcess,
    *,
    evidence_type: str,
    reason: str,
    requested_by: uuid.UUID | None = None,
) -> EvidenceExceptionRequest:
    """Создаёт запрос на исключение по недостающему доказательству (причина обязательна)."""
    if not reason or not reason.strip():
        raise EvidenceError("Для исключения необходимо указать причину")
    req = EvidenceExceptionRequest(
        process_id=process.id, evidence_type=evidence_type, reason=reason,
        status="pending", requested_by=requested_by,
    )
    session.add(req)
    session.flush()
    record_event(
        session, actor_type="user", action="evidence.exception.request",
        actor_user_id=requested_by, organization_id=process.organization_id,
        entity_type="workflow_process", entity_id=process.id,
        new_values={"evidence_type": evidence_type}, reason=reason,
        risk_level="R2", commit=True,
    )
    return req


def decide_exception(
    session: Session,
    request: EvidenceExceptionRequest,
    *,
    approver_user_id: uuid.UUID,
    approve: bool,
    comment: str | None = None,
) -> EvidenceExceptionRequest:
    """Решение по исключению — только уполномоченный руководитель (ген./исп. директор).

    При одобрении результат помечается «принят без стандартного доказательства»
    (учитывается гейтом). Решение, причина и согласующий — в неизменяемом аудите.
    """
    if request.status != "pending":
        raise EvidenceError("Запрос на исключение уже рассмотрен")
    roles = get_role_codes(session, approver_user_id)
    if not (roles & EXCEPTION_APPROVER_ROLES):
        raise EvidenceError(
            "Исключение согласует только уполномоченный руководитель "
            "(генеральный/исполнительный директор)"
        )
    request.status = "approved" if approve else "rejected"
    request.decided_by = approver_user_id
    request.decided_at = _now()
    request.decision_comment = comment
    process = session.get(WorkflowProcess, request.process_id)
    record_event(
        session, actor_type="user", action="evidence.exception.decide",
        actor_user_id=approver_user_id,
        organization_id=process.organization_id if process else None,
        entity_type="workflow_process", entity_id=request.process_id,
        old_values={"status": "pending"},
        new_values={"status": request.status, "evidence_type": request.evidence_type,
                    "accepted_without_standard_evidence": request.status == "approved"},
        reason=comment, risk_level="R3", commit=True,
    )
    return request


def list_evidence(session: Session, process_id: uuid.UUID) -> list[ProcessEvidence]:
    return list(
        session.execute(
            select(ProcessEvidence).where(ProcessEvidence.process_id == process_id)
        ).scalars()
    )


def list_exceptions(
    session: Session, process_id: uuid.UUID
) -> list[EvidenceExceptionRequest]:
    return list(
        session.execute(
            select(EvidenceExceptionRequest).where(
                EvidenceExceptionRequest.process_id == process_id
            )
        ).scalars()
    )
