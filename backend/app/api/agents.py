"""API модуля «Оркестратор ИИ-агентов» (governance + человек в контуре).

Backend — единственная точка доступа. RBAC: `agent.view` (реестр, запуски,
предложения, сводка), `agent.manage` (регистрация, статус, запуск, фиксация
результата, формирование предложения), `agent.approve` (утверждение/отклонение и
применение предложений — окончательное решение человека). ABAC: предложения с
проектом ограничены доступом к проекту. Всё — в `audit_events`. Фактический вызов
модели выполняется отдельным утверждённым коннектором и здесь не производится.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.db.session import get_db
from app.models import AgentProposal, AgentRun, AIAgent, Employee, User
from app.schemas.agents import (
    AgentIn,
    AgentOut,
    AgentStatusIn,
    ProposalIn,
    ProposalOut,
    ReviewIn,
    RunIn,
    RunOut,
    RunResultIn,
    SummaryOut,
)
from app.services import agents as svc

router = APIRouter(prefix="/agents", tags=["agents"])


def _org(db: Session, user: User) -> uuid.UUID:
    if user.employee_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пользователь не связан с сотрудником")
    emp = db.get(Employee, user.employee_id)
    return emp.organization_id


def _agent(db: Session, user: User, agent_id: uuid.UUID) -> AIAgent:
    a = db.get(AIAgent, agent_id)
    if a is None or a.organization_id != _org(db, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Агент не найден")
    return a


def _proposal(db: Session, user: User, proposal_id: uuid.UUID) -> AgentProposal:
    p = db.get(AgentProposal, proposal_id)
    if p is None or p.organization_id != _org(db, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Предложение не найдено")
    if p.project_id is not None:
        from app.services.access import can_access_project

        if not can_access_project(db, user, p.project_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к проекту предложения")
    return p


def _agent_out(a: AIAgent) -> AgentOut:
    return AgentOut(id=a.id, code=a.code, name=a.name, agent_type=a.agent_type,
                    status=a.status, default_risk_level=a.default_risk_level,
                    requires_human_approval=a.requires_human_approval)


def _prop_out(p: AgentProposal) -> ProposalOut:
    return ProposalOut(id=p.id, agent_id=p.agent_id, run_id=p.run_id,
                       proposal_type=p.proposal_type, title=p.title, summary=p.summary,
                       risk_level=p.risk_level, status=p.status, project_id=p.project_id,
                       applied_entity_type=p.applied_entity_type,
                       applied_entity_id=p.applied_entity_id, decided_at=p.decided_at)


def _guard(exc: svc.AgentError) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


# ------------------------------- Сводка ---------------------------------- #


@router.get("/summary", response_model=SummaryOut)
def summary(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("agent.view")),
) -> SummaryOut:
    return SummaryOut(**svc.summary(db, _org(db, user)))


# ------------------------------ Реестр ----------------------------------- #


@router.get("", response_model=list[AgentOut])
def list_agents(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("agent.view")),
) -> list[AgentOut]:
    return [_agent_out(a) for a in svc.list_agents(db, _org(db, user))]


@router.post("", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
def register_agent(
    payload: AgentIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("agent.manage")),
) -> AgentOut:
    try:
        a = svc.register_agent(db, organization_id=_org(db, user), user=user, **payload.model_dump())
    except svc.AgentError as exc:
        raise _guard(exc) from exc
    return _agent_out(a)


@router.post("/{agent_id}/status", response_model=AgentOut)
def set_status(
    agent_id: uuid.UUID, payload: AgentStatusIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("agent.manage")),
) -> AgentOut:
    a = _agent(db, user, agent_id)
    try:
        svc.set_agent_status(db, a, user=user, status=payload.status)
    except svc.AgentError as exc:
        raise _guard(exc) from exc
    return _agent_out(a)


# ------------------------------ Запуски ---------------------------------- #


def _run_out(r: AgentRun) -> RunOut:
    return RunOut(id=r.id, agent_id=r.agent_id, status=r.status, trigger_type=r.trigger_type,
                  input_summary=r.input_summary, output_summary=r.output_summary,
                  risk_level=r.risk_level)


@router.post("/{agent_id}/runs", response_model=RunOut, status_code=status.HTTP_201_CREATED)
def create_run(
    agent_id: uuid.UUID, payload: RunIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("agent.manage")),
) -> RunOut:
    a = _agent(db, user, agent_id)
    try:
        run = svc.create_run(db, a, user=user, trigger_type=payload.trigger_type,
                             input_summary=payload.input_summary, project_id=payload.project_id)
    except svc.AgentError as exc:
        raise _guard(exc) from exc
    return _run_out(run)


@router.post("/runs/{run_id}/result", response_model=RunOut)
def record_result(
    run_id: uuid.UUID, payload: RunResultIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("agent.manage")),
) -> RunOut:
    run = db.get(AgentRun, run_id)
    if run is None or run.organization_id != _org(db, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Запуск не найден")
    try:
        svc.record_run_result(db, run, user=user, status=payload.status,
                              output_summary=payload.output_summary, error_message=payload.error_message)
    except svc.AgentError as exc:
        raise _guard(exc) from exc
    return _run_out(run)


# ---------------------------- Предложения -------------------------------- #


@router.get("/proposals", response_model=list[ProposalOut])
def list_proposals(
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("agent.view")),
) -> list[ProposalOut]:
    return [_prop_out(p) for p in svc.list_proposals(db, user, _org(db, user), status=status_filter)]


@router.post("/{agent_id}/proposals", response_model=ProposalOut, status_code=status.HTTP_201_CREATED)
def add_proposal(
    agent_id: uuid.UUID, payload: ProposalIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("agent.manage")),
) -> ProposalOut:
    a = _agent(db, user, agent_id)
    try:
        p = svc.add_proposal(db, a, user=user, **payload.model_dump())
    except svc.AgentError as exc:
        raise _guard(exc) from exc
    return _prop_out(p)


@router.post("/proposals/{proposal_id}/review", response_model=ProposalOut)
def review_proposal(
    proposal_id: uuid.UUID, payload: ReviewIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("agent.approve")),
) -> ProposalOut:
    p = _proposal(db, user, proposal_id)
    try:
        svc.review_proposal(db, p, user=user, decision=payload.decision, comment=payload.comment)
    except svc.AgentError as exc:
        raise _guard(exc) from exc
    return _prop_out(p)


@router.post("/proposals/{proposal_id}/apply", response_model=ProposalOut)
def apply_proposal(
    proposal_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("agent.approve")),
) -> ProposalOut:
    p = _proposal(db, user, proposal_id)
    try:
        svc.apply_proposal(db, p, user=user)
    except svc.AgentError as exc:
        raise _guard(exc) from exc
    return _prop_out(p)
