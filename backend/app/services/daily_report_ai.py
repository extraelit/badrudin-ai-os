"""Ежедневный отчёт объекта: ИИ-черновик и правила отправки (этап E, PR-E).

Переиспользует существующие сущности (PROCESS_CORE_PLAN.md §6, D-010):
- отчёт — `DailyReport`, медиа — `DailyReportFile`/`File` (SHA-256, метаданные);
- ИИ-черновик — честный контур `AgentProposal` (ИИ **предлагает**, но не утверждает):
  черновик создаётся со статусом `pending`; отчёт **не** переводится в approved
  автоматически — результат подтверждает ответственный сотрудник.

Правила отправки:
- отчёт нельзя отправить без фото/видео, кроме отметки «работы не велись» (с
  обязательной причиной) либо согласованного исключения уполномоченного руководителя;
- достоверность геометки/времени съёмки не гарантируется — отсутствие метаданных
  помечается как фактор риска.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AgentProposal,
    AIAgent,
    DailyReport,
    DailyReportFile,
    DailyReportWorkItem,
    File,
    Project,
)
from app.services.access import get_role_codes
from app.services.audit import record_event

# Роли, уполномоченные согласовать отправку отчёта без медиа (исключение).
MEDIA_EXCEPTION_ROLES = {
    "system_owner", "general_director", "executive_director", "chief_engineer",
}
_DRAFT_AGENT_CODE = "daily_report_drafter"


class DailyReportError(Exception):
    """Ошибка бизнес-правил ежедневного отчёта."""


def _now() -> datetime:
    return datetime.now(UTC)


def _org_of_report(session: Session, report: DailyReport) -> uuid.UUID:
    project = session.get(Project, report.project_id)
    return project.organization_id


def _get_or_create_draft_agent(session: Session, organization_id: uuid.UUID) -> AIAgent:
    agent = session.scalar(
        select(AIAgent).where(AIAgent.code == _DRAFT_AGENT_CODE)
    )
    if agent is None:
        agent = AIAgent(
            organization_id=organization_id, code=_DRAFT_AGENT_CODE,
            name="Черновик ежедневного отчёта",
            agent_type="reporting", status="active",
            requires_human_approval=True,
        )
        session.add(agent)
        session.flush()
    return agent


def _media(session: Session, report_id: uuid.UUID) -> list[DailyReportFile]:
    return list(
        session.execute(
            select(DailyReportFile).where(
                DailyReportFile.daily_report_id == report_id
            )
        ).scalars()
    )


def media_metadata_warnings(session: Session, report: DailyReport) -> list[dict]:
    """Медиа с отсутствующими метаданными — фактор риска (геометка/время не гарантированы)."""
    warnings: list[dict] = []
    for m in _media(session, report.id):
        file = session.get(File, m.file_id)
        if file is None or not file.metadata_json:
            warnings.append({
                "file_id": str(m.file_id), "kind": m.kind,
                "warning": "нет метаданных съёмки (геометка/время не подтверждены)",
            })
    return warnings


def generate_ai_draft(
    session: Session, report: DailyReport, *, actor_user_id: uuid.UUID | None = None
) -> AgentProposal:
    """Формирует ИИ-черновик отчёта как предложение (не утверждает отчёт).

    Черновик агрегирует фактические данные отчёта (медиа, объёмы) и помечает
    расхождения/отсутствие метаданных. Результат — `AgentProposal` со статусом
    `pending`; применение — только по подтверждению ответственного сотрудника.
    """
    org = _org_of_report(session, report)
    agent = _get_or_create_draft_agent(session, org)
    media = _media(session, report.id)
    photos = [m for m in media if m.kind == "photo"]
    videos = [m for m in media if m.kind == "video"]
    work_items = list(
        session.execute(
            select(DailyReportWorkItem).where(
                DailyReportWorkItem.daily_report_id == report.id
            )
        ).scalars()
    )
    warnings = media_metadata_warnings(session, report)

    # Черновик строится из фактических данных (без выдумывания): честный контур.
    parts = [
        f"Черновик отчёта за {report.report_date}.",
        f"Медиа: фото — {len(photos)}, видео — {len(videos)}.",
        f"Зафиксировано работ: {len(work_items)}.",
    ]
    if report.workers_count is not None:
        parts.append(f"Работников: {report.workers_count}.")
    if not media:
        parts.append("Внимание: фото/видео не приложены.")
    if warnings:
        parts.append(f"Медиа без метаданных: {len(warnings)} (фактор риска).")
    draft_text = " ".join(parts)

    proposal = AgentProposal(
        organization_id=org, agent_id=agent.id, project_id=report.project_id,
        proposal_type="daily_report_draft",
        title=f"Черновик ежедневного отчёта {report.report_date}",
        summary=draft_text,
        payload_json={
            "photos": len(photos), "videos": len(videos),
            "work_items": len(work_items),
            "metadata_warnings": warnings,
            "missing_media": not media,
            "confidence": "low" if (warnings or not media) else "medium",
            "sources": {
                "daily_report_id": str(report.id),
                "media_file_ids": [str(m.file_id) for m in media],
            },
        },
        risk_level="R1", status="pending",
    )
    session.add(proposal)
    session.flush()
    record_event(
        session, actor_type="agent", action="daily_report.ai_draft.generate",
        actor_agent_id=agent.id, organization_id=org,
        entity_type="daily_report", entity_id=report.id,
        new_values={"proposal_id": str(proposal.id)}, risk_level="R1", commit=True,
    )
    return proposal


def confirm_ai_draft(
    session: Session, proposal: AgentProposal, *, actor_user_id: uuid.UUID
) -> AgentProposal:
    """Подтверждение ИИ-черновика ответственным сотрудником (ИИ сам не утверждает)."""
    if proposal.status != "pending":
        raise DailyReportError("Черновик уже рассмотрен")
    proposal.status = "approved"
    proposal.decided_by_user_id = actor_user_id
    proposal.decided_at = _now()
    # применение черновика к отчёту делает человек: заполняем сводку, если пуста
    if proposal.applied_entity_id is None and proposal.payload_json:
        report_id = uuid.UUID(proposal.payload_json["sources"]["daily_report_id"])
        report = session.get(DailyReport, report_id)
        if report is not None and not report.summary:
            report.summary = proposal.summary
        proposal.applied_entity_type = "daily_report"
        proposal.applied_entity_id = report_id
    record_event(
        session, actor_type="user", action="daily_report.ai_draft.confirm",
        actor_user_id=actor_user_id, organization_id=proposal.organization_id,
        entity_type="agent_proposal", entity_id=proposal.id,
        new_values={"status": "approved"}, risk_level="R1", commit=True,
    )
    return proposal


def reject_ai_draft(
    session: Session, proposal: AgentProposal, *, actor_user_id: uuid.UUID,
    comment: str | None = None,
) -> AgentProposal:
    if proposal.status != "pending":
        raise DailyReportError("Черновик уже рассмотрен")
    proposal.status = "rejected"
    proposal.decided_by_user_id = actor_user_id
    proposal.decided_at = _now()
    proposal.decision_comment = comment
    record_event(
        session, actor_type="user", action="daily_report.ai_draft.reject",
        actor_user_id=actor_user_id, organization_id=proposal.organization_id,
        entity_type="agent_proposal", entity_id=proposal.id,
        new_values={"status": "rejected"}, reason=comment, risk_level="R1", commit=True,
    )
    return proposal


def mark_no_work(
    session: Session, report: DailyReport, *, reason: str, actor_user_id: uuid.UUID
) -> DailyReport:
    """Отмечает отчёт «Работы не велись» с обязательной причиной."""
    if not reason or not reason.strip():
        raise DailyReportError("Отметка «работы не велись» требует причины")
    report.no_work = True
    report.no_work_reason = reason
    record_event(
        session, actor_type="user", action="daily_report.no_work",
        actor_user_id=actor_user_id, organization_id=_org_of_report(session, report),
        entity_type="daily_report", entity_id=report.id,
        new_values={"no_work": True}, reason=reason, risk_level="R1", commit=True,
    )
    return report


def submit_report(
    session: Session, report: DailyReport, *, actor_user_id: uuid.UUID
) -> DailyReport:
    """Отправка отчёта: требует медиа либо отметки «работы не велись»."""
    if report.status not in ("draft", "correction_required"):
        raise DailyReportError("Отчёт нельзя отправить из текущего статуса")
    if not report.no_work and not _media(session, report.id):
        raise DailyReportError(
            "Нельзя отправить отчёт без фото/видео. Приложите медиа, отметьте "
            "«работы не велись» с причиной либо оформите согласованное исключение."
        )
    report.status = "submitted"
    report.submitted_at = _now()
    record_event(
        session, actor_type="user", action="daily_report.submit",
        actor_user_id=actor_user_id, organization_id=_org_of_report(session, report),
        entity_type="daily_report", entity_id=report.id,
        new_values={"status": "submitted", "no_work": report.no_work},
        risk_level="R1", commit=True,
    )
    return report


def submit_without_media_exception(
    session: Session, report: DailyReport, *, actor_user_id: uuid.UUID, reason: str
) -> DailyReport:
    """Исключение: отправка без медиа по согласованию уполномоченного руководителя.

    Только роль ген./исп. директора (или главного инженера) с обязательной причиной;
    результат помечается как «отправлен без стандартного медиа» в неизменяемом аудите.
    """
    if report.status not in ("draft", "correction_required"):
        raise DailyReportError("Отчёт нельзя отправить из текущего статуса")
    if not reason or not reason.strip():
        raise DailyReportError("Исключение требует причины")
    roles = get_role_codes(session, actor_user_id)
    if not (roles & MEDIA_EXCEPTION_ROLES):
        raise DailyReportError(
            "Отправку без медиа согласует только уполномоченный руководитель"
        )
    report.status = "submitted"
    report.submitted_at = _now()
    record_event(
        session, actor_type="user", action="daily_report.submit_exception",
        actor_user_id=actor_user_id, organization_id=_org_of_report(session, report),
        entity_type="daily_report", entity_id=report.id,
        new_values={"status": "submitted", "submitted_without_standard_media": True},
        reason=reason, risk_level="R2", commit=True,
    )
    return report
