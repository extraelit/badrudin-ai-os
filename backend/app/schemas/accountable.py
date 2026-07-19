"""Pydantic-схемы модуля «Подотчётные средства». Суммы сериализуются строкой."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class AdvanceIn(BaseModel):
    employee_id: uuid.UUID
    purpose: str
    amount_issued: float = Field(gt=0)
    report_due_at: datetime | None = None
    project_id: uuid.UUID | None = None
    site_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    expense_category_id: uuid.UUID | None = None
    payment_method: str = "cash"
    currency_code: str = "RUB"


class AdvanceOut(BaseModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    project_id: uuid.UUID | None
    purpose: str
    amount_issued: str
    amount_spent_confirmed: str
    amount_returned: str
    amount_reimbursable: str
    balance_amount: str
    currency_code: str
    status: str
    risk_level: str
    report_due_at: datetime | None
    approval_id: uuid.UUID | None


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    comment: str | None = None
    mfa_code: str | None = None


class IssueIn(BaseModel):
    payment_reference: str | None = None


class ExpenseIn(BaseModel):
    expense_category_id: uuid.UUID
    amount: float = Field(gt=0)
    expense_date: date
    description: str
    supplier_id: uuid.UUID | None = None
    vat_amount: float | None = None
    payment_method: str = "cash"
    created_from_mobile: bool = False


class ExpenseOut(BaseModel):
    id: uuid.UUID
    advance_id: uuid.UUID
    expense_category_id: uuid.UUID
    amount: str
    expense_date: date
    description: str
    payment_method: str
    receipt_required: bool
    document_status: str
    verification_status: str


class DocumentIn(BaseModel):
    duplicate_hash: str
    file_id: uuid.UUID | None = None
    document_type: str = "receipt"
    document_number: str | None = None
    document_date: date | None = None
    seller_name: str | None = None
    extracted_amount: float | None = None


class DocumentOut(BaseModel):
    id: uuid.UUID
    expense_id: uuid.UUID
    document_type: str
    document_number: str | None
    ocr_status: str


class VerifyExpenseIn(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    reason: str | None = None


class ReportOut(BaseModel):
    id: uuid.UUID
    advance_id: uuid.UUID
    total_expenses_submitted: str
    total_expenses_approved: str
    amount_to_return: str
    amount_to_reimburse: str
    status: str


class ReviewReportIn(BaseModel):
    decision: str = Field(pattern="^(approved|correction_required)$")
    comment: str | None = None


class SettlementIn(BaseModel):
    settlement_type: str = Field(pattern="^(return|reimbursement)$")
    amount: float = Field(gt=0)
    report_id: uuid.UUID | None = None
    payment_method: str = "cash"
    payment_reference: str | None = None
    idempotency_key: str | None = None


class SettlementOut(BaseModel):
    id: uuid.UUID
    advance_id: uuid.UUID
    settlement_type: str
    amount: str
    status: str


class AccountableSummaryOut(BaseModel):
    advances_open: int
    advances_overdue: int
    total_issued: str
    total_spent: str
    total_outstanding: str
    reports_pending: int


class CategoryOut(BaseModel):
    id: uuid.UUID
    code: str | None
    name: str
    requires_receipt: bool
    requires_preapproval: bool
    default_limit: str | None
