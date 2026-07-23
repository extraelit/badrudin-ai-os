"""Схемы центра коммуникаций (PR-2)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ContactIn(BaseModel):
    display_name: str = Field(max_length=255)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    telegram: str | None = Field(default=None, max_length=128)
    whatsapp: str | None = Field(default=None, max_length=64)
    instagram: str | None = Field(default=None, max_length=128)
    counterparty_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    consent: bool = False


class ContactOut(BaseModel):
    id: uuid.UUID
    display_name: str
    email: str | None
    phone: str | None
    telegram: str | None
    whatsapp: str | None
    instagram: str | None
    project_id: uuid.UUID | None
    consent: bool
    stop_listed: bool


class StopListIn(BaseModel):
    stop_listed: bool


class TemplateIn(BaseModel):
    code: str = Field(max_length=64)
    name: str = Field(max_length=255)
    channel: str = Field(max_length=16)
    subject: str | None = Field(default=None, max_length=512)
    body_text: str


class TemplateOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    channel: str
    subject: str | None
    body_text: str
    is_approved: bool


class RecipientIn(BaseModel):
    address: str = Field(max_length=255)
    contact_id: uuid.UUID | None = None
    kind: str = Field(default="to", max_length=4)


class RecipientOut(BaseModel):
    id: uuid.UUID
    address: str
    kind: str
    status: str
    external_id: str | None
    error_reason: str | None


class MessageIn(BaseModel):
    channel: str = Field(max_length=16)
    subject: str | None = Field(default=None, max_length=512)
    body_text: str | None = None
    project_id: uuid.UUID | None = None
    template_id: uuid.UUID | None = None
    connector_id: uuid.UUID | None = None
    responsible_user_id: uuid.UUID | None = None
    scheduled_at: datetime | None = None
    entity_type: str | None = Field(default=None, max_length=48)
    entity_id: uuid.UUID | None = None
    recipients: list[RecipientIn] = Field(default_factory=list)


class MessageOut(BaseModel):
    id: uuid.UUID
    direction: str
    channel: str
    subject: str | None
    body_text: str | None
    project_id: uuid.UUID | None
    status: str
    external_id: str | None
    error_reason: str | None
    attempts: int
    scheduled_at: datetime | None
    sent_at: datetime | None
    responsible_user_id: uuid.UUID | None
    author_user_id: uuid.UUID | None
    created_at: datetime


class MessageDetailOut(MessageOut):
    recipients: list[RecipientOut]


class DeliveryEventOut(BaseModel):
    id: uuid.UUID
    event: str
    detail: str | None
    external_id: str | None
    recipient_id: uuid.UUID | None
    occurred_at: datetime


class CancelIn(BaseModel):
    reason: str | None = Field(default=None, max_length=512)


class ChannelOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    channel: str
    provider: str | None
    status: str
    credentials_configured_externally: bool
