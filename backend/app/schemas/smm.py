"""Pydantic-схемы модуля «SMM и внешние публикации» (внутренний контур)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


# ------------------------------ Контент-план ----------------------------- #


class PlanItemIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    theme: str | None = None
    channel: str = "internal"
    planned_date: date | None = None
    project_id: uuid.UUID | None = None
    notes: str | None = None


class PlanStatusIn(BaseModel):
    status: str = Field(pattern="^(idea|planned|in_progress|done|cancelled)$")


class PlanItemOut(BaseModel):
    id: uuid.UUID
    title: str
    theme: str | None
    channel: str
    planned_date: date | None
    project_id: uuid.UUID | None
    status: str
    notes: str | None


# ------------------------------ Публикации ------------------------------- #


class PublicationIn(BaseModel):
    channel: str = "internal"
    title: str | None = None
    body_text: str | None = None
    hashtags: str | None = None
    plan_item_id: uuid.UUID | None = None
    connector_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    scheduled_for: datetime | None = None


class ChecksIn(BaseModel):
    rights_confirmed: bool | None = None
    pii_checked: bool | None = None
    legal_checked: bool | None = None


class AssetIn(BaseModel):
    file_id: uuid.UUID | None = None
    caption: str | None = None
    quality_ok: bool = False
    rights_ok: bool = False


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    comment: str | None = None


class CancelIn(BaseModel):
    reason: str = Field(min_length=1)


class PublicationOut(BaseModel):
    id: uuid.UUID
    channel: str
    title: str | None
    body_text: str | None
    hashtags: str | None
    status: str
    rights_confirmed: bool
    pii_checked: bool
    legal_checked: bool
    scheduled_for: datetime | None
    risk_level: str
    project_id: uuid.UUID | None
    connector_id: uuid.UUID | None
    plan_item_id: uuid.UUID | None
    approval_id: uuid.UUID | None
    approved_at: datetime | None


class AssetOut(BaseModel):
    id: uuid.UUID
    publication_id: uuid.UUID
    file_id: uuid.UUID | None
    caption: str | None
    quality_ok: bool
    rights_ok: bool


class SummaryOut(BaseModel):
    plan_total: int
    plan_active: int
    publications_draft: int
    publications_pending: int
    publications_approved: int
