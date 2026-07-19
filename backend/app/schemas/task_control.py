"""Pydantic-схемы модуля «Контроль исполнения поручений»."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TaskCard(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID | None
    title: str
    status: str
    priority: str
    risk_level: str
    due_at: datetime | None
    overdue: bool
    blocked_reason: str | None
    escalation_level: int
    owner_employee_id: uuid.UUID | None


class BoardOut(BaseModel):
    overdue: list[TaskCard] = Field(default_factory=list)
    blocked: list[TaskCard] = Field(default_factory=list)
    waiting_for_information: list[TaskCard] = Field(default_factory=list)
    in_progress: list[TaskCard] = Field(default_factory=list)
    pending_review: list[TaskCard] = Field(default_factory=list)
    returned_for_revision: list[TaskCard] = Field(default_factory=list)


class BlockerIn(BaseModel):
    category: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1)


class MessageIn(BaseModel):
    message: str = Field(min_length=1)


class OptionalMessageIn(BaseModel):
    message: str | None = None


class ActivityOut(BaseModel):
    id: uuid.UUID
    update_type: str
    message: str | None
    blocker_category: str | None
    progress_percent: int | None
    created_at: datetime


class NotificationOut(BaseModel):
    id: uuid.UUID
    title: str | None
    message: str | None
    entity_type: str | None
    entity_id: uuid.UUID | None
    priority: str
    status: str
    read_at: datetime | None
    created_at: datetime
