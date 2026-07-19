"""Pydantic-схемы модуля «Ядро CRM». Денежные значения сериализуются строкой."""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, Field


# ------------------------------ Справочники ----------------------------- #


class LeadSourceIn(BaseModel):
    name: str
    code: str | None = None


class LeadSourceOut(BaseModel):
    id: uuid.UUID
    code: str | None
    name: str
    status: str


class LossReasonIn(BaseModel):
    name: str
    code: str | None = None


class LossReasonOut(BaseModel):
    id: uuid.UUID
    code: str | None
    name: str
    status: str


# ------------------------------ Воронка --------------------------------- #


class StageIn(BaseModel):
    name: str
    code: str | None = None
    sort_order: int = 0
    probability_percent: float = Field(0, ge=0, le=100)
    is_won: bool = False
    is_lost: bool = False


class StageOut(BaseModel):
    id: uuid.UUID
    code: str | None
    name: str
    sort_order: int
    probability_percent: str
    is_won: bool
    is_lost: bool
    status: str


# ------------------------------ Контрагенты ----------------------------- #


class CounterpartyIn(BaseModel):
    name: str
    inn: str | None = None
    counterparty_type: str = "customer"


class CounterpartyOut(BaseModel):
    id: uuid.UUID
    name: str
    inn: str | None
    counterparty_type: str
    status: str


class ContactIn(BaseModel):
    full_name: str
    position: str | None = None
    email: str | None = None
    phone: str | None = None
    messenger: str | None = None
    is_primary: bool = False
    consent_given: bool = False
    consent_date: date | None = None


class ContactOut(BaseModel):
    id: uuid.UUID
    counterparty_id: uuid.UUID
    full_name: str
    position: str | None
    email: str | None
    phone: str | None
    messenger: str | None
    is_primary: bool
    consent_given: bool
    consent_date: date | None
    pii_masked: bool
    status: str


# ------------------------------- Лиды ----------------------------------- #


class LeadIn(BaseModel):
    title: str
    description: str | None = None
    lead_source_id: uuid.UUID | None = None
    counterparty_id: uuid.UUID | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    company_name: str | None = None
    estimated_amount: float = Field(0, ge=0)
    currency: str = "RUB"
    responsible_employee_id: uuid.UUID | None = None


class LeadOut(BaseModel):
    id: uuid.UUID
    number: str | None
    title: str
    status: str
    lead_source_id: uuid.UUID | None
    counterparty_id: uuid.UUID | None
    contact_name: str | None
    contact_phone: str | None
    contact_email: str | None
    company_name: str | None
    estimated_amount: str
    currency: str
    responsible_employee_id: uuid.UUID | None
    converted_deal_id: uuid.UUID | None
    pii_masked: bool


class LeadConvertIn(BaseModel):
    counterparty_id: uuid.UUID | None = None
    amount: float | None = None
    responsible_employee_id: uuid.UUID | None = None


# ------------------------------ Сделки ---------------------------------- #


class DealIn(BaseModel):
    title: str
    counterparty_id: uuid.UUID
    description: str | None = None
    amount: float = Field(0, ge=0)
    currency: str = "RUB"
    pipeline_stage_id: uuid.UUID | None = None
    commercial_offer_id: uuid.UUID | None = None
    responsible_employee_id: uuid.UUID | None = None
    expected_close_date: date | None = None


class DealOut(BaseModel):
    id: uuid.UUID
    number: str | None
    title: str
    counterparty_id: uuid.UUID
    lead_id: uuid.UUID | None
    pipeline_stage_id: uuid.UUID | None
    commercial_offer_id: uuid.UUID | None
    contract_id: uuid.UUID | None
    project_id: uuid.UUID | None
    amount: str
    currency: str
    status: str
    risk_level: str
    responsible_employee_id: uuid.UUID | None
    expected_close_date: date | None
    loss_reason_id: uuid.UUID | None
    approval_id: uuid.UUID | None


class MoveStageIn(BaseModel):
    pipeline_stage_id: uuid.UUID
    note: str | None = None


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    comment: str | None = None
    mfa_code: str | None = None


class LoseDealIn(BaseModel):
    loss_reason_id: uuid.UUID | None = None
    comment: str | None = None


class CreateProjectIn(BaseModel):
    contract_id: uuid.UUID
    name: str | None = None
    project_type: str = "construction"


# ------------------------------ Договоры -------------------------------- #


class ContractIn(BaseModel):
    counterparty_id: uuid.UUID
    deal_id: uuid.UUID | None = None
    commercial_offer_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    contract_type: str = "contract"
    number: str | None = None
    subject: str | None = None
    amount: float = Field(0, ge=0)
    currency: str = "RUB"
    payment_terms: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    responsible_employee_id: uuid.UUID | None = None


class ContractOut(BaseModel):
    id: uuid.UUID
    counterparty_id: uuid.UUID
    deal_id: uuid.UUID | None
    commercial_offer_id: uuid.UUID | None
    project_id: uuid.UUID | None
    contract_type: str
    number: str | None
    subject: str | None
    amount: str
    currency: str
    status: str
    risk_level: str
    signed_at: date | None
    approval_id: uuid.UUID | None


class SignContractIn(BaseModel):
    signed_at: date | None = None


# ------------------------- Коммуникации --------------------------------- #


class CommunicationIn(BaseModel):
    channel: str = "manual"
    direction: str = "outbound"
    counterparty_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    lead_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    subject: str | None = None
    body_text: str | None = None
    responsible_employee_id: uuid.UUID | None = None


class CommunicationOut(BaseModel):
    id: uuid.UUID
    channel: str
    direction: str
    counterparty_id: uuid.UUID | None
    deal_id: uuid.UUID | None
    subject: str | None
    processing_status: str
    linked_task_id: uuid.UUID | None


class CommTaskIn(BaseModel):
    title: str
    owner_employee_id: uuid.UUID | None = None


# --------------------------- Цели менеджеров ---------------------------- #


class SalesTargetIn(BaseModel):
    employee_id: uuid.UUID
    period_year: int
    period_month: int | None = None
    target_amount: float = Field(0, ge=0)
    target_deals_count: int | None = None
    currency: str = "RUB"


class SalesTargetOut(BaseModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    period_year: int
    period_month: int | None
    target_amount: str
    target_deals_count: int | None
    currency: str


# ------------------------------ Аналитика ------------------------------- #


class FunnelRowOut(BaseModel):
    stage_id: uuid.UUID
    name: str
    sort_order: int
    deals_count: int
    amount: str


class LossReasonRowOut(BaseModel):
    reason_id: uuid.UUID | None
    count: int
    amount: str


class ManagerRowOut(BaseModel):
    employee_id: uuid.UUID | None
    deals_total: int
    won_count: int
    won_amount: str
    target_amount: str
    plan_fact_percent: str


class AnalyticsOut(BaseModel):
    deals_total: int
    open_count: int
    won_count: int
    lost_count: int
    open_amount: str
    won_amount: str
    lost_amount: str
    conversion_percent: str
    funnel: list[FunnelRowOut]
    loss_reasons: list[LossReasonRowOut]
    managers: list[ManagerRowOut]
