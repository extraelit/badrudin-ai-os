"""Схемы нормативного реестра и профиля проекта (этап 1)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class NormativeDocumentIn(BaseModel):
    full_title: str = Field(min_length=1, max_length=1024)
    doc_kind: str
    number: str | None = None
    edition: str | None = None
    amendment_no: str | None = None
    official_source_url: str | None = None
    scope: str | None = None
    work_types: list[str] | None = None
    object_types: list[str] | None = None
    related_control_ops: list[str] | None = None


class ConfirmStatusIn(BaseModel):
    status: str
    comment: str | None = None


class NormativeDocumentOut(BaseModel):
    id: uuid.UUID
    full_title: str
    number: str | None
    doc_kind: str
    edition: str | None
    amendment_no: str | None
    status: str
    effective_from: date | None
    effective_until: date | None
    official_source_url: str | None
    last_checked_at: datetime | None
    reviewer_comment: str | None
    is_archived: bool


class ProfileItemIn(BaseModel):
    normative_document_id: uuid.UUID
    applicable_edition: str | None = None
    mandatory: bool = True
    work_types: list[str] | None = None
    special_requirements: str | None = None


class ProfileItemOut(BaseModel):
    id: uuid.UUID
    normative_document_id: uuid.UUID
    applicable_edition: str | None
    mandatory: bool
    work_types: list[str] | None
    special_requirements: str | None


class ProfileOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    status: str
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    items: list[ProfileItemOut] = []
