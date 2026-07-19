"""Pydantic-схемы модуля «Снабжение и закупки»."""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, Field


# ------------------------------ Справочники ------------------------------ #


class WarehouseIn(BaseModel):
    name: str
    code: str | None = None
    site_id: uuid.UUID | None = None
    address: str | None = None


class WarehouseOut(BaseModel):
    id: uuid.UUID
    name: str
    code: str | None
    site_id: uuid.UUID | None
    status: str


# ------------------------------- Заявки ---------------------------------- #


class RequestLineIn(BaseModel):
    material_id: uuid.UUID | None = None
    estimate_position_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None
    description: str | None = None
    quantity: float = Field(0, ge=0)


class RequestIn(BaseModel):
    site_id: uuid.UUID | None = None
    location_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    responsible_employee_id: uuid.UUID | None = None
    number: str | None = None
    priority: str = "normal"
    is_critical: bool = False
    needed_by: date | None = None
    reason: str | None = None
    lines: list[RequestLineIn] = Field(default_factory=list)


class RequestOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    site_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    number: str | None
    status: str
    priority: str
    is_critical: bool = False
    risk_level: str = "R0"
    needed_by: date | None = None
    lines_count: int
    approval_id: uuid.UUID | None


class RequestLineOut(BaseModel):
    id: uuid.UUID
    material_id: uuid.UUID | None
    description: str | None
    quantity: str
    reserved_quantity: str
    issued_quantity: str
    returned_quantity: str
    status: str


class RequestDetailOut(RequestOut):
    reason: str | None = None
    rejection_reason: str | None = None
    lines: list[RequestLineOut] = Field(default_factory=list)


# ---- Жизненный цикл заявки: резерв, выдача, подтверждение, возврат ---- #


class ReserveIn(BaseModel):
    warehouse_id: uuid.UUID


class IssueItemIn(BaseModel):
    request_line_id: uuid.UUID
    quantity: float = Field(gt=0)


class IssueRequestIn(BaseModel):
    warehouse_id: uuid.UUID
    issued_to: uuid.UUID | None = None
    number: str | None = None
    evidence_document_id: uuid.UUID | None = None
    evidence_file_id: uuid.UUID | None = None
    items: list[IssueItemIn] = Field(default_factory=list)


class AcknowledgeIn(BaseModel):
    confirmed: bool = True
    employee_id: uuid.UUID | None = None
    reason: str | None = None
    evidence_document_id: uuid.UUID | None = None
    evidence_file_id: uuid.UUID | None = None


class RequestReturnIn(BaseModel):
    warehouse_id: uuid.UUID
    material_id: uuid.UUID
    quantity: float = Field(gt=0)
    request_line_id: uuid.UUID | None = None
    issue_id: uuid.UUID | None = None
    number: str | None = None
    reason: str | None = None


class ConfirmReturnIn(BaseModel):
    employee_id: uuid.UUID | None = None
    evidence_document_id: uuid.UUID | None = None


class IssueDetailOut(BaseModel):
    id: uuid.UUID
    warehouse_id: uuid.UUID
    material_request_id: uuid.UUID | None
    number: str | None
    status: str
    acknowledgement_status: str
    acknowledged_by: uuid.UUID | None
    lines_count: int


class ReturnOut(BaseModel):
    id: uuid.UUID
    material_id: uuid.UUID
    quantity: str
    return_type: str
    status: str
    material_request_id: uuid.UUID | None
    confirmed_by: uuid.UUID | None


# ------------------------- Запросы цен (RFQ) ----------------------------- #


class RfqLineIn(BaseModel):
    material_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None
    description: str | None = None
    quantity: float = Field(0, ge=0)


class RfqIn(BaseModel):
    project_id: uuid.UUID | None = None
    material_request_id: uuid.UUID | None = None
    number: str | None = None
    due_date: date | None = None
    supplier_ids: list[uuid.UUID] = Field(default_factory=list)
    lines: list[RfqLineIn] = Field(default_factory=list)


class OfferIn(BaseModel):
    supplier_id: uuid.UUID
    rfq_line_id: uuid.UUID | None = None
    supplier_product_id: uuid.UUID | None = None
    price: float = Field(0, ge=0)
    lead_time_days: int | None = None
    note: str | None = None


class RfqOut(BaseModel):
    id: uuid.UUID
    number: str | None
    status: str
    lines_count: int
    suppliers_count: int
    offers_count: int


class ComparisonOut(BaseModel):
    id: uuid.UUID
    recommended_supplier_id: uuid.UUID | None
    recommendation_reason: str | None
    approval_status: str


# ------------------------------- Заказы ---------------------------------- #


class OrderLineIn(BaseModel):
    material_id: uuid.UUID | None = None
    estimate_position_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None
    description: str | None = None
    quantity: float = Field(0, ge=0)
    unit_price: float = Field(0, ge=0)


class OrderIn(BaseModel):
    supplier_id: uuid.UUID
    project_id: uuid.UUID | None = None
    warehouse_id: uuid.UUID | None = None
    material_request_id: uuid.UUID | None = None
    number: str | None = None
    expected_delivery_date: date | None = None
    lines: list[OrderLineIn] = Field(default_factory=list)


class OrderOut(BaseModel):
    id: uuid.UUID
    supplier_id: uuid.UUID
    number: str | None
    status: str
    total_amount: str
    currency: str
    risk_level: str
    approval_id: uuid.UUID | None


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    comment: str | None = None
    mfa_code: str | None = None


# ---------------------- Поступление и приёмка ---------------------------- #


class ReceiptLineIn(BaseModel):
    material_id: uuid.UUID
    purchase_order_line_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None
    quantity_received: float = Field(0, ge=0)
    quantity_accepted: float = Field(0, ge=0)
    quantity_rejected: float = Field(0, ge=0)
    quality_status: str = "pending"
    certificate_document_id: uuid.UUID | None = None
    batch_number: str | None = None


class ReceiptIn(BaseModel):
    warehouse_id: uuid.UUID
    purchase_order_id: uuid.UUID | None = None
    supplier_id: uuid.UUID | None = None
    number: str | None = None
    receipt_date: date | None = None
    delivery_document_number: str | None = None
    lines: list[ReceiptLineIn] = Field(default_factory=list)


class ReceiptOut(BaseModel):
    id: uuid.UUID
    warehouse_id: uuid.UUID
    number: str | None
    status: str
    lines_count: int


# ------------------------------ Выдача ----------------------------------- #


class IssueLineIn(BaseModel):
    material_id: uuid.UUID
    estimate_position_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None
    quantity: float = Field(0, ge=0)


class IssueIn(BaseModel):
    warehouse_id: uuid.UUID
    project_id: uuid.UUID | None = None
    site_id: uuid.UUID | None = None
    number: str | None = None
    issue_date: date | None = None
    lines: list[IssueLineIn] = Field(default_factory=list)


class IssueOut(BaseModel):
    id: uuid.UUID
    warehouse_id: uuid.UUID
    number: str | None
    status: str
    lines_count: int


# ------------------------------- Склад ----------------------------------- #


class BalanceOut(BaseModel):
    material_id: uuid.UUID
    warehouse_id: uuid.UUID
    quantity: str
    reserved_quantity: str
    average_unit_cost: str


# ------------------ Перемещение, возврат, списание ----------------------- #


class TransferIn(BaseModel):
    from_warehouse_id: uuid.UUID
    to_warehouse_id: uuid.UUID
    material_id: uuid.UUID
    quantity: float = Field(0, gt=0)
    number: str | None = None


class ReturnIn(BaseModel):
    warehouse_id: uuid.UUID
    material_id: uuid.UUID
    quantity: float = Field(0, gt=0)
    return_type: str = "from_site"
    number: str | None = None
    reason: str | None = None


class WriteOffIn(BaseModel):
    warehouse_id: uuid.UUID
    material_id: uuid.UUID
    quantity: float = Field(0, gt=0)
    number: str | None = None
    reason: str


class WriteOffOut(BaseModel):
    id: uuid.UUID
    number: str | None
    status: str
    risk_level: str
    approval_id: uuid.UUID | None


class DocStatusOut(BaseModel):
    id: uuid.UUID
    status: str


# ---------------------------- Инвентаризация ----------------------------- #


class CountLineIn(BaseModel):
    material_id: uuid.UUID
    expected_quantity: float = 0
    counted_quantity: float = 0


class CountIn(BaseModel):
    warehouse_id: uuid.UUID
    number: str | None = None
    count_date: date | None = None
    lines: list[CountLineIn] = Field(default_factory=list)


class CountOut(BaseModel):
    id: uuid.UUID
    warehouse_id: uuid.UUID
    number: str | None
    status: str
    lines_count: int


# ------------------------------- Сводка ---------------------------------- #


class ProcurementSummary(BaseModel):
    requests_open: int
    orders_pending: int
    orders_active: int
    writeoffs_pending: int
    warehouses: int
    stock_positions: int
