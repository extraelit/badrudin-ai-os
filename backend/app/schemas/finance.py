"""Pydantic-схемы модуля «Финансы и бюджеты». Денежные значения — строкой."""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, Field


# ------------------------------ Справочники ----------------------------- #


class ExpenseCategoryIn(BaseModel):
    name: str
    code: str | None = None
    kind: str = "other"
    parent_id: uuid.UUID | None = None


class ExpenseCategoryOut(BaseModel):
    id: uuid.UUID
    code: str | None
    name: str
    kind: str
    parent_id: uuid.UUID | None
    status: str


# ------------------------------- Бюджет --------------------------------- #


class BudgetFromEstimateIn(BaseModel):
    estimate_id: uuid.UUID
    name: str | None = None


class BudgetLineOut(BaseModel):
    id: uuid.UUID
    cost_code: str | None
    category: str
    description: str
    planned_amount: str
    approved_amount: str
    source: str
    is_manual: bool
    source_reference: str | None
    status: str
    expense_category_id: uuid.UUID | None


class BudgetOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    source_estimate_id: uuid.UUID | None
    name: str
    version: int
    currency: str
    status: str
    planned_total: str
    approved_total: str
    risk_level: str
    approval_id: uuid.UUID | None
    lines: list[BudgetLineOut] = Field(default_factory=list)


class BudgetSummaryRow(BaseModel):
    id: uuid.UUID
    name: str
    version: int
    status: str
    planned_total: str
    approved_total: str


class ManualLineIn(BaseModel):
    description: str
    amount: float = Field(gt=0)
    source_reference: str
    category: str = "other"
    cost_code: str | None = None
    expense_category_id: uuid.UUID | None = None


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    comment: str | None = None
    mfa_code: str | None = None


# --------------------------- Обязательства ------------------------------ #


class CommitmentIn(BaseModel):
    description: str
    amount: float = Field(gt=0)
    source_reference: str
    counterparty_id: uuid.UUID | None = None
    budget_line_id: uuid.UUID | None = None
    due_date: date | None = None
    mfa_code: str | None = None


class CommitmentOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    description: str
    amount: str
    currency: str
    source_type: str
    source_reference: str | None
    counterparty_id: uuid.UUID | None
    due_date: date | None
    status: str
    risk_level: str


# ---------------------------- Сводка проекта ---------------------------- #


class SummaryComponentOut(BaseModel):
    label: str
    amount: str
    source: str


class FinancialSummaryOut(BaseModel):
    project_id: uuid.UUID
    currency: str
    approved_budget: str
    planned_budget: str
    committed: str
    actual: str
    remaining: str
    forecast: str
    forecast_deviation: str
    has_approved_budget: bool
    committed_breakdown: list[SummaryComponentOut]
    actual_breakdown: list[SummaryComponentOut]


# ------------------ Счета, заявки на оплату, платежи --------------------- #


class InvoiceIn(BaseModel):
    counterparty_id: uuid.UUID
    amount: float = Field(gt=0)
    vat_amount: float = Field(0, ge=0)
    invoice_number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    contract_id: uuid.UUID | None = None
    commitment_id: uuid.UUID | None = None
    budget_line_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None


class InvoiceOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    counterparty_id: uuid.UUID
    invoice_number: str | None
    invoice_date: date | None
    due_date: date | None
    amount: str
    vat_amount: str
    paid_amount: str
    currency: str
    status: str
    payment_status: str
    contract_id: uuid.UUID | None
    commitment_id: uuid.UUID | None


class PaymentRequestIn(BaseModel):
    amount: float | None = Field(None, gt=0)
    planned_payment_date: date | None = None
    priority: str = "normal"
    justification: str | None = None


class PaymentRequestOut(BaseModel):
    id: uuid.UUID
    invoice_id: uuid.UUID
    project_id: uuid.UUID
    amount: str
    currency: str
    priority: str
    planned_payment_date: date | None
    justification: str | None
    status: str
    risk_level: str
    approval_id: uuid.UUID | None


class RecordPaymentIn(BaseModel):
    amount: float | None = Field(None, gt=0)
    payment_date: date | None = None
    external_transaction_id: str | None = None
    idempotency_key: str | None = None
    mfa_code: str | None = None


class PaymentOut(BaseModel):
    id: uuid.UUID
    invoice_id: uuid.UUID | None
    payment_request_id: uuid.UUID | None
    amount: str
    currency: str
    payment_direction: str
    method: str
    payment_date: date | None
    status: str


class PayablesSummaryOut(BaseModel):
    project_id: uuid.UUID
    currency: str
    invoiced_total: str
    approved_to_pay: str
    paid_total: str
    outstanding: str
