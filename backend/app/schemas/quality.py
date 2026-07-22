"""Схемы строительного контроля и качества (этап F)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CardIn(BaseModel):
    work_type: str
    name: str = Field(min_length=1, max_length=512)
    controlled_parameter: str
    control_kind: str = "operational"
    project_id: uuid.UUID | None = None
    normative_item_id: uuid.UUID | None = None
    allowed_value: str | None = None
    check_method: str | None = None
    responsible_position: str | None = None
    requires_document: bool = False
    requires_photo: bool = True
    requires_measurement: bool = False


class CardOut(BaseModel):
    id: uuid.UUID
    work_type: str
    name: str
    control_kind: str
    controlled_parameter: str
    allowed_value: str | None
    check_method: str | None
    normative_item_id: uuid.UUID | None
    requires_document: bool
    requires_photo: bool
    requires_measurement: bool
    status: str


class CheckIn(BaseModel):
    result: str  # pass | fail | conditional
    measured_value: str | None = None
    instrument: str | None = None
    instrument_verification: str | None = None
    remark: str | None = None
    defect_deadline: datetime | None = None
    process_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    ai_suggestion: str | None = None


class RecheckIn(BaseModel):
    result: str
    measured_value: str | None = None
    instrument: str | None = None
    remark: str | None = None


class FinalizeIn(BaseModel):
    decision: str  # accepted | rejected
    comment: str | None = None


class CheckOut(BaseModel):
    id: uuid.UUID
    card_id: uuid.UUID
    result: str
    measured_value: str | None
    instrument: str | None
    instrument_verification: str | None
    remark: str | None
    defect_deadline: datetime | None
    recheck_required: bool
    recheck_of_check_id: uuid.UUID | None
    ai_suggestion: str | None
    final_decision: str | None
    final_decision_by: uuid.UUID | None
    checked_by: uuid.UUID | None
    checked_at: datetime | None
