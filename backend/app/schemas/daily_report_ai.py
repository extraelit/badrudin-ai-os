"""Схемы ежедневного отчёта: ИИ-черновик и правила отправки (этап E)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AiDraftOut(BaseModel):
    proposal_id: uuid.UUID
    status: str
    summary: str | None
    payload: dict | None


class DecisionIn(BaseModel):
    comment: str | None = None


class NoWorkIn(BaseModel):
    reason: str = Field(min_length=1)


class ExceptionSubmitIn(BaseModel):
    reason: str = Field(min_length=1)


class ReportStatusOut(BaseModel):
    id: uuid.UUID
    status: str
    no_work: bool
    no_work_reason: str | None
    submitted_at: datetime | None


class MediaWarningsOut(BaseModel):
    warnings: list[dict]
