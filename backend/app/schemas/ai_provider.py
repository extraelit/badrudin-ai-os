"""Схемы слоя ИИ-провайдеров (PR-8). Ключи никогда не передаются в ответах."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ProviderIn(BaseModel):
    code: str = Field(max_length=32)  # openai|anthropic|gemini|local
    name: str = Field(max_length=128)
    base_url: str | None = Field(default=None, max_length=512)
    default_model: str | None = Field(default=None, max_length=128)
    notes: str | None = Field(default=None, max_length=512)


class ProviderOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    enabled: bool
    base_url: str | None
    default_model: str | None
    credentials_configured_externally: bool
    key_hint: str  # маскированный индикатор ключа, не сам ключ
    notes: str | None


class EnableIn(BaseModel):
    enabled: bool


class ModelIn(BaseModel):
    code: str = Field(max_length=128)
    name: str = Field(max_length=128)
    supports_images: bool = False
    supports_tools: bool = False
    max_output_tokens: int | None = None


class ModelOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    supports_images: bool
    supports_tools: bool
    max_output_tokens: int | None
    enabled: bool


class AssignmentIn(BaseModel):
    primary_provider_id: uuid.UUID | None = None
    primary_model: str | None = None
    fallback_provider_id: uuid.UUID | None = None
    fallback_model: str | None = None
    temperature: float | None = None
    reasoning_level: str | None = Field(default=None, max_length=16)
    max_tokens: int | None = None
    monthly_budget: float | None = None
    timeout_seconds: int = 60
    allow_images: bool = False
    allow_documents: bool = False
    allow_tools: bool = False


class AssignmentOut(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    primary_provider_id: uuid.UUID | None
    primary_model: str | None
    fallback_provider_id: uuid.UUID | None
    fallback_model: str | None
    temperature: float | None
    reasoning_level: str | None
    max_tokens: int | None
    monthly_budget: float | None
    timeout_seconds: int
    allow_images: bool
    allow_documents: bool
    allow_tools: bool


class HealthOut(BaseModel):
    provider_id: uuid.UUID
    status: str
    checked_at: datetime
    detail: str | None


class UsageOut(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID | None
    provider_id: uuid.UUID | None
    model: str | None
    tokens_in: int
    tokens_out: int
    cost: float
    request_id: str | None
    created_at: datetime
