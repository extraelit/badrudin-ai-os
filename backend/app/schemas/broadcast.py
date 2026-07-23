"""Схемы рассылок (PR-7)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class BroadcastIn(BaseModel):
    channel: str = Field(max_length=16)
    title: str = Field(max_length=255)
    subject: str | None = Field(default=None, max_length=512)
    body_text: str | None = None
    template_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    scheduled_at: datetime | None = None
    contact_ids: list[uuid.UUID] = Field(default_factory=list)


class BroadcastOut(BaseModel):
    id: uuid.UUID
    channel: str
    title: str
    subject: str | None
    body_text: str | None
    project_id: uuid.UUID | None
    status: str
    scheduled_at: datetime | None
    total_count: int
    sent_count: int
    failed_count: int
    author_user_id: uuid.UUID | None
    created_at: datetime


class TargetsIn(BaseModel):
    contact_ids: list[uuid.UUID]


class TestSendIn(BaseModel):
    test_address: str = Field(max_length=255)


class DeliveryReportOut(BaseModel):
    broadcast_id: uuid.UUID
    total: int
    sent: int
    failed: int
    by_status: dict[str, int]


class PreviewOut(BaseModel):
    subject: str | None
    body: str | None
    recipients: int
