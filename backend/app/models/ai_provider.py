"""Слой сменяемых ИИ-провайдеров (PR-8).

Бизнес-логика не привязана к одному поставщику ИИ (ARCHITECTURE.md; CLAUDE.md §11,
§15): администратор выбирает провайдера и модель для каждого агента, с резервным
провайдером на случай недоступности. Ключи доступа НИКОГДА не хранятся в БД в
открытом виде и не в Git — только через окружение/secret manager; в БД хранится
лишь факт настройки ключа (`credentials_configured_externally`).

Сущности:
- `ai_providers` — подключённые поставщики (openai/anthropic/gemini/local);
- `ai_models` — доступные модели провайдера с возможностями;
- `agent_ai_assignments` — назначение провайдера/модели агенту (основной+резерв);
- `ai_usage_records` — метаданные расхода (токены/стоимость), БЕЗ промптов и
  скрытых рассуждений;
- `ai_provider_health` — состояние подключения провайдера.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    false,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

AI_PROVIDER_CODES = ("openai", "anthropic", "gemini", "local")
AI_HEALTH_STATUSES = ("unknown", "ok", "down")


class AIProvider(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "ai_providers"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    code: Mapped[str] = mapped_column(String(32))  # openai|anthropic|gemini|local
    name: Mapped[str] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    default_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Только признак, что ключ настроен во внешнем секрет-хранилище/окружении;
    # сам ключ в БД не хранится.
    credentials_configured_externally: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(String(512), nullable=True)


class AIModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_models"

    provider_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_providers.id"), index=True
    )
    code: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(128))
    supports_images: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    supports_tools: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    max_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(), nullable=False
    )


class AgentAIAssignment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_ai_assignments"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_agents.id"), index=True)
    primary_provider_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_providers.id"), nullable=True
    )
    primary_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    fallback_provider_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_providers.id"), nullable=True
    )
    fallback_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    temperature: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    reasoning_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthly_budget: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    allow_images: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    allow_documents: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    allow_tools: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )


class AIUsageRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_usage_records"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_agents.id"), nullable=True
    )
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_providers.id"), nullable=True
    )
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost: Mapped[float] = mapped_column(Numeric(12, 4), default=0, nullable=False)
    # Идентификатор запроса для трассировки. Промпты и скрытые рассуждения НЕ
    # сохраняются (CLAUDE.md §15, §13: без секретов и ПДн в журналах).
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class AIProviderHealth(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_provider_health"

    provider_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_providers.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="unknown")
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
