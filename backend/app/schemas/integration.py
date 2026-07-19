"""Pydantic-схемы модуля «Масштабирование интеграций» (внутренний контур)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ConnectorIn(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str
    channel: str = "internal"
    provider: str | None = None
    config_summary: str | None = None


class ConnectorStatusIn(BaseModel):
    status: str = Field(pattern="^(draft|configured|disabled)$")
    credentials_configured_externally: bool | None = None


class ConnectorOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    channel: str
    provider: str | None
    config_summary: str | None
    status: str
    credentials_configured_externally: bool


class OutboundIn(BaseModel):
    channel: str = "email"
    subject: str | None = None
    body_text: str | None = None
    connector_id: uuid.UUID | None = None
    recipient: str | None = None
    project_id: uuid.UUID | None = None
    counterparty_id: uuid.UUID | None = None
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    comment: str | None = None


class CancelIn(BaseModel):
    reason: str = Field(min_length=1)


class OutboundOut(BaseModel):
    id: uuid.UUID
    channel: str
    subject: str | None
    body_text: str | None
    recipient: str | None
    status: str
    risk_level: str
    project_id: uuid.UUID | None
    connector_id: uuid.UUID | None
    approval_id: uuid.UUID | None
    approved_at: datetime | None


class SummaryOut(BaseModel):
    connectors_total: int
    connectors_configured: int
    outbound_draft: int
    outbound_pending: int
    outbound_approved: int
