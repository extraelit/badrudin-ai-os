"""API слоя ИИ-провайдеров `/ai-providers` (PR-8).

Экран «Настройки → ИИ-провайдеры»: включение/отключение провайдера, модель по
умолчанию, проверка подключения, назначение модели каждому агенту, стоимость и
расход, журнал запросов. Ключи доступа НИКОГДА не возвращаются — только
маскированный индикатор. RBAC: `ai.provider.manage` (администрирование),
`ai.provider.view` (просмотр). Действия — в аудит.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.session import get_db
from app.models import (
    AgentAIAssignment,
    AIAgent,
    AIModel,
    AIProvider,
    AIUsageRecord,
    Employee,
    User,
)
from app.models.ai_provider import AI_PROVIDER_CODES
from app.schemas.ai_provider import (
    AssignmentIn,
    AssignmentOut,
    EnableIn,
    HealthOut,
    ModelIn,
    ModelOut,
    ProviderIn,
    ProviderOut,
    UsageOut,
)
from app.services import ai_provider as svc
from app.services.audit import record_event

router = APIRouter(prefix="/ai-providers", tags=["ai-providers"])


def _org(db: Session, user: User) -> uuid.UUID:
    if user.employee_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пользователь не связан с сотрудником")
    emp = db.get(Employee, user.employee_id)
    return emp.organization_id


def _provider_out(p: AIProvider) -> ProviderOut:
    key = svc._key_for(p.code) if p.code != "local" else svc.get_settings().local_ai_api_key
    return ProviderOut(
        id=p.id, code=p.code, name=p.name, enabled=p.enabled, base_url=p.base_url,
        default_model=p.default_model,
        credentials_configured_externally=p.credentials_configured_externally,
        key_hint=svc.mask_secret(key), notes=p.notes,
    )


def _provider(db: Session, user: User, pid: uuid.UUID) -> AIProvider:
    p = db.get(AIProvider, pid)
    if p is None or p.deleted_at is not None or p.organization_id != _org(db, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Провайдер не найден")
    return p


@router.get("/", response_model=list[ProviderOut])
def list_providers(current: User = Depends(require_permission("ai.provider.view")),
                   db: Session = Depends(get_db)) -> list[ProviderOut]:
    org = _org(db, current)
    rows = db.execute(select(AIProvider).where(
        AIProvider.organization_id == org, AIProvider.deleted_at.is_(None)
    )).scalars()
    return [_provider_out(p) for p in rows]


@router.post("/", response_model=ProviderOut, status_code=status.HTTP_201_CREATED)
def create_provider(payload: ProviderIn,
                    current: User = Depends(require_permission("ai.provider.manage")),
                    db: Session = Depends(get_db)) -> ProviderOut:
    if payload.code not in AI_PROVIDER_CODES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Неизвестный код провайдера")
    org = _org(db, current)
    adapter = svc.get_adapter(payload.code)
    p = AIProvider(
        organization_id=org, code=payload.code, name=payload.name,
        base_url=payload.base_url, default_model=payload.default_model,
        notes=payload.notes,
        credentials_configured_externally=adapter.available(),  # только факт, не ключ
    )
    db.add(p)
    db.flush()
    record_event(db, actor_type="user", action="ai.provider.create",
                 actor_user_id=current.id, organization_id=org,
                 entity_type="ai_provider", entity_id=p.id,
                 new_values={"code": p.code}, risk_level="R1", commit=True)
    return _provider_out(p)


@router.post("/{provider_id}/enable", response_model=ProviderOut)
def set_enabled(provider_id: uuid.UUID, payload: EnableIn,
                current: User = Depends(require_permission("ai.provider.manage")),
                db: Session = Depends(get_db)) -> ProviderOut:
    p = _provider(db, current, provider_id)
    p.enabled = payload.enabled
    record_event(db, actor_type="user", action="ai.provider.enable",
                 actor_user_id=current.id, organization_id=p.organization_id,
                 entity_type="ai_provider", entity_id=p.id,
                 new_values={"enabled": payload.enabled}, risk_level="R1", commit=True)
    return _provider_out(p)


@router.post("/{provider_id}/health", response_model=HealthOut)
def provider_health(provider_id: uuid.UUID,
                    current: User = Depends(require_permission("ai.provider.manage")),
                    db: Session = Depends(get_db)) -> HealthOut:
    p = _provider(db, current, provider_id)
    h = svc.check_health(db, p)
    db.commit()
    return HealthOut(provider_id=p.id, status=h.status, checked_at=h.checked_at,
                     detail=h.detail)


@router.get("/{provider_id}/models", response_model=list[ModelOut])
def list_models(provider_id: uuid.UUID,
                current: User = Depends(require_permission("ai.provider.view")),
                db: Session = Depends(get_db)) -> list[ModelOut]:
    p = _provider(db, current, provider_id)
    rows = db.execute(select(AIModel).where(AIModel.provider_id == p.id)).scalars()
    return [ModelOut(id=m.id, code=m.code, name=m.name, supports_images=m.supports_images,
                     supports_tools=m.supports_tools, max_output_tokens=m.max_output_tokens,
                     enabled=m.enabled) for m in rows]


@router.post("/{provider_id}/models", response_model=ModelOut,
             status_code=status.HTTP_201_CREATED)
def add_model(provider_id: uuid.UUID, payload: ModelIn,
              current: User = Depends(require_permission("ai.provider.manage")),
              db: Session = Depends(get_db)) -> ModelOut:
    p = _provider(db, current, provider_id)
    m = AIModel(provider_id=p.id, code=payload.code, name=payload.name,
                supports_images=payload.supports_images, supports_tools=payload.supports_tools,
                max_output_tokens=payload.max_output_tokens)
    db.add(m)
    db.commit()
    return ModelOut(id=m.id, code=m.code, name=m.name, supports_images=m.supports_images,
                    supports_tools=m.supports_tools, max_output_tokens=m.max_output_tokens,
                    enabled=m.enabled)


def _assignment_out(a: AgentAIAssignment) -> AssignmentOut:
    return AssignmentOut(
        id=a.id, agent_id=a.agent_id, primary_provider_id=a.primary_provider_id,
        primary_model=a.primary_model, fallback_provider_id=a.fallback_provider_id,
        fallback_model=a.fallback_model,
        temperature=float(a.temperature) if a.temperature is not None else None,
        reasoning_level=a.reasoning_level, max_tokens=a.max_tokens,
        monthly_budget=float(a.monthly_budget) if a.monthly_budget is not None else None,
        timeout_seconds=a.timeout_seconds, allow_images=a.allow_images,
        allow_documents=a.allow_documents, allow_tools=a.allow_tools,
    )


@router.get("/agents/{agent_id}/assignment", response_model=AssignmentOut | None)
def get_assignment(agent_id: uuid.UUID,
                   current: User = Depends(require_permission("ai.provider.view")),
                   db: Session = Depends(get_db)) -> AssignmentOut | None:
    org = _org(db, current)
    agent = db.get(AIAgent, agent_id)
    if agent is None or agent.organization_id != org:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Агент не найден")
    a = db.scalar(select(AgentAIAssignment).where(AgentAIAssignment.agent_id == agent_id))
    return _assignment_out(a) if a else None


@router.put("/agents/{agent_id}/assignment", response_model=AssignmentOut)
def set_assignment(agent_id: uuid.UUID, payload: AssignmentIn,
                   current: User = Depends(require_permission("ai.provider.manage")),
                   db: Session = Depends(get_db)) -> AssignmentOut:
    org = _org(db, current)
    agent = db.get(AIAgent, agent_id)
    if agent is None or agent.organization_id != org:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Агент не найден")
    a = db.scalar(select(AgentAIAssignment).where(AgentAIAssignment.agent_id == agent_id))
    if a is None:
        a = AgentAIAssignment(organization_id=org, agent_id=agent_id)
        db.add(a)
    a.primary_provider_id = payload.primary_provider_id
    a.primary_model = payload.primary_model
    a.fallback_provider_id = payload.fallback_provider_id
    a.fallback_model = payload.fallback_model
    a.temperature = payload.temperature
    a.reasoning_level = payload.reasoning_level
    a.max_tokens = payload.max_tokens
    a.monthly_budget = payload.monthly_budget
    a.timeout_seconds = payload.timeout_seconds
    a.allow_images = payload.allow_images
    a.allow_documents = payload.allow_documents
    a.allow_tools = payload.allow_tools
    db.flush()
    record_event(db, actor_type="user", action="ai.provider.assign",
                 actor_user_id=current.id, organization_id=org,
                 entity_type="ai_agent", entity_id=agent_id,
                 new_values={"primary_provider": str(payload.primary_provider_id)},
                 risk_level="R1", commit=True)
    return _assignment_out(a)


@router.get("/usage", response_model=list[UsageOut])
def usage(current: User = Depends(require_permission("ai.provider.view")),
          db: Session = Depends(get_db)) -> list[UsageOut]:
    org = _org(db, current)
    rows = db.execute(
        select(AIUsageRecord).where(AIUsageRecord.organization_id == org)
        .order_by(AIUsageRecord.created_at.desc()).limit(200)
    ).scalars()
    return [UsageOut(id=r.id, agent_id=r.agent_id, provider_id=r.provider_id, model=r.model,
                     tokens_in=r.tokens_in, tokens_out=r.tokens_out, cost=float(r.cost),
                     request_id=r.request_id, created_at=r.created_at) for r in rows]
