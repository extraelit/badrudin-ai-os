"""Pydantic-схемы модуля «Сметы и ценообразование»."""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, Field


# ------------------------------ Справочники ------------------------------ #


class UnitOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    category: str


class RateItemIn(BaseModel):
    code: str
    name: str
    unit_id: uuid.UUID | None = None
    material_cost: float = Field(0, ge=0)
    labor_cost: float = Field(0, ge=0)
    machine_cost: float = Field(0, ge=0)
    source: str = "own"


class RateItemOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    unit_id: uuid.UUID | None
    material_cost: str
    labor_cost: str
    machine_cost: str
    source: str
    status: str


# -------------------------------- Смета ---------------------------------- #


class EstimateIn(BaseModel):
    name: str
    estimate_type: str = "local"
    number: str | None = None
    site_id: uuid.UUID | None = None
    contract_id: uuid.UUID | None = None
    discipline_id: uuid.UUID | None = None
    design_brief_id: uuid.UUID | None = None
    parent_estimate_id: uuid.UUID | None = None
    currency: str = "RUB"
    base_index: float = 1
    vat_rate: float = 20
    overhead_percent: float = 0
    profit_percent: float = 0
    rounding: str = "0.01"


class PositionIn(BaseModel):
    name: str
    code: str | None = None
    work_type: str | None = None
    unit_id: uuid.UUID | None = None
    rate_item_id: uuid.UUID | None = None
    material_id: uuid.UUID | None = None
    design_specification_id: uuid.UUID | None = None
    discipline_id: uuid.UUID | None = None
    location_id: uuid.UUID | None = None
    quantity: float = Field(0, ge=0)
    material_unit_cost: float = Field(0, ge=0)
    labor_unit_cost: float = Field(0, ge=0)
    machine_unit_cost: float = Field(0, ge=0)
    coefficient: float = 1
    overhead_percent: float = 0
    profit_percent: float = 0


class PositionOut(BaseModel):
    id: uuid.UUID
    code: str | None
    name: str
    unit_id: uuid.UUID | None
    quantity: str
    material_unit_cost: str
    labor_unit_cost: str
    machine_unit_cost: str
    coefficient: str
    overhead_percent: str
    profit_percent: str
    position_direct: str
    position_overhead: str
    position_profit: str
    position_total: str


class EstimateOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    number: str | None
    estimate_type: str
    version: int
    status: str
    currency: str
    base_index: str
    vat_rate: str
    material_total: str
    labor_total: str
    machine_total: str
    direct_total: str
    overhead_total: str
    profit_total: str
    subtotal: str
    vat_total: str
    grand_total: str
    positions: list[PositionOut] = Field(default_factory=list)


class ChangeIn(BaseModel):
    change_type: str = "scope"
    reason: str
    amount_delta: float = 0
    position_id: uuid.UUID | None = None


class NewVersionIn(BaseModel):
    reason: str


# ------------------------- Коммерческое предложение ---------------------- #


class OfferIn(BaseModel):
    markup_percent: float = Field(0, ge=0)
    valid_until: date | None = None


class OfferOut(BaseModel):
    id: uuid.UUID
    estimate_id: uuid.UUID
    markup_percent: str
    base_amount: str
    offer_amount: str
    currency: str
    status: str
    risk_level: str
    approval_id: uuid.UUID | None


class OfferDecisionIn(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    comment: str | None = None
    mfa_code: str | None = None


# ------------------------------ План-факт -------------------------------- #


class PlanFactRowOut(BaseModel):
    position_id: uuid.UUID
    name: str
    planned_quantity: str
    actual_quantity: str
    planned_total: str
    actual_total: str
    deviation: str


class PlanFactOut(BaseModel):
    estimate_id: uuid.UUID
    planned_total: str
    actual_total: str
    deviation: str
    rows: list[PlanFactRowOut]


# ------------------------------- Сводка ---------------------------------- #


class EstimateSummaryRow(BaseModel):
    estimate_id: uuid.UUID
    name: str
    version: int
    status: str
    grand_total: str


class ProjectEstimateSummary(BaseModel):
    project_id: uuid.UUID
    estimates_total: int
    approved_total: int
    grand_total_approved: str
    offers_pending: int
    estimates: list[EstimateSummaryRow]
