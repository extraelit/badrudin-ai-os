"""Pydantic-схемы модуля «Складской учёт и остатки»."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class StockSummaryOut(BaseModel):
    positions: int
    warehouses_with_stock: int
    total_value: str
    reserved_positions: int
    low_stock: int
    negative_stock: int


class StockRow(BaseModel):
    warehouse_id: uuid.UUID
    material_id: uuid.UUID
    material_name: str | None = None
    location_id: uuid.UUID | None
    quantity: str
    reserved_quantity: str
    available_quantity: str
    minimum_quantity: str
    average_unit_cost: str
    currency: str
    low: bool


class LedgerRow(BaseModel):
    id: uuid.UUID
    warehouse_id: uuid.UUID
    material_id: uuid.UUID
    material_name: str | None = None
    transaction_type: str
    quantity: str
    unit_cost: str
    source_type: str | None
    source_id: uuid.UUID | None
    occurred_at: datetime | None


class StockCardOut(BaseModel):
    warehouse_id: uuid.UUID
    material_id: uuid.UUID
    balance: StockRow | None
    transactions: list[LedgerRow] = Field(default_factory=list)


class MinQuantityIn(BaseModel):
    warehouse_id: uuid.UUID
    material_id: uuid.UUID
    minimum_quantity: float = Field(ge=0)


class ReservationIn(BaseModel):
    warehouse_id: uuid.UUID
    material_id: uuid.UUID
    quantity: float = Field(gt=0)
    reserved_until: date | None = None
    reason: str | None = None


class ReservationOut(BaseModel):
    id: uuid.UUID
    warehouse_id: uuid.UUID | None
    material_id: uuid.UUID
    material_name: str | None = None
    quantity: str
    status: str
    reserved_until: date | None
    reason: str | None
    purchase_order_id: uuid.UUID | None = None
    material_request_id: uuid.UUID | None = None


class LocationIn(BaseModel):
    name: str
    code: str | None = None
    parent_location_id: uuid.UUID | None = None


class LocationOut(BaseModel):
    id: uuid.UUID
    warehouse_id: uuid.UUID
    name: str
    code: str | None
    parent_location_id: uuid.UUID | None
