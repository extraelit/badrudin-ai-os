"""Pydantic-схемы модуля «Исполнительная документация ПТО»."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DocumentIn(BaseModel):
    project_id: uuid.UUID
    doc_type: str
    title: str = Field(min_length=1, max_length=500)
    number: str | None = None
    description: str | None = None
    file_id: uuid.UUID | None = None
    work_item_type: str | None = None
    work_item_id: uuid.UUID | None = None
    supersedes_id: uuid.UUID | None = None


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    comment: str | None = None


class DocumentOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    doc_type: str
    number: str | None
    title: str
    description: str | None
    file_id: uuid.UUID | None
    work_item_type: str | None
    work_item_id: uuid.UUID | None
    version_number: int
    supersedes_id: uuid.UUID | None
    status: str
    approval_id: uuid.UUID | None
    reviewed_by_user_id: uuid.UUID | None
    review_comment: str | None
    approved_at: datetime | None


class CompletenessOut(BaseModel):
    required: list[str]
    present: list[str]
    missing: list[str]
    complete: bool


class SummaryOut(BaseModel):
    documents_total: int
    documents_draft: int
    documents_under_review: int
    documents_approved: int
    documents_superseded: int
