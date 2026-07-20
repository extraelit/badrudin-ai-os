"""Pydantic-схемы центра уведомлений (in-app)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class NotificationOut(BaseModel):
    id: uuid.UUID
    title: str | None
    message: str | None
    priority: str
    status: str
    entity_type: str | None
    entity_id: uuid.UUID | None
    read_at: datetime | None
    created_at: datetime


class UnreadCountOut(BaseModel):
    unread: int


class MarkAllOut(BaseModel):
    marked: int


class InternalNotificationIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    message: str | None = None
    recipient_user_id: uuid.UUID | None = None
    recipient_employee_id: uuid.UUID | None = None
    priority: str = Field(default="normal", pattern="^(low|normal|high|critical)$")
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
