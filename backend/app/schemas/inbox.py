"""Pydantic-схемы модуля «Единый входящий поток»."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CaptureIn(BaseModel):
    subject: str | None = None
    body_text: str | None = None
    source_type: str = "manual"
    channel: str = "manual"
    communication_id: uuid.UUID | None = None
    sender_name: str | None = None
    sender_contact: str | None = None
    counterparty_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    external_ref: str | None = None


class ClassifyIn(BaseModel):
    category: str
    priority: str | None = None
    project_id: uuid.UUID | None = None
    site_id: uuid.UUID | None = None
    counterparty_id: uuid.UUID | None = None
    assigned_to_employee_id: uuid.UUID | None = None


class AssignIn(BaseModel):
    employee_id: uuid.UUID


class ConvertTaskIn(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: str | None = None


class MarkConvertedIn(BaseModel):
    entity_type: str = Field(pattern="^(document|material_request|risk|lead)$")
    entity_id: uuid.UUID | None = None
    note: str | None = None


class DismissIn(BaseModel):
    reason: str = Field(min_length=1)


class ItemOut(BaseModel):
    id: uuid.UUID
    source_type: str
    channel: str
    subject: str | None
    body_text: str | None
    status: str
    category: str | None
    priority: str
    project_id: uuid.UUID | None
    counterparty_id: uuid.UUID | None
    assigned_to_employee_id: uuid.UUID | None
    converted_entity_type: str | None
    converted_entity_id: uuid.UUID | None
    received_at: datetime | None


class TaskRefOut(BaseModel):
    id: uuid.UUID
    title: str
    status: str


class SummaryOut(BaseModel):
    new: int
    classified: int
    in_progress: int
    converted: int
    dismissed: int
    unresolved: int
