"""Реестр ИИ-агентов и их запусков (T-1.B7).

Соответствует DATABASE.md раздел 5. `default_risk_level`/`risk_level` используют
шкалу R0–R4 (D-001). Провайдер-независимость модели — D-010.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AIAgent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_agents"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # провайдер модели (D-010) — конкретное значение утверждается после юр-проверки
    model_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    system_prompt_version: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default="inactive")
    requires_human_approval: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    default_risk_level: Mapped[str] = mapped_column(String(2), default="R1")
    configuration_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class AgentRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_runs"

    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_agents.id"))
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    initiated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True
    )
    parent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_runs.id"), nullable=True
    )
    trigger_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    risk_level: Mapped[str] = mapped_column(String(2), default="R0")
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)


class AgentProposal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Предложение ИИ-агента, требующее решения человека (AGENTS.md §2.1, §15).

    Агент по итогам запуска формирует предложение (задача, документ, предупреждение,
    заявка, риск). Предложение не имеет силы до утверждения человеком; применение
    утверждённого предложения переиспользует общие сервисы (например, создание
    задачи), не дублируя сущности. Всё — под контролем аудита.
    """

    __tablename__ = "agent_proposals"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_agents.id"))
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_runs.id"), nullable=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    # task | document | warning | material_request | risk | note
    proposal_type: Mapped[str] = mapped_column(String(32), default="task")
    title: Mapped[str] = mapped_column(String(500))
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    risk_level: Mapped[str] = mapped_column(String(2), default="R1")
    # pending | approved | rejected | applied
    status: Mapped[str] = mapped_column(String(16), default="pending")
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decision_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ссылка на созданную сущность после применения (без дублирования)
    applied_entity_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    applied_entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
