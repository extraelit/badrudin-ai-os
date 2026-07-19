"""Оркестрация ИИ-агентов и человеческий контроль (ROADMAP этап 6, AGENTS.md §2/§15).

Контур управления: реестр агентов (`ai_agents`) → запуски (`agent_runs`) →
предложения агента (`agent_proposals`), каждое из которых **не имеет силы до
утверждения человеком** (человек принимает окончательное решение). Утверждённое
предложение применяется через общие сервисы (например, создание задачи
`services.core.create_task`) — сущности не дублируются.

Важно (D-010, CLAUDE.md §5): модуль реализует governance-контур и журнал запусков.
Фактический вызов языковой модели выполняется отдельным утверждённым коннектором и
здесь НЕ производится: вход и результат запуска фиксируются как данные, а
предложения проходят человеческое утверждение. Всё — в `audit_events`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AgentProposal, AgentRun, AIAgent, Project, Task, User
from app.services import core as core_svc
from app.services.access import can_access_project
from app.services.audit import record_event


class AgentError(RuntimeError):
    """Нарушение правил оркестрации агентов."""


PROPOSAL_TYPES = ("task", "document", "warning", "material_request", "risk", "note")


# ------------------------------ Реестр ----------------------------------- #


def register_agent(
    session: Session, *, organization_id: uuid.UUID, user: User, code: str, name: str,
    agent_type: str | None = None, description: str | None = None,
    default_risk_level: str = "R1", requires_human_approval: bool = True,
) -> AIAgent:
    existing = session.execute(select(AIAgent).where(AIAgent.code == code)).scalars().first()
    if existing is not None:
        raise AgentError(f"агент с кодом '{code}' уже существует")
    agent = AIAgent(
        organization_id=organization_id, code=code, name=name, agent_type=agent_type,
        description=description, default_risk_level=default_risk_level,
        requires_human_approval=requires_human_approval, status="inactive",
    )
    session.add(agent)
    session.flush()
    _audit(session, user, "agent.registered", organization_id, "ai_agent", agent.id,
           {"code": code, "name": name})
    session.commit()
    return agent


def set_agent_status(session: Session, agent: AIAgent, *, user: User, status: str) -> AIAgent:
    if status not in ("active", "inactive", "suspended"):
        raise AgentError(f"недопустимый статус '{status}'")
    agent.status = status
    _audit(session, user, "agent.status_changed", agent.organization_id, "ai_agent",
           agent.id, {"status": status})
    session.commit()
    return agent


# ------------------------------ Запуски ---------------------------------- #


def create_run(
    session: Session, agent: AIAgent, *, user: User, trigger_type: str = "manual",
    input_summary: str | None = None, project_id: uuid.UUID | None = None,
) -> AgentRun:
    if agent.status != "active":
        raise AgentError("запуск возможен только для активного агента")
    run = AgentRun(
        agent_id=agent.id, organization_id=agent.organization_id, project_id=project_id,
        initiated_by_user_id=user.id, trigger_type=trigger_type,
        input_summary=input_summary, status="pending", risk_level=agent.default_risk_level,
        started_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()
    _audit(session, user, "agent.run_created", agent.organization_id, "agent_run", run.id,
           {"agent": agent.code, "trigger": trigger_type})
    session.commit()
    return run


def record_run_result(
    session: Session, run: AgentRun, *, user: User, status: str,
    output_summary: str | None = None, error_message: str | None = None,
) -> AgentRun:
    """Фиксирует результат запуска (данные, полученные из коннектора агента)."""
    if status not in ("completed", "failed"):
        raise AgentError("результат запуска — completed | failed")
    run.status = status
    run.output_summary = output_summary
    run.error_message = error_message
    run.finished_at = datetime.now(UTC)
    _audit(session, user, f"agent.run_{status}", run.organization_id, "agent_run", run.id, {})
    session.commit()
    return run


# ---------------------------- Предложения -------------------------------- #


def add_proposal(
    session: Session, agent: AIAgent, *, user: User, proposal_type: str, title: str,
    summary: str | None = None, run_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None, risk_level: str | None = None,
    payload: dict | None = None,
) -> AgentProposal:
    if proposal_type not in PROPOSAL_TYPES:
        raise AgentError(f"недопустимый тип предложения '{proposal_type}'")
    proposal = AgentProposal(
        organization_id=agent.organization_id, agent_id=agent.id, run_id=run_id,
        project_id=project_id, proposal_type=proposal_type, title=title, summary=summary,
        payload_json=payload, risk_level=risk_level or agent.default_risk_level,
        status="pending",
    )
    session.add(proposal)
    session.flush()
    _audit(session, user, "agent.proposal_created", agent.organization_id,
           "agent_proposal", proposal.id, {"type": proposal_type, "title": title})
    session.commit()
    return proposal


def review_proposal(
    session: Session, proposal: AgentProposal, *, user: User, decision: str,
    comment: str | None = None,
) -> AgentProposal:
    """Человек утверждает или отклоняет предложение агента (окончательное решение)."""
    if decision not in ("approved", "rejected"):
        raise AgentError("решение — approved | rejected")
    if proposal.status != "pending":
        raise AgentError("предложение уже обработано")
    proposal.status = decision
    proposal.decided_by_user_id = user.id
    proposal.decided_at = datetime.now(UTC)
    proposal.decision_comment = comment
    _audit(session, user, f"agent.proposal_{decision}", proposal.organization_id,
           "agent_proposal", proposal.id, {"decision": decision})
    session.commit()
    return proposal


def apply_proposal(session: Session, proposal: AgentProposal, *, user: User) -> AgentProposal:
    """Применяет утверждённое предложение через общий сервис (без дублирования).

    Реализовано применение типа `task` — создаётся поручение. Иные типы фиксируются
    как применённые с отметкой цели (создание конкретных сущностей — по мере готовности
    соответствующих сервисов). Применять можно только утверждённое человеком предложение.
    """
    if proposal.status != "approved":
        raise AgentError("применять можно только утверждённое предложение")
    if proposal.proposal_type == "task":
        if proposal.project_id is None:
            raise AgentError("для задачи требуется проект в предложении")
        project = session.get(Project, proposal.project_id)
        if project is None or project.deleted_at is not None:
            raise AgentError("проект не найден")
        task: Task = core_svc.create_task(
            session, project, user=user, title=proposal.title,
            description=proposal.summary, priority="normal",
        )
        proposal.applied_entity_type = "task"
        proposal.applied_entity_id = task.id
    else:
        proposal.applied_entity_type = proposal.proposal_type
    proposal.status = "applied"
    _audit(session, user, "agent.proposal_applied", proposal.organization_id,
           "agent_proposal", proposal.id, {"applied_as": proposal.applied_entity_type})
    session.commit()
    return proposal


# ------------------------------ Чтение ----------------------------------- #


def list_agents(session: Session, organization_id: uuid.UUID) -> list[AIAgent]:
    return list(session.execute(
        select(AIAgent).where(AIAgent.organization_id == organization_id)
        .order_by(AIAgent.created_at.desc())
    ).scalars())


def list_proposals(
    session: Session, user: User, organization_id: uuid.UUID, *, status: str | None = None,
) -> list[AgentProposal]:
    stmt = select(AgentProposal).where(AgentProposal.organization_id == organization_id)
    if status is not None:
        stmt = stmt.where(AgentProposal.status == status)
    rows = list(session.execute(stmt.order_by(AgentProposal.created_at.desc())).scalars())
    return [p for p in rows if p.project_id is None or can_access_project(session, user, p.project_id)]


def summary(session: Session, organization_id: uuid.UUID) -> dict:
    agents = list_agents(session, organization_id)
    props = list(session.execute(
        select(AgentProposal).where(AgentProposal.organization_id == organization_id)
    ).scalars())
    return {
        "agents_total": len(agents),
        "agents_active": sum(1 for a in agents if a.status == "active"),
        "proposals_pending": sum(1 for p in props if p.status == "pending"),
        "proposals_approved": sum(1 for p in props if p.status in ("approved", "applied")),
        "proposals_rejected": sum(1 for p in props if p.status == "rejected"),
    }


def _audit(session, user, action, org_id, entity_type, entity_id, new_values):
    record_event(
        session, actor_type="user", action=action, actor_user_id=user.id,
        organization_id=org_id, entity_type=entity_type, entity_id=entity_id,
        new_values=new_values, risk_level="R1", commit=False,
    )
